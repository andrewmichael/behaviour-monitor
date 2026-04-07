---
phase: 18-correlation-discovery
plan: 01
subsystem: correlation
tags: [correlation-detector, pmi, co-occurrence, discovery]

requires:
  - phase: 17-foundation-and-rehydration
    provides: MIN_CO_OCCURRENCES, PMI_THRESHOLD, CONF_CORRELATION_WINDOW constants
provides:
  - CorrelationDetector class with record_event, recompute_daily, get_correlated_pairs
  - to_dict/from_dict persistence
affects: []

tech-stack:
  added: []
  patterns: [PMI-based co-occurrence scoring, bounded deque per entity, lazy pair creation]

key-files:
  created:
    - custom_components/behaviour_monitor/correlation_detector.py
    - tests/test_correlation_detector.py
  modified: []

key-decisions:
  - "PMI scoring with math.log2(p_ab / (p_a * p_b)) for correlation strength"
  - "Bounded deque per entity for recent timestamps, lazy pair creation on first co-occurrence"
  - "MIN_CO_OCCURRENCES gate prevents premature correlation promotion"

patterns-established:
  - "CorrelationDetector follows detector-per-file pure Python pattern"

requirements-completed: [COR-01, COR-02]

duration: 5min
completed: 2026-04-04
---

# Phase 18 Plan 01: CorrelationDetector Summary

**CorrelationDetector with PMI-based co-occurrence discovery, minimum co-occurrence gating, and to_dict/from_dict persistence**

## Performance

- **Tasks:** 1 (TDD)
- **Files created:** 2

## Accomplishments
- Created correlation_detector.py with CorrelationDetector class
- PMI-based scoring discovers entity pairs that co-occur more than chance
- MIN_CO_OCCURRENCES gate prevents premature correlation promotion (COR-02)
- to_dict/from_dict for persistence support
- 23 tests passing in test_correlation_detector.py

## Task Commits

1. **TDD RED:** `4fd4c7b` — test(18-01): add failing tests for CorrelationDetector PMI discovery
2. **TDD GREEN:** `5c46260` — feat(18-01): implement CorrelationDetector with PMI-based discovery

## Deviations from Plan
None.

## Issues Encountered
None.

---
*Phase: 18-correlation-discovery*
*Completed: 2026-04-04*
