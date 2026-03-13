# Project Research Summary

**Project:** Behaviour Monitor v1.1 Detection Rebuild
**Domain:** Home Assistant custom integration — routine-based anomaly detection for welfare monitoring
**Researched:** 2026-03-13
**Confidence:** HIGH (stack, architecture, pitfalls) / MEDIUM (feature thresholds, CUSUM parameter tuning)

## Executive Summary

The v1.1 rebuild replaces the existing z-score bucket analyzer and River ML engine with a two-engine routine-based detection system: acute inactivity detection (real-time, event-driven) and drift detection (gradual change, periodic CUSUM). Research confirms this is the correct direction — the existing 672-bucket approach suffered from fundamental sparsity problems that produced unstable statistics and unreliable detections. The replacement approach is well-documented in the IoT welfare monitoring literature, implementable in pure Python stdlib with no new dependencies, and architecturally cleaner than the 1,066-line monolithic coordinator it replaces.

The recommended approach builds a layered system with strict separation of concerns: a `RoutineModel` (pure Python, HA-free) learns per-entity baselines from historical data; `AcuteDetector` and `DriftDetector` (also HA-free) consume the baseline; a thin coordinator orchestrator wires these to HA's event bus and sensor layer. This layering is the critical architectural improvement over v1.0 — it makes every detection component unit-testable without mocking HA infrastructure. The entire detection stack runs on Python stdlib alone, eliminating HACS installation friction and the River dependency.

The primary risk is the transition itself, not the algorithm. Three migration hazards require explicit engineering: (1) cold start false negatives — the period after upgrade before any baseline is established when the system silently detects nothing; (2) storage migration failure — the v2 z-score storage format is incompatible with the new routine model and must be gracefully discarded, not deserialized; (3) sensor entity state contract changes — five ML-specific sensors must be deprecated in-place rather than removed, to preserve user automations. Each of these is a recoverable engineering task with a defined solution, not a research gap.

## Key Findings

### Recommended Stack

The entire detection rebuild uses Python stdlib only. `statistics.NormalDist` (Python 3.8+, present in all HA 2024.1.0+ environments) provides z-score computation for the routine model. `collections.deque(maxlen=N)` provides O(1) rolling windows without manual pruning. CUSUM drift detection is approximately 15 lines of pure arithmetic — no library required. The HA recorder integration (`homeassistant.components.recorder.history.get_significant_states`) is the stable interface for bootstrapping baseline history from existing HA state data on first startup.

**Core technologies:**
- `statistics.NormalDist` (stdlib): z-score for acute detection — zero install cost, `NormalDist.zscore()` available directly, Python 3.8+
- `collections.deque(maxlen=N)` (stdlib): rolling observation windows — O(1) append/eviction, ideal for 4-week history
- CUSUM algorithm (~15 lines, no imports): drift detection — streaming, O(1) per observation, no ruptures/numpy needed
- `homeassistant.components.recorder.history`: bootstrap from existing state history — stable HA internal API, eliminates cold-start learning period for existing installations
- `homeassistant.helpers.storage.Store`: persist learned routine models — already used in v1.0, same pattern carries forward
- `async_track_state_change_event` (HA internal): entity-scoped event subscription — replaces deprecated `EVENT_STATE_CHANGED` bus listener, required for HA 2025.5+ compatibility

**What NOT to use:** `ruptures` (requires numpy/scipy, batch-oriented not streaming), `numpy`/`scipy` (HA install conflicts, 60-200MB overhead), `river` (explicitly removed per project constraint), direct SQLAlchemy queries on HA DB (fragile across schema versions).

### Expected Features

Research confirms the feature set is well-scoped and backed by welfare monitoring literature. Alert fatigue is identified as the primary failure mode for smart home welfare monitoring systems — users disable integrations when acute alerts fire too often. The core design principle must be: every alert represents something genuinely unusual.

**Must have (v1.1 table stakes):**
- Routine model — per-entity rolling baseline (binary: event intervals; numeric: mean/std) — foundation for both detection engines
- Acute detection engine — sustained inactivity vs. learned typical interval; requires N consecutive coordinator cycles before firing, not single-point detection
- Drift detection engine — CUSUM on per-entity daily activity rates; minimum 5–7 day evidence window before alerting
- Rebuilt coordinator — re-implements all existing suppression logic (holiday, snooze, cooldown, welfare debounce)
- Binary + numeric entity support — event-count/interval model for binary; mean/std model for numeric
- Config flow extensions with migration — history window, inactivity multiplier, drift sensitivity; existing entries migrate gracefully
- Sensor data dict compatibility — all 14 entity IDs preserved; ML-specific sensors deprecated in-place, not removed
- Persistent routine model storage — survives HA restarts; users cannot wait 4 weeks to re-learn after a restart

**Should have (v1.x differentiators):**
- Day-of-week learned intervals — per-DOW variation prevents weekend/weekday false positives
- Drift alert context detail — "no kettle activity for 5 days (was daily)" rather than generic notification
- Confidence ramp-up during learning — suppress/weaken alerts during first half of learning window to prevent alert floods on fresh setup
- Routine Reset service call — lets users acknowledge drift alerts and update the baseline to current behavior

**Defer (v2+):**
- Daily digest notification — adds scheduling complexity, out of scope per PROJECT.md
- Per-entity sensitivity tuning UI — validate global sensitivity is sufficient first
- Seasonal/calendar awareness — high complexity, uncertain value for primary use case

### Architecture Approach

The new architecture decomposes the existing 1,066-line monolithic coordinator into five separate files with strict boundaries. Three files (`routine_model.py`, `acute_detector.py`, `drift_detector.py`) contain zero HA imports and are independently testable. A new `notification.py` extracts the ~400 lines of notification logic currently embedded in the coordinator. The rewritten `coordinator.py` becomes a thin orchestrator targeting under 350 lines. Detection operates on two timescales: acute checks happen inline with state change callbacks (O(1), synchronous); drift checks happen in the 60-second `_async_update_data` poll (O(history_days), async). This split prevents blocking HA's event loop.

**Major components:**
1. `RoutineModel` (`routine_model.py`) — learns per-entity baselines; provides `expected_gap_seconds()` and `daily_rate()` to detectors; pure Python; serializes to/from dict for persistence
2. `AcuteDetector` (`acute_detector.py`) — real-time inactivity gap check against routine baseline; fires per state change event; pure Python
3. `DriftDetector` (`drift_detector.py`) — per-entity CUSUM on daily activity rates; runs on 60s coordinator poll; pure Python
4. `NotificationManager` (`notification.py`) — cooldown, deduplication, severity gate, welfare debounce, message construction; extracted from coordinator
5. `BehaviourMonitorCoordinator` (`coordinator.py`) — HA lifecycle, event subscription, orchestration, persistence, sensor data dict assembly; delegates all domain logic above

**Build order enforced by dependencies:** `const.py` → `routine_model.py` → `acute_detector.py` + `drift_detector.py` (parallel) → `notification.py` → `coordinator.py` → `sensor.py` + `config_flow.py` (parallel).

### Critical Pitfalls

1. **Cold start silent false negatives** — after upgrade, the routine model has no baseline; acute detection fires nothing; users assume the system is working when it is not. Avoid by: surfacing an explicit "detection inactive" sensor state; sending a one-time startup notification; considering a fallback fixed-threshold mode during cold start. Silence must never be invisible.

2. **Config entry migration failure crashes startup** — the v2 storage format (`analyzer` key, 672-bucket z-score data) cannot deserialize into the new routine model. Avoid by: incrementing `STORAGE_VERSION` to 3; wrapping `Store.async_load()` in try/except; detecting old format by presence of `analyzer` key, logging a clear message, and starting fresh. Implement `async_migrate_entry` in `__init__.py` to clean up dead config keys (`CONF_ENABLE_ML`, `CONF_RETRAIN_PERIOD`, etc.).

3. **Sensor entity state contract break** — five ML-specific sensors (`ml_status`, `ml_training_remaining`, `cross_sensor_patterns`, and affected sensors) must not be removed; they must return defined stub states in v1.1 and only be removed in v1.2 with advance notice. `coordinator.data` must never be `None` on first refresh — all 14 sensors must return safe defaults.

4. **Drift fires on legitimate routine changes** — CUSUM cannot distinguish voluntary schedule changes from gradual decline. Avoid by: requiring minimum 5–7 day sustained evidence window; implementing a `reset_drift_baseline` service call; resetting drift accumulator when holiday mode is disabled (not just suppressing during it).

5. **Acute threshold not routine-relative** — using a fixed hour threshold instead of a multiplier of the learned typical quiet period produces false positives at night and false negatives during day windows. Avoid by: building the routine model before the acute detector; expressing the config option as a multiplier of the learned interval, not raw hours; testing with synthetic overnight quiet periods.

## Implications for Roadmap

Based on the dependency graph in FEATURES.md and the build order in ARCHITECTURE.md, research supports a five-phase structure ordered by strict dependency and risk.

### Phase 1: Foundation — Constants, Data Models, Storage Migration
**Rationale:** Everything depends on `const.py` being updated first. Storage migration must be designed before any code that loads storage is written — otherwise migration is an afterthought that gets patched in incorrectly. This phase produces no user-visible behavior change but makes all subsequent phases safe to build.
**Delivers:** Updated `const.py` with new config keys and ML constants removed; `async_migrate_entry` in `__init__.py` handling v2→v3 migration; storage fixture tests confirming old z-score format loads without crashing; orphaned ML storage cleanup.
**Addresses:** Config flow migration, storage compatibility.
**Avoids:** Pitfall 2 (config migration failure), Pitfall 6 (River dependency removal loose ends).

### Phase 2: Routine Model
**Rationale:** Both detection engines consume the routine model's output. This must be fully built and tested before either detector is implemented. Building it first forces the detection API (`expected_gap_seconds`, `daily_rate`) to be defined as an interface, not discovered during detector implementation.
**Delivers:** `routine_model.py` with `EntityRoutine` and `RoutineModel`; `to_dict`/`from_dict` persistence; history bootstrap from HA recorder; explicit cold start handling with "detection inactive" status; full unit tests with no HA mocks required.
**Uses:** `statistics.NormalDist`, `collections.deque`, `homeassistant.components.recorder.history`.
**Avoids:** Pitfall 1 (cold start false negatives), Pitfall 5 (fixed vs routine-relative threshold — forces the API to be routine-relative from the start).

### Phase 3: Detection Engines (Acute + Drift)
**Rationale:** Both engines depend on RoutineModel and can be built in parallel. Acute detection is the primary safety use case; drift is secondary but architecturally parallel. Both must be HA-free so they can be unit-tested independently before coordinator wiring.
**Delivers:** `acute_detector.py` (sustained inactivity gap check, N-cycle evidence requirement, no overnight false positives); `drift_detector.py` (CUSUM with 5–7 day minimum evidence window, drift reset mechanism, holiday mode integration); full unit tests including overnight quiet period scenarios.
**Uses:** CUSUM (~15 lines pure Python), routine model API, `statistics.NormalDist`.
**Avoids:** Pitfall 4 (drift on legitimate routine changes), Pitfall 5 (fixed threshold), performance trap (CUSUM gated to periodic poll, not per-event callback).

### Phase 4: Coordinator Rebuild + Notification Manager
**Rationale:** The coordinator is the HA integration layer that wires everything together. It cannot be built until the components it orchestrates exist. Notification extraction happens in the same phase because the coordinator and notification manager are coupled through `AcuteResult`/`DriftResult` types.
**Delivers:** Rewritten `coordinator.py` (under 350 lines; `async_track_state_change_event` subscription; `async_set_updated_data` for event-driven sensor push; holiday mode, snooze, welfare debounce preserved); `notification.py` with cooldown, deduplication, severity gate, and message construction extracted; STORAGE_VERSION 3 migration logic integrated.
**Avoids:** Anti-patterns from ARCHITECTURE.md (everything in coordinator, CUSUM in @callback, `async_request_refresh` on every event, deprecated `EVENT_STATE_CHANGED` subscription).

### Phase 5: Sensor Compatibility + Config Flow Extension
**Rationale:** Sensor layer and config flow both depend on the coordinator's data dict being stable. They cannot be updated until Phase 4 defines the exact output contract. These can be built in parallel with each other but must follow Phase 4.
**Delivers:** Updated `sensor.py` `value_fn` lambdas for new data dict keys; ML-specific sensors (`ml_status`, `ml_training_remaining`, `cross_sensor_patterns`) returning defined stub states rather than going unavailable; `config_flow.py` extended with history window, inactivity multiplier, and drift sensitivity options; `coordinator.data` never-None guarantee verified with tests.
**Addresses:** Sensor layer compatibility, config flow extensions.
**Avoids:** Pitfall 3 (sensor entity state contract break).

### Phase Ordering Rationale

- **Const and migration first** because every file imports const and migration is dangerous to add late — it becomes an afterthought bolted onto already-wired coordinator code.
- **Routine model before detection engines** because the model defines the API both engines consume; reversing this order means the API is discovered during implementation, not designed upfront.
- **Detection engines before coordinator** because HA-free components built first can be fully tested without mocking HA; the coordinator test then verifies orchestration rather than algorithm correctness.
- **Sensor and config flow last** because they depend on the coordinator data contract being frozen; changing the data dict after writing sensor lambdas requires double work.
- This order matches the bottom-up dependency graph in ARCHITECTURE.md exactly and enforces the "pure models before HA wiring" principle.

### Research Flags

Phases likely needing `/gsd:research-phase` during planning:
- **Phase 2 (Routine Model):** Recorder bootstrap API — `get_significant_states` is used by built-in integrations but the async job pattern (`async_add_executor_job`) may have changed in recent HA versions. Phase research should verify the current call signature against HA 2025.x.
- **Phase 3 (Drift Detection):** CUSUM parameter validation — k=0.5 and h=4.0 are documented at MEDIUM confidence (blog source + Wikipedia ARL tables). Phase research should validate these against simulated residential sensor data before implementation to confirm the ARL maps to ~168 days as expected. The minimum evidence window (5–7 days) also needs cross-referencing against typical event rates for the sensor types users have configured.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Constants + Migration):** `async_migrate_entry` is a standard HA hook with clear official documentation. Storage version bumping follows the established pattern in the existing codebase.
- **Phase 4 (Coordinator):** `DataUpdateCoordinator`, `async_track_state_change_event`, `async_set_updated_data`, and `_async_setup` are all documented in official HA developer docs at HIGH confidence and have confirmed stable APIs.
- **Phase 5 (Sensor + Config Flow):** Both follow established HA patterns already present in the codebase. No novel patterns required.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Core decisions (stdlib-only, CUSUM formula, recorder bootstrap) verified against official Python docs, HA developer docs, and the existing codebase. Only gap: CUSUM parameter tuning (k, h values) is MEDIUM confidence. |
| Features | MEDIUM | Must-have features and anti-features supported by peer-reviewed IoT welfare monitoring literature (2024–2025). Specific numerical thresholds (multipliers, evidence windows) are literature estimates, not validated against this codebase's sensor population. |
| Architecture | HIGH | Full codebase read confirms current pain points and validates decomposition approach. HA API patterns verified against official developer docs. Build order derived from actual code dependencies with no speculation. |
| Pitfalls | HIGH | Critical pitfalls identified from direct codebase inspection (cold start gap, migration failure path, sensor contract). Prevention strategies from HA community patterns and developer docs. CUSUM tuning pitfall is less certain. |

**Overall confidence:** HIGH for architecture and technology decisions; MEDIUM for numerical thresholds (CUSUM parameters, minimum evidence windows, inactivity multipliers). The "what to build" question is answered with high confidence; the "how to tune it" question requires validation during Phase 3 planning.

### Gaps to Address

- **CUSUM parameter validation (k=0.5, h=4.0):** Literature values confirmed at MEDIUM confidence only. Phase 3 planning should include simulation against representative residential sensor data to validate ARL before implementation. If ARL differs materially from ~168 days, the default h value needs adjustment.
- **Minimum evidence window for drift (5–7 days):** Derived from IoT welfare monitoring literature but not validated against actual event rates from the existing integration's sensor population. Phase 3 planning should cross-reference with typical daily event counts from the `daily_count` sensor data that existing users have.
- **Cold start fallback threshold:** Research recommends a "bootstrap mode" fixed threshold during cold start but does not specify a value. This should be a configurable constant (e.g., 8 hours for no motion) with a documented rationale, not a magic number. Phase 2 planning should decide whether to include this or surface a clear "detection inactive" warning instead.
- **Sensor deprecation message text:** Research recommends deprecated ML sensors return a fixed state like `"Removed in v1.1"` but the exact value may affect users with automations that check sensor state. Phase 5 planning should decide on the exact stub state and document it in the release notes.
- **Recorder bootstrap API currency:** `get_significant_states` is used by built-in integrations as a stable interface, but the exact async call pattern should be verified against the current HA version (2025.x) before Phase 2 implementation.

## Sources

### Primary (HIGH confidence)
- Existing codebase (`coordinator.py`, `analyzer.py`, `ml_analyzer.py`, `sensor.py`, `const.py`, `__init__.py`) — direct inspection; build order, data contracts, migration requirements, and anti-patterns all derived from reading actual code
- [Python docs: statistics.NormalDist](https://docs.python.org/3/library/statistics.html) — zscore() method confirmed, Python 3.8+
- [HA Developer Docs: Integration manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/) — requirements array, no-duplicate-core-requirements constraint
- [HA 2024.8 _async_setup announcement](https://developers.home-assistant.io/blog/2024/08/05/coordinator_async_setup/) — lifecycle method confirmed, called automatically by async_config_entry_first_refresh
- [async_track_state_change_event migration](https://developers.home-assistant.io/blog/2024/04/13/deprecate_async_track_state_change/) — deprecation and removal (HA 2025.5) confirmed
- [CUSUM — Wikipedia](https://en.wikipedia.org/wiki/CUSUM) — algorithm definition and ARL tables
- [GitHub: deepcharles/ruptures](https://github.com/deepcharles/ruptures) — scipy>=0.19.1 dependency confirmed (rules out use in HA custom integration)
- [Algorithm to Detect Abnormally Long Inactivity in a Home (ResearchGate)](https://www.researchgate.net/publication/221234469_Algorithm_to_automatically_detect_abnormally_long_periods_of_inactivity_in_a_home) — foundational inactivity detection method, HIGH confidence

### Secondary (MEDIUM confidence)
- [Anomaly Detection Technologies for Dementia Care — Sage Journals, 2025](https://journals.sagepub.com/doi/10.1177/07334648251357031) — sustained evidence requirement, alert fatigue as primary failure mode
- [IoT Edge Intelligence Framework for Elderly Monitoring — PMC 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC11944996/) — per-individual learned intervals outperform fixed thresholds
- [Smart Home Anomaly Detection for Older Adults — PMC 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12106144/) — drift detection patterns for welfare monitoring
- [The CUSUM Algorithm — Stackademic](https://blog.stackademic.com/the-cusum-algorithm-all-the-essential-information-you-need-with-python-examples-f6a5651bf2e5) — CUSUM formula and parameters (k=0.5, h=4.0) with Python examples
- [Behavior drift detection in home automation — MDPI](https://www.mdpi.com/2227-7080/6/1/16) — p-value thresholds for fragile populations, concept drift model confidence failure mode
- [Config entry minor versions blog post](https://developers.home-assistant.io/blog/2023/12/18/config-entry-minor-version/) — major vs minor version semantics for HA config entries
- [Inactivity Patterns and Alarm Generation in Senior Citizens' Houses (ResearchGate)](https://www.researchgate.net/publication/281804588_Inactivity_patterns_and_alarm_generation_in_senior_citizens'_houses) — alarm cadence expectations and evidence window guidance
- [HA community — unavailable states breaking automations](https://community.home-assistant.io/t/wth-is-unavailable-breaking-everything/474217) — state transition side effects on automation triggers

---
*Research completed: 2026-03-13*
*Ready for roadmap: yes*
