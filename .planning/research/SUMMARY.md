# Project Research Summary

**Project:** Behaviour Monitor v4.0 — Cross-Entity Correlation & Startup Tier Rehydration
**Domain:** Home Assistant custom integration — cross-entity temporal co-occurrence detection
**Researched:** 2026-04-03
**Confidence:** HIGH

## Executive Summary

Behaviour Monitor v4.0 adds two distinct features to a mature, well-architected codebase: cross-entity correlation discovery with break detection, and a startup tier rehydration bug fix. Both features are implementable using only Python stdlib (already in use) with zero new external dependencies. The codebase has a proven, strictly enforced architecture pattern — pure Python detectors, coordinator-as-wiring-layer, sustained-evidence gating, single-Store persistence — and v4.0 must follow it precisely to avoid regressions against the existing 449-test suite.

The recommended approach for correlation is Pointwise Mutual Information (PMI) computed in a daily batch, following the same pattern as the existing daily tier classification. PMI normalizes for entity frequency, which is critical in a smart home where high-frequency motion sensors would spuriously dominate raw-count or Jaccard metrics. The correlation detector follows the established detector contract (pure Python, zero HA imports, returns AlertResult, serializable via to_dict/from_dict) and integrates into the coordinator as a fourth detector alongside AcuteDetector and DriftDetector. The startup tier rehydration fix is a 5-line change to coordinator.py that prevents a race condition where state changes arriving before the first coordinator update cycle can prevent tiers from being classified until midnight.

The key risks are: (1) correlation alerts firing during the learning period before sufficient evidence exists — must gate on minimum co-occurrence count and sustained-evidence cycles; (2) correlation alerts being injected into welfare status derivation and escalating severity inappropriately — correlation alerts should default to LOW severity and should not disrupt existing per-entity alert suppression keys; (3) storage migration breaking existing installs — the new `correlation_state` top-level key must use `.get()` with a safe default in `async_setup`, and STORAGE_VERSION bumps to 9 alongside a config migration v8->v9.

---

## Key Findings

### Recommended Stack

No new external dependencies. Every v4.0 feature is implementable with Python stdlib modules already imported in the codebase: `math.log2` for PMI calculation, `statistics.median` for lag computation, `collections.defaultdict` and `deque` for co-occurrence tracking, `itertools.combinations` for pair enumeration, and `dataclasses` for the new `CorrelationPair` structure. The existing `homeassistant.helpers.storage.Store` handles persistence by extending the current save dict with a `"correlation_state"` key.

**Core technologies:**
- `math.log2` + `statistics.median`: PMI formula and lag computation — normalizes co-occurrence for base-rate differences between high- and low-frequency entities
- `itertools.combinations`: entity pair enumeration — generates N*(N-1)/2 pairs from monitored list; stdlib, no graph library needed at home scale (N < 50)
- `collections.deque`: bounded event buffer per entity — matches existing `event_times` pattern (maxlen=56); prevents unbounded memory growth
- `homeassistant.helpers.storage.Store`: persistence — extends existing single-file pattern; no new Store instance needed

### Expected Features

**Must have (table stakes for v4.0):**
- Startup tier rehydration fix — standalone bug: race condition leaves `_activity_tier = None` until midnight, causing high-frequency entities to lose their inactivity floor for one cycle
- Auto-discover correlated entity groups — pairwise PMI-based co-occurrence discovery; daily batch computation following the proven `classify_tier()` scheduling pattern
- Expose discovered groups as sensor attributes — populate the existing empty `cross_sensor_patterns: []` placeholder in `_build_sensor_data`; no new sensor entity IDs
- Alert on broken correlations — `AlertType.CORRELATION_BREAK`; sustained-evidence gating (3 consecutive cycles); integrates with existing alert suppression and severity infrastructure
- Config migration v8->v9 — new `CONF_CORRELATION_WINDOW` key with `setdefault` pattern; required for any new config key

**Should have (low-cost, high-value):**
- Correlation confidence scoring — expose per-pair co-occurrence rate alongside learned pairs; analogous to existing `confidence()` per-entity pattern; improves alert quality
- Minimum learning period gate — suppress correlation alerts until minimum observation count is met (10+ co-occurrences); prevents false alerts during ramp-up
- Correlation group decay — remove stale correlations when behavior changes; prevents accumulated noise from replaced or repurposed entities

**Defer to v5+:**
- Time-of-day scoped correlations — requires per-slot pair data, multiplying storage and computation; global correlation covers the primary welfare monitoring use case
- Directional correlation (A triggers B) — useful enrichment but bidirectional is sufficient for v4.0 break detection
- Cross-entity drift detection (CUSUM at pair level) — doubles drift detection complexity for marginal v4.0 value

### Architecture Approach

v4.0 introduces `correlation_detector.py` as a fourth pure-Python detector class following the identical contract as `AcuteDetector` and `DriftDetector`. The coordinator wires it into `_handle_state_changed` (event recording via `record_event()`) and `_run_detection` (break checking via `check()`). Correlation discovery (PMI recomputation) runs once per day in the existing date-change block alongside `classify_tier()`. The startup rehydration fix adds a `_tiers_initialized: bool` flag so tiers are classified even when the date-change guard is already satisfied on the first update cycle due to the known race condition.

**Major components:**
1. `correlation_detector.py` (new file, ~200 lines) — `CorrelationPair` dataclass + `CorrelationDetector` class; pure Python, zero HA imports; `record_event()` for learning, `check()` for break detection, `recompute()` for daily PMI batch, `to_dict()`/`from_dict()` for persistence
2. `coordinator.py` (modified, ~40 lines net) — instantiate `CorrelationDetector`; add `_tiers_initialized` flag + `_classify_all_tiers()` method; wire `record_event()` in `_handle_state_changed`; wire `check()` in `_run_detection`; add `"correlation_state"` to `_save_data` and `async_setup` restore; populate `cross_sensor_patterns` in `_build_sensor_data`
3. `alert_result.py` (1-line change) — add `CORRELATION_BREAK = "correlation_break"` to `AlertType` enum; integrates with existing suppression key pattern automatically
4. `const.py` + `config_flow.py` + `__init__.py` — `CONF_CORRELATION_WINDOW`, `DEFAULT_CORRELATION_WINDOW = 300`, `CORRELATION_MIN_OBSERVATIONS = 20`, `CORRELATION_MIN_RATE = 0.7`; v8->v9 migration; config UI field for correlation window

**Total estimated: ~275 lines of new/modified production code** across 7 files plus tests.

### Critical Pitfalls

1. **Startup tier rehydration race condition** — A state change arriving between `async_setup()` (which registers the listener) and the first `_async_update_data()` call sets `_today_date` to today. When the first update runs, `_today_date == now.date()` is `True` and the tier classification block is skipped — tiers remain `None` until midnight. Prevention: add a `_tiers_initialized` flag; classify tiers on the first update cycle unconditionally using an `elif not self._tiers_initialized` branch.

2. **Correlation alerts firing during the learning period** — Without gating, the detector produces break alerts before a pair has enough co-occurrence history to be trustworthy. Prevention: require minimum observations (20) before a pair is "learned"; apply sustained-evidence gating (3 cycles); gate on both entities having `learning_status == "ready"`.

3. **Corrupting existing detection via update cycle changes** — Adding correlation alerts to the same `alerts` list could cause welfare status to escalate unnecessarily; suppression keys must not collide with existing `INACTIVITY|UNUSUAL_TIME|DRIFT` types. Prevention: append correlation alerts after existing detectors; default severity to LOW; use `"correlation_break"` as a distinct AlertType value; run full 449-test regression before merge.

4. **Storage migration breaking existing installs** — Adding new keys to the persisted JSON without a safe default causes `async_setup` to fail on existing installs. Prevention: use `.get("correlation_state")` with `None` default in restore logic (empty detector = no learned correlations, correct for any missing key); bump STORAGE_VERSION to 9; add a test that loads a v8 fixture and verifies clean upgrade.

5. **Combinatorial pair explosion** — Pre-computing or tracking all N*(N-1)/2 pairs is wasteful; for N=50 that is 1,225 pairs, most of which are noise. Prevention: lazy pair creation — only create a `CorrelationPair` when an actual co-occurrence is observed; apply `MIN_CO_OCCURRENCES = 10` gate before promoting a pair to "learned".

---

## Implications for Roadmap

Based on combined research, suggested phase structure:

### Phase 1: Startup Tier Rehydration Fix
**Rationale:** Independent bug fix with no dependency on correlation work; unblocks all subsequent phases that rely on accurate tier classification; low risk (5 lines of code via `_tiers_initialized` flag + `_classify_all_tiers()` helper).
**Delivers:** Tiers correctly classified on first update cycle after restart; eliminates one-cycle spurious inactivity alerts for high-frequency entities.
**Addresses:** Startup tier rehydration (table stakes, standalone fix).
**Avoids:** Pitfall 5 (tiers None after restart affecting inactivity floor for HIGH-tier entities).

### Phase 2: Foundation — AlertType, Constants, Config Migration
**Rationale:** Zero-risk additions that all subsequent phases depend on; establishes the `CORRELATION_BREAK` suppression key namespace and new config keys before any correlation logic touches the coordinator.
**Delivers:** `AlertType.CORRELATION_BREAK = "correlation_break"` in alert_result.py; `CONF_CORRELATION_WINDOW`, `CORRELATION_MIN_OBSERVATIONS`, `CORRELATION_MIN_RATE` constants in const.py; config migration v8->v9 with `setdefault` pattern; translations.
**Uses:** Existing `setdefault` migration chain pattern; existing `AlertType` enum extension point.
**Avoids:** Pitfall 11 (enum extension surprises — descriptive string value), Pitfall 12 (migration chain — minimal new config keys), Pitfall 13 (attribute naming mismatch — reuse existing `cross_sensor_patterns` key).

### Phase 3: CorrelationDetector — Data Structures and Discovery
**Rationale:** New file with no HA imports; fully independently testable before coordinator wiring; PMI batch computation design must be finalized before detection logic is added.
**Delivers:** `CorrelationPair` dataclass; `CorrelationDetector` class with `record_event()`, `recompute()` (daily PMI batch), `get_correlation_groups()`, `to_dict()`/`from_dict()`; bounded event deque per entity.
**Uses:** `math.log2`, `statistics.median`, `itertools.combinations`, `collections.deque`; PMI algorithm with `CO_OCCURRENCE_WINDOW_SECONDS=300`, `MIN_CO_OCCURRENCES=10`, `PMI_THRESHOLD=1.0`.
**Avoids:** Pitfall 1 (pair explosion via lazy creation + MIN_CO_OCCURRENCES gate), Pitfall 9 (unbounded event buffer via bounded deque), Pitfall 10 (discovery runs every cycle — daily-batch separation from per-cycle detection).

### Phase 4: Coordinator Wiring
**Rationale:** Integration into the coordinator is the highest-risk step; builds on the independently-validated CorrelationDetector from Phase 3; must preserve all existing detection behavior.
**Delivers:** CorrelationDetector instantiated in `__init__`; `record_event()` wired in `_handle_state_changed`; daily `recompute()` in date-change block; `"correlation_state"` in `_save_data` and `async_setup` restore; `cross_sensor_patterns` populated in `_build_sensor_data`; `correlated_with` in `entity_status` entries.
**Implements:** Coordinator-as-wiring-layer pattern; single Store file persistence; PMI serialization via `to_dict()`/`from_dict()`.
**Avoids:** Pitfall 3 (corrupting existing detection — append after existing detectors, LOW severity default), Pitfall 4 (storage migration — `.get()` default for missing `"correlation_state"` key).

### Phase 5: Break Detection and Alert Integration
**Rationale:** Alert generation is the payoff feature; separated from discovery wiring to allow Phase 4 to be validated in isolation; must integrate cleanly with existing `_handle_alerts` and welfare derivation.
**Delivers:** `check()` method producing `AlertResult` with `AlertType.CORRELATION_BREAK`; sustained-evidence gating via `_break_cycles` dict; minimum-learning-period gate (10+ co-occurrences); group-level alert deduplication to prevent alert floods from multi-entity groups.
**Addresses:** Alert on broken correlations (table stakes), minimum learning period gate (should-have), correlation confidence scoring (should-have).
**Avoids:** Pitfall 2 (alerts during learning period — confidence gate), Pitfall 8 (alert flood from multi-entity group — group-level suppression key).

### Phase 6: Config UI and Sensor Exposure Polish
**Rationale:** Config UI and sensor attribute shape are user-facing and benefit from being finalized after detection behavior is stable; minimal risk as they are data-flow endpoints.
**Delivers:** Correlation window config option in options flow; `cross_sensor_patterns` attribute with defined schema per group (`entities`, `co_occurrence_rate`, `total_observations`, `status`); limited to top-N groups to avoid HA recorder database bloat.
**Avoids:** Pitfall 13 (attribute schema mismatch — flat JSON-serializable shape, bounded group count).

### Phase 7: Correlation Lifecycle Management
**Rationale:** Cleanup and decay prevent stale state accumulation over time; logically separated from detection behavior; can be shipped in v4.0 without blocking core detection.
**Delivers:** Group pruning on config reload when entities are removed from `monitored_entities`; correlation pair decay (recency weighting to retire stale pairs automatically).
**Addresses:** Correlation group decay (should-have).
**Avoids:** Pitfall 7 (stale correlation groups after entity removal — prune on `async_reload_entry`, guard all lookups with `if eid in self._monitored_entities`).

### Phase Ordering Rationale

- Phase 1 before Phase 3: tier rehydration is independent and unblocks accurate tier data during correlation testing.
- Phase 2 before Phase 3: `AlertType.CORRELATION_BREAK` and constants must exist before the detector references them.
- Phase 3 before Phase 4: coordinator wiring is easier to validate when the detector itself has passing unit tests in isolation.
- Phase 5 after Phase 4: detection and alert integration risk is lower once discovery wiring is proven stable with a passing regression suite.
- Phase 6 after Phase 5: sensor output schema is stabilized once alert behavior is confirmed correct.
- Phase 7 last: lifecycle management is correctness polish that does not affect the core detection path.

### Research Flags

Phases with well-documented patterns (skip research-phase):
- **Phase 1:** Direct code fix; race condition mechanism fully analyzed in ARCHITECTURE.md and PITFALLS.md with line-level references.
- **Phase 2:** Mechanical enum addition and setdefault migration; identical to v7->v8 pattern executed five times previously.
- **Phase 6:** Sensor attribute exposure via existing `cross_sensor_patterns` placeholder; no new sensor entities; straightforward data-flow endpoint.

Phases that may benefit from design review before execution:
- **Phase 3:** PMI threshold constants (`PMI_THRESHOLD=1.0`, `MIN_CO_OCCURRENCES=10`, `CO_OCCURRENCE_WINDOW_SECONDS=300`) are MEDIUM-confidence estimates. Define these as named constants in `const.py` (not hardcoded literals) so they can be adjusted without code changes after real-household feedback.
- **Phase 5:** Alert integration with welfare derivation requires an explicit design decision: should `CORRELATION_BREAK` alerts contribute to welfare status escalation? The research recommendation is NO (excluded from welfare calculation, or counted as LOW-only weight). This must be decided before implementation to avoid retroactive refactoring.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All features use stdlib modules already present; PMI is well-established in co-occurrence literature; zero dependency additions required |
| Features | HIGH | Table stakes features have direct code evidence (cross_sensor_patterns placeholder exists at coordinator.py L325+L338, AlertType is extension-ready); correlation threshold values are MEDIUM |
| Architecture | HIGH | Complete codebase analysis; all integration points identified with file and line references; follows proven existing detector patterns exactly |
| Pitfalls | HIGH | Derived from direct code analysis with line references; race condition and migration risks are concrete, not speculative |

**Overall confidence:** HIGH

### Gaps to Address

- **PMI threshold values** (`PMI_THRESHOLD=1.0`, `MIN_CO_OCCURRENCES=10`, `CO_OCCURRENCE_WINDOW_SECONDS=300`): Reasonable starting points from literature, but MEDIUM confidence. Define as named constants in `const.py` from day one so they can be tuned based on real-household behavior without code changes. Monitor for false-positive or false-negative patterns in first release.

- **Correlation strength threshold (`CORRELATION_MIN_RATE=0.7`)**: LOW confidence; no empirical smart-home data for this specific metric. FEATURES.md and ARCHITECTURE.md use this value but acknowledge it needs real-world validation. Start conservative (high threshold = fewer but higher-quality correlated pairs) and lower only if users report missed correlations.

- **Welfare status weight for correlation alerts**: Research recommends excluding `CORRELATION_BREAK` from welfare escalation (or treating it as LOW-only). This must be an explicit design decision in Phase 5, not an implicit default, to prevent confusion during future welfare status debugging.

---

## Sources

### Primary (HIGH confidence — direct codebase analysis)
- `coordinator.py` — lifecycle, wiring points, race condition site at `_handle_state_changed` / `_async_update_data` boundary, alert suppression pattern
- `routine_model.py` — `classify_tier()` once-per-day guard logic, `EntityRoutine` field definitions (`init=False` tier fields), `ActivitySlot.event_times` deque
- `acute_detector.py` — sustained-evidence counter pattern (`_inactivity_cycles`, `_unusual_time_cycles` dicts); reused for `_break_cycles`
- `drift_detector.py` — CUSUM accumulator pattern; `to_dict()`/`from_dict()` serialization contract to match
- `alert_result.py` — `AlertType` enum extension point; suppression key format `f"{entity_id}|{alert_type.value}"`
- `const.py` — `SUSTAINED_EVIDENCE_CYCLES = 3`, `STORAGE_VERSION = 8`, existing tier boundary constants

### Secondary (HIGH confidence — peer-reviewed literature)
- [A Framework for Event Co-occurrence Detection in Event Streams (arXiv)](https://arxiv.org/pdf/1603.09012) — temporal co-occurrence with window-based detection
- [Mining Correlation Patterns among Appliances in Smart Home (Springer)](https://link.springer.com/chapter/10.1007/978-3-319-06605-9_19) — CoPMiner algorithm; confirms pairwise approach is appropriate at home scale
- [Temporal Pattern Discovery for Anomaly Detection in Smart Home (ResearchGate)](https://www.researchgate.net/publication/4317368_Temporal_pattern_discovery_for_anomaly_detection_in_a_smart_home) — Allen temporal relations; confirms window-based approach
- [A Better Index for Analysis of Co-occurrence (Science Advances)](https://www.science.org/doi/10.1126/sciadv.abj9204) — PMI vs. Jaccard comparison; confirms PMI advantage with base-rate normalization

### Tertiary (MEDIUM confidence — threshold values need real-world validation)
- [Pointwise Mutual Information calculation guidance (ListenData)](https://www.listendata.com/2022/06/pointwise-mutual-information-pmi.html) — PMI interpretation; `PMI > 1.0` as "2x above chance" cutoff
- [On Co-occurrence Pattern Discovery from Spatio-temporal Event Stream (Springer)](https://link.springer.com/chapter/10.1007/978-3-642-41154-0_29) — sliding window algorithms; informs `CO_OCCURRENCE_WINDOW_SECONDS=300` default
- [A Method for Temporal Event Correlation (IEEE)](https://ieeexplore.ieee.org/document/8717853) — temporal similarity for event correlation

---
*Research completed: 2026-04-03*
*Ready for roadmap: yes*
