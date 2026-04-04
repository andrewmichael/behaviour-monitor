# Phase 18: Correlation Discovery - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-04
**Phase:** 18-correlation-discovery
**Areas discussed:** File structure, Co-occurrence recording, Sensor attribute format, Persistence scope

---

## CorrelationDetector File Structure

| Option | Description | Selected |
|--------|-------------|----------|
| New correlation_detector.py | Follows established detector-per-file pattern. Pure Python. | ✓ |
| You decide | Let Claude pick. | |

**User's choice:** New correlation_detector.py (Recommended)

---

## Co-occurrence Recording Approach

| Option | Description | Selected |
|--------|-------------|----------|
| Record on state_changed, compute daily | detector.record_event() on each state change. PMI computed daily in batch. | |
| Record in coordinator update cycle only | Only record during polling update. Simpler but misses events. | |
| You decide | Let Claude pick. | ✓ |

**User's choice:** You decide

---

## Sensor Attribute Format

| Option | Description | Selected |
|--------|-------------|----------|
| List of pairs with strength and count | Flat, dashboard-friendly. | |
| Grouped clusters with shared members | Pre-computed groups. More complex. | |
| You decide | Let Claude pick. | ✓ |

**User's choice:** You decide

---

## Persistence Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Learned pairs + raw counts | Enables PMI recomputation. Bounds via pair limit. | |
| Learned pairs only | Smaller storage, loses recomputation. | |
| You decide | Let Claude pick. | ✓ |

**User's choice:** You decide

---

## Claude's Discretion

- Recording approach, sensor format, persistence scope, public API, storage bounds

## Deferred Ideas

None — discussion stayed within phase scope.
