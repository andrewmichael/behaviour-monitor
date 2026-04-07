---
phase: 19-break-detection-and-alerting
verified: 2026-04-06T00:00:00Z
status: passed
score: 10/10 must-haves verified
---

# Phase 19: Break Detection and Alerting Verification Report

**Phase Goal:** Users are alerted when learned correlations break, with noise suppression that prevents false or redundant alerts.
**Verified:** 2026-04-06
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `check_breaks` returns AlertResult list when learned correlation partner is missing beyond window | VERIFIED | Method at line 281 of `correlation_detector.py`; 9 TestCheckBreaks tests pass |
| 2 | `check_breaks` returns empty list when all learned partners fired within window | VERIFIED | `test_all_partners_within_window_returns_empty` passes |
| 3 | Break alerts only fire after SUSTAINED_EVIDENCE_CYCLES (3) consecutive misses | VERIFIED | Counter gating at lines 317-322 of `correlation_detector.py`; tests for miss 1, 2, 3 pass |
| 4 | Counter resets to 0 when the correlation is satisfied | VERIFIED | Line 314 of `correlation_detector.py`; `test_counter_resets_on_satisfied` passes |
| 5 | One AlertResult per triggering entity even when multiple partners are missing (group dedup) | VERIFIED | `test_multi_partner_group_dedup` passes; single alert with both partners in details |
| 6 | Break cycles state survives `to_dict`/`from_dict` round trip | VERIFIED | `test_break_cycles_round_trip` passes; `break_cycles` key in `to_dict` at line 373 and restored at lines 407-409 of `correlation_detector.py` |
| 7 | `_run_detection` calls `check_breaks` for each monitored entity | VERIFIED | Lines 228-231 of `coordinator.py`; `test_run_detection_calls_check_breaks` and `test_run_detection_check_breaks_passes_last_seen` pass |
| 8 | Correlation break alerts go through existing `_alert_suppression` pipeline with `CORRELATION_BREAK` type key | VERIFIED | Suppression key format `{entity_id}|{alert_type.value}` at line 245 of `coordinator.py`; `test_correlation_break_suppression_key` asserts `"sensor.a|correlation_break"` |
| 9 | Correlation break alerts do NOT escalate welfare status (LOW severity, excluded from welfare derivation) | VERIFIED | `welfare_alerts` filter at lines 288-290 of `coordinator.py`; `test_derive_welfare_excludes_correlation_breaks` asserts status `"ok"`; `test_derive_welfare_escalates_with_non_correlation_alerts` confirms non-correlation alerts still escalate |
| 10 | `correlation_detector.py` has zero Home Assistant imports | VERIFIED | `TestNoHAImports::test_no_homeassistant_import` passes; grep confirms 0 `homeassistant` occurrences |

**Score:** 10/10 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `custom_components/behaviour_monitor/correlation_detector.py` | `check_breaks` method with sustained evidence and group dedup | VERIFIED | `def check_breaks` at line 281; `_break_cycles` at line 126; `AlertType.CORRELATION_BREAK` at line 337; `SUSTAINED_EVIDENCE_CYCLES` at line 321; `break_cycles` in `to_dict`/`from_dict` |
| `tests/test_correlation_detector.py` | Break detection unit tests | VERIFIED | `class TestCheckBreaks` at line 296 with 9 tests; `test_break_cycles_round_trip` in `TestPersistence` |
| `custom_components/behaviour_monitor/coordinator.py` | `check_breaks` wired into `_run_detection`, welfare exclusion | VERIFIED | `check_breaks` loop at lines 228-231; `welfare_alerts` filter at lines 288-290; `CORRELATION_BREAK` exclusion at line 288 |
| `tests/test_coordinator_correlation.py` | Coordinator break detection wiring tests | VERIFIED | `class TestCorrelationBreakDetection` at line 351 with 5 tests |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `correlation_detector.py` | `alert_result.py` | `AlertResult, AlertType.CORRELATION_BREAK, AlertSeverity.LOW` | WIRED | `from .alert_result import AlertResult, AlertSeverity, AlertType` at line 16; `AlertType.CORRELATION_BREAK` used at line 337; `AlertSeverity.LOW` at line 339 |
| `correlation_detector.py` | `const.py` | `SUSTAINED_EVIDENCE_CYCLES` constant | WIRED | `SUSTAINED_EVIDENCE_CYCLES` imported at line 21; used in gating condition at line 321 |
| `coordinator.py:_run_detection` | `correlation_detector.check_breaks` | method call in detection loop | WIRED | `self._correlation_detector.check_breaks(eid, now, self._last_seen)` at line 230 |
| `coordinator.py:_derive_welfare` | `AlertType.CORRELATION_BREAK` | exclusion filter | WIRED | `a.alert_type != AlertType.CORRELATION_BREAK` at line 288; `AlertType` imported at line 17 |

---

## Data-Flow Trace (Level 4)

Not applicable — phase produces pure-Python detection logic (no UI/rendering components). Data flow is exercised directly by the test suite.

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 50 tests in phase-related files pass | `python -m pytest tests/test_correlation_detector.py tests/test_coordinator_correlation.py -x` | 50 passed, 0 failures, 1 warning | PASS |
| All 4 TDD commits exist in git history | `git log --oneline` | 463c8ee, 94aac4e, d5bc4e5, 896b419 all present | PASS |
| `correlation_detector.py` has zero HA imports | `grep "homeassistant" correlation_detector.py` | 0 matches | PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| COR-05 | 19-01, 19-02 | System alerts when a learned correlation breaks (entity A fires without expected companion B within the window) | SATISFIED | `check_breaks` method returns `AlertResult` with `AlertType.CORRELATION_BREAK`; wired into `_run_detection`; verified by 9 unit tests and 2 integration tests |
| COR-06 | 19-01, 19-02 | Break alerts require sustained evidence (multiple consecutive misses) before firing | SATISFIED | `SUSTAINED_EVIDENCE_CYCLES` (=3) gate in `check_breaks`; `_break_cycles` counter increments on each miss and resets on satisfaction; verified by test_first_miss, test_second_miss, test_third_miss tests |
| COR-07 | 19-01, 19-02 | Alerts are deduplicated at the group level — one alert per broken group, not per pair | SATISFIED | `check_breaks` collects all missing partners into `missing_partners` list and produces a single `AlertResult` with all partners in `details["missing_partners"]`; verified by `test_multi_partner_group_dedup` |

All 3 requirement IDs declared across both plans are accounted for. No orphaned requirements found for Phase 19 in REQUIREMENTS.md (COR-05, COR-06, COR-07 map to Phase 19 only).

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | — |

No stubs, placeholders, TODOs, empty returns, or hardcoded empty data found in phase-modified files. The `return []` occurrences in `check_breaks` are correct early-return paths (no partners / no misses / insufficient evidence), not stubs — all are exercised by passing tests.

---

## Human Verification Required

None. All phase behaviors are fully testable programmatically:

- Alert suppression operates on suppression dict keys (no HA notification service needed to verify)
- Welfare exclusion operates on pure data structures
- No UI or visual components were added in this phase
- No external service integration

---

## Gaps Summary

No gaps. All 10 observable truths verified, all 4 required artifacts substantive and wired, all 3 requirement IDs satisfied, all 4 TDD commits present in git history, and 50 tests pass with 0 failures.

---

_Verified: 2026-04-06_
_Verifier: Claude (gsd-verifier)_
