---
phase: 1
slug: coordinator-suppression
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-13
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x with pytest-asyncio |
| **Config file** | none — pytest invoked directly |
| **Quick run command** | `venv/bin/python -m pytest tests/test_coordinator.py -v` |
| **Full suite command** | `venv/bin/python -m pytest tests/ -v` |
| **Estimated runtime** | ~0.3 seconds (coordinator), ~15 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run `venv/bin/python -m pytest tests/test_coordinator.py -v`
- **After every plan wave:** Run `venv/bin/python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | NOTIF-01 | unit | `pytest tests/test_coordinator.py::TestCoordinatorNotificationSuppression::test_cooldown_per_entity -x` | ✅ | ✅ green |
| 01-01-02 | 01 | 1 | NOTIF-01 | unit | `pytest tests/test_coordinator.py::TestCoordinatorNotificationSuppression::test_cooldown_suppresses_repeat -x` | ✅ | ✅ green |
| 01-01-03 | 01 | 1 | NOTIF-01 | unit | `pytest tests/test_coordinator.py::TestCoordinatorNotificationSuppression::test_cooldown_expires -x` | ✅ | ✅ green |
| 01-01-04 | 01 | 1 | NOTIF-01 | unit | `pytest tests/test_coordinator.py::TestCoordinatorNotificationSuppression::test_cooldown_resets_on_clear -x` | ✅ | ✅ green |
| 01-02-01 | 01 | 1 | NOTIF-02 | unit | `pytest tests/test_coordinator.py::TestCoordinatorNotificationSuppression::test_dedup_different_types_separate -x` | ✅ | ✅ green |
| 01-02-02 | 01 | 1 | NOTIF-02 | unit | `pytest tests/test_coordinator.py::TestCoordinatorNotificationSuppression::test_cross_path_dedup -x` | ✅ | ✅ green |
| 01-03-01 | 01 | 1 | NOTIF-03 | unit | `pytest tests/test_coordinator.py::TestCoordinatorNotificationSuppression::test_severity_gate_suppresses -x` | ✅ | ✅ green |
| 01-03-02 | 01 | 1 | NOTIF-03 | unit | `pytest tests/test_coordinator.py::TestCoordinatorNotificationSuppression::test_severity_gate_sensor_state_unaffected -x` | ✅ | ✅ green |
| 01-03-03 | 01 | 1 | NOTIF-03 | unit | `pytest tests/test_coordinator.py::TestCoordinatorNotificationSuppression::test_severity_gate_passes_above_threshold -x` | ✅ | ✅ green |
| 01-04-01 | 01 | 1 | WELF-01 | unit | `pytest tests/test_coordinator.py::TestCoordinatorNotificationSuppression::test_welfare_debounce_no_notify_first_cycle -x` | ✅ | ✅ green |
| 01-04-02 | 01 | 1 | WELF-01 | unit | `pytest tests/test_coordinator.py::TestCoordinatorNotificationSuppression::test_welfare_debounce_notifies_after_n_cycles -x` | ✅ | ✅ green |
| 01-04-03 | 01 | 1 | WELF-01 | unit | `pytest tests/test_coordinator.py::TestCoordinatorNotificationSuppression::test_welfare_debounce_resets_on_revert -x` | ✅ | ✅ green |
| 01-04-04 | 01 | 1 | WELF-01 | unit | `pytest tests/test_coordinator.py::TestCoordinatorNotificationSuppression::test_welfare_debounce_deescalation -x` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_coordinator.py` — 13 suppression test methods in TestCoordinatorNotificationSuppression
- [x] Existing test infrastructure covers framework and fixtures

*All Wave 0 requirements fulfilled during Phase 1 Plan 01 execution.*

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

All 13 tests existed and passed. No gaps to fill — status updated from draft to approved.
