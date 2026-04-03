# Phase 17: Foundation and Rehydration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-03
**Phase:** 17-foundation-and-rehydration
**Areas discussed:** Rehydration fix approach, Correlation constants scope, Correlation window UI control

---

## Rehydration Fix Approach

| Option | Description | Selected |
|--------|-------------|----------|
| Only set date guard on successful classification | ~1 line change. Leave guard unset when confidence too low so retries next cycle. | ✓ |
| Add explicit retry in coordinator | Coordinator checks for None tiers, schedules retry. More complex. | |
| You decide | Let Claude pick. | |

**User's choice:** Only set date guard on successful classification (Recommended)
**Notes:** The real bug is _tier_classified_date being set even when classification returns None.

---

## Correlation Constants Scope

| Option | Description | Selected |
|--------|-------------|----------|
| All constants now | AlertType.CORRELATION_BREAK, CONF_CORRELATION_WINDOW, DEFAULT, MIN_CO_OCCURRENCES, PMI_THRESHOLD. | ✓ |
| Minimal — only config keys | Just CONF and DEFAULT. Others deferred to Phase 18. | |
| You decide | Let Claude pick. | |

**User's choice:** All constants now (Recommended)
**Notes:** Downstream phases just import, no const.py changes needed later.

---

## Correlation Window UI Control

| Option | Description | Selected |
|--------|-------------|----------|
| NumberSelector in seconds (30-600, default 120) | Simple numeric input. 2-minute default from research. | ✓ |
| SelectSelector with preset options | Dropdown: Tight/Default/Loose. | |
| You decide | Let Claude pick. | |

**User's choice:** NumberSelector in seconds (30-600, default 120)
**Notes:** Matches existing numeric config patterns.

---

## Claude's Discretion

- Constant placement/grouping in const.py
- Whether CORRELATION_BREAK uses existing LOW severity or needs new level

## Deferred Ideas

None — discussion stayed within phase scope.
