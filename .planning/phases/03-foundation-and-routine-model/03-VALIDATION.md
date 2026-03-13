---
phase: 3
slug: foundation-and-routine-model
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-13
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml / Makefile |
| **Quick run command** | `make test` |
| **Full suite command** | `make test-cov` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `make test`
- **After every plan wave:** Run `make test-cov`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | INFRA-01 | unit | `make test` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | INFRA-02 | unit | `make test` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ROUTINE-01 | unit | `make test` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ROUTINE-02 | unit | `make test` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ROUTINE-03 | unit | `make test` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_routine_model.py` — stubs for ROUTINE-01, ROUTINE-02, ROUTINE-03
- [ ] `tests/test_migration.py` — stubs for INFRA-01, INFRA-02
- [ ] Existing `tests/` infrastructure covers framework install

*Existing pytest infrastructure is in place from v1.0.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| HA startup with v1.0 storage doesn't crash | INFRA-01 | Needs real HA instance | Upgrade from v1.0, check logs for migration message |
| Deprecated sensors visible in HA UI | INFRA-02 | Needs real HA dashboard | Check entity list for ml_status, ml_training_remaining, cross_sensor_patterns |
| Recorder bootstrap populates model | ROUTINE-02 | Needs HA recorder with history | Start integration, check learning_progress sensor |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
