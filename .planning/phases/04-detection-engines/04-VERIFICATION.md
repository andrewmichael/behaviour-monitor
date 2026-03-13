---
phase: 04-detection-engines
verified: 2026-03-13T21:15:00Z
status: passed
score: 11/11 must-haves verified
re_verification: false
---

# Phase 4: Detection Engines Verification Report

**Phase Goal:** Acute and drift detectors are implemented as HA-free pure-Python components that consume the routine model API and produce structured alert results — fully testable without mocking HA infrastructure
**Verified:** 2026-03-13T21:15:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

Truths are drawn from PLAN frontmatter `must_haves` blocks (04-01-PLAN.md and 04-02-PLAN.md) and the ROADMAP.md Phase 4 Success Criteria.

#### Plan 04-01 Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | Inactivity alert fires when elapsed time exceeds 3x the learned typical interval for the current time slot | VERIFIED | `check_inactivity` computes `threshold = inactivity_multiplier * expected_gap`; test `test_cycle_3_returns_alert_result` passes |
| 2 | Unusual-time alert fires when activity occurs in a slot with fewer than MIN_SLOT_OBSERVATIONS events | VERIFIED | `check_unusual_time` gates on `slot.is_sufficient`; `test_cycle_3_returns_alert_result` (unusual_time class) passes |
| 3 | No alert fires from a single observation — 3 consecutive polling cycles of sustained evidence required | VERIFIED | `test_cycle_1_returns_none`, `test_cycle_2_returns_none` both pass for both check methods |
| 4 | Cycle counter resets to zero when alerting condition clears, requiring fresh evidence to re-fire | VERIFIED | `test_counter_resets_when_below_threshold` and `test_counter_resets_when_slot_becomes_sufficient` both pass |
| 5 | Inactivity severity is LOW at 2-3x, MEDIUM at 3-5x, HIGH at 5x+ the threshold | VERIFIED | `test_severity_low_at_2_5x_threshold`, `test_severity_medium_at_3_5x_threshold`, `test_severity_high_at_6x_threshold` all pass; boundary tests at exactly 3x and 5x pass |

#### Plan 04-02 Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 6 | Drift alert fires only after CUSUM accumulator exceeds threshold for 3+ consecutive days of shifted behavior | VERIFIED | `test_requires_3_day_evidence_window` passes; `days_above_threshold >= MIN_EVIDENCE_DAYS` guard in `check()` |
| 7 | Bidirectional CUSUM detects both activity increases and decreases | VERIFIED | `test_upward_drift_detection` (direction=increase) and `test_downward_drift_detection` (direction=decrease) both pass |
| 8 | routine_reset clears the drift accumulator for a single entity without affecting baseline history | VERIFIED | `test_reset_entity_clears_accumulator` and `test_reset_entity_preserves_other_entities` both pass |
| 9 | Sensitivity setting (high/medium/low) maps to pre-tuned CUSUM k and h parameters | VERIFIED | `test_high_sensitivity`, `test_low_sensitivity`, `test_invalid_sensitivity_falls_back_to_medium` all pass; CUSUM_PARAMS{"high":(0.25,2.0),"medium":(0.5,4.0),"low":(1.0,6.0)} |
| 10 | CUSUM state serializes and deserializes correctly for persistence across HA restarts | VERIFIED | `test_drift_detector_serialization_roundtrip` and `test_cusum_state_serialization_roundtrip` pass |
| 11 | Zero-baseline entities return None (no division error) | VERIFIED | `test_returns_none_zero_baseline` passes; explicit `if baseline_mean == 0: return None` guard in `check()` |

**Score:** 11/11 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `custom_components/behaviour_monitor/alert_result.py` | AlertResult dataclass, AlertType enum, AlertSeverity enum | VERIFIED | 65 lines; all three types present; `to_dict()` produces JSON-safe dict; zero HA imports |
| `custom_components/behaviour_monitor/acute_detector.py` | AcuteDetector with check_inactivity and check_unusual_time | VERIFIED | 198 lines; both methods present and substantive; imports from `.alert_result`, `.const`, `.routine_model`; zero HA imports |
| `custom_components/behaviour_monitor/drift_detector.py` | DriftDetector with bidirectional CUSUM and routine_reset | VERIFIED | 303 lines; `CUSUMState` and `DriftDetector` present; `reset_entity()`, `to_dict()`, `from_dict()` all implemented; zero HA imports |
| `tests/test_acute_detector.py` | Unit tests for acute detection logic (min 150 lines) | VERIFIED | 458 lines; 29 tests; all pass |
| `tests/test_drift_detector.py` | Unit tests for drift detection and CUSUM validation (min 150 lines) | VERIFIED | 674 lines; 29 tests (58 total including alert_result tests); all pass |
| `custom_components/behaviour_monitor/const.py` | Extended with detection constants | VERIFIED | Lines 169-187: DEFAULT_INACTIVITY_MULTIPLIER=3.0, SUSTAINED_EVIDENCE_CYCLES=3, MIN_EVIDENCE_DAYS=3, MINIMUM_CONFIDENCE_FOR_UNUSUAL_TIME=0.3, CUSUM_PARAMS with all three sensitivity tiers |

**Bonus artifact verified:** `tests/test_alert_result.py` — 215 lines, 28 tests; all pass (mentioned in SUMMARY but not required in PLAN must_haves)

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `acute_detector.py` | `alert_result.py` | `from .alert_result import AlertResult, AlertSeverity, AlertType` | WIRED | Line 15: import confirmed; AlertResult used in both `check_inactivity` and `check_unusual_time` return paths |
| `acute_detector.py` | `routine_model.py` | `from .routine_model import EntityRoutine` | WIRED | Line 21: import confirmed; EntityRoutine used as type annotation and `.expected_gap_seconds()`, `.confidence()`, `.slots`, `.slot_index()` all called |
| `drift_detector.py` | `alert_result.py` | `from .alert_result import AlertResult, AlertType, AlertSeverity` | WIRED | Line 19: import confirmed; AlertResult produced in `check()` return path |
| `drift_detector.py` | `routine_model.py` | `from .routine_model import EntityRoutine` | WIRED | Line 21: import confirmed; `routine.slots`, `routine.daily_activity_rate()`, `routine.confidence()` all called in `check()` |
| `drift_detector.py` | `const.py` | `from .const import CUSUM_PARAMS, MIN_EVIDENCE_DAYS, SENSITIVITY_MEDIUM` | WIRED | Line 20: all three constants used in `__init__` and `check()` |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| ACUTE-01 | 04-01-PLAN.md | System alerts when no expected activity occurs for a configurable multiplier of the learned typical interval per entity | SATISFIED | `check_inactivity` fires after 3 cycles of `elapsed >= multiplier * expected_gap`; multiplier defaults to `DEFAULT_INACTIVITY_MULTIPLIER=3.0` from const.py |
| ACUTE-02 | 04-01-PLAN.md | System alerts on activity at times that have never or rarely occurred in learned history | SATISFIED | `check_unusual_time` fires when `slot.is_sufficient` is False and `confidence >= 0.3` after 3 cycles |
| ACUTE-03 | 04-01-PLAN.md | System requires sustained evidence (multiple consecutive polling cycles) before firing any acute alert | SATISFIED | Both `check_inactivity` and `check_unusual_time` use `SUSTAINED_EVIDENCE_CYCLES=3`; cycles 1 and 2 return None |
| DRIFT-01 | 04-02-PLAN.md | System detects persistent changes in daily behavior metrics using CUSUM change point detection | SATISFIED | Bidirectional CUSUM (S+ and S−) in `DriftDetector.check()`; fires after `MIN_EVIDENCE_DAYS=3` consecutive days of threshold breach |
| DRIFT-02 | 04-02-PLAN.md | User can call a routine_reset service to tell the model their routine changed intentionally | SATISFIED (pure-Python scope) | `DriftDetector.reset_entity()` clears the CUSUM accumulator for a single entity; HA service dispatch is Phase 5 wiring. Phase 4 goal is explicitly "HA-free pure-Python components." |
| DRIFT-03 | 04-02-PLAN.md | User can configure drift detection sensitivity in the config flow UI | SATISFIED | `DriftDetector(sensitivity=...)` reads `CUSUM_PARAMS[sensitivity]`; config flow already exposes `CONF_SENSITIVITY`; `DriftDetector` tests confirm all three sensitivity tiers |

**No orphaned requirements found.** All six requirement IDs (ACUTE-01 through DRIFT-03) appear in plan frontmatter and have implementation evidence.

---

## Anti-Patterns Found

No anti-patterns detected.

| File | Scan Result |
|------|------------|
| `alert_result.py` | No TODO/FIXME/placeholder; no empty returns; no stubs |
| `acute_detector.py` | No TODO/FIXME/placeholder; all code paths return substantive results or None with explicit reasoning |
| `drift_detector.py` | No TODO/FIXME/placeholder; all guards are explicit and documented |
| `test_acute_detector.py` | No placeholder tests; all assertions are substantive |
| `test_drift_detector.py` | No placeholder tests; CUSUM accumulation tests use real `EntityRoutine` instances with controlled `event_times` |

---

## Human Verification Required

None. All phase 4 behaviors are fully verifiable programmatically:

- Zero HA imports confirmed by `grep -c homeassistant` (all three implementation files return 0)
- All 86 tests pass (29 acute + 29 drift + 28 alert_result) in 0.23s
- CUSUM parameter validation against simulated 1-sigma shift is covered by `test_cusum_params_1sigma_medium_sensitivity`

---

## Summary

Phase 4 goal is fully achieved. Both detectors are pure-Python, HA-free, and consume the Phase 3 `EntityRoutine` API directly. The full test suite (86 tests across three test files) runs without mocking any HA infrastructure — using only `MagicMock` for `EntityRoutine` in the acute detector tests, and real `EntityRoutine` instances with populated `event_times` in the drift detector tests.

Key design decisions that were verified against must_haves:

- **Severity ratio relative to threshold, not expected_gap:** Correct — `severity_ratio = elapsed / threshold` produces coherent LOW/MEDIUM/HIGH tiers above the alerting threshold.
- **Stdev=0 fallback:** `max(1.0, baseline_mean * 0.1)` prevents infinite z-scores while preserving sensitivity for low-count signals.
- **Transient spike test uses state priming, not extreme events:** Correct — direct priming isolates reset-logic from signal-magnitude effects; documented as a deliberate decision.
- **reset() preserves last_update_date:** Correct — prevents double-processing on the same day if reset_entity() and check() are called in the same coordinator cycle.

All 6 requirement IDs are satisfied within the Phase 4 pure-Python scope. DRIFT-02 HA service registration and DRIFT-03 config flow UI option are both already infrastructurally present (config flow has `CONF_SENSITIVITY`; Phase 5 will wire the service call dispatch into `__init__.py`).

---

_Verified: 2026-03-13T21:15:00Z_
_Verifier: Claude (gsd-verifier)_
