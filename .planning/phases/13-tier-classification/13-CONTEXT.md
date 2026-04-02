# Phase 13: Tier Classification - Context

**Gathered:** 2026-04-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Add `classify_tier()` method to `EntityRoutine` that auto-classifies each entity into HIGH/MEDIUM/LOW frequency tiers based on observed event rates. Classification is gated on learning confidence, reclassified at most once per day, and tier changes are logged at debug level. This phase does NOT wire tier into detection or coordinator — those are Phases 14 and 15.

</domain>

<decisions>
## Implementation Decisions

### Classification Gating
- **D-01:** Gate tier classification on `learning_status == "ready"` (confidence >= 0.8). Entities below this threshold remain unclassified. This is consistent with how DriftDetector gates on sufficient data.

### Rate Computation Method
- **D-02:** Claude's Discretion — choose the best approach for computing events-per-day from existing `event_times` deques during planning. Options considered: total events / distinct days observed, or median of per-slot daily rates.

### Reclassification Timing
- **D-03:** Claude's Discretion — choose whether to compute tier on load and cache in memory (using coordinator's existing `_today_date` day-change pattern for reclassification), or persist tier in storage. The research recommends compute-on-load with memory caching to avoid storage schema changes.

### Default Tier for Unclassified Entities
- **D-04:** Unclassified entities (insufficient data) get `None` — tier-aware logic is skipped entirely for them. They behave exactly as they do today with no floor and no boost. This ensures zero behavior change for new/learning entities.

### Claude's Discretion
- Rate computation method (D-02): total/days vs median-of-slots
- Reclassification timing and persistence (D-03): memory-only vs storage
- Whether `activity_tier` property returns `ActivityTier | None` or uses a sentinel
- Internal implementation of `reclassify_tier()` guard (timestamp vs date comparison)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 12 Foundation
- `custom_components/behaviour_monitor/const.py` — ActivityTier enum, TIER_BOUNDARY_HIGH=24, TIER_BOUNDARY_LOW=4, TIER_FLOOR_SECONDS, TIER_BOOST_FACTOR

### Routine Model (target file)
- `custom_components/behaviour_monitor/routine_model.py` — EntityRoutine class, ActivitySlot.event_times deques, confidence(), learning_status(), to_dict()/from_dict(), expected_gap_seconds()

### Existing Gating Patterns
- `custom_components/behaviour_monitor/drift_detector.py` — MIN_EVIDENCE_DAYS usage pattern, day-counting logic for baseline computation

### Research
- `.planning/research/SUMMARY.md` — Phase 2 section covers classification architecture, tier boundary reconciliation, and pitfalls (oscillation, premature classification)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `EntityRoutine.confidence()` and `learning_status()`: Ready-made gating mechanism — classification activates when `learning_status == "ready"`
- `ActivitySlot.event_times`: Deque of ISO timestamp strings per slot (168 slots, max 56 entries each) — raw data source for rate computation
- `EntityRoutine.to_dict()`/`from_dict()`: Serialization hooks — if tier is persisted, these need updating
- `MIN_EVIDENCE_DAYS = 3` in `const.py`: Existing constant for minimum data gating in DriftDetector

### Established Patterns
- Coordinator uses `_today_date` comparison to detect day boundaries — natural hook point for daily reclassification
- `EntityRoutine` properties are computed from slot data (e.g., `expected_gap_seconds()`) — tier could follow this pattern
- All datetime objects passed as parameters to routine_model (pure Python, no HA imports)

### Integration Points
- `EntityRoutine` is the data layer — `classify_tier()` and `activity_tier` property belong here
- Coordinator calls `EntityRoutine` methods during update cycle — Phase 15 will wire daily reclassification there
- `ActivitySlot.event_times` contains the raw timestamps needed for rate computation

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. Research SUMMARY.md recommends ~30 lines for classify_tier() on EntityRoutine.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 13-tier-classification*
*Context gathered: 2026-04-02*
