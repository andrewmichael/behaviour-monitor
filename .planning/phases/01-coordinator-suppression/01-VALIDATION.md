---
phase: 1
slug: coordinator-suppression
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| **Estimated runtime** | ~15 seconds |

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
| 01-01-01 | 01 | 1 | NOTIF-01 | unit | `pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_cooldown_per_entity -x` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | NOTIF-01 | unit | `pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_cooldown_suppresses_repeat -x` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01 | 1 | NOTIF-01 | unit | `pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_cooldown_expires -x` | ❌ W0 | ⬜ pending |
| 01-01-04 | 01 | 1 | NOTIF-01 | unit | `pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_cooldown_resets_on_clear -x` | ❌ W0 | ⬜ pending |
| 01-02-01 | 01 | 1 | NOTIF-02 | unit | `pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_dedup_different_types_separate -x` | ❌ W0 | ⬜ pending |
| 01-02-02 | 01 | 1 | NOTIF-02 | unit | `pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_cross_path_dedup -x` | ❌ W0 | ⬜ pending |
| 01-03-01 | 01 | 1 | NOTIF-03 | unit | `pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_severity_gate_suppresses -x` | ❌ W0 | ⬜ pending |
| 01-03-02 | 01 | 1 | NOTIF-03 | unit | `pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_severity_gate_sensor_state_unaffected -x` | ❌ W0 | ⬜ pending |
| 01-03-03 | 01 | 1 | NOTIF-03 | unit | `pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_severity_gate_passes_above_threshold -x` | ❌ W0 | ⬜ pending |
| 01-04-01 | 01 | 1 | WELF-01 | unit | `pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_welfare_debounce_no_notify_first_cycle -x` | ❌ W0 | ⬜ pending |
| 01-04-02 | 01 | 1 | WELF-01 | unit | `pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_welfare_debounce_notifies_after_n_cycles -x` | ❌ W0 | ⬜ pending |
| 01-04-03 | 01 | 1 | WELF-01 | unit | `pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_welfare_debounce_resets_on_revert -x` | ❌ W0 | ⬜ pending |
| 01-04-04 | 01 | 1 | WELF-01 | unit | `pytest tests/test_coordinator.py::TestBehaviourMonitorCoordinator::test_welfare_debounce_deescalation -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_coordinator.py` — add 13 new test stubs for suppression behavior
- [ ] Existing test infrastructure covers framework and fixtures

*Existing infrastructure covers framework; only new test cases needed.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
