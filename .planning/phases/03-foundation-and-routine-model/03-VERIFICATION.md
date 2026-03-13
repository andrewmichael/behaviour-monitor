---
phase: 03-foundation-and-routine-model
verified: 2026-03-13T12:00:00Z
status: passed
score: 18/18 must-haves verified
re_verification:
  previous_status: gaps_found
  previous_score: 16/18
  gaps_closed:
    - "history_window_days from config entry is used to initialize RoutineModel — coordinator.py line 92 now correctly reads CONF_HISTORY_WINDOW_DAYS"
    - "Bootstrap with partial history sets proportional confidence — test_bootstrap_partial_history added to TestRecorderBootstrap; asserts confidence 0.4–0.6 after 14 days against 28-day window"
  gaps_remaining: []
  regressions: []
---

# Phase 3: Foundation and Routine Model — Verification Report

**Phase Goal:** Storage is safely migrated to v3 format, deprecated ML sensors return defined stub states, and a routine model learns per-entity baselines from configurable rolling history — enabling both detection engines to consume structured baseline data.
**Verified:** 2026-03-13 (re-verification after gap closure)
**Status:** passed — all 18 must-haves verified
**Re-verification:** Yes — after gap closure. Previous score 16/18, now 18/18.

---

## Re-Verification Summary

Two gaps from the initial verification were both closed:

**Gap 1 closed — Correct config key in coordinator:**
`coordinator.py` line 92 now reads `entry.data.get(CONF_HISTORY_WINDOW_DAYS, DEFAULT_HISTORY_WINDOW_DAYS)`. The import of `CONF_HISTORY_WINDOW_DAYS` is present at line 22. The old `CONF_LEARNING_PERIOD` key is still imported for the statistical learning period (line 115, line 330, line 381), which is correct — those references are for the separate stat analyzer learning period, not the RoutineModel window. An additional test (`test_history_window_days_reads_correct_key`) was added verifying that a config entry with `"history_window_days": 14` yields `coordinator._history_window_days == 14` (not 7 from the old default).

**Gap 2 closed — Partial history confidence test written:**
`tests/test_coordinator.py` now contains `test_bootstrap_partial_history` in `TestRecorderBootstrap` (lines 1794–1831). The test uses a fixed reference time, generates 140 binary events over 14 days, bootstraps the coordinator, and asserts `0.4 <= overall_confidence(reference_now) <= 0.6`.

**Test suite:** 225 tests pass (up from 223), 0 failures, 2 harmless coroutine RuntimeWarnings from mock infrastructure.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | RoutineModel has zero HA imports — pure Python stdlib only | VERIFIED | `grep "from homeassistant" routine_model.py` returns nothing; imports are stdlib only |
| 2 | 168 hour-of-day x day-of-week slots per entity, correctly indexed | VERIFIED | `SLOTS_PER_ENTITY = 168`; `slot_index(hour, dow) = dow * 24 + hour`; range [0,167] |
| 3 | Binary entities store event times and inter-event intervals | VERIFIED | `ActivitySlot.event_times = deque(maxlen=56)`; `record_binary()` appends ISO timestamps; `expected_gap_seconds()` computes median inter-event intervals |
| 4 | Numeric entities store mean/stdev/count via Welford online algorithm | VERIFIED | `record_numeric()` implements Welford: count++, delta=value-mean, mean+=delta/count, delta2=value-mean, m2+=delta*delta2 |
| 5 | Sparse slots (< 4 observations) return None from query methods | VERIFIED | `is_sufficient` guards both `expected_gap_seconds()` and `slot_distribution()` — returns None when count < 4 |
| 6 | RoutineModel round-trips through to_dict/from_dict with full fidelity | VERIFIED | All three classes have to_dict/from_dict; deque contents preserved as list; Welford accumulators preserved as floats |
| 7 | learning_status transitions inactive -> learning -> ready | VERIFIED | `learning_status()` returns "inactive" (conf<0.1), "learning" (0.1<=conf<0.8), "ready" (conf>=0.8) |
| 8 | confidence is proportional to observation history vs configured window | VERIFIED | `confidence(now) = min(1.0, days_elapsed / history_window_days)` |
| 9 | Upgrading from v1.0 does not crash — old config entry keys are migrated gracefully | VERIFIED | `async_migrate_entry` pops 4 ML keys, adds history_window_days=28, updates entry to version=3, returns True |
| 10 | Three deprecated ML sensors return defined stub states, not unavailable | VERIFIED | ml_status: `lambda data: "Removed in v1.1"`; ml_training_remaining: `lambda data: "N/A"`; cross_sensor_patterns: `lambda data: 0` |
| 11 | Deprecation warning logged once per startup for each deprecated sensor | VERIFIED | Three `_LOGGER.warning()` calls in `async_setup()`, one per deprecated sensor |
| 12 | STORAGE_VERSION is 3 in const.py | VERIFIED | `STORAGE_VERSION: Final = 3` at line 71 |
| 13 | ML config keys removed from config entry during migration | VERIFIED | `async_migrate_entry` pops enable_ml, retrain_period, ml_learning_period, cross_sensor_window |
| 14 | New history_window_days key added to config entry with default 28 | VERIFIED | `new_data.setdefault(CONF_HISTORY_WINDOW_DAYS, DEFAULT_HISTORY_WINDOW_DAYS)` in async_migrate_entry |
| 15 | Loading v2 z-score storage does not crash | VERIFIED | Coordinator detects "analyzer" key without "routine_model", logs info, creates empty RoutineModel |
| 16 | Orphaned ML storage file is deleted on setup | VERIFIED | `_cleanup_ml_store()` called in `async_setup()`; loads ML store, calls async_remove if not None |
| 17 | Recorder bootstrap populates RoutineModel from historical state changes | VERIFIED | `_bootstrap_from_recorder()` uses `recorder_state_changes_during_period`, filters unavailable/unknown, calls `self._routine_model.record()` |
| 18 | Bootstrap with partial history sets proportional confidence | VERIFIED | `test_bootstrap_partial_history`: 140 events over 14 days against 28-day window yields `0.4 <= confidence <= 0.6`; test passes |

**Score:** 18/18 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `custom_components/behaviour_monitor/routine_model.py` | ActivitySlot, EntityRoutine, RoutineModel classes | VERIFIED | 421 lines; all three classes present; zero HA imports |
| `tests/test_routine_model.py` | Unit tests for all RoutineModel behaviors | VERIFIED | 560 lines; 8 test classes covering slot indexing, binary/numeric slots, serialization, model-level behavior |
| `custom_components/behaviour_monitor/const.py` | STORAGE_VERSION=3, new config keys, new defaults | VERIFIED | STORAGE_VERSION=3 at line 71; CONF_HISTORY_WINDOW_DAYS and DEFAULT_HISTORY_WINDOW_DAYS=28 present |
| `custom_components/behaviour_monitor/__init__.py` | async_migrate_entry for config entry v2->v3 migration | VERIFIED | async_migrate_entry at line 37; handles v2->v3, always returns True |
| `custom_components/behaviour_monitor/sensor.py` | Stub value_fn for 3 deprecated ML sensors | VERIFIED | ml_status: "Removed in v1.1"; ml_training_remaining: "N/A"; cross_sensor_patterns: 0 |
| `custom_components/behaviour_monitor/coordinator.py` | Storage migration, ML cleanup, bootstrap, correct config key wiring | VERIFIED | CONF_HISTORY_WINDOW_DAYS read at line 92; bootstrap present; migration logic present |
| `tests/test_coordinator.py` | Migration, cleanup, bootstrap, deprecation log, partial history confidence tests | VERIFIED | 225 tests pass; TestRecorderBootstrap includes test_bootstrap_partial_history |
| `tests/fixtures/v2_storage.json` | v2 format storage fixture for migration tests | VERIFIED | File exists; contains "analyzer" key with z-score bucket data and "coordinator" state key |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| routine_model.py | collections.deque | deque(maxlen=56) for slot observations | VERIFIED | Line 68: `deque(maxlen=_DEQUE_MAXLEN)` where `_DEQUE_MAXLEN = 56` |
| routine_model.py | statistics | median for numeric slot distributions | VERIFIED | Line 13: `from statistics import median` |
| EntityRoutine.record() | ActivitySlot | slot_index(hour, dow) routing | VERIFIED | Line 223: `idx = self.slot_index(hour=timestamp.hour, dow=timestamp.weekday())` |
| coordinator.py _async_setup | RoutineModel.from_dict | v3 storage deserialization | VERIFIED | Line 249: `self._routine_model = RoutineModel.from_dict(stored_data["routine_model"])` |
| coordinator.py _bootstrap_from_recorder | state_changes_during_period | get_instance(hass).async_add_executor_job | VERIFIED | recorder_get_instance and recorder_state_changes_during_period called correctly |
| coordinator.py _build_sensor_data | sensor.py value_fn lambdas | ml_status_stub, ml_training_stub, cross_sensor_stub data keys | PARTIAL | Keys present in data dict; sensor value_fns are hardcoded lambdas that do not read from data — stubs work correctly despite the disconnect (no behavioral impact) |
| __init__.py async_migrate_entry | const.py DEFAULT_HISTORY_WINDOW_DAYS | new_data.setdefault | VERIFIED | Line 50: `new_data.setdefault(CONF_HISTORY_WINDOW_DAYS, DEFAULT_HISTORY_WINDOW_DAYS)` |
| coordinator.py _history_window_days | CONF_HISTORY_WINDOW_DAYS | config entry data read | VERIFIED | Line 92: `entry.data.get(CONF_HISTORY_WINDOW_DAYS, DEFAULT_HISTORY_WINDOW_DAYS)` — gap closed |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ROUTINE-01 | Plan 01 | 168 hour-of-day x day-of-week slots per entity from configurable rolling history window | SATISFIED | ActivitySlot × 168 per EntityRoutine; history_window_days drives confidence and bootstrap window |
| ROUTINE-02 | Plan 03 | Bootstrap routine model from HA recorder history on first load | SATISFIED | `_bootstrap_from_recorder()` called on empty model during async_setup; uses recorder state_changes_during_period |
| ROUTINE-03 | Plan 01 | Event frequency/timing for binary; value distributions for numeric | SATISFIED | Binary: deque of event_times + expected_gap_seconds(); Numeric: Welford accumulators + slot_distribution() |
| INFRA-01 | Plans 02, 03 | Migrate from v2 z-score storage format; clean up orphaned ML storage | SATISFIED | async_migrate_entry handles config entry v2->v3; coordinator detects "analyzer" key, discards it, creates fresh RoutineModel; _cleanup_ml_store() deletes orphaned ML storage |
| INFRA-02 | Plans 02, 03 | ML-specific sensors preserved as deprecated stubs with safe default states | SATISFIED | Three sensors return hardcoded stubs; deprecated=True extra_attrs; deprecation warnings logged on startup |

No orphaned requirements: all 5 requirement IDs (ROUTINE-01, ROUTINE-02, ROUTINE-03, INFRA-01, INFRA-02) appear in plan frontmatter and are accounted for. INFRA-03 (config flow UI) is correctly mapped to Phase 5 — not expected here.

---

## Anti-Patterns Found

None. The wiring gap from the initial verification (wrong config key at coordinator.py line 91) is resolved. No TODO/FIXME/placeholder comments found in phase-modified files. No empty implementations. No stub return values in non-deprecated paths.

The PARTIAL link (coordinator data dict keys not consumed by sensor value_fns) is informational only — the hardcoded stub lambdas produce correct output and the disconnect causes no behavioral issue.

---

## Human Verification Required

None — all critical behaviors are verifiable programmatically.

---

## Test Results

All 225 tests pass across 4 test files (0 failures, 2 harmless coroutine RuntimeWarnings from mock infrastructure):

```
tests/test_routine_model.py   59 passed
tests/test_init.py            25 passed
tests/test_sensor.py          52 passed
tests/test_coordinator.py     89 passed
Total: 225 passed in 0.91s
```

Two tests added since initial verification:
- `TestRecorderBootstrap::test_bootstrap_partial_history` (Gap 2)
- `TestRecorderBootstrap::test_history_window_days_reads_correct_key` (Gap 1 regression guard)

---

_Verified: 2026-03-13_
_Verifier: Claude (gsd-verifier)_
