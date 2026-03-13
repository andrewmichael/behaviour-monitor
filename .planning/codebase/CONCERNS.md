# Codebase Concerns

**Analysis Date:** 2026-03-13

## Tech Debt

**Hardcoded Welfare Status Thresholds:**
- Issue: Multiple threshold values for welfare status determination scattered throughout analyzer.py without centralized definition
- Files: `custom_components/behaviour_monitor/analyzer.py` (lines 553-561, 618-622, 667-671, 714-721)
- Impact: Difficult to adjust sensitivity; inline comments like "was 1.5 — tolerates up to 2x" (line 553) indicate ad-hoc tuning; no systematic way to validate threshold changes
- Fix approach: Extract all thresholds to WelfareThresholds dataclass in const.py; parameterize with sensitivity level like ML_CONTAMINATION; add unit tests for threshold transitions

**Sensitivity Configuration Not Fully Coupled:**
- Issue: User can set sensitivity (LOW/MEDIUM/HIGH) but welfare status thresholds are hardcoded independent of sensitivity choice
- Files: `custom_components/behaviour_monitor/analyzer.py`, `custom_components/behaviour_monitor/const.py`
- Impact: Setting HIGH sensitivity doesn't make welfare alerts more aggressive; user expectations mismatched with behavior (e.g., all thresholds fixed at concern_level < 2.0)
- Fix approach: Derive welfare_status thresholds from SENSITIVITY_THRESHOLDS; scale concern_level multipliers based on user's sensitivity selection

**Floating-Point Infinity as Sentinel:**
- Issue: Z-score calculation uses float("inf") without documented bounds checking (line 448)
- Files: `custom_components/behaviour_monitor/analyzer.py` line 448
- Impact: Infinity serializes to JSON as null; could lose anomaly information; comparisons against finite thresholds silently fail
- Fix approach: Use bounded value (e.g., SENSITIVITY_THRESHOLD + 10) instead; add round-trip serialization tests to prevent data loss

**Entity Pattern Array Reconstruction Assumes Fixed Structure:**
- Issue: from_dict() silently fills missing buckets if data corrupted; no validation of expected structure
- Files: `custom_components/behaviour_monitor/analyzer.py` lines 156-161
- Impact: Malformed stored data could create inconsistent patterns without error signals; while-loop appends missing buckets indefinitely
- Fix approach: Add explicit length assertions; raise ValueError if critical structure violations detected; log warnings for repaired data

## Known Bugs

**Snooze Expiration Not Proactively Cleared:**
- Symptoms: Expired snooze timestamp persists in storage until next coordinator update if HA reboots during snooze
- Files: `custom_components/behaviour_monitor/coordinator.py` lines 232-237 (loads expired snooze), lines 175-185 (checks expiry on each call)
- Trigger: HA reboots while snooze active; snooze expires during downtime; expired timestamp still saved
- Workaround: is_snoozed() properly checks for expiration; only affects storage, not behavior
- Impact: Very low; internal state only; snooze correctly reports as inactive

**ML Learning Window Edge Case:**
- Symptoms: ML notifications could fire moments before time threshold if sample threshold (100) reached faster than learning period (7 days)
- Files: `custom_components/behaviour_monitor/coordinator.py` lines 549-557
- Trigger: High-frequency state changes (100+ samples in 2 days); checks both conditions but timing depends on update cycle
- Workaround: Both time AND samples must pass before notifications (line 555); timing window ~60 seconds
- Impact: Low; both conditions enforced, but window exists

**Cross-Sensor Pattern Key Format Inconsistency:**
- Symptoms: Stored patterns may use different serialization formats (tuple vs string) from different code versions
- Files: `custom_components/behaviour_monitor/ml_analyzer.py` lines 340-341 (create tuple keys), 644-650 (serialize/deserialize)
- Trigger: Loading ML data saved before standardization
- Workaround: Keys reconstructed from stored format on load; sorting provides normalization
- Impact: Low; keys consistently alphabetized, format mismatches absorbed

## Security Considerations

**Notification Service Format Not Pre-Validated:**
- Risk: Arbitrary notify service names from config called without type checking; invalid services fail silently
- Files: `custom_components/behaviour_monitor/coordinator.py` lines 926-946
- Current mitigation: Try/catch with warning log for each failed service (line 942)
- Recommendations:
  - Add config_flow validation to verify notify.service_name exists before saving
  - Test service availability with test call during config
  - Add sensor reporting failed notification services

**Timezone-Aware/Naive Datetime Mismatch Risk:**
- Risk: Fallback to UTC if tzinfo missing (lines 217, 230, 168, 174); could create mixed aware/naive datetimes
- Files: `custom_components/behaviour_monitor/coordinator.py` lines 216-217, 230-231; `analyzer.py` lines 168-170, 174-177
- Current mitigation: All use .replace(tzinfo=...) which preserves time while adding timezone
- Recommendations: Document that all internal timestamps are UTC; add assertions on deserialization; standardize all functions to require timezone-aware input

**ML check_anomaly() None Return Path:**
- Risk: check_anomaly() returns None if untrained (line 464); calling code may not expect None in all paths
- Files: `custom_components/behaviour_monitor/ml_analyzer.py` lines 461-464
- Current mitigation: Coordinator checks is_trained (line 524) before calling check_anomaly()
- Recommendations: Make return type consistent (empty list or sentinel object); document all None-able returns; add type hints

**No Rate Limiting on Notifications:**
- Risk: Rapid anomalies could trigger notification flood (60+ per minute theoretically possible)
- Files: `custom_components/behaviour_monitor/coordinator.py` lines 560-572 (notification sending)
- Current mitigation: Only updates on state changes; coordinator updates every 60 seconds
- Recommendations:
  - Implement minimum time between identical notification types (e.g., 5 min cooldown per anomaly type)
  - Track notification_time per source type (statistical, ml, welfare) separately

## Performance Bottlenecks

**Entity Status Calculated Every Update Cycle:**
- Problem: get_entity_status() calls on every coordinator update (60x per minute); recalculates Z-scores for all entities
- Files: `custom_components/behaviour_monitor/analyzer.py` lines 629-678; called from coordinator line 590
- Cause: No caching; recalculates even if no state changes occurred
- Improvement path:
  - Cache entity_status with TTL; only invalidate on state change or anomaly detection
  - Memoize with @functools.lru_cache
  - Current impact: Minimal for 5-20 entities; scales poorly beyond 50+

**Event List Filtering on Every State Change:**
- Problem: Recent events filtered by timestamp O(n) on every state change
- Files: `custom_components/behaviour_monitor/coordinator.py` lines 481-482; `ml_analyzer.py` lines 330-332
- Cause: List comprehension filters entire event list rather than queue-based removal
- Improvement path: Replace list with collections.deque(maxlen=...); O(1) amortized complexity
- Current impact: Negligible for typical 100-500 events; noticeable at 10k+ events

**Full Event Replay on ML Retrain:**
- Problem: Every train() call replays all stored events through model (expensive for 10k+ events)
- Files: `custom_components/behaviour_monitor/ml_analyzer.py` lines 441-446
- Cause: River Half-Space Trees doesn't support incremental persistence; must warm up from scratch
- Improvement path: Checkpoint model every N retrains; implement delta replay (only new events since checkpoint); target 80% reduction
- Current impact: Retraining every 14 days; with 1000 events takes seconds; acceptable but could be faster

**Dictionary Key Normalization via Sort:**
- Problem: Cross-sensor pattern lookup sorts entities alphabetically on every state change
- Files: `custom_components/behaviour_monitor/ml_analyzer.py` lines 340-341
- Cause: Ensures key consistency but adds sort overhead
- Improvement path: Canonicalize during registration; use hash-based ordering
- Current impact: Negligible for 10-50 patterns; sorts < 100ns

## Fragile Areas

**Multi-Level Welfare Status Decision Tree:**
- Files: `custom_components/behaviour_monitor/analyzer.py` lines 680-742
- Why fragile: Nested if/elif chain with overlapping conditions (e.g., line 714 "if activity_context["status"] == "check_recommended" or attention_count > 2"); unclear priority when multiple conditions true
- Safe modification:
  - Create decision matrix/scoring system instead of cascading if/else
  - Extract condition evaluation to separate methods
  - Add comprehensive unit tests for all combinations of (activity_status, alert_count, concern_count, routine_status)
  - Document decision precedence explicitly
- Test coverage: test_analyzer.py has limited welfare status tests; no matrix of edge cases

**Z-Score Calculation Edge Cases:**
- Files: `custom_components/behaviour_monitor/analyzer.py` lines 444-450
- Why fragile: Three branches for variance = 0; logic tightly coupled to sensitivity_threshold; branch conditions not symmetrical
- Safe modification:
  - Extract to z_score_calculation function with unit tests for each branch
  - Add symbolic test cases (variance=0, actual=0, threshold=2.0, etc.)
  - Document why infinity vs threshold + 1 chosen for different branches
- Test coverage: test_analyzer.py::TestAnomalyDetection covers some cases but not edge branches

**Timestamp Serialization Format Assumption:**
- Files: `custom_components/behaviour_monitor/analyzer.py` lines 165-177; `coordinator.py` lines 213-237
- Why fragile: Multiple fromisoformat() calls with UTC fallback; assumes isoformat() always used
- Safe modification:
  - Enforce UTC-only storage (all timestamps serialized with +00:00)
  - Add version field to storage format for format migrations
  - Add round-trip serialization tests with multiple timezone scenarios
- Test coverage: PERSISTENCE_TESTS.md documents timezone tests; verify test_analyzer.py and test_coordinator.py actually exercise these

**ML Model State After from_dict() Deserialization:**
- Files: `custom_components/behaviour_monitor/ml_analyzer.py` lines 438-446 (from_dict), 641-700 (to_dict/from_dict logic)
- Why fragile: Model recreated from fresh HalfSpaceTrees instance; lost model state not preserved; events replayed to rebuild state
- Safe modification:
  - Document that from_dict() models start untrained until retrain() called
  - Add pre-retrain state assertions
  - Test that deserialized model produces same results as original
- Test coverage: test_ml_analyzer.py has serialization tests but not equivalence tests (original vs. deserialized)

## Scaling Limits

**ML Event List Unbounded Until Pruning:**
- Current capacity: 14-day retrain period at 1 event/min = ~20k events in memory; ~150 bytes per event = ~3MB
- Limit: At 10 events/min, reaches 30MB in 20 days; 100 events/min = 300MB in 20 days (problematic on constrained HA instances)
- Scaling path:
  - Implement automatic aggressive pruning (keep last 5k events, prune daily)
  - Use ring buffer (fixed-size deque) instead of unbounded list
  - Add memory warning if events_list exceeds configurable threshold
- Current protection: prune_old_events() called before retrain (coordinator line 365); protection only at 2x retrain_period

**Daily Counts Dictionary Reset:**
- Current capacity: One entry per entity per day; reset daily (correct)
- Limit: None; bounded to 24-hour window
- Scaling path: Already optimal; no action needed

**Pattern Storage Per Entity:**
- Current capacity: 7 days × 96 intervals = 672 buckets per entity; 50 entities = ~20k buckets at 40 bytes each = 800KB total
- Limit: 200+ entities × 672 = 134k buckets = ~5MB (acceptable for HA); 500+ entities = ~12MB (marginal)
- Scaling path: Could implement data rotation (archive old patterns weekly); compress summaries; no immediate concern

**Cross-Sensor Pattern Dictionary Growth:**
- Current capacity: N entities choose 2 = ~N²/2 patterns; 20 entities = 190 patterns; 50 entities = 1225 patterns
- Limit: Pattern matching becomes O(n²) at lookup; 1000+ entities would create 500k patterns (memory + lookup time significant)
- Scaling path: Currently acceptable; if needed, implement pattern culling (keep only strong patterns > threshold)

## Dependencies at Risk

**River ML Library Optional Dependency:**
- Risk: River import silently fails (ml_analyzer.py lines 15-25); ML features completely disabled without user awareness
- Impact: Users expecting ML features get statistics-only; confusion risk
- Current mitigation: Log WARNING at import, coordinator logs INFO/WARNING at startup (lines 94-106)
- Recommendations:
  - Add persistent_notification warning if ML requested but unavailable
  - Add diagnostic sensor showing ML availability/failure reason
  - Consider detecting River install failure during config and suggesting pip install

**Home Assistant Test Environment Requirement:**
- Risk: Tests require full Home Assistant installed; CI/dev setup problematic on ARM (README-DEV.md line 59)
- Impact: Blocks contributions; CI slow; development friction
- Current mitigation: Makefile provides multiple setup options (Docker, existing HA installation, pip)
- Recommendations:
  - Unit tests already isolated from HA (PatternAnalyzer, MLPatternAnalyzer independent)
  - Split test suite: unit tests (no HA required) vs. integration tests (requires HA)
  - Run unit tests in CI without full HA

## Missing Critical Features

**No Sensor Malfunction Detection:**
- Problem: Anomalies could be triggered by sensor stuck on same value, not actual behavior change
- Blocks: Can't distinguish inactivity from broken sensor
- Recommendations: Add sensor health check; flag entities with N consecutive identical values as "sensor_stuck"; suppress anomalies from stuck sensors

**No Manual Reset Without Complete Integration Deletion:**
- Problem: User can't reset learning without deleting integration and losing all config
- Blocks: If behavior intentionally changes (new schedule), patterns can't be recalibrated
- Recommendations: Add service behaviour_monitor.reset_learning or config flow button to clear patterns

**No Automatic Cleanup of Deleted Entities:**
- Problem: If user removes entity from monitored list, stored pattern data persists orphaned
- Blocks: Can't clean up storage for old entities without manual editing
- Recommendations:
  - Auto-prune patterns for non-existent entities on startup
  - Add diagnostic sensor showing stored vs. monitored entities
  - Add "cleanup storage" action in options flow

**No External Event Integration:**
- Problem: Welfare status based only on monitored entities; can't account for expected changes (visitor detected, scheduled event)
- Blocks: False welfare alerts when external factors explain pattern deviation
- Recommendations: Design webhook API for external services to register expected activity windows

## Test Coverage Gaps

**Welfare Status Transition Matrix:**
- What's not tested: All combinations of (activity_status, entity_alert_count, entity_concern_count, routine_status) → welfare_status
- Files: `tests/test_analyzer.py` (missing TestWelfareStatusTransitions class)
- Risk: Threshold changes could break decision logic; commit 71d357d shows multiple adjustments without validation
- Priority: High (welfare status is primary alert mechanism for elder care)
- Recommended fix: Add 4D matrix test covering all status combinations

**Timezone Edge Cases:**
- What's not tested: Midnight transitions; DST boundaries; operations in UTC vs local time
- Files: `tests/test_analyzer.py`, `tests/test_coordinator.py` (PERSISTENCE_TESTS.md documents some tests)
- Risk: Could incorrectly assign activities to previous/next day on timezone boundaries
- Priority: Medium (daily count resets depend on accurate timezone handling)
- Recommended fix: Add parameterized tests for UTC, EST, JST, and DST transition times

**Cross-Sensor Correlation Calculation:**
- What's not tested: correlation_strength() with edge inputs (same entity, zero co-occurrences, single observation)
- Files: `tests/test_ml_analyzer.py` (CrossSensorPattern not directly tested)
- Risk: Incorrect strength values reported; unexpected patterns marked as strong
- Priority: Medium (affects anomaly flagging)
- Recommended fix: Unit test CrossSensorPattern with symbolic inputs

**Notification Service Failure Handling:**
- What's not tested: Partial failures (2 of 3 notify services throw); timeout; malformed service_data
- Files: `tests/test_coordinator.py` (notification tests mock success only)
- Risk: One bad notify service could block all notifications
- Priority: Medium (notification reliability important for elder care)
- Recommended fix: Test partial failures; verify all services called even if one fails

**High-Frequency State Changes:**
- What's not tested: 100+ events in single interval; rapid successive changes on same entity
- Files: `tests/test_coordinator.py`, `tests/test_analyzer.py` (tests use reasonable event spacing)
- Risk: Z-score calculations could overflow with extreme frequencies
- Priority: Low (use-case dependent)
- Recommended fix: Stress test with 10+ events/second on single entity

**ML Model Retraining Edge Cases:**
- What's not tested: Retrain with fewer events than MIN_SAMPLES_FOR_ML; concurrent train() calls; memory usage with 10k+ events
- Files: `tests/test_ml_analyzer.py` (train() tested but not edge cases)
- Risk: Retraining under resource constraints could crash coordinator
- Priority: High (production reliability)
- Recommended fix: Add tests for undersampled retrain, concurrent calls, memory monitoring

**Serialization with Zero-Variance Data:**
- What's not tested: Patterns where all buckets have single observation (std_dev = 0); patterns spanning timezone boundaries
- Files: `tests/test_analyzer.py`, `tests/test_ml_analyzer.py`
- Risk: Data loss in edge cases discovered only in production
- Priority: Medium (rare but high-impact)
- Recommended fix: Add round-trip serialization tests with synthetic edge-case data

---

*Concerns audit: 2026-03-13*
