---
phase: 2
slug: analyzer-tightening
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-13
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (see `pytest.ini`) |
| **Config file** | `pytest.ini` |
| **Quick run command** | `python -m pytest tests/test_analyzer.py tests/test_ml_analyzer.py -v --tb=short` |
| **Full suite command** | `make test` |
| **Estimated runtime** | ~0.2 seconds (phase tests), ~15 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_analyzer.py tests/test_ml_analyzer.py -v --tb=short`
- **After every plan wave:** Run `make test`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | STAT-01 | unit | `pytest tests/test_analyzer.py::TestBucketGuards::test_sparse_bucket_skipped -x` | ✅ | ✅ green |
| 02-01-02 | 01 | 1 | STAT-01 | unit | `pytest tests/test_analyzer.py::TestBucketGuards::test_no_inf_z_score -x` | ✅ | ✅ green |
| 02-01-03 | 01 | 1 | STAT-02 | unit | `pytest tests/test_analyzer.py::TestBucketGuards::test_near_zero_mean_skipped -x` | ✅ | ✅ green |
| 02-01-04 | 01 | 1 | STAT-03 | unit | `pytest tests/test_analyzer.py::TestSensitivityConstants::test_medium_threshold_raised -x` | ✅ | ✅ green |
| 02-02-01 | 02 | 2 | STAT-04 | unit | `pytest tests/test_analyzer.py::TestAdaptiveThresholds -x` | ✅ | ✅ green |
| 02-02-02 | 02 | 2 | STAT-04 | unit | `pytest tests/test_analyzer.py::TestAdaptiveThresholds::test_multiplier_capped -x` | ✅ | ✅ green |
| 02-03-01 | 03 | 1 | ML-01 | unit | `pytest tests/test_ml_analyzer.py::TestCrossSensorGuard::test_low_count_excluded -x` | ✅ | ✅ green |
| 02-03-02 | 03 | 1 | ML-02 | unit | `pytest tests/test_ml_analyzer.py::TestMLContaminationConstants::test_medium_contamination_raised -x` | ✅ | ✅ green |
| 02-03-03 | 03 | 1 | ML-03 | unit | `pytest tests/test_ml_analyzer.py::TestEMASmoothing::test_spike_suppressed -x` | ✅ | ✅ green |
| 02-03-04 | 03 | 1 | ML-03 | unit | `pytest tests/test_ml_analyzer.py::TestEMASmoothing::test_sustained_anomaly_detected -x` | ✅ | ✅ green |
| 02-03-05 | 03 | 1 | ML-03 | unit | `pytest tests/test_ml_analyzer.py::TestEMASmoothing::test_ema_serialization -x` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_analyzer.py::TestBucketGuards` class — covers STAT-01, STAT-02
- [x] `tests/test_analyzer.py::TestSensitivityConstants` class — covers STAT-03
- [x] `tests/test_analyzer.py::TestAdaptiveThresholds` class — covers STAT-04
- [x] `tests/test_ml_analyzer.py::TestCrossSensorGuard` class — covers ML-01
- [x] `tests/test_ml_analyzer.py::TestMLContaminationConstants` class — covers ML-02
- [x] `tests/test_ml_analyzer.py::TestEMASmoothing` class — covers ML-03

*All Wave 0 requirements fulfilled during Phase 2 execution (TDD red-green pattern).*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-13

---

## Validation Audit 2026-03-13

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

All 11 tests existed and passed (89 total in phase files, 0.17s). No gaps to fill — status updated from draft to approved.
