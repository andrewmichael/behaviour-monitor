---
phase: 11
slug: adaptive-inactivity
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `pytest.ini` / `Makefile` |
| **Quick run command** | `make test` |
| **Full suite command** | `make test` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `make test`
- **After every plan wave:** Run `make test`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | INAC-01 | unit | `python -m pytest tests/test_routine_model.py -x -k cv` | ❌ Wave 0 | ⬜ pending |
| 11-01-02 | 01 | 1 | INAC-01 | unit | `python -m pytest tests/test_acute_detector.py -x -k adaptive` | ❌ Wave 0 | ⬜ pending |
| 11-01-03 | 01 | 1 | INAC-01 | unit | `python -m pytest tests/test_acute_detector.py -x -k "fallback or clamp"` | ❌ Wave 0 | ⬜ pending |
| 11-02-01 | 02 | 1 | INAC-01 | unit | `python -m pytest tests/test_config_flow.py -x -k min_exceeds_max` | ❌ Wave 0 | ⬜ pending |
| 11-02-02 | 02 | 1 | INAC-01 | unit | `python -m pytest tests/test_init.py -x -k v7` | ❌ Wave 0 | ⬜ pending |
| 11-02-03 | 02 | 1 | INAC-01 | integration | `make test` | ✅ exists | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. `tests/conftest.py` and `tests/__init__.py` provide `mock_hass` / `mock_config_entry` fixtures needed for config flow and init tests. All new tests are written in the same tasks that implement the features.

*No new test files or fixtures needed before implementation begins.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
