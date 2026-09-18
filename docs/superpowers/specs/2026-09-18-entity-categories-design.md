# Entity Categories, Motion Debounce and Weighted Welfare — v5.0 Design

**Date:** 2026-09-18
**Status:** Approved for planning
**Milestone:** v5.0

## Goal

Make Behaviour Monitor aware of what kind of device each monitored entity is,
so that (a) noisy PIR motion sensors stop polluting the learned routine and
(b) alerts from automated devices such as plugs and lights carry less weight
in the welfare status than alerts from devices that directly evidence a
person's presence.

## Non-goals

- Per-category or per-entity user-tunable weights. Weights are constants.
- Changing individual alert severity, notification content, or the
  minimum-notification-severity gate.
- Changing the activity tier system, its boost factors or floors.
- Changing the `routine_reset` service, which today clears CUSUM drift state
  only.
- Debouncing anything other than the motion category.

## Background

Today every monitored entity is treated identically apart from a binary /
numeric split based on its state value. Every state transition is recorded
into the 168-slot routine model, the correlation detector and the daily
count. A PIR sensor therefore produces two events per trigger (on and off)
and a burst of events while a person moves around a room. The only
compensation is the activity tier boost and floor, applied after the noisy
data is already in the model. Welfare status is the maximum alert severity
across entities with no notion of device type.

## Architecture

A new module `custom_components/behaviour_monitor/entity_category.py` owns
the category concept. It contains:

- `EntityCategory` enum: `MOTION`, `CONTACT`, `PLUG`, `LIGHT`, `OTHER`.
- `infer_categories(hass, entity_ids, overrides) -> dict[str, EntityCategory]`.
- `MotionDebouncer` class.
- `derive_weighted_status(alerts, categories) -> tuple[str, str]` returning
  `(status, recommendation)`.

The coordinator builds the category map once in `async_setup`. Setup runs on
every entry load, including the reload triggered by the options flow update
listener, so options changes are picked up without extra wiring.

All new logic is pure Python and testable without Home Assistant, matching
the existing detector modules. The coordinator gains roughly fifteen lines.

## 1. Categorisation and config

### Inference order

For each monitored entity, in order, first match wins:

1. **Override lists.** If the entity appears in the motion, contact, plug or
   light override list, that category is used.
2. **Entity registry device class.** Look up the registry entry.
   - `motion`, `occupancy`, `presence` → `MOTION`
   - `door`, `window`, `opening`, `garage_door` → `CONTACT`
   - `outlet`, `plug` → `PLUG`
3. **Domain fallback.** If the entity has no registry entry or no matching
   device class:
   - domain `switch` → `PLUG`
   - domain `light` → `LIGHT`
   - anything else → `OTHER`

Numeric entities always resolve to `OTHER` regardless of the above, since
none of the named categories describe a numeric signal. Numeric-ness is
determined by the existing `is_binary_state` check on the entity's current
state at inference time; if the state is unavailable at that moment the
inference rules above apply unchanged.

### New config keys

| Key | Type | Default | Notes |
|---|---|---|---|
| `category_motion` | list[str] | `[]` | Override list |
| `category_contact` | list[str] | `[]` | Override list |
| `category_plug` | list[str] | `[]` | Override list |
| `category_light` | list[str] | `[]` | Override list |
| `motion_debounce_seconds` | int | `120` | 0–600; 0 disables debounce |

The config flow adds four `EntitySelector(multiple=True)` fields and one
`NumberSelector` after the existing track_attributes include/exclude fields.
Validation rejects any entity present in more than one category list with a
new error key `category_overlap`, following the existing
`_validate_track_attribute_overrides` pattern. Cleared selectors normalise to
empty lists as the track_attributes lists do.

Config entry version becomes **11**.

### Visibility

The `entity_status_summary` sensor's per-entity `entity_status` entries gain a
`category` attribute (string value of the enum) next to `activity_tier`.

## 2. Motion debounce

### Rule

For an entity whose category is `MOTION`, an event is **counted** only if:

- it is a rising edge: new state is `on` and old state is not `on`
  (old state `None`, as on the first event after startup, counts as a rising
  edge), and
- at least `motion_debounce_seconds` have elapsed since the last counted
  event for that entity. Exactly the window elapsed counts.

Off transitions are never counted. A window of `0` counts every rising edge.
For entities in any other category every event is counted.

### `MotionDebouncer`

```
MotionDebouncer(window_seconds: int)
    .should_count(entity_id: str, is_motion: bool,
                  old_state: str | None, new_state: str,
                  timestamp: datetime) -> bool
```

Holds `dict[str, datetime]` of last-counted timestamps. `should_count`
updates the timestamp when it returns `True`. State is not persisted; after a
restart the first rising edge always counts.

### Placement in `_handle_state_changed`

1. Existing monitored-entity and track_attributes filters, unchanged.
2. Update `_last_seen[eid]` with the raw event. Any transition, including
   off, means the sensor observed something, so inactivity detection stays
   honest.
3. Call the debouncer. If it returns `False`, return.
4. Record into the routine model, the correlation detector and the daily
   count, as today.

### Effect on the model

Expected gaps for motion entities grow from seconds between retriggers to
minutes between activity episodes. Tier boosts and floors are unchanged; a
motion sensor in a busy room may still legitimately classify as HIGH tier.

## 3. Weighted welfare

### Scoring

Each non-correlation alert scores `severity_points × category_weight`:

| Severity | Points |
|---|---|
| LOW | 1 |
| MEDIUM | 2 |
| HIGH | 3 |

| Category | Weight |
|---|---|
| MOTION | 1.0 |
| CONTACT | 0.8 |
| OTHER | 1.0 |
| PLUG | 0.5 |
| LIGHT | 0.5 |

Welfare status is derived from the **maximum** score across alerts, not the
sum, so several weak alerts cannot compound.

| Top score | Status | Recommendation |
|---|---|---|
| ≥ 2.25 | `alert` | Immediate welfare check recommended. |
| ≥ 1.25 | `concern` | Schedule a welfare check soon. |
| otherwise | `check_recommended` | Monitor closely. |

Resulting behaviour: MOTION and OTHER are identical to today at every
severity. CONTACT HIGH → alert, CONTACT MEDIUM → concern, CONTACT LOW →
check_recommended. PLUG/LIGHT HIGH → concern, PLUG/LIGHT MEDIUM →
check_recommended, PLUG/LIGHT LOW → check_recommended.

### Constants

`SEVERITY_POINTS`, `CATEGORY_WEIGHT`, `WELFARE_ALERT_SCORE = 2.25` and
`WELFARE_CONCERN_SCORE = 1.25` live in `const.py` beside `PMI_THRESHOLD`.

### Unchanged

Individual alert severity, notifications, the minimum notification severity
gate, the reasons list, `entity_count_by_status`, and the exclusion of
correlation breaks from welfare are all untouched. `_derive_welfare` calls
`derive_weighted_status` in place of its current max-severity branch; the
rest of the returned dict is built as today.

## 4. Migration, re-bootstrap and bootstrap

### Migration v10 → v11

In `async_migrate_entry`, following the v10 pattern:

- `setdefault` the four override lists to `[]` and
  `motion_debounce_seconds` to `120`.
- Set `rebootstrap_motion = True` in entry data. The migration runs before
  the coordinator exists, so it cannot re-bootstrap itself.
- Bump to version 11.

### Re-bootstrap on first setup after migration

In `async_setup`, after the store is loaded and categories are inferred, if
`rebootstrap_motion` is true:

1. For every entity whose category is `MOTION`: remove its `EntityRoutine`
   from the routine model and call `CorrelationDetector.remove_entity`.
   CUSUM drift state and `_last_seen` are kept.
2. Replay recorder history for those entities only, through a fresh
   `MotionDebouncer` instance, using the same helper as first-install
   bootstrap.
3. Save the store, then clear the flag via `async_update_entry`.

If the recorder is unavailable, the routines stay cleared and relearn live;
a warning is logged. The flag is still cleared so the reset does not repeat.

### Bootstrap change

`_bootstrap_from_recorder` is refactored to accept an explicit list of
entity ids (defaulting to all monitored entities) and a debouncer instance.
Recorder states are already returned in time order per entity, so each is
fed to `should_count` with the previous state as `old_state`. The bootstrap
debouncer is separate from the live one so replay never disturbs live
timestamps.

## 5. Docs and translations

- README: new "Entity categories" section covering inference rules, the four
  override lists, the debounce setting and the weight table. Configuration
  table rows for the five new keys. Troubleshooting note for noisy PIRs
  pointing at the debounce window.
- `translations/en.json`: labels and descriptions for the five new fields,
  the `category_overlap` error.
- `.planning/PROJECT.md` and `.planning/ROADMAP.md`: v5.0 milestone.
- `manifest.json` version is handled by the release workflow; a
  `feat!:` commit marks the major bump.

## 6. Testing

All without Home Assistant, using existing mock patterns.

- **Category inference:** every device class mapping; switch and light
  domain fallbacks; override precedence over device class; entity missing
  from registry; numeric entity forced to OTHER.
- **Debouncer:** rising edge counted; off transition never counted; second
  edge inside window dropped; edge at exactly the window counted; zero
  window counts every edge; `None` old state counts; non-motion always
  counts; entities are independent.
- **Weighted welfare:** every category × severity cell against the table
  above; max not sum; correlation breaks excluded; no alerts → ok;
  recommendation strings.
- **Coordinator:** debounced event updates `_last_seen` but not the model,
  correlation detector or daily count; category attribute appears in sensor
  data; re-bootstrap clears only motion entities, keeps CUSUM and last_seen,
  clears the flag, and still clears the flag when the recorder is missing.
- **Config flow:** five new fields present; overlap across any two of the
  four lists rejected; empty-list normalisation; prefill in options flow;
  debounce range enforced.
- **Migration:** v10 → v11 seeds defaults and the flag; existing lists
  preserved; chained tests from v2/v4/v6/v7/v8 gain one more update call;
  v11 no-op.

## Decisions log

| Decision | Choice |
|---|---|
| Plugs in welfare | Down-weighted to 0.5, not excluded |
| Motion debounce default | On, 120 seconds |
| Lights | Separate `LIGHT` category, weight 0.5, domain fallback |
| Existing motion baselines on upgrade | Re-bootstrap from recorder with debounce |
| Where category lives | New `entity_category.py` module (Option B) |
| Weight aggregation | Max score, not sum |
| Version | v5.0 (welfare scoring changes alert behaviour) |
