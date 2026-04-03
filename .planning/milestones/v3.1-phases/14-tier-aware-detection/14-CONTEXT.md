# Phase 14: Tier-Aware Detection - Context

**Gathered:** 2026-04-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Modify `AcuteDetector.check_inactivity()` to apply tier-specific multiplier boost and absolute minimum inactivity floor when an entity has a classified tier. Fix sub-hour alert display formatting using `format_duration()`. This phase does NOT touch the coordinator or config — those are Phases 15 and 16.

</domain>

<decisions>
## Implementation Decisions

### Tier Parameter Application Order
- **D-01:** Claude's Discretion — choose the best approach for how boost factor and floor interact with the existing adaptive threshold computation. Research recommends `max(TIER_FLOOR, multiplier * TIER_BOOST * scalar * expected_gap)` where floor acts as safety net. Alternative: floor replaces threshold entirely for HIGH tier. Pick based on research pitfall analysis (Pitfall 5: single global floor ignores entity rate).

### Explanation String Format
- **D-02:** Claude's Discretion — choose whether to change the explanation string from hours (`0.0h`) to `format_duration()` output (`45m`), or only add `elapsed_formatted` and `typical_formatted` to the `AlertResult.details` dict while keeping the explanation unchanged. Research Pitfall 4 warned about automation breakage from string format changes.

### Unclassified Entity Handling
- **D-03:** When `activity_tier` is `None` (insufficient data), skip tier logic entirely — no boost, no floor. Behave exactly as the current code does. Consistent with Phase 13 decision D-04 (unclassified = None, zero behavior change).

### Claude's Discretion
- Boost/floor application order (D-01)
- Whether to change explanation string format or only details dict (D-02)
- How to pass tier into check_inactivity() — new parameter vs reading from routine
- Whether to add `activity_tier` to AlertResult.details for downstream visibility

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Detection Engine (target file)
- `custom_components/behaviour_monitor/acute_detector.py` — check_inactivity() method, threshold computation, AlertResult construction, explanation string format

### Phase 12 Foundation
- `custom_components/behaviour_monitor/const.py` — TIER_FLOOR_SECONDS, TIER_BOOST_FACTOR, ActivityTier enum

### Phase 13 Classification
- `custom_components/behaviour_monitor/routine_model.py` — EntityRoutine.activity_tier property, format_duration() utility

### Alert Result Structure
- `custom_components/behaviour_monitor/alert_result.py` — AlertResult dataclass, details dict structure

### Research
- `.planning/research/SUMMARY.md` — Phase 3 section covers tier-aware detection, Pitfall 4 (automation breakage), Pitfall 5 (wrong floor)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `format_duration()` in `routine_model.py`: Ready to use for display formatting
- `EntityRoutine.activity_tier`: Returns `ActivityTier | None` — the tier data source
- `TIER_FLOOR_SECONDS` and `TIER_BOOST_FACTOR` dicts in `const.py`: Lookup tables keyed by ActivityTier

### Established Patterns
- Threshold computation: `threshold = multiplier * scalar * expected_gap` — tier modifiers extend this
- `AlertResult.details` dict: Already contains `elapsed_seconds`, `expected_gap_seconds`, `threshold_seconds`, `adaptive_scalar` — natural place for tier info
- `check_inactivity()` receives `routine: EntityRoutine` — can read `routine.activity_tier` directly

### Integration Points
- `check_inactivity()` signature may gain an optional `tier` parameter, or read from `routine.activity_tier`
- `AlertResult.explanation` string is the user-visible output — format change here
- `AlertResult.details` dict is the structured output — new keys here

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. Research estimates ~14 lines of changes to acute_detector.py.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 14-tier-aware-detection*
*Context gathered: 2026-04-02*
