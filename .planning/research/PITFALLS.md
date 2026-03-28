# Domain Pitfalls

**Domain:** Activity-rate classification for anomaly detection (adding to existing behaviour-monitor)
**Researched:** 2026-03-28

## Critical Pitfalls

Mistakes that cause rewrites, broken upgrades, or detection regressions.

### Pitfall 1: Tier boundary oscillation (entity flaps between tiers)

**What goes wrong:** An entity whose event rate sits near a tier boundary (e.g., 50 events/day when the high/medium cutoff is 48) gets reclassified every time the sliding window shifts by a single day. Each reclassification changes its detection parameters, which can cause alerts to fire then clear then fire again on a per-day cadence.

**Why it happens:** Naive threshold-based classification with no hysteresis. The event rate is a noisy signal -- weekday vs weekend, holidays, seasonal variation all shift the rate. A hard cutoff at a single number guarantees oscillation for entities near the boundary.

**Consequences:** Users see spurious alerts disappearing and reappearing. If tier changes trigger detection parameter changes mid-cycle, the system may also lose accumulated evidence counters in `_inactivity_cycles` and `_unusual_time_cycles`, resetting the sustained-evidence gate and producing transient false positives.

**Prevention:**
- Implement hysteresis bands around tier boundaries (e.g., classify UP at 48 events/day but only classify DOWN at 36). Once an entity enters a tier, it stays until it clearly belongs elsewhere.
- Alternatively, compute the classification from a longer window (e.g., full `history_window_days` median) rather than a recent-day snapshot.
- Never reset sustained-evidence counters when tier changes -- the counters belong to the detection engine, not the classification layer.

**Detection:** Log tier transitions with timestamps. If any entity transitions more than once per week, the hysteresis band is too narrow.

### Pitfall 2: Auto-classification runs before enough data exists

**What goes wrong:** On first load or after adding new entities, the system attempts to classify entities into tiers with only hours or days of data. A motion sensor that fired 200 times on install day (testing, setup activity) gets classified as "high frequency" permanently, or a sensor that happened to be quiet on day one gets classified as "low frequency" and receives overly aggressive inactivity thresholds.

**Why it happens:** The classification runs unconditionally in the coordinator update loop. There is no guard equivalent to the existing `learning_status` / `confidence` gate that prevents detection from firing before the routine model is ready.

**Consequences:** Wrong tier assignment persists because the user does not know to override it. Detection parameters are wrong from the start, producing either false positives (low-freq entity with tight thresholds) or missed alerts (high-freq entity with loose thresholds).

**Prevention:**
- Gate auto-classification on `routine.confidence(now) >= 0.5` (at minimum). Below that threshold, use a "default" tier with conservative parameters.
- The existing `RoutineModel.learning_status()` already returns "inactive" / "learning" / "ready". Classification should only produce a confident tier when learning_status is "ready".
- Store the classification timestamp and mark it as "provisional" vs "confirmed" so the user (and logs) know whether the tier is data-driven or a guess.

**Detection:** If an entity's auto-classified tier differs from what a manual inspection of its `daily_activity_rate()` history would suggest, the classification ran too early or on insufficient data.

### Pitfall 3: Config migration v7 to v8 silently drops user overrides

**What goes wrong:** The v7->v8 migration adds the new `activity_tier_override` config key with `setdefault()`, which is fine. But the migration also needs to handle the case where detection parameters that were previously global (single `inactivity_multiplier`) now need to coexist with tier-specific parameters. If the migration simply adds tier defaults without preserving the user's existing `inactivity_multiplier` as the baseline for their entities' actual tiers, the user's carefully tuned sensitivity resets to defaults on upgrade.

**Why it happens:** Previous migrations (v4->v5, v5->v6, v6->v7) only added new keys with `setdefault()` and never needed to reinterpret existing keys. The v7->v8 migration is structurally different because the new tier system changes the *meaning* of existing parameters.

**Consequences:** Users who tuned `inactivity_multiplier` to 5.0 for their specific entity mix suddenly get the default 3.0 for some tiers. This manifests as a wave of false positive alerts immediately after upgrading, which destroys trust.

**Prevention:**
- The migration must read the existing `inactivity_multiplier` value and use it as the base for all tiers, not just inject new tier-specific defaults.
- Specifically: if a user had `inactivity_multiplier: 5.0`, the high-frequency tier should get `5.0 * high_tier_multiplier_factor` (not `DEFAULT_INACTIVITY_MULTIPLIER * high_tier_multiplier_factor`).
- Test the migration with a config entry that has non-default values for every parameter.
- The `setdefault` pattern from previous migrations is safe for *new* keys but dangerous when new keys interact with old keys.

**Detection:** Migration test that creates a v7 config with non-default `inactivity_multiplier`, migrates to v8, and asserts the user's value is preserved as the effective baseline.

### Pitfall 4: Display formatting breaks existing automations

**What goes wrong:** The alert `explanation` string in `AlertResult` currently formats all intervals as hours (e.g., `"no activity for 0.3h (typical interval: 0.2h)"`). Changing this to minutes for sub-hour intervals (e.g., `"no activity for 18m (typical interval: 12m)"`) breaks any user automations that parse the explanation string with regex patterns expecting the `Xh` format.

**Why it happens:** The `explanation` field is a human-readable string exposed as a sensor attribute via `anomalies` in the coordinator data dict. Users build automations that trigger on specific text patterns. HA template sensors parsing `{:.1f}h` will break when the format changes to `{:d}m`.

**Consequences:** Silent automation breakage. The user's regex stops matching because the format changed. Since HA automations fail silently (they just don't trigger), the user may not notice until a real alert goes undelivered.

**Prevention:**
- Add the formatted values as *separate structured fields* in `AlertResult.details` (e.g., `elapsed_formatted`, `typical_formatted`) rather than changing the `explanation` string format.
- Keep the `explanation` field format stable -- always use hours -- and add a new `explanation_display` field with the user-friendly format.
- Or: change the format but also add `elapsed_seconds` and `typical_interval_seconds` to the details dict (already present at lines 128-133 of `acute_detector.py`) and document that automations should use the structured fields, not the explanation string.
- The `details` dict already contains `elapsed_seconds` and `expected_gap_seconds`, so the raw data is available. The formatting change is purely cosmetic and should be additive, not a replacement.

**Detection:** Search for any documentation, examples, or community templates that reference the explanation string format. Add a deprecation note if changing the format.

## Moderate Pitfalls

### Pitfall 5: Tier-specific parameters create a combinatorial config explosion

**What goes wrong:** If each tier (high/medium/low) gets its own `inactivity_multiplier`, `min_inactivity_multiplier`, and `max_inactivity_multiplier`, the config UI balloons from the current 12 fields to 18+ fields. Users are already confused by the distinction between `inactivity_multiplier`, `min_inactivity_multiplier`, and `max_inactivity_multiplier`. Adding per-tier variants makes the UI unusable.

**Prevention:**
- Do NOT expose per-tier multipliers in the config UI. Instead, define tier behavior as internal multiplier *factors* applied on top of the user's single global `inactivity_multiplier`.
- Example: high-frequency tier internally uses `global_multiplier * 2.0` and a minimum absolute floor of 300 seconds. The user only sees and tunes the single global multiplier.
- The tier factors and absolute floors should be constants in `const.py`, not user-configurable (at least in v3.1). Per-entity sensitivity tuning is explicitly out of scope per PROJECT.md.

### Pitfall 6: Minimum absolute floor without considering entity's actual rate

**What goes wrong:** A "minimum absolute floor" for high-frequency inactivity (e.g., "never alert if silent less than 5 minutes") sounds reasonable, but if the floor is too low, it generates noise for entities that fire every 30 seconds (PIR sensors). If too high, it masks genuine inactivity for entities that fire every 2 minutes.

**Prevention:**
- The floor should be derived from the entity's *observed* median interval, not a global constant. E.g., floor = `max(ABSOLUTE_MINIMUM, median_interval * floor_factor)`.
- The current `expected_gap_seconds()` on `EntityRoutine` already computes the median interval per-slot. The floor should be a function of this value, not independent of it.
- Start with a generous floor (e.g., 3x the median interval or 5 minutes, whichever is greater) and tune down based on testing.

### Pitfall 7: User tier override not persisted correctly

**What goes wrong:** The user overrides an entity's auto-classified tier via the config UI, but the override is stored only in the config entry data (not consulted by the coordinator). On reload, the auto-classifier runs again and overwrites the user's choice because the coordinator reads auto-classified tiers from the routine model, not from config.

**Prevention:**
- User overrides must be stored in the config entry data (via config flow) and take precedence over auto-classification. The coordinator must check for overrides *before* running auto-classification.
- The existing pattern stores all user config in `entry.data`. Tier overrides should follow this pattern: `entry.data["activity_tier_overrides"] = {"sensor.motion_kitchen": "high"}`.
- Auto-classification should only apply to entities without an override.

### Pitfall 8: Coordinator reload path does not re-apply tier parameters

**What goes wrong:** When the user changes config options (triggering `async_reload_entry` at line 264 of `__init__.py`), the coordinator is reconstructed from scratch. If the tier classification is computed during `async_setup()` but the `AcuteDetector` is constructed in `__init__()` with only global parameters (lines 79-83 of `coordinator.py`), the detector does not receive tier-specific parameters until classification completes.

**Prevention:**
- The `AcuteDetector` must accept tier-aware parameters per-entity, not just global parameters in its constructor. This means either:
  - Passing tier info to `check_inactivity()` at call time (preferred -- keeps detector stateless re: tiers), or
  - Reconstructing the detector when tiers change.
- The current `_run_detection` loop (line 191 of `coordinator.py`) already passes per-entity `routine` objects. Adding a per-entity tier parameter to `check_inactivity()` is the natural extension.

## Minor Pitfalls

### Pitfall 9: Time formatting edge cases

**What goes wrong:** The "show minutes instead of hours" formatting logic has edge cases: exactly 60 minutes (show as "1h 0m" or "60m"?), exactly 0 minutes (show as "0m" or "just now"?), very large values (show as "72h" or "3d"?). Inconsistent formatting across the codebase -- the coordinator's `_build_sensor_data` (lines 282-288) has one inline formatter, the `AcuteDetector.check_inactivity` explanation (lines 113-114) has another.

**Prevention:**
- Create a single `format_duration(seconds: float) -> str` utility function and use it everywhere. Define the rules once: <60s = "<1m", 1-59m = "Xm", 60m-1439m = "Xh Ym", >=24h = "Xd Yh".
- Replace the inline formatting in both `coordinator.py` and `acute_detector.py` with calls to this function.

### Pitfall 10: Storage version bump missed for new tier data

**What goes wrong:** If tier classification results are persisted in the `.storage` file (e.g., cached tier assignments), the `STORAGE_VERSION` must be bumped from 7 to 8. If forgotten, loading old storage data into new code that expects tier fields causes KeyError or incorrect defaults.

**Prevention:**
- If tier data is stored in `.storage`, bump `STORAGE_VERSION` and handle the old-format gracefully in `async_setup()` (the `from_dict` pattern already handles missing fields with defaults).
- If tier data is computed at runtime and not persisted, no storage version bump is needed -- but document this decision explicitly.
- Note: config entry VERSION (currently 7 in `config_flow.py` line 249) and STORAGE_VERSION (currently 7 in `const.py` line 52) are separate. Both may need bumping but for different reasons.

### Pitfall 11: Entity tier override UI becomes stale

**What goes wrong:** The config UI shows a list of entities with tier override dropdowns. If the user removes an entity from monitoring, the override for that entity remains in config data as dead weight. If the user later re-adds the entity, the stale override may apply an inappropriate tier.

**Prevention:**
- On config save (options flow), prune any tier overrides for entities not in the current `monitored_entities` list.
- This is the same pattern as how `notify_services` is handled in the current options flow (lines 333-336 of `config_flow.py`).

### Pitfall 12: Classification uses wrong time window for rate calculation

**What goes wrong:** `daily_activity_rate()` on `EntityRoutine` (line 284 of `routine_model.py`) counts events for a *specific calendar date* by filtering `event_times` in the 24 hour-slots for that day-of-week. But the deque has `maxlen=56` and events are ISO timestamps -- if the entity has been running for weeks, older events age out of the deque. The "rate" computed from a single recent day is volatile. Computing rate from multiple days requires calling `daily_activity_rate()` for each day and averaging, which iterates the same deques repeatedly.

**Prevention:**
- Add a dedicated rate-computation method that aggregates across the full deque contents (all timestamps in all slots) and divides by the number of distinct days observed. This is O(n) over events, not O(days * slots * events).
- Alternatively, maintain a running event counter per entity (increment on every `record()` call, store first/last observation timestamps) and compute rate as `total_events / days_elapsed`. This is O(1) at query time.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Auto-classification logic | Pitfall 1 (oscillation), Pitfall 2 (premature classification) | Implement hysteresis + confidence gate before wiring into detector |
| Tier-specific detection parameters | Pitfall 5 (config explosion), Pitfall 6 (wrong floor) | Use internal factors, not per-tier UI fields; derive floor from observed rate |
| User override in config UI | Pitfall 7 (override not persisted), Pitfall 11 (stale overrides) | Store in entry.data, prune on save |
| Display formatting (minutes vs hours) | Pitfall 4 (automation breakage), Pitfall 9 (edge cases) | Add structured fields, single format utility, keep explanation stable |
| Config migration v7 to v8 | Pitfall 3 (user values lost), Pitfall 10 (storage version) | Read existing multiplier as baseline; test with non-default values |
| Coordinator integration | Pitfall 8 (reload path), Pitfall 12 (rate computation) | Pass tier to check_inactivity() at call time; add efficient rate method |

## Sources

- Direct codebase analysis of `acute_detector.py`, `coordinator.py`, `routine_model.py`, `config_flow.py`, `__init__.py`, `const.py`, `sensor.py` (HIGH confidence -- all pitfalls derived from actual code structure and line-level inspection)
- Existing migration chain pattern (v2->v3->v4->v5->v6->v7) in `__init__.py` (HIGH confidence)
- PROJECT.md constraints: sensor stability, config migration, no new dependencies, per-entity sensitivity tuning out of scope (HIGH confidence)
