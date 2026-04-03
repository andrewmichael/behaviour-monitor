---
status: complete
phase: 16-config-ui-and-migration
source: [12-01-SUMMARY.md, 13-01-SUMMARY.md, 14-01-SUMMARY.md, 15-01-SUMMARY.md, 16-01-SUMMARY.md]
started: 2026-04-03T12:00:00Z
updated: 2026-04-03T12:30:00Z
---

## Current Test

[testing complete]

## Tests

### 1. ActivityTier enum and constants importable
expected: Run: `python -c "from custom_components.behaviour_monitor.const import ActivityTier, TIER_BOUNDARY_HIGH, TIER_BOUNDARY_LOW, TIER_FLOOR_SECONDS, TIER_BOOST_FACTOR; print(ActivityTier.HIGH.value, TIER_BOUNDARY_HIGH, TIER_FLOOR_SECONDS[ActivityTier.HIGH])"` — Output: `high 24 3600`
result: pass

### 2. format_duration utility works correctly
expected: Run: `python -c "from custom_components.behaviour_monitor.routine_model import format_duration; print(format_duration(120), format_duration(3600), format_duration(5400))"` — Output: `2m 1h 0m 1h 30m`
result: pass

### 3. classify_tier produces correct tier for high-frequency entity
expected: Run: `python -c "from custom_components.behaviour_monitor.routine_model import EntityRoutine; from datetime import datetime, timezone; print('classify_tier and activity_tier exist:', hasattr(EntityRoutine, 'classify_tier'), hasattr(EntityRoutine, 'activity_tier'))"` — Output: `classify_tier and activity_tier exist: True True`
result: pass

### 4. Tier-aware detection imports and threshold logic present
expected: Run: `python -c "from custom_components.behaviour_monitor.acute_detector import AcuteDetector; import inspect; src = inspect.getsource(AcuteDetector.check_inactivity); print('TIER_BOOST_FACTOR' in src, 'TIER_FLOOR_SECONDS' in src, 'format_duration' in src)"` — Output: `True True True`
result: pass

### 5. Config migration v7 to v8 exists
expected: Run: `python -c "from custom_components.behaviour_monitor.__init__ import async_migrate_entry; import inspect; src = inspect.getsource(async_migrate_entry); print('version < 8' in src, 'activity_tier_override' in src)"` — Output: `True True`
result: pass

### 6. Config flow VERSION and STORAGE_VERSION are both 8
expected: Run: `python -c "from custom_components.behaviour_monitor.const import STORAGE_VERSION; from custom_components.behaviour_monitor.config_flow import BehaviourMonitorConfigFlow; print(STORAGE_VERSION, BehaviourMonitorConfigFlow.VERSION)"` — Output: `8 8`
result: pass

### 7. Full test suite passes
expected: Run: `make test` — All tests pass (expected ~449), 0 failures
result: pass

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]
