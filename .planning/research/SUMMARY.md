# Project Research Summary

**Project:** Behaviour Monitor v3.1 — Activity-Rate Classification
**Domain:** Home Assistant custom integration — anomaly detection for heterogeneous IoT sensors
**Researched:** 2026-03-28
**Confidence:** HIGH

## Executive Summary

Behaviour Monitor v3.1 solves a specific, well-understood false-positive problem: the existing `AcuteDetector.check_inactivity()` applies a uniform threshold multiplier to all entities regardless of their natural event frequency. A motion sensor firing every 2 minutes and a lock toggling twice a day both pass through the same multiplier arithmetic. The root cause is mathematical — a short median gap multiplied by even a large multiplier still produces a dangerously short alert threshold. The fix requires classifying entities into frequency tiers and applying tier-specific detection parameters, primarily an absolute minimum floor for high-frequency entities.

The recommended approach is entirely internal: no new dependencies, no new sensor entities, no new storage files. Classification is computed from existing `ActivitySlot.event_times` deques already persisted per entity, making tier derivation a ~30-line addition to `routine_model.py`. The tier is then passed at call-time to `AcuteDetector.check_inactivity()`, keeping the detector stateless with respect to tiers. An optional config UI step allows user overrides, but auto-classification alone solves the primary problem and is sufficient for MVP.

The key risks are behavioral, not technical. Tier boundary oscillation (entities near the boundary flapping between tiers daily) and premature classification (too little data) can both produce worse behavior than the current untiered system. These are prevented by gating classification on the existing `learning_status` confidence flag and reclassifying at most once per day. The display formatting fix (minutes instead of hours for sub-hour intervals) carries a secondary risk of breaking user automations that parse the `explanation` string — mitigated by adding structured fields to `AlertResult.details` rather than changing the string format.

---

## Key Findings

### Recommended Stack

No new dependencies. All v3.1 features are implementable with Python stdlib (`statistics`, `collections.deque`, `enum`) on data already stored in `EntityRoutine.slots[*].event_times`. The existing HA selector framework (`SelectSelector`) handles the config UI widget, following the identical pattern used for `CONF_DRIFT_SENSITIVITY`. Config migration follows the established `setdefault` pattern (v7 to v8). Storage schema is unchanged for the classification result — tier is computed at runtime from existing persisted data, consistent with the v3.0 decision to compute CV at query time.

**Core technologies:**
- `Python stdlib statistics.median`: classification metric — median daily event rate, robust to outlier days
- `Python stdlib collections.deque`: source data — `event_times` deques in `ActivitySlot` (168 slots, up to 56 timestamps each)
- `homeassistant.helpers.selector.SelectSelector`: config UI dropdown for tier override — identical to existing drift_sensitivity selector
- `voluptuous`: config flow schema for new tier override field — already used throughout

**New internal components (zero external dependencies):**
- `ActivityTier` enum (`HIGH`/`MEDIUM`/`LOW`) in `const.py`
- `EntityRoutine.classify_tier()` method in `routine_model.py`
- `_format_duration()` shared utility in `routine_model.py`
- Tier-aware threshold branch in `AcuteDetector.check_inactivity()`
- Config migration v7 to v8 in `__init__.py`

### Expected Features

**Must have (table stakes):**
- Auto-classify entities into HIGH/MEDIUM/LOW frequency tiers — foundational; without this, all other tier work is blocked
- Tier-appropriate inactivity detection with absolute minimum floor — the actual false-positive fix; a minimum floor prevents sub-minute alert thresholds on chatty sensors
- Fix alert display formatting (minutes instead of hours for sub-hour intervals) — low effort, high visibility; current `"0.0h"` output is unprofessional
- Config migration v7 to v8 — non-negotiable; required for every prior milestone

**Should have (differentiators):**
- Activity tier exposed as sensor attribute on `entity_status_summary` — near-free, critical for user trust and debugging; users cannot understand changed alert behavior without visibility into tier assignment
- Shared `format_duration()` utility replacing duplicated inline formatters — prevents future drift between `acute_detector.py` and `coordinator.py` formatting
- User tier override in config UI — escape hatch for misclassified entities; auto-classify solves 90%+ of cases but some edge cases need manual correction

**Defer (v2+):**
- Per-entity tier override (as opposed to global override) — explicitly out of scope per PROJECT.md; complex UI for uncertain benefit
- Configurable tier boundary thresholds — premature; ship fixed defaults, add only if user feedback indicates defaults are wrong
- Tier-specific sustained evidence cycles — belt-and-suspenders; absolute floor likely sufficient alone
- ML-based classification — violates hard no-external-dependencies constraint; threshold-based is fully sufficient and interpretable

### Architecture Approach

The architecture follows a single design principle: classify at the data layer (`EntityRoutine`), consume everywhere. Tier is a property of an entity's learned routine, not a property of the detector. The `classify_tier()` method lives on `EntityRoutine` in `routine_model.py`, keeping all HA-free pure Python logic together and fully unit-testable without HA mocking. The coordinator calls `reclassify_tier()` at most once per day and applies user overrides from config entry data. `AcuteDetector.check_inactivity()` receives tier at call time (not stored on the detector), keeping the detector stateless. No new files are needed — all changes touch existing modules.

**Major components and changes:**
1. `const.py` — `ActivityTier` enum, tier boundary constants, floor/boost lookup dicts, new config key (~25 lines)
2. `routine_model.py` — `classify_tier()`, `activity_tier` property, `reclassify_tier()`, `_format_duration()` utility, `to_dict`/`from_dict` update (~58 lines)
3. `acute_detector.py` — tier-aware threshold (boost + floor), display formatting fix (~14 lines)
4. `coordinator.py` — tier override injection, daily reclassification, tier in sensor data, formatting fix (~34 lines)
5. `config_flow.py` + `__init__.py` — tier override UI step, config migration v7 to v8 (~50 lines)

**Total estimated: ~195 lines of new/modified code** across 6 files with no new files.

### Critical Pitfalls

1. **Tier boundary oscillation** — An entity near a boundary flips between tiers as the sliding observation window shifts day by day. Each reclassification potentially resets the `_inactivity_cycles` sustained-evidence counter, producing transient false positives. Mitigation: reclassify at most once per day using full `history_window_days` median (not a recent snapshot); consider hysteresis bands in future iterations if oscillation is observed.

2. **Premature classification on insufficient data** — Classification with only hours of data (new entity, fresh install) produces wrong tier assignments that persist. Mitigation: gate classification on `learning_status == "ready"` (equivalent to `routine.confidence() >= 0.5`). Return `None` and use conservative defaults below this threshold. The existing `MIN_EVIDENCE_DAYS` used by `DriftDetector` is the right model.

3. **Config migration drops user-tuned multiplier as baseline** — Unlike previous `setdefault`-only migrations, v7 to v8 introduces parameters whose meaning depends on the user's existing `inactivity_multiplier`. Injecting default tier factors without referencing the user's current value effectively resets carefully tuned sensitivity. Mitigation: migration must read existing `inactivity_multiplier` and use it as the base for tier floor/boost calculations, not raw defaults.

4. **Display formatting breaks automations parsing explanation string** — Changing `"0.0h"` to `"45m"` in `AlertResult.explanation` silently breaks any user automations with regex on that string. Mitigation: add `elapsed_formatted` and `typical_formatted` to `AlertResult.details` dict rather than changing the `explanation` string format. The `details` dict already contains `elapsed_seconds` and `expected_gap_seconds` as structured data.

5. **Absolute floor set as a global constant ignores entity rate** — A single floor value that prevents false positives for a 30-second-interval sensor will mask genuine inactivity for a 2-minute-interval sensor. Mitigation: floor should be `max(ABSOLUTE_MINIMUM, observed_median_interval * floor_factor)` rather than a pure constant. The `expected_gap_seconds()` method already computes the per-slot median interval.

---

## Implications for Roadmap

Based on research, the dependency graph is clear: classification must exist before tier-aware detection can branch on it, and detection changes are the primary deliverable. Display formatting is fully independent.

### Phase 1: Constants and Utilities

**Rationale:** Foundation layer with zero dependencies. Everything else imports from here. Independently testable with import verification only.
**Delivers:** `ActivityTier` enum, tier boundary constants, floor/boost lookup dicts, `CONF_ACTIVITY_TIER_OVERRIDES` key, `_format_duration()` utility in `routine_model.py`
**Addresses:** Display formatting precondition; all tier constants required by downstream phases
**Avoids:** Pitfall 9 (time formatting edge cases) — single utility defined once with explicit rules

### Phase 2: Tier Classification on EntityRoutine

**Rationale:** Classification is the data-layer foundation. `AcuteDetector` and coordinator both depend on `routine.activity_tier`. Must ship before detection changes.
**Delivers:** `classify_tier()`, `activity_tier` property, `reclassify_tier()`, `to_dict`/`from_dict` update on `EntityRoutine`
**Addresses:** Table-stakes auto-classification; produces the tier data that sensor attribute exposure requires
**Avoids:** Pitfall 1 (oscillation) — classify once per day, use full-window median; Pitfall 2 (premature classification) — gate on `learning_status`; Pitfall 12 (wrong rate computation) — aggregate across full deque, divide by distinct days observed

### Phase 3: Tier-Aware Detection and Display Formatting

**Rationale:** Primary deliverable of the milestone. Depends on Phase 2 for tier data. Display formatting fix is independent but logically belongs here since both touch `acute_detector.py`.
**Delivers:** Tier-aware threshold (multiplier boost + absolute floor) in `check_inactivity()`; human-readable duration formatting in alert explanations; structured `elapsed_formatted` / `typical_formatted` in `AlertResult.details`
**Addresses:** Table-stakes tier-appropriate detection; display formatting fix
**Avoids:** Pitfall 4 (automation breakage) — add structured fields, keep explanation string format; Pitfall 5 (config explosion) — internal factors only, not per-tier UI fields; Pitfall 6 (wrong floor) — derive floor from observed median gap

### Phase 4: Coordinator Integration

**Rationale:** Wires classification and detection together. Depends on Phases 2 and 3. The coordinator is the integration point where overrides are applied and reclassification is scheduled.
**Delivers:** Tier override injection from config, daily reclassification call, tier in `entity_status` sensor data, display formatting fix in `_build_sensor_data`
**Addresses:** Activity tier as sensor attribute (data surfaced here); user override persistence
**Avoids:** Pitfall 7 (override not persisted) — store in `entry.data`, check before auto-classification; Pitfall 8 (reload path) — pass tier to `check_inactivity()` at call time, not stored on detector

### Phase 5: Config UI and Migration

**Rationale:** Migration is required for any new config keys. Config UI is the phase most safely deferred — auto-classification alone (Phases 1-4) solves the primary false-positive problem.
**Delivers:** Config migration v7 to v8; optional tier override step in options flow; translations
**Addresses:** Table-stakes config migration; user override escape hatch
**Avoids:** Pitfall 3 (migration drops user values) — read existing `inactivity_multiplier` as baseline; Pitfall 10 (storage version missed) — bump `STORAGE_VERSION` and `ConfigFlow.VERSION` together; Pitfall 11 (stale overrides) — prune overrides for removed entities on save

### Phase Ordering Rationale

- Phases 1 and 2 are strict prerequisites for Phase 3 — the detector cannot branch on tier without the enum and classification existing.
- Phase 4 depends on Phases 2 and 3 but is otherwise independent of Phase 5 — coordinator integration does not require the config UI to exist (overrides default to auto-detect when the key is absent).
- Phase 5 (config UI) is the only deferrable phase. If MVP scope is tight, ship Phases 1-4 and add the override UI as a follow-up. The migration should only be included if new config keys are actually added.
- Display formatting fix (part of Phase 3) could be extracted to ship independently before Phase 2 if a quick win is desired, since it touches only string formatting with no data dependencies.

### Research Flags

Phases with well-documented patterns (skip deeper research):
- **Phase 1 (Constants):** Pure constants and a string utility. No research needed.
- **Phase 3 (Detection):** Threshold arithmetic is well-understood from existing code. Branch logic is a straightforward conditional addition.
- **Phase 5 (Migration):** Established `setdefault` migration pattern used five times previously. No research needed for the migration itself.

Phases that may benefit from validation during planning:
- **Phase 2 (Classification):** Tier boundaries are inconsistent across the three research files (see Gaps below) and need reconciliation before implementation. The minimum data requirement (3 days vs 7 days) should be validated against the existing `MIN_EVIDENCE_DAYS` constant used by `DriftDetector`.
- **Phase 4 (Coordinator):** The daily reclassification hook location needs confirmation against actual coordinator update cycle behavior — specifically whether the existing `_today_date` check is the right place to inject reclassification.
- **Phase 5 (Config UI):** The `async_show_menu` multi-step options flow pattern should be confirmed against current HA version before implementing the per-step approach. The simpler global `SelectSelector` override is safe and sufficient for v3.1.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | No new dependencies; all patterns verified against existing codebase. Full codebase read across all 9 source files. |
| Features | HIGH | Table stakes derived from direct arithmetic proof of the detection failure; must-have status is unambiguous |
| Architecture | HIGH | Full read of all 9 source files; integration points identified at line level; no speculation |
| Pitfalls | HIGH | All pitfalls derived from actual code structure — migration chain, detection loop, alert string format, coordinator reload path |

**Overall confidence:** HIGH

### Gaps to Address

- **Tier boundary values are inconsistent between research files:** STACK.md uses events/hour (>6 = HIGH, <0.5 = LOW) while FEATURES.md uses events/day (>50 = HIGH, <5 = LOW) and ARCHITECTURE.md uses events/day (>24 = HIGH, <4 = LOW). These are the same concept expressed as three different threshold sets. Reconcile before Phase 2 implementation by choosing one unit (events/day is more intuitive for users) and one set of boundary values. Validate against a representative sample of real HA entity logs before committing.

- **Absolute floor value needs reconciliation:** STACK.md proposes 300 seconds (5 minutes) as the HIGH-tier floor; ARCHITECTURE.md proposes 3600 seconds (1 hour). These differ by 12x. The 1-hour floor is more conservative and safer for initial deployment; the 5-minute floor is more aggressive. Resolve during Phase 3 planning — recommend starting with the 1-hour floor and tuning down based on user feedback.

- **Minimum data requirement not established:** Research proposes 3 days (ARCHITECTURE.md) as the minimum for classification. Confirm alignment with the existing `MIN_EVIDENCE_DAYS` constant used by `DriftDetector` before Phase 2 implementation to ensure consistent learning-period semantics across the system.

- **Per-entity vs global override scope conflict:** STACK.md recommends a global override (single dropdown for all entities in the entry), while ARCHITECTURE.md designs a per-entity override (dict mapping entity_id to tier). Per PROJECT.md constraints, per-entity tuning is out of scope for v3.1. Resolve by implementing global override only; per-entity is a future milestone.

---

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis — `routine_model.py` (458 lines), `acute_detector.py` (215 lines), `coordinator.py` (377 lines), `config_flow.py` (406 lines), `sensor.py` (252 lines), `const.py` (156 lines), `alert_result.py` (66 lines), `drift_detector.py` (389 lines), `__init__.py` (267 lines)
- PROJECT.md — milestone constraints (no new dependencies, per-entity sensitivity tuning out of scope)
- Existing migration chain v2-v7 in `__init__.py` — established `setdefault` pattern

### Secondary (MEDIUM confidence)
- [HA Community: Debouncing binary sensors](https://community.home-assistant.io/t/debouncing-binary-sensory/111833) — community patterns for high-frequency sensor handling
- [HA Community: Filtering motion detection](https://community.home-assistant.io/t/filtering-motion-detected/590359) — real-world false positive patterns
- [Home Assistant Statistics integration](https://www.home-assistant.io/integrations/statistics/) — HA's approach to sensor data frequency handling

### Tertiary (LOW confidence)
- [Effective Anomaly Detection by Integrating Event Time Intervals](https://www.sciencedirect.com/science/article/pii/S1877050922015757) — time-interval-based anomaly detection with frequency awareness; confirms tiered approach is established practice
- [IoT anomaly detection methods survey](https://www.sciencedirect.com/science/article/pii/S2542660522000622) — adaptive threshold approaches for heterogeneous sensor types
- [Activity and Anomaly Detection in Smart Home survey](https://link.springer.com/chapter/10.1007/978-3-319-21671-3_9) — frequency-based activity classification patterns

---

*Research completed: 2026-03-28*
*Ready for roadmap: yes*
