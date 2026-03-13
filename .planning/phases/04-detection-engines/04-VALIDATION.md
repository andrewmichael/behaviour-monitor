---
phase: 4
slug: detection-engines
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-13
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml (existing) |
| **Quick run command** | `cd /Users/abourne/Documents/source/behaviour-monitor && venv/bin/python -m pytest tests/test_acute_detector.py tests/test_drift_detector.py -x -q` |
| **Full suite command** | `cd /Users/abourne/Documents/source/behaviour-monitor && venv/bin/python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run quick run command (acute + drift tests)
- **After every plan wave:** Run full suite command
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-T1 | 01 | 1 | ACUTE-01, ACUTE-02, ACUTE-03 | unit | `pytest tests/test_acute_detector.py -x -q` | ❌ W0 | ⬜ pending |
| 04-02-T1 | 02 | 1 | DRIFT-01, DRIFT-02, DRIFT-03 | unit | `pytest tests/test_drift_detector.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_acute_detector.py` — stubs for ACUTE-01, ACUTE-02, ACUTE-03
- [ ] `tests/test_drift_detector.py` — stubs for DRIFT-01, DRIFT-02, DRIFT-03

*Existing infrastructure (pytest, conftest.py, routine_model fixtures) covers framework needs.*

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
