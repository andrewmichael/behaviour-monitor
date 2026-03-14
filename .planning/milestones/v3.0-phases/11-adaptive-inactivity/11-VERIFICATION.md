---
phase: 11-adaptive-inactivity
verified: 2026-03-14T20:15:00Z
status: passed
score: 12/12 must-haves verified
re_verification: false
---

# Phase 11: Adaptive Inactivity Verification Report

**Phase Goal:** Each entity's inactivity threshold adapts to its own observed timing variance, replacing the uniform global multiplier.
**Verified:** 2026-03-14T20:15:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|---------|
| 1  | A slot with regular inter-event intervals returns a low CV (near 0) | VERIFIED | `ActivitySlot.interval_cv()` lines 133–160 in routine_model.py; returns `stdev(intervals)/mean(intervals)`; test_cv_zero_for_identical_intervals and test_cv_zero_for_regular_intervals_five_events pass |
| 2  | A slot with irregular intervals returns a high CV (> 0.5) | VERIFIED | test_cv_nonzero_for_irregular_intervals and test_cv_correct_value_for_known_intervals pass; implementation confirmed at routine_model.py:160 |
| 3  | A slot with fewer than MIN_SLOT_OBSERVATIONS events returns CV = None | VERIFIED | Sparse guard at routine_model.py:141 (`if len(self.event_times) < MIN_SLOT_OBSERVATIONS: return None`); test_cv_returns_none_when_sparse_less_than_min passes |
| 4  | AcuteDetector uses threshold = global_multiplier x clamp(1+cv, min, max) x expected_gap when CV is available | VERIFIED | acute_detector.py lines 85–91 implement exactly this formula; 11 adaptive/clamp/compare tests pass |
| 5  | AcuteDetector falls back to threshold = global_multiplier x expected_gap when CV is None | VERIFIED | acute_detector.py lines 92–94; test_fallback_when_cv_is_none and test_fallback_no_alert_below_simple_threshold pass |
| 6  | Regular entities get tighter inactivity thresholds than erratic entities with the same expected_gap | VERIFIED | test_compare_thresholds_regular_vs_erratic passes; clamp at min=1.5 for CV=0 vs higher scalar for high CV |
| 7  | The HA config UI exposes 'Inactivity sensitivity scaling', 'Min inactivity multiplier', and 'Max inactivity multiplier' fields | VERIFIED | translations/en.json confirmed in both config.step.user.data and options.step.init.data; config_flow.py schema includes CONF_MIN/MAX_INACTIVITY_MULTIPLIER with NumberSelector |
| 8  | Saving the config with min > max shows an error and blocks the save | VERIFIED | `errors["base"] = "inactivity_min_exceeds_max"` implemented in both async_step_user (line 269) and async_step_init (line 322); 2 tests pass |
| 9  | Saving the config with min <= max succeeds | VERIFIED | Validation flow in config_flow.py passes through when min <= max; covered by existing config flow tests |
| 10 | Existing v6 config entries gain min_inactivity_multiplier=1.5 and max_inactivity_multiplier=10.0 on next HA startup | VERIFIED | __init__.py lines 143–149 implement migration block using setdefault; test_migrate_v6_to_v7_adds_min_inactivity_multiplier and test_migrate_v6_to_v7_adds_max_inactivity_multiplier pass |
| 11 | Config entries already at v7 are not re-migrated | VERIFIED | test_migrate_v7_is_noop passes |
| 12 | STORAGE_VERSION and ConfigFlow.VERSION are both 7 | VERIFIED | const.py line 52: `STORAGE_VERSION: Final = 7`; config_flow.py line 249: `VERSION = 7` |

**Score:** 12/12 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `custom_components/behaviour_monitor/const.py` | CONF_MIN/MAX_INACTIVITY_MULTIPLIER + DEFAULT_MIN/MAX_INACTIVITY_MULTIPLIER; STORAGE_VERSION = 7 | VERIFIED | Lines 25–31 add all four constants; line 52 has `STORAGE_VERSION: Final = 7` |
| `custom_components/behaviour_monitor/routine_model.py` | ActivitySlot.interval_cv() and EntityRoutine.interval_cv(hour, dow) | VERIFIED | ActivitySlot.interval_cv() at lines 133–160; EntityRoutine.interval_cv() at lines 276–282 |
| `custom_components/behaviour_monitor/acute_detector.py` | Adaptive threshold logic in check_inactivity(); min/max multiplier constructor params | VERIFIED | __init__ accepts min_multiplier and max_multiplier (lines 38–39); adaptive threshold at lines 85–94; adaptive_scalar in details dict (line 132) |
| `custom_components/behaviour_monitor/coordinator.py` | Updated AcuteDetector construction passing min/max from config | VERIFIED | Lines 79–83 pass both min_multiplier and max_multiplier from config entry data |
| `custom_components/behaviour_monitor/config_flow.py` | Two new NumberSelector fields; min>max validation in both flows; VERSION=7 | VERIFIED | Both fields in _build_data_schema(); validation in async_step_user and async_step_init; VERSION = 7 |
| `custom_components/behaviour_monitor/__init__.py` | v6->v7 migration block adding min/max defaults | VERIFIED | Migration block at lines 143–150 using setdefault semantics |
| `custom_components/behaviour_monitor/translations/en.json` | Friendly labels for all three fields in config and options steps | VERIFIED | "Inactivity sensitivity scaling", "Min inactivity multiplier", "Max inactivity multiplier" present in both config.step.user.data and options.step.init.data; descriptions in data_description |
| `tests/test_routine_model.py` | Unit tests for interval_cv() | VERIFIED | 12 cv-tagged tests at lines 579–664; all pass |
| `tests/test_acute_detector.py` | Unit tests for adaptive threshold | VERIFIED | 11 adaptive/fallback/clamp/compare tests at lines 507–706; all pass |
| `tests/test_config_flow.py` | min>max validation tests | VERIFIED | 2 min_exceeds_max tests at lines 170 and 631; both pass |
| `tests/test_init.py` | v6->v7 migration test; already-v7 no-op test | VERIFIED | test_migrate_v6_to_v7_adds_min_inactivity_multiplier, test_migrate_v6_to_v7_adds_max_inactivity_multiplier, test_migrate_v6_to_v7_bumps_version, test_migrate_v7_is_noop all pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| coordinator.py | AcuteDetector.__init__ | keyword args min_multiplier, max_multiplier | WIRED | Lines 79–83: `AcuteDetector(float(...), min_multiplier=float(d.get(CONF_MIN_INACTIVITY_MULTIPLIER, ...)), max_multiplier=float(d.get(CONF_MAX_INACTIVITY_MULTIPLIER, ...)))` |
| acute_detector.py check_inactivity() | routine.interval_cv() | method call on EntityRoutine | WIRED | Line 85: `cv = routine.interval_cv(now.hour, now.weekday())` |
| ActivitySlot.interval_cv() | event_times deque | statistics.stdev / mean on parsed intervals | WIRED | Lines 153–160: `from statistics import mean, stdev; m = mean(intervals); return stdev(intervals) / m` |
| config_flow.py _build_data_schema() | CONF_MIN/MAX_INACTIVITY_MULTIPLIER in const.py | import from .const | WIRED | Lines 34–35 import both constants; lines 138–154 use them in schema |
| __init__.py async_migrate_entry() | CONF_MIN/MAX_INACTIVITY_MULTIPLIER in const.py | setdefault on new_data dict | WIRED | Lines 145–146: `new_data.setdefault(CONF_MIN_INACTIVITY_MULTIPLIER, ...)` and `new_data.setdefault(CONF_MAX_INACTIVITY_MULTIPLIER, ...)` |
| async_step_user / async_step_init | errors dict | errors["base"] = "inactivity_min_exceeds_max" | WIRED | Both flows (lines 269 and 322) set `errors["base"] = "inactivity_min_exceeds_max"` when min > max |
| translations/en.json config.step.user.data | CONF_INACTIVITY_MULTIPLIER selector key | key match on inactivity_multiplier | WIRED | "inactivity_multiplier": "Inactivity sensitivity scaling" present in both config and options data blocks |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| INAC-01 | 11-01-PLAN.md, 11-02-PLAN.md | The inactivity threshold for each entity is derived from that entity's own observed inter-event variance rather than applying a single global multiplier uniformly | SATISFIED | interval_cv() computes per-slot CV; AcuteDetector uses adaptive threshold = global_multiplier x clamp(1+cv, 1.5, 10.0) x expected_gap; coordinator wires config min/max bounds; config UI exposes bounds; migration ensures existing installs get defaults; 403 tests pass |

No orphaned requirements found. REQUIREMENTS.md line 49 confirms INAC-01 maps to Phase 11 and is marked Complete.

### Anti-Patterns Found

None. All seven modified source files and both test files were scanned for TODO, FIXME, XXX, HACK, PLACEHOLDER, empty returns, and stub patterns. No issues found.

### Human Verification Required

None required. All observable truths are programmable testable behaviors (formula correctness, threshold computation, config migration, test pass/fail). No UI rendering, real-time behavior, or external service integration is involved.

### Gaps Summary

No gaps. All 12 observable truths verified, all 11 artifacts confirmed substantive and wired, all 7 key links confirmed wired end-to-end. Full test suite passes at 403 tests with no regressions.

---

_Verified: 2026-03-14T20:15:00Z_
_Verifier: Claude (gsd-verifier)_
