---
phase: 20-correlation-lifecycle
verified: 2026-04-07T10:00:00Z
status: passed
score: 5/5 must-haves verified
gaps: []
---

# Phase 20: Correlation Lifecycle Verification Report

**Phase Goal:** Correlation state stays clean over time without manual intervention.
**Verified:** 2026-04-07
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | Stale pairs are pruned from _pairs during recompute() when PMI is below threshold and co-occurrences are below minimum | VERIFIED | `decay_stale_pairs()` exists at line 243 of correlation_detector.py; `recompute()` calls `self.decay_stale_pairs()` at line 237 after updating `_learned_pairs`; 4 tests in `TestDecayAndRemoval` cover this behavior |
| 2 | remove_entity() purges all pairs, learned_pairs, entity_event_counts, break_cycles, and adjusts total_event_count | VERIFIED | `remove_entity()` exists at line 267 of correlation_detector.py; all 5 data structures purged: `_pairs` (line 280-282), `_learned_pairs` (line 285-287), `_entity_event_counts` + `_total_event_count` (lines 290-291), `_break_cycles` (line 294); 5 targeted tests confirm each purge |
| 3 | Decay and removal methods are pure Python with zero HA imports | VERIFIED | `grep homeassistant correlation_detector.py` returns no matches; `TestNoHAImports.test_no_homeassistant_import` in test suite covers this |
| 4 | When an entity is removed from monitored_entities via config change, all its correlation pairs, event counts, break cycles, and learned pairs are purged on next startup | VERIFIED | coordinator.py `async_setup()` lines 137-144 compute `stale_entities` as set difference between `_entity_event_counts` and `_monitored_entities`, then calls `remove_entity()` for each; `TestCorrelationEntityRemoval` class with 4 tests validates all scenarios |
| 5 | Cleanup happens automatically during async_setup after restoring correlation state | VERIFIED | Cleanup block is inside the `if "correlation_state" in stored:` branch (line 133-144), runs only when state is restored — no manual intervention required |

**Score:** 5/5 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `custom_components/behaviour_monitor/correlation_detector.py` | `decay_stale_pairs()` method | VERIFIED | Defined at line 243; substantive (18 lines, prunes noise pairs); called at end of `recompute()` line 237 |
| `custom_components/behaviour_monitor/correlation_detector.py` | `remove_entity()` method | VERIFIED | Defined at line 267; substantive (28 lines, purges 4 data structures); wired into coordinator |
| `tests/test_correlation_detector.py` | `class TestDecayAndRemoval` | VERIFIED | Class at line 518; 9 test methods covering all specified behaviors |
| `custom_components/behaviour_monitor/coordinator.py` | Entity removal cleanup in `async_setup` | VERIFIED | Cleanup block at lines 137-144 inside `if "correlation_state" in stored:`; calls `remove_entity()` |
| `tests/test_coordinator_correlation.py` | `class TestCorrelationEntityRemoval` | VERIFIED | Class at line 499; 4 test methods covering stale removal, monitored retention, no stored state, empty counts |

---

## Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `correlation_detector.py recompute()` | `decay_stale_pairs()` | called at end of recompute | WIRED | `self.decay_stale_pairs()` at line 237, after `self._learned_pairs = new_learned` |
| `coordinator.py async_setup()` | `correlation_detector.remove_entity()` | diff between `_entity_event_counts` and `_monitored_entities` | WIRED | Lines 138-144: set difference computed, loop calls `self._correlation_detector.remove_entity(eid)` |

---

## Data-Flow Trace (Level 4)

Not applicable. Phase 20 delivers methods on a detector class and coordinator wiring logic — no rendering components or dynamic data display. Both methods mutate internal state that is subsequently serialized via `to_dict()` / `_save_data()`.

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| All correlation + entity removal tests pass | `python -m pytest tests/test_correlation_detector.py tests/test_coordinator_correlation.py -x -q` | 63 passed, 1 warning | PASS |
| Zero HA imports in correlation_detector.py | `grep homeassistant correlation_detector.py` | No matches | PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| COR-08 | 20-01-PLAN.md | Stale correlation pairs decay automatically when entities stop co-occurring | SATISFIED | `decay_stale_pairs()` implemented; called automatically by `recompute()` daily; noise pairs (below `_min_observations` and not learned) are pruned without any manual trigger |
| COR-09 | 20-01-PLAN.md, 20-02-PLAN.md | Correlation state is cleaned up when monitored entities are removed | SATISFIED | `remove_entity()` on detector purges all state for an entity; coordinator `async_setup()` calls it for any entity in restored state but absent from current `_monitored_entities` |

**Coverage:** 2/2 phase requirements satisfied. No orphaned requirements — REQUIREMENTS.md traceability table maps both COR-08 and COR-09 exclusively to Phase 20.

**Note on REQUIREMENTS.md status:** COR-08 is still marked `[ ]` (pending) in REQUIREMENTS.md at line 31. The checkbox was not updated after phase execution. This is a documentation gap only — the implementation is fully present and tested. COR-09 is correctly marked `[x]` at line 32.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| None | — | — | — | No anti-patterns found in modified files |

Scanned `correlation_detector.py` and `coordinator.py` for TODOs, placeholders, empty returns, and stub indicators. No matches.

---

## Human Verification Required

None. All behaviors are verifiable programmatically:
- Methods exist, are substantive, and are wired
- Tests pass and cover all specified behaviors
- No UI, visual, or real-time behavior introduced in this phase

---

## Commits Verified

All 4 commits documented in SUMMARYs confirmed present in git history:

- `6a01447` — test(20-01): add failing tests for decay_stale_pairs and remove_entity
- `2cdf835` — feat(20-01): add decay_stale_pairs and remove_entity to CorrelationDetector
- `bad8c74` — test(20-02): add failing tests for entity removal cleanup in coordinator
- `3a89116` — feat(20-02): wire entity removal cleanup into coordinator async_setup

---

## Gaps Summary

No gaps. All 5 observable truths verified. Both requirements (COR-08, COR-09) satisfied by substantive, wired, tested implementations. The only outstanding item is a documentation update: COR-08 checkbox in REQUIREMENTS.md should be marked `[x]`.

---

_Verified: 2026-04-07_
_Verifier: Claude (gsd-verifier)_
