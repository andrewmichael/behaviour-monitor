# Phase 14: Tier-Aware Detection - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-02
**Phase:** 14-tier-aware-detection
**Areas discussed:** Tier parameter application order, Explanation string format change, Unclassified entity handling

---

## Tier Parameter Application Order

| Option | Description | Selected |
|--------|-------------|----------|
| Boost multiplier, then floor as final max() | threshold = max(FLOOR, multiplier * BOOST * scalar * gap). Floor as safety net. | |
| Floor replaces threshold entirely for HIGH | Always use TIER_FLOOR_SECONDS for HIGH. Simple but ignores adaptive multiplier. | |
| You decide | Let Claude pick during planning. | ✓ |

**User's choice:** You decide
**Notes:** Deferred to Claude's discretion during planning.

---

## Explanation String Format Change

| Option | Description | Selected |
|--------|-------------|----------|
| Change explanation + add to details | Use format_duration() in explanation, add formatted strings to details dict. | |
| Details dict only | Keep explanation as '0.0h', only add formatted fields to details. | |
| You decide | Let Claude pick based on research pitfall analysis. | ✓ |

**User's choice:** You decide
**Notes:** Deferred to Claude's discretion. Research Pitfall 4 about automation breakage was noted.

---

## Unclassified Entity Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Exact current behavior — no boost, no floor | Skip tier logic when tier is None. Zero behavior change. | ✓ |
| Apply MEDIUM tier as conservative default | Treat unclassified as MEDIUM. Changes behavior before classification. | |

**User's choice:** Exact current behavior — no boost, no floor (Recommended)
**Notes:** Consistent with Phase 13 decision D-04.

---

## Claude's Discretion

- Boost/floor application order
- Explanation string format change approach

## Deferred Ideas

None — discussion stayed within phase scope.
