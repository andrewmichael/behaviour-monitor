---
phase: 5
slug: integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-13
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing, see `tests/`) |
| **Config file** | `setup.cfg`, `conftest.py` for HA mocks |
| **Quick run command** | `venv/bin/python -m pytest tests/test_coordinator.py tests/test_config_flow.py tests/test_init.py -x -q` |
| **Full suite command** | `make test` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `venv/bin/python -m pytest tests/test_coordinator.py tests/test_config_flow.py -x -q`
- **After every plan wave:** Run `make test`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 5-01-01 | 01 | 1 | INFRA-03c | unit | `pytest tests/test_init.py -k "migrate" -x` | ❌ W0 | ⬜ pending |
| 5-01-02 | 01 | 1 | INFRA-03a,b | unit | `pytest tests/test_config_flow.py -k "inactivity or drift" -x` | ❌ W0 | ⬜ pending |
| 5-02-01 | 02 | 1 | INFRA-03d | unit | `pytest tests/test_coordinator.py -k "first_refresh or safe_defaults" -x` | ❌ W0 | ⬜ pending |
| 5-02-02 | 02 | 1 | INFRA-03e | unit | `pytest tests/test_sensor.py -x` | ✅ needs update | ⬜ pending |
| 5-02-03 | 02 | 1 | INFRA-03f | unit | `pytest tests/test_coordinator.py -k "notification" -x` | ❌ W0 | ⬜ pending |
| 5-02-04 | 02 | 1 | INFRA-03h | unit | `pytest tests/test_coordinator.py -k "holiday or snooze or cooldown" -x` | ❌ W0 | ⬜ pending |
| 5-02-05 | 02 | 1 | INFRA-03g | unit | `pytest tests/test_coordinator.py -k "routine_reset" -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_coordinator.py` — rewrite for new coordinator (old tests reference `coord.analyzer`, `coord.ml_analyzer`, ML_AVAILABLE — all deleted)
- [ ] `tests/test_config_flow.py` — update for removed ML options and new inactivity_multiplier / drift_sensitivity options
- [ ] `tests/test_init.py` — add test for v3→v4 migration with new keys
- [ ] `conftest.py` `mock_config_entry` — update fixture to remove ML keys, add inactivity_multiplier and drift_sensitivity
- [ ] `tests/test_sensor.py` — update `mock_coordinator` fixture for new coordinator.data structure

*Note: Existing test infrastructure (conftest.py, pytest setup) covers framework requirements. Wave 0 updates existing stubs rather than creating from scratch.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Config flow UI renders new options correctly | INFRA-03a,b | HA UI rendering requires browser | Load integration options, verify inactivity_multiplier number box and drift_sensitivity dropdown appear |
| Existing v1.0 config entry loads after upgrade | INFRA-03c | End-to-end HA startup required | Install over v1.0 entry, verify no errors in HA logs on startup |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
