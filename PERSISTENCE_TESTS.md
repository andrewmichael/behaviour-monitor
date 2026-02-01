# Persistence Tests Summary

This document describes the new tests added for daily counts and coordinator state persistence.

## Overview

New tests have been added to verify that transient data correctly survives Home Assistant reboots:
- **Daily activity counts** (analyzer.py)
- **Notification tracking** (coordinator.py)
- **Welfare status tracking** (coordinator.py)

## Test Files Modified

### 1. tests/test_analyzer.py

Added new test class: `TestDailyCountsPersistence` with 8 tests:

#### Test Coverage

1. **test_daily_counts_saved_in_to_dict**
   - Verifies daily counts are included in serialization
   - Checks both `daily_counts` and `daily_count_date` fields exist

2. **test_daily_counts_restored_same_day**
   - Tests that daily counts are correctly restored when loading data from the same day
   - Verifies per-entity counts and total count

3. **test_daily_counts_not_restored_different_day**
   - Ensures daily counts from yesterday are NOT restored (should start fresh)
   - Critical for preventing data pollution across day boundaries

4. **test_backward_compatibility_no_daily_counts**
   - Tests old format (without daily_counts) still loads correctly
   - Ensures existing installations upgrade smoothly

5. **test_daily_counts_persist_across_multiple_saves**
   - Verifies counts accumulate correctly across multiple save/load cycles
   - Simulates multiple HA restarts during the same day

6. **test_daily_count_date_timezone_handling**
   - Ensures timezone-aware datetime handling works correctly

7. **test_routine_progress_uses_persisted_daily_counts**
   - Integration test verifying routine progress calculation uses restored counts
   - Critical for elder care monitoring

### 2. tests/test_coordinator.py

Added new test class: `TestCoordinatorStatePersistence` with 8 tests:

#### Test Coverage

1. **test_coordinator_state_saved_in_new_format**
   - Verifies new storage format has both "analyzer" and "coordinator" sections
   - Checks notification time, type, and welfare status are saved

2. **test_coordinator_state_restored_from_new_format**
   - Tests restoration of coordinator state from new format
   - Verifies all three state variables are correctly restored

3. **test_backward_compatibility_with_old_format**
   - Ensures old format (just analyzer dict) still loads
   - Coordinator state defaults to None values

4. **test_notification_tracking_persists_across_save_load**
   - End-to-end test of notification tracking persistence
   - Creates new coordinator instance and verifies state transfer

5. **test_welfare_status_persists_across_save_load**
   - End-to-end test of welfare status persistence
   - Prevents duplicate welfare notifications after reboot

6. **test_empty_coordinator_state_handles_none_values**
   - Tests graceful handling of None values in coordinator state

7. **test_notification_time_timezone_handling**
   - Ensures notification timestamps maintain timezone awareness

## Running the Tests

### Prerequisites

Tests require Home Assistant to be installed. See README-DEV.md for setup instructions.

### Run All New Tests

```bash
# Activate venv (if not already active)
source venv/bin/activate

# Run analyzer persistence tests
pytest tests/test_analyzer.py::TestDailyCountsPersistence -v

# Run coordinator persistence tests
pytest tests/test_coordinator.py::TestCoordinatorStatePersistence -v

# Run all tests
make test
```

### Run Specific Tests

```bash
# Test daily counts restoration on same day
pytest tests/test_analyzer.py::TestDailyCountsPersistence::test_daily_counts_restored_same_day -v

# Test backward compatibility
pytest tests/test_coordinator.py::TestCoordinatorStatePersistence::test_backward_compatibility_with_old_format -v
```

## What's Being Tested

### Daily Counts Persistence
- ✅ Counts are saved during serialization
- ✅ Counts are restored when date matches
- ✅ Counts are reset when date differs (new day)
- ✅ Old format without counts still loads
- ✅ Multiple save/load cycles work correctly
- ✅ Timezone handling is correct
- ✅ Routine progress uses persisted counts

### Coordinator State Persistence
- ✅ New format includes coordinator section
- ✅ Coordinator state is restored correctly
- ✅ Old format (without coordinator section) still works
- ✅ Notification tracking survives reboot
- ✅ Welfare status survives reboot
- ✅ None values are handled gracefully
- ✅ Timezone handling for timestamps

## Storage Format

### New Format (After Update)
```json
{
  "analyzer": {
    "patterns": {...},
    "sensitivity_threshold": 2.0,
    "learning_period_days": 7,
    "daily_counts": {
      "sensor.test1": 5,
      "sensor.test2": 3
    },
    "daily_count_date": "2024-01-15T00:00:00+00:00"
  },
  "coordinator": {
    "last_notification_time": "2024-01-15T14:30:00+00:00",
    "last_notification_type": "statistical",
    "last_welfare_status": "ok"
  }
}
```

### Old Format (Backward Compatible)
```json
{
  "patterns": {...},
  "sensitivity_threshold": 2.0,
  "learning_period_days": 7
}
```

## Expected Behavior After Reboot

### Before This Update
- ❌ Daily counts reset to 0
- ❌ Routine progress shows 0% even if active
- ❌ Activity score artificially drops
- ❌ Last notification sensor shows "Unknown"
- ❌ May send duplicate welfare notifications

### After This Update
- ✅ Daily counts preserved if same day
- ✅ Routine progress accurate after reboot
- ✅ Activity score reflects actual activity
- ✅ Last notification sensor shows correct time
- ✅ No duplicate welfare notifications

## Verification Steps

After deploying to Home Assistant:

1. **Test Daily Counts Persistence:**
   - Note current daily activity count
   - Restart Home Assistant
   - Verify count is preserved (same day)
   - Wait until next day
   - Verify count resets to 0

2. **Test Notification Tracking:**
   - Trigger an anomaly notification
   - Note the "Last Notification" sensor value
   - Restart Home Assistant
   - Verify sensor still shows last notification time

3. **Test Welfare Status:**
   - Wait for welfare status to be non-"ok"
   - Restart Home Assistant
   - Verify no duplicate notification is sent

## Notes

- All tests use proper timezone-aware datetime handling
- Backward compatibility is maintained for existing installations
- Tests follow existing project patterns (pytest, fixtures, mocking)
- Syntax validation passed ✓
