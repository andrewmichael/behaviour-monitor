---
phase: 20-correlation-lifecycle
plan: 01
subsystem: correlation
tags: [decay, cleanup, lifecycle, remove-entity]

requires:
  - phase: 18-correlation-discovery
    provides: CorrelationDetector with _pairs, _learned_pairs, _entity_event_counts, _break_cycles
provides:
  - decay_stale_pairs() method for automatic noise pair pruning
  - remove_entity() method for cleanup on entity removal
affects: []

tech-stack:
  added: []
  patterns: [noise-pair pruning during recompute, entity purge across all state dicts]

key-files:
  created: []
  modified:
    - custom_components/behaviour_monitor/correlation_detector.py
    - tests/test_correlation_detector.py

key-decisions:
  - "Decay prunes pairs NOT in _learned_pairs AND below _min_observations — keeps learned pairs and pairs with enough data"
  - "decay_stale_pairs() called at end of recompute() — natural daily hook"
  - "remove_entity() purges _pairs, _learned_pairs, _entity_event_counts, _break_cycles, and adjusts _total_event_count"

requirements-completed: [COR-08]

duration: 3min
completed: 2026-04-07
---

# Phase 20 Plan 01: Decay and Removal Summary

**decay_stale_pairs() and remove_entity() methods on CorrelationDetector for automatic lifecycle management**

## Accomplishments
- Added `decay_stale_pairs()` — prunes noise pairs (not learned, below min observations) during daily recompute
- Added `remove_entity(entity_id)` — purges all pairs, event counts, break cycles, learned pairs for a given entity
- `decay_stale_pairs()` called automatically at end of `recompute()`
- 9 new tests in TestDecayAndRemoval class, 42 total correlation tests passing

## Task Commits

1. **TDD RED:** `6a01447` — test(20-01): add failing tests for decay_stale_pairs and remove_entity
2. **TDD GREEN:** `2cdf835` — feat(20-01): add decay_stale_pairs and remove_entity to CorrelationDetector

---
*Phase: 20-correlation-lifecycle*
*Completed: 2026-04-07*
