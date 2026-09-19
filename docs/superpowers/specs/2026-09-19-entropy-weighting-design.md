# Entropy Weighting — v5.4 Design

**Date:** 2026-09-19
**Status:** Approved for planning
**Milestone:** v5.4 (third of five from `docs/design/2026-09-18-detection-gap-analysis.md`)
**Source:** `docs/design/2026-09-18-detection-and-weighting-design.md` §Weighting, §Replay testing, §Per-entity silence thresholds (deferred part)
**Builds on:** branch `feat/event-pipeline-roles` (v5.3 roles and pipeline)

## Goal

Replace the interim per-kind welfare weights with a per-entity weight derived
from how irregular the entity's activations are over time of day. A timer
that fires at the same minute every day says nothing about the resident and
must stop counting as evidence of activity; a kettle used at varying times
must count. Weights are recomputed daily, surfaced in status, and validated
offline through the replay CLI.

## Non-goals

- Per-entity silence thresholds inside inactivity detection (own milestone;
  needs replay evidence for the percentile first).
- Rules, escalation levels, derived windows, away state (v6.0).
- Any change to what the pipeline emits or what the routine model stores.
- Persisting weights. They are recomputed from stored activations in
  milliseconds.

## Decisions carried in

- Welfare uses a weight relative to the deployment's best ready entity,
  with an absolute fallback when no entity is human-like.
- Timer-like entities keep liveness monitoring by re-typing their inactivity
  alerts as device-health alerts, reusing the v5.2 path.
- One or two non-empty buckets score zero entropy regardless of split.

## Architecture

- `entropy_weight.py` (new, pure): `compute_weight(...)` returns a
  `WeightResult`; `relative_weights(...)` derives the welfare weights.
- `entity_role.py`: `derive_weighted_status(alerts, welfare_weights)` keyed
  by entity id; `KIND_WEIGHT` removed from `const.py`.
- `coordinator.py`: `_refresh_weights(now)` at setup, at the daily rollover
  and after any re-bootstrap; timer re-typing in `_run_detection`; status
  fields; config keys.
- `config_flow.py`, `__init__.py`, `translations/en.json`: four keys,
  v14 → v15 migration.
- `scripts/replay.py`: `--weights`.

## 1. Entropy computation

### 1.1 Inputs

For each monitored, non-panic entity with a binary routine, the activation
timestamps are every ISO string in that entity's 168 `ActivitySlot.event_times`
deques. The coordinator supplies them as parsed datetimes; the module never
touches the routine model. Numeric routines have no timestamps.

### 1.2 `compute_weight`

```python
@dataclass(frozen=True)
class WeightResult:
    status: str            # "training" | "ready" | "timer" | "not_applicable"
    h_norm: float | None   # normalised entropy, None while training / n.a.
    weight: float | None   # max(floor, h_norm); None while training; 1.0 for n.a.
    buckets: int           # non-empty buckets in the window
    days: int              # distinct calendar days with an activation in the window
    samples: int           # activations in the window

def compute_weight(
    activations: Iterable[datetime],
    now: datetime,
    *,
    window_days: int,
    bucket_minutes: int,
    min_days: int,
    floor: float,
) -> WeightResult
```

Steps:

1. Keep activations with `now - window_days <= t <= now`. Naive and aware
   datetimes are made comparable by treating naive as UTC, the same
   convention `EntityRoutine.confidence` uses.
2. `days` is the number of distinct local calendar dates among them. If
   `days < min_days`: status `training`, `h_norm` and `weight` None.
3. Bucket each activation by `(t.hour * 60 + t.minute) // bucket_minutes`.
   `buckets` is the number of non-empty buckets.
4. If `buckets <= 2`: `h_norm = 0.0`. Otherwise
   `h_norm = -sum(p_i * ln(p_i)) / ln(buckets)` over non-empty buckets, where
   `p_i` is that bucket's share of `samples`. Clamp to `[0.0, 1.0]`.
5. `weight = max(floor, h_norm)`. Status is `timer` when `h_norm <= floor`,
   else `ready`.

`compute_weight_not_applicable()` returns `WeightResult("not_applicable",
None, 1.0, 0, 0, 0)` for numeric entities, preserving their current weight.

Rationale for step 4's short-circuit: a timer whose firing minute drifts
across a bucket boundary would otherwise split evenly across two buckets and
score `h_norm = 1.0`; a distribution over two hourly buckets cannot evidence
human irregularity.

### 1.3 `relative_weights`

```python
def relative_weights(results: Mapping[str, WeightResult]) -> dict[str, float]
```

Returns a welfare weight for every entity whose status is `ready`, `timer`
or `not_applicable` (training entities are absent from the result). Let
`top` be the maximum `weight` over `ready` and `timer` entities. If `top >=
RELATIVE_WEIGHT_MIN_TOP` (0.5): each such entity's welfare weight is
`min(1.0, weight / top)`. Otherwise welfare weight equals `weight` unchanged.
`not_applicable` entities always get 1.0. With no ready or timer entities the
result contains only the `not_applicable` ones.

## 2. Welfare, liveness and status

### 2.1 Welfare

`derive_weighted_status(alerts, welfare_weights: Mapping[str, float])`
replaces the role-keyed signature. An alert whose entity is missing from
`welfare_weights` (training, or unknown) is skipped in scoring, as panic and
correlation-break alerts already are. Everything else is unchanged: score is
`SEVERITY_POINTS[severity] * welfare_weights[entity]`, maximum not sum,
thresholds `WELFARE_ALERT_SCORE` 2.25 and `WELFARE_CONCERN_SCORE` 1.25,
`check_recommended` when nothing scores. `KIND_WEIGHT` is deleted.

Skipped alerts still appear in `anomalies`, `reasons`,
`alert_count_by_entity` and notifications; only the status derivation
ignores them.

### 2.2 Liveness for timer entities

In `_run_detection`, after the acute detector returns an `INACTIVITY` alert
for an entity whose weight status is `timer`, the coordinator replaces it
with an `AlertResult` of type `DEVICE_HEALTH`, same severity and confidence,
`details={"kind": "device_silent", "original": "inactivity",
"expected_gap_seconds": ...}` carried over from the original details, and
explanation `"{entity_id} (automated device) has not switched for {elapsed};
it usually switches every {gap}"`. Everything downstream is the existing
v5.2 device-health path: ordinary notification route, not suppressed by
snooze or holiday, shown in anomalies, excluded from welfare status, and
counted in `qualify_welfare`'s `device_alerts` flag so an otherwise-ok house
reads `degraded`.

`UNUSUAL_TIME` and `DRIFT` alerts on timer entities are unchanged.

### 2.3 Recompute schedule

`_refresh_weights(now)` runs: at the end of `async_setup` after roles are
resolved and any bootstrap or re-bootstrap has finished; inside
`_async_update_data` in the daily-rollover block next to `classify_tier`;
and at the end of `_rebootstrap_motion_entities` /
`_rebootstrap_role_entities`. It computes a `WeightResult` for every
monitored non-panic entity (numeric routines get `not_applicable`; entities
with no routine yet get `training` with zero counts), then
`relative_weights` over the map. Both maps are coordinator attributes:
`self._weights: dict[str, WeightResult]` and
`self._welfare_weights: dict[str, float]`.

### 2.4 Status

Each `entity_status` entry gains:

| Field | Value |
|---|---|
| `weight` | `WeightResult.weight` (null while training) |
| `welfare_weight` | relative weight, or null while training |
| `weight_status` | `training` / `ready` / `timer` / `not_applicable` |
| `entropy_buckets` | `WeightResult.buckets` |

Panic entities carry none of these. A top-level `weights` attribute maps
each status to its entity count, zeros included, and is exposed on the
`entity_status_summary` sensor next to `roles`. `_build_safe_defaults`
carries the zeroed map.

## 3. Configuration and migration

| Key | Selector | Range | Default |
|---|---|---|---|
| `entropy_bucket_minutes` | select: 30, 60 | | 60 |
| `entropy_window_days` | number, box | 7–28 | 14 |
| `entropy_min_days` | number, box | 3–14 | 7 |
| `weight_floor` | number, box, step 0.01 | 0.01–0.5 | 0.05 |

Validation error `entropy_min_exceeds_window` when the minimum days exceed
the window. Config entry v15 seeds the four keys with defaults;
`STORAGE_VERSION` becomes 15; `_async_migrate_func` still passes data
through. No re-bootstrap and no repair issue.

`RELATIVE_WEIGHT_MIN_TOP = 0.5` is a named constant in `const.py`, not an
option: it is a guard against a degenerate deployment, not a tuning knob.

## 4. Replay CLI

`scripts/replay.py --weights` runs `compute_weight` over each entity's
replayed activation timestamps (excursions count once at the anchor, exactly
as the coordinator records them) with `now` equal to the last event
timestamp, and prints `h_norm`, `weight`, `status`, `buckets`, `days` per
entity, plus the relative welfare weights. Flags `--window-days`,
`--bucket-minutes`, `--min-days`, `--weight-floor` mirror the options with
the same defaults. `--json` includes a `weights` object.

## 5. Docs

- README: the "Weighted welfare" paragraph becomes an "Entropy Weighting"
  subsection under Roles: formula, the three rules, relative scaling and its
  guard, the four status fields and the `weights` attribute, timer liveness.
  Four option rows. v15 upgrade line. Replay section gains `--weights`.
- Gap analysis: section C marked delivered except the silence threshold,
  which moves to its own line under D.
- CLAUDE.md file structure: `entropy_weight.py`.

## 6. Testing (HA-free unless stated)

- `test_entropy_weight.py`: one-bucket timer → 0.0/floor/timer; timer
  straddling a boundary (two buckets, even split) → 0.0; three equal buckets
  → 1.0; skewed distribution → value checked against a hand computation;
  window filtering excludes older activations; `min_days` boundary (6 days
  training, 7 ready); bucket width 30 changes the bucket count; floor
  applied; clamp; naive/aware mixing; `relative_weights` with top ≥ 0.5,
  with top < 0.5 (absolute fallback), with only training entities, with
  `not_applicable` present.
- `test_entity_role.py`: `derive_weighted_status` with weights, skipping
  entities absent from the map, training exclusion.
- `test_coordinator.py` (mock HA): `_refresh_weights` at setup and at
  rollover; numeric entity `not_applicable`; entity without routine
  `training`; timer inactivity re-typed with details and explanation and
  excluded from welfare; welfare uses relative weights; status fields and
  `weights` attribute; safe defaults.
- `test_sensor.py`: `weights` exposed.
- `test_config_flow.py`, `test_init.py`: four fields, the validation error,
  v14 → v15 migration, chain tests advanced to 15.
- `test_replay_fixture.py`: `--weights` on the fixture reports the teasmade
  as `timer` at the floor and the bathroom sensor as `ready` with
  `h_norm > 0.5`.

## Decisions log

- Relative welfare weight, guarded at 0.5, so today's thresholds keep their
  meaning and an all-timer deployment cannot promote a timer.
- One or two non-empty buckets score zero: boundary straddling is the most
  common timer artefact and two hourly buckets are not irregularity.
- Timer inactivity becomes a device-health alert rather than a new detector:
  one timing model, one notification path, already snooze-proof.
- Training entities are excluded from welfare scoring but not from alerts
  or notifications; hiding an alert is worse than under-weighting it.
- Weights are not persisted; recompute is cheap and avoids a storage
  migration.
- Silence thresholds deferred to a milestone with replay evidence.
