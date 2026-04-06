# Phase 20: Correlation Lifecycle - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.

**Date:** 2026-04-06
**Phase:** 20-correlation-lifecycle
**Areas discussed:** Stale pair decay strategy, Entity removal cleanup, Decay aggressiveness

---

## Stale Pair Decay Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Remove during daily recompute when PMI drops | Natural, uses existing cycle. | |
| Time-based — remove after N days | Track last_co_occurrence timestamp. | |
| You decide | Let Claude pick. | ✓ |

---

## Entity Removal Cleanup

| Option | Description | Selected |
|--------|-------------|----------|
| remove_entity() method on detector | Purges pairs, counts, break cycles. Coordinator calls it. | |
| You decide | Let Claude pick. | ✓ |

---

## Decay Aggressiveness

| Option | Description | Selected |
|--------|-------------|----------|
| Match history_window_days (28 days) | Consistent with routine model. | |
| Faster — 7 days | More aggressive pruning. | |
| You decide | Let Claude pick. | ✓ |

---

## Claude's Discretion

All three areas deferred.
