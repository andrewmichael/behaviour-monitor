# Phase 19: Break Detection and Alerting - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-04
**Phase:** 19-break-detection-and-alerting
**Areas discussed:** Break detection trigger logic, Group-level deduplication, Alert severity and suppression

---

## Break Detection Trigger Logic

| Option | Description | Selected |
|--------|-------------|----------|
| New method on CorrelationDetector | check_breaks() on detector, returns AlertResults. Follows detector pattern. | ✓ |
| In coordinator directly | Inline in coordinator. Breaks detector pattern. | |
| You decide | Let Claude pick. | |

**User's choice:** New method on CorrelationDetector (Recommended)

---

## Group-Level Deduplication

| Option | Description | Selected |
|--------|-------------|----------|
| One alert per triggering entity | Entity A fires, B+C missing → one alert listing all missing. Dedup by trigger entity. | ✓ |
| One alert per correlation group | Pre-compute groups, one alert per group. More complex. | |
| You decide | Let Claude pick. | |

**User's choice:** One alert per triggering entity (Recommended)

---

## Alert Severity and Suppression

| Option | Description | Selected |
|--------|-------------|----------|
| Use existing alert_suppression, same interval | CORRELATION_BREAK key in same dict. Consistent. | ✓ |
| Separate suppression with different interval | Dedicated suppression. More flexible, more config. | |
| You decide | Let Claude pick. | |

**User's choice:** Use existing alert_suppression dict, same repeat interval (Recommended)

---

## Claude's Discretion

- Miss count storage location (detector vs coordinator)
- check_breaks call timing (per-event vs per-cycle)
- Explanation string format

## Deferred Ideas

None — discussion stayed within phase scope.
