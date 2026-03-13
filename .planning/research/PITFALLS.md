# Pitfalls Research: Detection Rebuild (v1.1)

**Domain:** Home Assistant custom integration — replacing statistical/ML anomaly detection with routine-based detection (acute + drift)
**Researched:** 2026-03-13
**Confidence:** HIGH (codebase analysis) / MEDIUM (HA migration patterns, IoT detection research)

---

## Critical Pitfalls

Mistakes that cause rewrites, break user trust, create welfare safety regressions, or silently break existing automations.

---

### Pitfall 1: Cold Start Produces Immediate False Negatives on Live Users

**What goes wrong:**
The routine model replaces the z-score analyzer. On first boot after the upgrade, the routine model has no learned history. During the history window build-up period (default 4 weeks), the acute detection engine has no baseline to compare against — so it cannot fire alerts even when a genuine welfare event occurs. This is the inverse of the false positive problem: **silence when an alert should fire**.

For a welfare monitoring integration, a silent false negative during cold start is a safety regression. The old z-score analyzer fired (sometimes too often). The new engine fires nothing. The user and their family assume the system is working when it is not.

**Why it happens:**
Routine-based detection is inherently baseline-dependent. There is no baseline until history accumulates. Developers focus on eliminating the learning period UI noise and forget that "no detections" is also a user-visible regression.

**How to avoid:**
- Expose a `learning_status` sensor state that clearly says "No baseline yet — detection inactive" (not just a progress percentage).
- Send a one-time notification when the integration starts in cold-start mode, and another when acute detection activates.
- Consider a "bootstrap mode": during cold start, fall back to a simple inactivity threshold (e.g., no activity in X hours fires an alert unconditionally, without requiring a routine baseline). This is worse than routine detection but better than silence.
- Document the cold start window explicitly in the config flow description.

**Warning signs:**
- `baseline_confidence` sensor shows 0% but no notification is surfaced to the user.
- Users report no alerts for days after installation without realising the integration is in learning mode.
- Tests pass (because they mock a pre-loaded baseline) but live installations silently suppress all alerts for weeks.

**Phase to address:** Routine model phase — define cold start behaviour as an explicit design decision before implementing the detection engine, not as an afterthought.

---

### Pitfall 2: Config Entry Migration Fails Silently — Users Lose All Stored Patterns

**What goes wrong:**
The existing integration stores patterns in `.storage/behaviour_monitor.{entry_id}.json` at `STORAGE_VERSION = 2`. The new coordinator replaces `analyzer.py` entirely. If the new code attempts to deserialize old storage data using the new routine model's `from_dict()`, it will either crash (raising `KeyError`/`TypeError` on missing fields) or silently produce an invalid model (partially populated).

A crash in `async_setup()` means the integration fails to load. The config entry is left in a broken state. HA logs show the error but users often do not check logs — they just see "Integration unavailable."

Separately: the config entry itself (`entry.data`) contains keys for `CONF_ENABLE_ML`, `CONF_RETRAIN_PERIOD`, `CONF_ML_LEARNING_PERIOD`, `CONF_CROSS_SENSOR_WINDOW` that no longer apply. These must be cleaned up or ignored — but if any new code calls `entry.data.get(CONF_ENABLE_ML)` on an entry that has been migrated away from those keys, the fallback default must be correct.

**Why it happens:**
- `STORAGE_VERSION` is tracked but `async_migrate_entry` does not exist in the current `__init__.py`. The migration hook must be added.
- Storage migration is separate from config entry migration. Both need handling.
- Developers test fresh installs and forget to test upgrade paths.

**How to avoid:**
- Increment `STORAGE_VERSION` to 3 for v1.1. In `async_setup()`, handle version 2 data gracefully: detect it by checking for the `analyzer` key, log a clear message, and discard it (start fresh) rather than crashing.
- Implement `async_migrate_entry` in `__init__.py` to remove or rename old config entry keys (`CONF_ENABLE_ML`, `CONF_RETRAIN_PERIOD`, etc.) and add new keys (`CONF_HISTORY_WINDOW`, `CONF_ACUTE_THRESHOLD`, etc.) with safe defaults.
- Use minor version bump for additive config changes (new optional keys), major bump for breaking removals.
- Write an integration test that loads a v2 storage fixture and confirms the integration sets up successfully with an empty routine model rather than crashing.
- Per HA docs: if `async_migrate_entry` returns `False`, the entry is disabled. Prefer returning `True` with a fresh state over returning `False` and disabling the integration.

**Warning signs:**
- `async_setup_entry` raises `KeyError` or `TypeError` on first boot after upgrade.
- Integration appears in HA as "Failed to set up" after update.
- Storage fixture in tests uses fresh data format but no test covers loading old format data.

**Phase to address:** Coordinator rebuild phase — migration must be designed before the new coordinator is wired in, not added as a cleanup step at the end.

---

### Pitfall 3: Sensor Entity State Contract Breaks Existing Automations

**What goes wrong:**
The 14 sensor entities must keep the same entity IDs. This is explicitly required (`entity_id` stability is maintained via `unique_id` in the entity registry). However, the *state values and attributes* of several sensors will change meaning:

- `sensor.behaviour_monitor_anomaly_detected`: currently `"on"/"off"` reflecting z-score or ML anomalies. After rebuild, this must reflect routine-based acute detections. If the value is momentarily `None` or `"unknown"` during coordinator rebuild, any automation with `trigger: state` on this entity will fire unexpectedly.
- `sensor.behaviour_monitor_baseline_confidence`: currently reflects z-score learning progress (days_elapsed / learning_period_days). After rebuild, this reflects routine model training progress. The scale and meaning differ.
- `sensor.behaviour_monitor_ml_status`: currently `"Ready"/"Learning"/"Disabled"`. After rebuild, ML is removed. This sensor should either be removed or repurposed — but **removing a sensor entity breaks any automation referencing it** and leaves a dead entity in the entity registry.
- `sensor.behaviour_monitor_ml_training_remaining`: same problem — removing it is a breaking change for users who have automations or dashboards referencing it.
- `sensor.behaviour_monitor_cross_sensor_patterns`: depends on ML cross-sensor patterns which are being removed.

**Why it happens:**
The project spec says "keep sensor entity IDs" but the old sensors that exposed ML-specific data (`ml_status`, `ml_training_remaining`, `cross_sensor_patterns`) cannot sensibly map to the new engine. The temptation is to quietly remove them.

**How to avoid:**
- Audit every sensor entity against the new coordinator's data output before writing any sensor code.
- For sensors that no longer have meaningful data: keep the entity but surface a fixed state that makes the deprecation visible (e.g., `ml_status` → always `"Removed in v1.1"`, `ml_training_remaining` → `"N/A"`).
- Never remove a sensor entity in the same release that changes the detection engine. Deprecate in v1.1, remove in v1.2 with advance notice.
- During coordinator data rebuild, ensure `coordinator.data` is never `None` after first refresh — `CoordinatorEntity` availability propagates from `coordinator.last_update_success`, and if first refresh fails, all 14 sensors go `unavailable` simultaneously, triggering any automations that watch for state changes.

**Warning signs:**
- `sensor.behaviour_monitor_anomaly_detected` transitions through `"unknown"` during HA restart after the upgrade.
- Automated tests mock the coordinator but never assert the exact state values that automations would depend on.
- Entity registry contains orphaned unique IDs from old sensor keys that no longer exist.

**Phase to address:** Sensor compatibility review must happen before coordinator implementation — define the exact output contract of `coordinator.data` first, then implement both sensor and coordinator to that contract.

---

### Pitfall 4: Drift Detection Triggers During Legitimate Routine Changes

**What goes wrong:**
The drift detection engine is designed to detect when behavior persistently shifts over days/weeks (e.g., someone sleeping later, moving less). But legitimate voluntary routine changes (a new job schedule, a visitor staying for a week, recovery from illness) look identical to pathological drift. If drift detection fires aggressively, it produces high false positive rates for exactly the users who are most likely to have changing routines.

This is the fundamental tension: the system cannot distinguish "gradual decline" from "gradual deliberate change" without external context.

**Why it happens:**
Change-point detection algorithms (CUSUM, PELT, Bayesian change points) detect statistical shifts in distributions. They have no concept of "voluntary." The research literature confirms this: for fragile populations, the threshold p-value is often set to 0.85–0.925 precisely because the cost of a false negative is higher than a false positive, but this increases noise.

**How to avoid:**
- Drift alerts must require sustained evidence over a minimum window (e.g., 5–7 days of consistent deviation) before firing, not a single detected change point.
- Provide a "Routine Reset" mechanism: a service call or config option that tells the drift engine "this is the new normal." Without this, a user who changes their schedule has no way to stop recurring drift alerts.
- Holiday mode already exists and suppresses monitoring — ensure it also resets the drift baseline when disabled, not just resumes from the old baseline.
- Drift alerts should be informational, not urgent — separate notification severity from acute event alerts.

**Warning signs:**
- Drift alert fires within 2–3 days of a known schedule change (holiday return, new arrangement).
- Users disable drift detection entirely rather than tolerate false positives.
- No mechanism exists to acknowledge or dismiss a drift alert and update the baseline.

**Phase to address:** Drift detection engine phase — define the minimum evidence window and the routine reset mechanism as requirements before implementing the algorithm.

---

### Pitfall 5: Acute Detection Inactivity Threshold Is Fixed, Not Routine-Relative

**What goes wrong:**
Acute detection flags "out of character" events in real time. The most common implementation mistake is using a fixed configurable inactivity threshold (e.g., "alert if no activity for 4 hours") rather than a routine-relative threshold (e.g., "alert if no activity during a time window when activity normally occurs").

A fixed threshold produces false positives at night (no activity for 8 hours is normal) and false negatives during day windows where activity is expected but delayed only 30 minutes.

**Why it happens:**
Fixed thresholds are simpler to implement and configure. Routine-relative thresholds require the routine model to be functional first. During early implementation, a fixed threshold is used as a placeholder and never replaced.

**How to avoid:**
- The acute detection threshold must be parameterized relative to the learned routine model, not as a flat time value. The config option should be "how many times the typical quiet period before alerting" not "how many hours before alerting."
- Implement the routine model before the acute detection engine — do not build detection that cannot use the model yet.
- Test acute detection with synthetic routine data that includes overnight quiet periods to confirm it does not alert during expected inactivity.

**Warning signs:**
- Acute alerts fire every morning before the monitored person wakes up.
- The `CONF_ACUTE_THRESHOLD` is a raw hour value rather than a multiplier on the learned interval.
- Tests only exercise the detection engine with uniform round-the-clock activity distributions.

**Phase to address:** Routine model phase (define the output API the detection engine will consume), then acute detection engine phase.

---

### Pitfall 6: River Dependency Removal Breaks Existing Installations That Rely on It

**What goes wrong:**
The River ML library is being removed as a dependency. Existing users who have River installed and `CONF_ENABLE_ML = True` in their config entries will see the integration start normally but with ML disabled. This is handled gracefully in the existing code (`ML_AVAILABLE` check). However, if the new coordinator code removes the `ml_analyzer` property and the `ML_AVAILABLE` import entirely, any external code or custom templates referencing `coordinator.ml_analyzer` will break.

More critically: the ML storage file (`.storage/behaviour_monitor_ml.{entry_id}.json`) will be orphaned — it won't be loaded or cleaned up. This is harmless but wastes disk space and may confuse users inspecting their storage.

**Why it happens:**
Removing a dependency is treated as internal cleanup. The external surface area (coordinator properties, storage files) is overlooked.

**How to avoid:**
- Clean up the ML storage file on first startup after the upgrade. In `async_setup()`, detect and delete the orphaned ML store: `await self._ml_store.async_remove()` if it exists.
- Remove `CONF_ENABLE_ML`, `CONF_RETRAIN_PERIOD`, `CONF_ML_LEARNING_PERIOD`, `CONF_CROSS_SENSOR_WINDOW` from config entry data via migration, so they do not appear as dead options in the integration's config panel.
- Log clearly at startup: "ML features have been removed in v1.1. Routine-based detection is now active."
- Do not retain any public coordinator properties (`ml_analyzer`, `ml_enabled`, `recent_ml_anomalies`) in the new coordinator — they become dead references that confuse future maintainers.

**Warning signs:**
- `.storage/behaviour_monitor_ml.*.json` files exist on disk but are never loaded or cleaned.
- `CONF_ENABLE_ML` appears in the options flow UI with no effect.
- `coordinator.ml_enabled` returns `False` for all users but the property still exists.

**Phase to address:** Coordinator rebuild phase — dependency cleanup and storage migration are part of the coordinator replacement, not a separate cleanup step.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Use fixed inactivity threshold instead of routine-relative | Simpler to implement | False positives at night; false negatives during day | Never — the whole value of the routine model is eliminated |
| Keep ML sensor entities as stubs returning hardcoded values | No breaking change for automations | Dead code, confusing state, misleading sensor names | Acceptable for one release cycle as deprecation bridge |
| Skip storage migration, start fresh | No migration code needed | Users lose all learned patterns and must wait for re-learning | Never for welfare monitoring — silent false negative risk during cold start |
| Implement drift detection with a 24-hour window | Quick to ship | Too noisy; fires on weekday/weekend variation | Never — minimum viable window is 5–7 days |
| Suppress all alerts during cold start with no user notification | No false positives | User believes system is working; genuine events missed silently | Never — silence must be surfaced explicitly |
| Reuse existing `UPDATE_INTERVAL = 60s` for drift checks | No architectural change | Drift runs on every tick unnecessarily; drift is inherently a long-horizon check | Acceptable if drift evaluation is gated behind a "last checked N hours ago" guard |

---

## Integration Gotchas

Common mistakes specific to the Home Assistant integration layer.

| Integration Point | Common Mistake | Correct Approach |
|-------------------|----------------|------------------|
| `async_migrate_entry` | Not implementing it; letting old config entries fail silently | Always implement; return `True` with migrated data or fresh defaults — never `False` unless the entry is genuinely unrecoverable |
| `Store.async_load()` | Crashing on stale format; `KeyError` on missing keys | Wrap deserialization in try/except; log warning and continue with empty model if format is unrecognised |
| `DataUpdateCoordinator.data` | Returning `None` on first refresh failure | Ensure `_async_update_data` returns a valid empty-state dict rather than raising; sensors should return safe defaults, not go unavailable |
| Sensor entity removal | Deleting a `SensorEntityDescription` entry | Leaving stale unique IDs in entity registry that HA never cleans up; users see ghost entities. Prefer keeping deprecated sensors with a stub state |
| Config entry options cleanup | Leaving old keys (`CONF_ENABLE_ML`) in `entry.data` | They appear in storage forever; options flow may surface them with no effect. Clean up via migration |
| Holiday mode + drift baseline | Resuming drift tracking from pre-holiday baseline after holiday ends | Drift engine will immediately fire because post-holiday behavior differs from pre-holiday. Reset drift baseline when holiday mode is disabled |
| `EVENT_STATE_CHANGED` subscription | Subscribing before coordinator is ready | State changes arrive before `async_setup` completes; handler references uninitialized model. Subscribe only after model is initialized |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Scanning full history window on every state change | CPU spike on every entity event; HA becomes sluggish | Maintain rolling statistics (mean, variance) as events arrive; never re-scan history on each event | At 5+ monitored entities with frequent changes |
| Running drift detection on every 60-second coordinator tick | Unnecessary computation; drift is a days-scale phenomenon | Gate drift evaluation to run at most once per hour or once per day | Always — drift evaluation at 60s intervals is always wasteful |
| Storing raw event history for drift in memory | Memory grows unbounded over 4-week window | Use fixed-size circular buffer or pre-aggregated daily summaries, not raw event lists | At ~4 weeks of data for high-frequency sensors |
| Loading entire history from HA recorder API on every restart | Slow startup; blocks coordinator initialization | Pre-aggregate and persist summaries; only fetch from recorder on first install or after data loss | Immediately on any system with >2 weeks of data |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No user-visible indication of cold start mode | User believes system is monitoring when it is not; misses genuine welfare events | Surface cold start status prominently: sensor state, persistent notification, or startup log at WARNING level |
| Drift alert with no dismiss/acknowledge mechanism | User cannot stop repeated drift alerts after a voluntary routine change | Add "Update baseline" service call that resets the drift reference point to current behavior |
| Acute threshold as raw hours in config flow | Users set it too low (constant alerts) or too high (misses genuine events) | Express threshold as a multiplier of the learned typical quiet period; show learned value in config flow description |
| Single "Anomaly Detected" binary sensor for both acute and drift | Automation cannot distinguish urgent (acute) from informational (drift) | Expose separate `acute_alert` and `drift_alert` sensors, or use sensor attributes to distinguish |
| Re-running learning period after any config change | Users lose months of baseline data when reconfiguring | Only reset the model when monitored entities change; preserve the routine model when thresholds or notification settings change |

---

## "Looks Done But Isn't" Checklist

- [ ] **Cold start handling:** Integration surfaces "detection inactive" status — verify a new install with no history shows a clear user-visible warning, not just a 0% confidence value.
- [ ] **Storage migration:** Load a v2 storage fixture (z-score format) in tests — confirm integration starts, does not crash, and logs a clear message about starting fresh.
- [ ] **Config entry migration:** Confirm old keys (`CONF_ENABLE_ML`, `CONF_RETRAIN_PERIOD`) are absent from `entry.data` after migration — check with a migration integration test.
- [ ] **ML sensor deprecation:** Verify `sensor.behaviour_monitor_ml_status` and `ml_training_remaining` return defined (not `unavailable`) states rather than disappearing from the entity registry.
- [ ] **Holiday mode + drift:** Confirm drift baseline resets when holiday mode is disabled — not just resumes from the pre-holiday baseline.
- [ ] **Routine reset service:** A service call or config option exists to acknowledge a drift alert and update the baseline to current behavior.
- [ ] **Acute detection overnight:** Confirm no alerts fire during an overnight quiet period when testing with a routine model that includes expected overnight inactivity.
- [ ] **`coordinator.data` never None:** First coordinator refresh returns a valid empty-state dict even with no stored history — all 14 sensors return safe defaults instead of going unavailable.
- [ ] **Orphaned ML storage file:** Confirm `.storage/behaviour_monitor_ml.{entry_id}.json` is cleaned up (or not created) after the upgrade.
- [ ] **Automation smoke test:** Manually verify `sensor.behaviour_monitor_anomaly_detected` state transitions on an actual HA instance after the upgrade, not just in unit tests.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Cold start produces false negatives for weeks | HIGH | Ship bootstrap mode (simple fixed threshold during cold start) as a fast-follow patch; add prominent UI warning immediately |
| Config migration crashes on startup | HIGH | Release hotfix that wraps storage load in try/except and clears on failure; users lose learned patterns but integration recovers |
| Sensor entity removal breaks user automations | MEDIUM | Re-add removed sensor entities as stubs in a patch release; deprecation warning in state attributes |
| Drift fires constantly after legitimate routine change | MEDIUM | Add `reset_drift_baseline` service call; document in release notes as the workaround |
| Acute detection ignores overnight quiet periods | MEDIUM | Patch the threshold logic to use routine-relative comparison; release as bugfix |
| ML storage files orphaned | LOW | Add cleanup step in next release's `async_setup`; inform users via CHANGELOG |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Cold start false negatives (Pitfall 1) | Routine model phase — define cold start behavior as a first-class requirement | Test: new install with no history never silently suppresses; user-visible status confirmed |
| Config entry migration failure (Pitfall 2) | Coordinator rebuild phase — migration implemented before new coordinator wired in | Test: load v2 storage fixture; confirm clean startup and logged warning |
| Sensor entity state contract break (Pitfall 3) | Pre-implementation — audit sensor output contract before writing coordinator | Test: all 14 sensors return defined values after coordinator rebuild; no `unavailable` on first refresh |
| Drift on legitimate routine changes (Pitfall 4) | Drift detection engine phase — minimum evidence window and reset mechanism defined upfront | Test: drift engine does not fire within 3 days of a simulated schedule change |
| Fixed vs routine-relative acute threshold (Pitfall 5) | Routine model phase — define detection API before building detection engine | Test: no acute alert during synthetic overnight quiet period with learned routine model |
| River dependency removal loose ends (Pitfall 6) | Coordinator rebuild phase — include storage cleanup and config migration in same PR | Test: orphaned ML storage file absent after upgrade; `CONF_ENABLE_ML` absent from migrated entry |

---

## Sources

- `custom_components/behaviour_monitor/coordinator.py` — existing storage migration pattern, sensor data output, ML dependency wiring (HIGH confidence, direct inspection)
- `custom_components/behaviour_monitor/sensor.py` — 14 sensor entity definitions, entity ID stability, `unique_id` pattern (HIGH confidence, direct inspection)
- `custom_components/behaviour_monitor/const.py` — `STORAGE_VERSION = 2`, all `CONF_*` keys being deprecated, `UPDATE_INTERVAL` (HIGH confidence, direct inspection)
- `.planning/PROJECT.md` — explicit constraints: entity IDs must not change, config migration must be graceful, River dependency being removed (HIGH confidence)
- Home Assistant Developer Docs — `async_migrate_entry` requirements, major vs minor version semantics, config entry mutation rules (MEDIUM confidence, verified via WebFetch)
- [Config entry minor versions blog post](https://developers.home-assistant.io/blog/2023/12/18/config-entry-minor-version/) — minor bump is backwards compatible; major bump fails setup on downgrade (MEDIUM confidence)
- [IoT anomaly detection survey — ScienceDirect](https://www.sciencedirect.com/science/article/pii/S2542660522000622) — false negative risk in unbalanced datasets, cold start baseline establishment patterns (MEDIUM confidence)
- [Behavior drift detection in home automation — MDPI](https://www.mdpi.com/2227-7080/6/1/16) — p-value thresholds for fragile populations, concept drift model confidence failure mode (MEDIUM confidence)
- [Home Assistant community — unavailable states breaking automations](https://community.home-assistant.io/t/wth-is-unavailable-breaking-everything/474217) — state transition side effects on automation triggers (MEDIUM confidence)

---
*Pitfalls research for: Home Assistant behaviour monitoring — v1.1 Detection Rebuild*
*Researched: 2026-03-13*
