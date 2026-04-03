# Phase 15: Coordinator Integration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-03
**Phase:** 15-coordinator-integration
**Areas discussed:** Tier in entity_status sensor data, Daily reclassification hook, Duplicated duration formatting

---

## Tier in entity_status Sensor Data

| Option | Description | Selected |
|--------|-------------|----------|
| Add 'activity_tier' per entity, null if unclassified | Simple, consistent with ActivityTier.value strings. | |
| Add 'activity_tier' per entity, 'unknown' if unclassified | More explicit in HA dashboards but magic string. | |
| You decide | Let Claude pick during planning. | ✓ |

**User's choice:** You decide
**Notes:** Deferred to Claude's discretion.

---

## Daily Reclassification Hook

| Option | Description | Selected |
|--------|-------------|----------|
| In _today_date day-change block, before detection | Natural fit, tiers fresh before check_inactivity. | |
| You decide | Let Claude pick during planning. | ✓ |

**User's choice:** You decide
**Notes:** Deferred to Claude's discretion.

---

## Duplicated Duration Formatting

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — replace inline formatting | Eliminates duplicated logic, consistent with acute_detector. | ✓ |
| No — leave as-is | Works, avoids touching sensor data formatting. | |

**User's choice:** Yes — replace inline formatting (Recommended)
**Notes:** None.

---

## Claude's Discretion

- Tier attribute value for unclassified entities (null vs 'unknown')
- Reclassification hook placement in coordinator

## Deferred Ideas

None — discussion stayed within phase scope.
