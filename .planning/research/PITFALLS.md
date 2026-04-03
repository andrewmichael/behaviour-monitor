# Domain Pitfalls

**Domain:** Cross-entity correlation and startup tier rehydration added to existing per-entity anomaly detection
**Researched:** 2026-04-03

## Critical Pitfalls

Mistakes that cause rewrites, false positive floods, or broken existing detection.

### Pitfall 1: Combinatorial Pair Explosion

**What goes wrong:** Naively tracking all entity pairs creates O(N^2) correlation slots. With 20 monitored entities, that is 190 pairs. With 50, it is 1,225. Each pair needs its own co-occurrence window, state tracking, and persistence. The coordinator update cycle (currently 60s) becomes CPU-bound iterating pairs, and storage balloons.

**Why it happens:** The natural mental model is "compare every entity to every other entity," but correlation discovery must be selective, not exhaustive.

**Consequences:** Update cycle latency exceeds the 60s interval. Storage JSON grows from kilobytes to megabytes. HA event loop blocks during `_save_data()`. Users with many entities see UI lag.

**Prevention:**
- Gate correlation discovery behind a minimum co-occurrence count (e.g., 5+ co-occurrences within the time window before a pair is promoted to a tracked candidate). This is the "candidate promotion" pattern.
- Limit tracked correlation groups to a configurable maximum (e.g., 20 groups). Drop lowest-confidence groups first.
- Use an event-driven approach: only evaluate correlation when an entity fires, checking it against recent events in a bounded time-window buffer, not by iterating all pairs every cycle.
- Track groups (sets of entities), not pairs. If A, B, and C all co-occur, that is one group, not three pairs.

**Detection:** Monitor `_async_update_data` wall-clock time. If it exceeds 5s with correlation enabled, the pair count is too high.

**Phase guidance:** Address in the correlation discovery phase. The data structure design must enforce bounded pair counts from day one.

---

### Pitfall 2: Correlation Alerts During Learning Period

**What goes wrong:** The correlation detector starts generating "broken correlation" alerts before it has enough evidence that entities actually correlate. A pair that co-occurred 2 out of 3 days fires a divergence alert on day 4 when one entity is simply quiet.

**Why it happens:** The existing per-entity detectors have confidence gates (0.8 for tier classification, 0.3 for unusual-time). A new correlation detector without equivalent gates produces noise immediately.

**Consequences:** Users see false alerts about "broken routines" that never existed. Trust in the entire alert system erodes. This is especially damaging because cross-entity alerts are inherently harder for users to evaluate ("is it really unusual that the kitchen and hallway didn't fire together?").

**Prevention:**
- Require a minimum observation window before any correlation is considered "learned" (e.g., 14 days of co-occurrence data, or N co-occurrences where N >= 10).
- Apply a confidence threshold to correlation strength before divergence alerts fire. A pair must co-occur in >= 70% of observation windows before absence is flagged.
- Reuse the existing `SUSTAINED_EVIDENCE_CYCLES` pattern: require 3+ consecutive update cycles where the expected companion is missing before alerting.
- Gate on the routine model's `learning_status == "ready"` for both entities in the pair.

**Detection:** Track correlation_confidence per group and log when alerts are suppressed by the confidence gate. If suppressed alerts >> fired alerts during the first month, the gate is working.

**Phase guidance:** Must be implemented in the same phase as correlation detection, not deferred. Gating is not a polish feature; it is a correctness feature.

---

### Pitfall 3: Corrupting Existing Detection by Modifying the Update Cycle

**What goes wrong:** Adding correlation logic inside `_run_detection()` or `_handle_state_changed()` introduces subtle side effects. For example, recording a correlation timestamp in `_handle_state_changed` changes the timing of `async_request_refresh()`, or adding correlation alerts to the `alerts` list changes welfare status derivation and alert suppression keys.

**Why it happens:** The coordinator is tightly wired: `_handle_state_changed` -> `async_request_refresh` -> `_async_update_data` -> `_run_detection` -> `_handle_alerts` -> `_derive_welfare`. Inserting correlation into this pipeline requires understanding the full chain. The `_handle_alerts` method uses `f"{a.entity_id}|{a.alert_type.value}"` as suppression keys (line 216, 248 of coordinator.py). A new AlertType will create new keys, but if welfare derivation counts correlation alerts toward severity escalation, the welfare status becomes noisier.

**Consequences:** 449 existing tests pass, but production behavior changes. Alert suppression keys collide if the new AlertType is not carefully namespaced. Welfare status derivation sees correlation alerts and escalates unnecessarily. Notification deduplication breaks.

**Prevention:**
- Add a new `AlertType.CORRELATION_DIVERGENCE` to the enum, ensuring suppression keys are distinct from existing `INACTIVITY`, `UNUSUAL_TIME`, and `DRIFT` types.
- Run correlation detection as a separate method called from `_run_detection`, appending results to the same `alerts` list but after existing detectors (lines 202-211 of coordinator.py). This preserves existing detector ordering.
- Ensure correlation alerts default to LOW severity. A broken correlation should not escalate welfare to "alert" unless combined with per-entity evidence. Consider excluding correlation alerts from `_derive_welfare` entirely, or weighting them lower.
- Do NOT modify `_handle_state_changed`. Instead, maintain a separate recent-events buffer that `_handle_state_changed` feeds into, and let `_run_detection` query it.
- Write integration tests that run the full coordinator cycle with correlation enabled and verify that existing per-entity alerts are unchanged.

**Detection:** Before merging, run the full 449-test suite with correlation enabled in the coordinator config. Any failure is a regression signal.

**Phase guidance:** The AlertType addition and suppression key namespace should be in a foundation phase before the detector itself. Alert integration (welfare weight) is a separate concern from detection.

---

### Pitfall 4: Storage Schema Migration Breaks Existing Installs

**What goes wrong:** Adding correlation state to the persisted JSON (currently `routine_model` + `cusum_states` + `coordinator` dict in `_save_data` at line 147 of coordinator.py) without a migration path causes `async_setup` to crash on existing installs that lack the new keys.

**Why it happens:** The current `_save_data` / `async_setup` uses `stored.get("key", {})` for top-level keys (lines 121-134 of coordinator.py) but relies on the keys existing in the stored JSON. The `STORAGE_VERSION` is 8 (in const.py line 59), used in the `Store` constructor. If the stored data structure changes shape and the Store version is not bumped, `async_load` returns old-format data silently.

**Consequences:** HA restart after upgrade fails to load the integration. Users see "Integration failed to set up" in the UI. They must delete `.storage/behaviour_monitor.{entry_id}.json` and lose all learned patterns (routine model, CUSUM state, alert suppression history).

**Prevention:**
- Use `.get()` with safe defaults for ALL new top-level keys in `async_setup` when loading stored data. The existing code already does this well for `cusum_states` (line 123). Follow the identical pattern for correlation state.
- Store correlation state under a single new top-level key (e.g., `"correlation_state"`) so there is exactly one new key to `.get()` safely.
- Bump `STORAGE_VERSION` to 9 and implement a data migration in `async_setup` that handles the v8-to-v9 transition.
- Add a test that loads a v8-format stored dict (without correlation keys) and verifies `async_setup` completes without error and initializes empty correlation state.

**Detection:** Test with a storage fixture that matches the current v8 format. If `async_setup` raises, migration is broken.

**Phase guidance:** Storage persistence phase. Must be addressed when correlation state is first persisted, not after.

---

### Pitfall 5: Startup Tier Rehydration Gap

**What goes wrong:** After HA restart, `EntityRoutine._activity_tier` is `None` for all entities because the field is explicitly not serialized (routine_model.py line 244-249: "not serialized -- recomputed on startup"). The first `_async_update_data` call (lines 182-190 of coordinator.py) classifies tiers via `classify_tier(now)` on date rollover. However, this classification is gated on two conditions:
1. `self._today_date != now.date()` -- True on first run because `_today_date` is None. This works.
2. Inside `classify_tier()`: `self.confidence(now) >= 0.8` -- This may fail for recently-added entities.

The real gap: between `async_setup()` completing (line 138 of coordinator.py) and the first `_async_update_data()` execution (triggered by `async_config_entry_first_refresh` at line 173 of __init__.py), the `AcuteDetector` can run with `routine.activity_tier == None`. The tier-aware boost/floor in `check_inactivity` (acute_detector.py lines 98-102) is skipped when tier is None, meaning high-frequency entities lose their protective floor for one cycle.

**Why it happens:** Tier classification was designed to run daily in the coordinator update loop. It was not designed to run at load time. The "recomputed on startup" comment implies it happens automatically, but there is a timing gap.

**Consequences:** High-frequency entities (PIR sensors, power monitors) may fire a spurious inactivity alert on the first update cycle after restart because the 1-hour floor (TIER_FLOOR_SECONDS[HIGH] = 3600) is not applied. For correlation, entities without tier classification may be grouped inconsistently.

**Prevention:**
- Call `classify_tier(now)` for all entities inside `async_setup()`, after loading stored data and before the first coordinator refresh. Insert at line 137 (after `_handle_state_changed` listener but before returning).
- Apply tier overrides from config in the same block (same pattern as lines 187-190 of coordinator.py).
- Add a test: load stored data for entities with sufficient history, verify `_activity_tier` is not None before `_async_update_data` runs.

**Detection:** Log tier classification results at startup. If tiers are None for entities with weeks of history, rehydration is broken.

**Phase guidance:** This is a standalone bug fix that should be an early phase, before correlation work begins. It affects the existing v3.1 system independently.

## Moderate Pitfalls

### Pitfall 6: Time Window Alignment Creates Phantom Correlations

**What goes wrong:** The co-occurrence time window (e.g., "entities that fire within 10 minutes of each other") is either too tight or too loose. Too tight: real correlations are missed (kitchen motion and hallway motion are 12 minutes apart due to HA polling latency or human movement speed). Too loose: everything correlates with everything because a 30-minute window captures unrelated events in an active household.

**Prevention:**
- Make the window configurable with a sensible default (5 minutes is a good starting point for home automation entity co-occurrence).
- Use asymmetric windows: if A fires, check for B in [A-window, A+window]. Do not require exact simultaneity.
- Consider time-of-day bucketed correlation (same hour-of-day x day-of-week slot) as a complementary approach. Two entities that both have activity in the same routine slot are "slot-correlated" even if their exact timestamps differ by 20 minutes. This is coarser but robust to polling delays and HA restart gaps.

**Phase guidance:** Correlation discovery phase. The window size should be a constant in `const.py` first, with a config UI option added in a later phase only if needed.

---

### Pitfall 7: Correlation State Not Cleaned Up When Entities Are Removed

**What goes wrong:** User removes an entity from `monitored_entities` via the config UI (triggering `async_reload_entry`). Per-entity state (routine model, CUSUM) is naturally orphaned but harmless -- it sits in storage doing nothing. Correlation state referencing the removed entity continues to track groups containing it. The system produces "broken correlation" alerts for a group that no longer makes sense, or worse, tries to check `_routine_model._entities[removed_id]` and gets a KeyError.

**Prevention:**
- On config reload (`async_reload_entry` at line 274 of __init__.py), prune correlation groups that reference entities no longer in `_monitored_entities`.
- When an entity is removed, dissolve any group that contained it and re-evaluate the remaining members. Two remaining entities from a 3-entity group may not correlate without the third.
- Guard all correlation detection lookups with `if eid in self._monitored_entities` (same pattern as `_run_detection` line 205-206 of coordinator.py).
- Add a test: configure 3 entities in a correlation group, remove one via config flow, verify the group is dissolved or reformed without the removed entity.

**Phase guidance:** Correlation lifecycle management phase, after basic correlation works.

---

### Pitfall 8: Correlation Alerts Flood the Notification Pipeline

**What goes wrong:** If 5 entities form a correlated group and one entity goes quiet, the system could generate 4 "expected companion missing" alerts (one for each remaining entity noticing the absence). The notification pipeline sends 4 alerts in one cycle via `_send_notification` (line 252 of coordinator.py), overwhelming the user with redundant information about the same underlying event.

**Prevention:**
- Alert at the GROUP level, not the pair level. "Correlation group [kitchen, hallway, living room]: kitchen_motion not seen alongside expected companions" is one alert, not three.
- Use the existing `_alert_suppression` mechanism with a group-level key (e.g., `"correlation_group:kitchen_cluster|correlation_divergence"`).
- Cap correlation alerts per update cycle (e.g., max 2 correlation alerts per cycle, highest confidence first).
- The existing deduplication in `_handle_alerts` (lines 214-249) uses per-entity suppression keys. Group-level keys need to coexist without interfering.

**Detection:** If correlation alert count regularly exceeds per-entity alert count by 3x+, the grouping or deduplication is wrong.

**Phase guidance:** Alert integration phase. Must be designed alongside the correlation detector, not bolted on after.

---

### Pitfall 9: Async Event Buffer Grows Unbounded

**What goes wrong:** The correlation detector needs a recent-events buffer (timestamps of recent state changes per entity) to check for co-occurrences. If this buffer is not bounded, it grows with every state change and is never pruned. High-frequency entities (24+ events/day = HIGH tier) can generate hundreds of entries per day. Over weeks, the buffer holds thousands of timestamps consuming memory unnecessarily.

**Prevention:**
- Use a bounded deque per entity (matching the existing `event_times` deque pattern with `maxlen=56` in routine_model.py line 89). For correlation, a shorter window suffices: keep only events from the last 30 minutes (or 2x the correlation window).
- Prune by timestamp, not by count: on each `_handle_state_changed` call, append the new event and lazily discard entries older than the correlation window on next read.
- Do NOT persist this buffer to storage. It is ephemeral -- correlation detection only needs recent events. On restart, the buffer starts empty and refills naturally.

**Phase guidance:** Correlation data structure design phase (same as Pitfall 1).

---

### Pitfall 10: Correlation Discovery Runs Every Update Cycle

**What goes wrong:** Correlation group discovery (which entities correlate?) is expensive: it must scan co-occurrence history across all entity pairs, compute co-occurrence rates, and form/update groups. Running this every 60 seconds (in every `_run_detection` call) wastes CPU when correlations change slowly over days or weeks.

**Prevention:**
- Separate discovery from detection. Discovery runs once per day (like tier classification at lines 184-190 of coordinator.py). Detection runs every cycle but only checks already-discovered groups.
- Use the same `_today_date` guard pattern: `if self._today_date != now.date(): ... run_correlation_discovery()`.
- Discovery writes to a `_correlation_groups` list. Detection reads from it. This mirrors the tier pattern (`_activity_tier` computed daily, used every cycle by `AcuteDetector`).
- If an entity fires and it is in a known correlation group, check the group. If it is not in any group, skip it. This makes per-cycle detection O(groups) not O(entities^2).

**Detection:** Profile `_run_detection` with correlation enabled. If discovery logic dominates, it is running too often.

**Phase guidance:** Correlation discovery phase. This separation must be an architectural decision made before implementation.

## Minor Pitfalls

### Pitfall 11: AlertType Enum Extension Breaks Sensor Serialization

**What goes wrong:** Adding `AlertType.CORRELATION_DIVERGENCE` to the enum is straightforward, but existing sensor data serialization (`AlertResult.to_dict()` at line 56 of alert_result.py) emits `alert_type.value` as a string. If downstream consumers (HA automations, template sensors) match on alert type strings with an exhaustive list, a new type value could cause unexpected behavior (e.g., a Jinja template that does `{% if alert.alert_type in ['inactivity', 'unusual_time', 'drift'] %}` silently drops correlation alerts).

**Prevention:**
- Use a descriptive value string: `"correlation_divergence"` not just `"correlation"`. This makes it self-documenting in sensor attributes.
- Document the new alert type value in release notes with an example of how to handle it in automations.
- The existing `_build_sensor_data` (line 306 of coordinator.py) includes all alerts in the `anomalies` list using `to_dict()`. No special handling needed -- correlation alerts flow through the same path.

**Phase guidance:** Foundation phase (AlertType addition).

---

### Pitfall 12: Config Migration Chain Extends to v9

**What goes wrong:** The migration chain in `__init__.py` is already v2 through v8 (seven sequential if-blocks, lines 73-161). Adding v8-to-v9 for correlation config (e.g., correlation window size, max groups) extends it further. The chain is linear and each migration is independent (setdefault pattern), so it is structurally sound. The risk is in testing: each new migration needs a test for every prior version that might upgrade directly.

**Prevention:**
- Follow the established `setdefault` pattern exactly. Each migration only adds keys with defaults; it never modifies existing keys.
- Add a test that creates a v8 config entry and verifies it migrates to v9 with correct defaults.
- Minimize new config keys. Consider making correlation window and max groups constants in `const.py` initially, promoting to config only if user tuning proves necessary. Fewer config keys = fewer migration steps.

**Phase guidance:** Config/storage phase, when new config keys are added.

---

### Pitfall 13: `cross_sensor_patterns` Attribute Already Exists as Empty List

**What goes wrong:** The `_build_sensor_data` method (line 325 of coordinator.py) already outputs `"cross_sensor_patterns": []`. If the correlation feature populates this key with a different data shape than what users or the UI might expect, or if the key name implies something different from what correlation groups represent, there is a naming mismatch.

**Prevention:**
- Reuse the existing `cross_sensor_patterns` key to expose discovered correlation groups. This avoids adding new sensor attributes and maintains backward compatibility (it was always a list, just empty).
- Define the list item schema clearly: each item should be a dict with `group_id`, `entities`, `confidence`, and `last_co_occurrence`. Keep it flat and JSON-serializable.
- Limit exposed groups (e.g., top 10 by confidence) to avoid HA recorder database bloat from large attribute payloads.

**Phase guidance:** Sensor exposure phase.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Startup tier rehydration fix | Pitfall 5 - tiers None after restart | Call `classify_tier()` in `async_setup` after loading stored data; standalone fix before correlation |
| Foundation (AlertType, constants) | Pitfall 11 - enum extension, Pitfall 13 - attribute naming | Descriptive value string; reuse `cross_sensor_patterns` key |
| Correlation data structures | Pitfall 1 - pair explosion, Pitfall 9 - unbounded buffer | Bounded candidate set, bounded event deque, max group cap |
| Correlation discovery | Pitfall 6 - phantom correlations, Pitfall 10 - runs too often | Configurable window, daily discovery cycle separated from per-cycle detection |
| Correlation detection + alerting | Pitfall 2 - alerts during learning, Pitfall 8 - alert flood | Confidence gate, group-level alerts, sustained evidence |
| Alert integration with coordinator | Pitfall 3 - breaks existing detection | Separate AlertType, careful welfare weight, run full 449-test regression |
| Storage persistence | Pitfall 4 - migration breaks installs | New top-level key with `.get()` default, bump STORAGE_VERSION to 9, test v8 fixture |
| Config migration | Pitfall 12 - chain extension | Follow setdefault pattern, minimize new config keys |
| Entity lifecycle | Pitfall 7 - stale groups after entity removal | Prune groups on config reload, guard lookups |

## Sources

- Direct code analysis of coordinator.py (391 lines), routine_model.py (560 lines), acute_detector.py (226 lines), drift_detector.py (389 lines), __init__.py (277 lines), const.py (198 lines), alert_result.py (66 lines) -- all line references verified against current codebase (HIGH confidence)
- Existing architecture patterns observed in codebase: sustained evidence cycles, daily reclassification guard, `.get()` migration pattern, bounded deques, setdefault config migration chain (HIGH confidence)
- Cross-entity correlation pitfalls derived from combinatorial analysis and the specific constraints of this codebase: pure Python stdlib, 60s update cycle, HA async event loop, 449 existing tests (MEDIUM confidence -- engineering analysis, not empirical post-mortems)
