# Detection and weighting design — gap analysis and decomposition

**Date:** 2026-09-18
**Source:** `docs/design/2026-09-18-detection-and-weighting-design.md`
**Baseline:** branch `feat/entity-categories` (v5.0 entity categories + v5.1 panic button, PR #2)

## What the code already does

| Design requirement | Status today | Notes |
|---|---|---|
| Motion debounce 2 min, per entity | **Done (v5.0)** | `MotionDebouncer`, rising edges only, `motion_debounce_seconds` default 120 |
| Preserve `last_seen` through debounce | **Done (v5.0)** | last-seen updated on every raw event before the debounce decision |
| Panic path bypassing everything | **Done (v5.1)** | Bypasses notify toggle, holiday, snooze, severity gate, repeat interval; re-notify until acknowledged; distinct notification id |
| Per-entity silence threshold derived from history | **Partly** | `expected_gap_seconds` per 168 slots + CV-adaptive scalar + tier floors. Not entropy-based, but derived |
| Daytime inactivity (Rule 6) | **Partly** | `check_inactivity` covers it without a derived active window |
| Expected anchor missed (Rule 4) | **Partly** | `check_unusual_time` / expected-gap logic is adjacent; no explicit per-anchor times |
| Pure-function detectors | **Partly** | `routine_model`, `acute_detector`, `drift_detector`, `correlation_detector`, `entity_category`, `panic_monitor` are HA-free; the event pipeline itself lives in the coordinator |
| Roles | **Partly** | Categories motion/contact/plug/light/panic/other exist. Design wants room-level motion roles, exterior/interior door split, `appliance` |

## What conflicts with the current design

| Current behaviour | Design says | Resolution |
|---|---|---|
| Fixed per-category welfare weights (motion 1.0, contact 0.8, plug/light 0.5) — v5.0, in PR #2 | "Categories carry no implicit weight." Weight is per-entity normalised entropy with a 0.05 floor, recomputed daily | Entropy weighting **replaces** `CATEGORY_WEIGHT` in the weighting milestone. Until then the v5.0 weights stay as an interim |
| Alert severities LOW/MEDIUM/HIGH → welfare ok/check/concern/alert | Escalation levels Watch/Soft/Escalate/Panic driven by concurrent markers | New level model layered on top; existing detectors become markers |
| One `notify_services` list | Per-level targets, escalate/panic always critical | Config change in the escalation milestone |
| Motion-only debounce | Doors 60 s per entity; retrigger collapse < 5 s | Pipeline milestone |

## Confirmed defects (from the document, verified in code)

1. **Status summary counts keys that are never emitted.** `sensor.py` reads `entity_count_by_status` keys `normal` / `attention` / `concern` / `alert`; the coordinator emits `{entity_id: alert_count}`. The sensor therefore always shows "0 OK, 0 Need Attention".
2. **No entity existence check.** Nothing verifies a configured entity resolves; a deleted entity is silently skipped and welfare stays "ok".
3. **"ok" is unqualified.** The welfare payload carries no count of contributing entities.
4. **Panic device liveness is unknown.** Panic entities are excluded from last-seen by design, so `last_seen: None` is permanent and nothing surfaces battery or heartbeat.

## Not covered anywhere today

Artifact discard (reload bursts, start-up grace); door debounce; retrigger collapse; excursion grouping; door open-duration classes; derived sleep window; away state; adjacency graph; transit timing; Rules 1, 2, 3, 5; visitor context; escalation levels and markers; per-level notification targets; iOS critical payload; input-loss score; deliberate-disconnection semantics; replay harness; multi-occupant degrade.

## Proposed decomposition

Ordered as the document asks: integrity first, then the pipeline that feeds everything else, then weighting, then rules. Each is one spec → plan → execute cycle.

### A. v5.2 — System integrity (do first)
- Fix the status summary counter to count what the producer emits.
- Welfare payload carries `contributing_entities` and `expected_entities`; status never reads "ok" from zero inputs (new `blind` status or qualified text).
- Configured entities that do not resolve in the state machine raise a Home Assistant repair issue and appear as `missing` in entity status; welfare score is lowered, not renormalised.
- Panic device liveness: per-panic-entity `available`/`unavailable` tracking, battery attribute pass-through where present, a heartbeat-silence alert on its own path, and a `panic_test` service that records a test press without alerting.
- Start-up grace: ignore events for a configurable 60–120 s after `homeassistant_start`; discard same-second bursts of ≥3 entities (this is integrity, not detection: it stops restarts corrupting the baseline).

### B. v5.3 — Event pipeline and roles
- Roles replace/extend categories: `motion.{bathroom,bedroom,living,kitchen,transit}`, `door.{exterior,interior}`, `appliance`, `panic`, `other`. Config flow lists per role; migration maps `contact` → `door.interior` and `plug`/`light` → `appliance` with a repair issue prompting the user to assign exterior doors and rooms.
- Door debounce 60 s per entity; retrigger collapse < 5 s for all binary entities.
- Excursion grouping for exterior doors (pairs within 60 s → one excursion with duration).
- Door open-duration classes (brief/extended/prolonged) recorded per event.
- Optional adjacency graph in options (YAML-ish text or per-door room selector), with a derivation-from-history proposal deferred.
- Replay harness: a pure `pipeline.py` taking `(entity_id, role, timestamp, state)` events and a CLI/test helper that replays recorder exports through it.

### C. v5.4 — Entropy weighting
- Per-entity normalised entropy over 60-min buckets, 14-day rolling window, 7-day minimum, floor 0.05, recomputed daily; computed over debounced activations.
- Replaces `CATEGORY_WEIGHT`; weight surfaced per entity in status; entities under the training minimum reported as `training` and excluded from scoring.
- Liveness monitoring for zero-weight entities (device silence alert, separate from welfare).
- Per-entity silence threshold derived from the same distribution.

### D. v6.0 — Derived state, rules and escalation
- Derived sleep window and active window.
- Away state machine (enter/exit/inconsistency) suspending absence rules.
- Rules 1–6 as pure marker functions with the document's defaults in options.
- Visitor-day tagging from near-zero-usage exterior doors.
- Escalation levels Watch/Soft/Escalate/Panic with an explicit marker list; per-level notification targets; iOS critical payload for escalate/panic.
- Multi-occupant setting that degrades to liveness + panic.

### E. v6.1 — Trends
- Transit timing per adjacent room pair, rolling median, trend attributes only (never alerts).
- Night-bathroom frequency trend view.

## Open questions to settle before each spec
- A: should a blind monitor show a distinct `blind` status or "ok (0 of N)"? Recommend a distinct status.
- B: role assignment UI — five motion lists plus two door lists is a lot of selectors; consider a single "role per entity" text map or a repair-driven wizard.
- C: what feeds the weight into welfare once categories no longer carry one — score = severity × entity weight, same thresholds?
- D: the marker list (document's own open question).
