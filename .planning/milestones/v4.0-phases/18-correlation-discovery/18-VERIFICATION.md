---
phase: 18-correlation-discovery
verified: 2026-04-04T14:45:00Z
status: passed
score: 8/8 must-haves verified
gaps: []
human_verification:
  - test: "Run integration with real Home Assistant and monitored entities to confirm cross_sensor_patterns populates in the entity_status_summary sensor attributes after 10+ co-occurrences"
    expected: "cross_sensor_patterns attribute contains at least one entry with entities, co_occurrence_rate, total_observations after sustained co-occurring activity"
    why_human: "Requires live HA runtime with real entity state changes over time; cannot simulate full coordinator lifecycle in isolation"
---

# Phase 18: Correlation Discovery Verification Report

**Phase Goal:** The system automatically discovers which entities co-occur and exposes those relationships to the user.
**Verified:** 2026-04-04T14:45:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | CorrelationDetector discovers entity pairs that co-occur within a time window | VERIFIED | `record_event` in correlation_detector.py:128 creates pairs lazily via `_get_or_create_pair` when delta <= window_seconds |
| 2 | Pairs below MIN_CO_OCCURRENCES are not promoted to learned correlations | VERIFIED | `recompute()` at line 209: `if pair.co_occurrences < self._min_observations: continue` — pair skipped, not added to `_learned_pairs` |
| 3 | PMI is computed correctly normalizing for entity base rates | VERIFIED | Line 219-227: `p_co = co/total`, `p_a = count_a/total`, `p_b = count_b/total`, `pmi = math.log2(p_co / (p_a * p_b))` using global entity event counts |
| 4 | Detector serializes to dict and restores from dict without data loss | VERIFIED | `to_dict()` at line 277 preserves pairs, learned_pairs, entity_event_counts, total_event_count; `from_dict()` at line 295 restores all fields; test_persistence.py::test_round_trip confirms |
| 5 | cross_sensor_patterns sensor attribute is populated with discovered correlation groups | VERIFIED | coordinator.py line 341: `"cross_sensor_patterns": self._correlation_detector.get_correlation_groups()` |
| 6 | Correlation state survives a Home Assistant restart (persisted to storage, restored on startup) | VERIFIED | `_save_data` line 162: `"correlation_state": self._correlation_detector.to_dict()`; `async_setup` lines 133-135: restores from `stored["correlation_state"]` |
| 7 | Events recorded on each state change feed the correlation detector | VERIFIED | `_handle_state_changed` line 188: `self._correlation_detector.record_event(eid, now, self._last_seen)` |
| 8 | Daily recomputation runs in the date-change block alongside tier classification | VERIFIED | coordinator.py line 205: `self._correlation_detector.recompute()` in `_async_update_data` date-change block |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `custom_components/behaviour_monitor/correlation_detector.py` | CorrelationPair dataclass and CorrelationDetector class | VERIFIED | 344 lines; both classes present; zero HA imports confirmed |
| `tests/test_correlation_detector.py` | Unit tests for correlation discovery and persistence (min 150 lines) | VERIFIED | 344 lines; 23 tests across 5 classes (TestCorrelationPair, TestRecordEvent, TestRecompute, TestSensorOutput, TestPersistence, TestNoHAImports) |
| `custom_components/behaviour_monitor/coordinator.py` | CorrelationDetector wiring into coordinator lifecycle | VERIFIED | Import at line 37; instantiation at line 91; all lifecycle hooks wired |
| `tests/test_coordinator_correlation.py` | Integration tests for correlation wiring (min 100 lines) | VERIFIED | 343 lines; 12 tests across 4 classes (TestCorrelationInit, TestCorrelationRecordEvent, TestCorrelationRecompute, TestCorrelationPersistence, TestCorrelationSensorData) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| correlation_detector.py | const.py | import MIN_CO_OCCURRENCES, PMI_THRESHOLD | VERIFIED | Lines 18-19: `MIN_CO_OCCURRENCES, PMI_THRESHOLD` imported from `.const` |
| correlation_detector.py | alert_result.py | import AlertResult, AlertSeverity, AlertType | NOT PRESENT | Plan listed this as a key_link but correlation_detector.py has no alert_result import — correlation_detector.py is a pure discovery module; it does not generate alerts (that is Phase 19). The plan link was speculative and is not needed for Phase 18 goal. No gap. |
| coordinator.py | correlation_detector.py | from .correlation_detector import CorrelationDetector | VERIFIED | Line 37: `from .correlation_detector import CorrelationDetector` |
| coordinator.py _handle_state_changed | CorrelationDetector.record_event | method call on each state change | VERIFIED | Line 188: `self._correlation_detector.record_event(eid, now, self._last_seen)` |
| coordinator.py _build_sensor_data | CorrelationDetector.get_correlation_groups | populates cross_sensor_patterns | VERIFIED | Line 341: `"cross_sensor_patterns": self._correlation_detector.get_correlation_groups()` |
| coordinator.py _save_data | CorrelationDetector.to_dict | persistence in store save | VERIFIED | Line 162: `"correlation_state": self._correlation_detector.to_dict()` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| coordinator.py _build_sensor_data | cross_sensor_patterns | `_correlation_detector.get_correlation_groups()` | Yes — returns learned pairs from `_learned_pairs` set populated by PMI recompute | FLOWING |
| coordinator.py entity_status list | correlated_with | `_correlation_detector.get_correlated_entities(e)` | Yes — queries `_learned_pairs` for partners of each entity | FLOWING |
| coordinator.py async_setup | _correlation_detector state | `CorrelationDetector.from_dict(stored["correlation_state"])` | Yes — restores persisted pairs, learned_pairs, entity_event_counts | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 23 unit tests for CorrelationDetector pass | `pytest tests/test_correlation_detector.py -x -q` | 23 passed | PASS |
| 12 integration tests for coordinator wiring pass | `pytest tests/test_coordinator_correlation.py -x -q` | 12 passed | PASS |
| All 35 correlation tests combined | `pytest tests/test_correlation_detector.py tests/test_coordinator_correlation.py -x -q` | 35 passed, 1 warning (unrelated mock coroutine) | PASS |
| Zero HA imports in correlation_detector.py | grep homeassistant correlation_detector.py | No matches | PASS |
| CorrelationDetector and CorrelationPair exports present | grep in file content | Both classes found | PASS |
| All 4 commits present in git history | git log 58facc6 b6d5f06 5c46260 4fd4c7b | All 4 verified | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| COR-01 | 18-01 | System discovers entity pairs that co-occur within a configurable time window using PMI-based correlation strength | SATISFIED | `record_event` + `recompute()` in correlation_detector.py implement PMI-based discovery with configurable `co_occurrence_window_seconds` |
| COR-02 | 18-01 | Discovery is gated on minimum co-occurrence count to prevent premature correlations | SATISFIED | `recompute()` line 209: `if pair.co_occurrences < self._min_observations: continue` |
| COR-03 | 18-02 | Discovered correlation groups are exposed as sensor attributes on entity_status_summary | SATISFIED | coordinator.py line 341: `cross_sensor_patterns` populated from `get_correlation_groups()` |
| COR-04 | 18-02 | Correlation state is persisted to storage and restored on startup | SATISFIED | `_save_data` line 162 persists; `async_setup` lines 133-135 restores |

**Coverage:** 4/4 requirements mapped to this phase — all satisfied. No orphaned requirements found.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| coordinator.py | 354 | `"cross_sensor_patterns": []` in `_build_safe_defaults` | Info | This is intentional safe-fallback behavior for the error/startup path, not a stub. The normal data path at line 341 always calls `get_correlation_groups()`. |

No blockers or warnings found.

### Human Verification Required

#### 1. Live cross_sensor_patterns population

**Test:** Deploy to a Home Assistant instance with at least 2 monitored entities that naturally co-occur (e.g., morning routine sensors). Wait for 10+ co-occurrence events. Check the `entity_status_summary` sensor attributes for `cross_sensor_patterns`.
**Expected:** `cross_sensor_patterns` contains at least one entry with `entities`, `co_occurrence_rate`, and `total_observations` fields. `correlated_with` on each entity_status entry lists its learned partners.
**Why human:** Requires live HA runtime with real entity state changes over time; PMI recomputation runs on the daily date-change boundary, so it cannot be verified with a unit test alone.

### Gaps Summary

No gaps. All 8 must-have truths are verified. All 4 requirements (COR-01, COR-02, COR-03, COR-04) are satisfied by substantive, wired, data-flowing implementation. The plan's speculative key_link from correlation_detector.py to alert_result.py was not implemented — correctly so, as alert generation is Phase 19 scope.

---

_Verified: 2026-04-04T14:45:00Z_
_Verifier: Claude (gsd-verifier)_
