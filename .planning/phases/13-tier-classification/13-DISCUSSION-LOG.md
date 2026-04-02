# Phase 13: Tier Classification - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-02
**Phase:** 13-tier-classification
**Areas discussed:** Classification gating, Rate computation method, Reclassification timing, Default tier for new entities

---

## Classification Gating

| Option | Description | Selected |
|--------|-------------|----------|
| learning_status == 'ready' | Requires 0.8 confidence. Consistent with DriftDetector. Most conservative. | ✓ |
| MIN_EVIDENCE_DAYS (3 days) | Faster classification. Matches DriftDetector constant. May classify prematurely. | |
| Custom threshold | Different confidence level or time-based gate. | |

**User's choice:** learning_status == 'ready' (Recommended)
**Notes:** None — straightforward selection of recommended option.

---

## Rate Computation Method

| Option | Description | Selected |
|--------|-------------|----------|
| Total events / distinct days observed | Simple, robust. Similar to DriftDetector day-counting. | |
| Median of per-slot daily rates | More resistant to single busy slots but more complex. | |
| You decide | Let Claude pick during planning. | ✓ |

**User's choice:** You decide
**Notes:** Deferred to Claude's discretion during planning.

---

## Reclassification Timing

| Option | Description | Selected |
|--------|-------------|----------|
| Compute on load, cache in memory | No storage schema change. Use coordinator _today_date pattern. | |
| Persist tier in storage | Avoids recomputation. Requires backward compat consideration. | |
| You decide | Let Claude pick during planning. | ✓ |

**User's choice:** You decide
**Notes:** Deferred to Claude's discretion during planning.

---

## Default Tier for New Entities

| Option | Description | Selected |
|--------|-------------|----------|
| None — skip tier logic | Unclassified entities behave exactly as today. Zero behavior change. | ✓ |
| MEDIUM — safe middle ground | Applies MEDIUM floor. Changes current behavior for new entities. | |
| LOW — least disruptive | No floor/boost but explicitly labeled. | |

**User's choice:** None — skip tier logic (Recommended)
**Notes:** None — straightforward selection of recommended option.

---

## Claude's Discretion

- Rate computation method (total/days vs median-of-slots)
- Reclassification timing and persistence (memory-only vs storage)

## Deferred Ideas

None — discussion stayed within phase scope.
