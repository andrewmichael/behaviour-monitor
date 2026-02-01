# Holiday Mode and Visitor Snooze

This document describes the Holiday Mode and Visitor/Snooze features added to Behaviour Monitor.

## Overview

Two new modes help manage tracking during exceptional circumstances:

### 🏖️ Holiday Mode
**Complete Pause** - Use when the monitored person is away

- ✋ **No state tracking** - State changes are completely ignored
- ✋ **No pattern learning** - Statistical baselines and ML models not updated
- ✋ **No anomaly detection** - No checks performed
- ✋ **No notifications** - All alerts disabled
- 🔄 **Persists across reboots** - Stays enabled until manually disabled

**Use Case:** Person is on vacation, visiting family, or otherwise away from home. Prevents false welfare alerts and keeps baseline patterns clean.

### 🔕 Visitor/Snooze Mode
**Temporary Pause** - Use when unusual but expected activity occurs

- ✅ **State tracking continues** - Events are logged (for ML history)
- ✋ **Pattern learning paused** - Statistical baselines not updated
- ✋ **ML training paused** - ML models not updated with visitor activity
- ✋ **No anomaly detection** - No checks performed
- ✋ **No notifications** - All alerts suppressed
- ⏰ **Auto-expires** - Automatically resumes after set duration
- 🔄 **Persists across reboots** - If HA reboots during snooze, it continues

**Use Case:** Visitors staying overnight, care worker present, unusual scheduled event. Prevents contaminating baseline patterns while maintaining event history.

## New Entities

### Switch: Holiday Mode
- **Entity ID:** `switch.behaviour_monitor_holiday_mode`
- **Icon:** `mdi:beach`
- **States:** `on` / `off`

**Controls:**
- Turn on: Enable holiday mode
- Turn off: Disable holiday mode and resume tracking

**Attributes:**
```yaml
description: When enabled, all tracking and learning is paused...
```

### Select: Snooze Notifications
- **Entity ID:** `select.behaviour_monitor_snooze_notifications`
- **Icon:** `mdi:bell-sleep`
- **Options:** Off, 1 Hour, 2 Hours, 4 Hours, 1 Day

**Controls:**
- Select duration: Activates snooze for chosen period
- Select "Off": Immediately clears active snooze

**Attributes:**
```yaml
snooze_active: true/false
snooze_until: "2026-02-01T14:30:00+00:00"  # When snooze expires
description: Temporarily pause anomaly detection...
```

## Services

### behaviour_monitor.enable_holiday_mode
Enable holiday mode.

```yaml
service: behaviour_monitor.enable_holiday_mode
```

**Example Automation:**
```yaml
automation:
  - alias: "Enable Holiday Mode on Vacation"
    trigger:
      - platform: calendar
        event: start
        entity_id: calendar.vacation
    action:
      - service: behaviour_monitor.enable_holiday_mode
```

### behaviour_monitor.disable_holiday_mode
Disable holiday mode and resume tracking.

```yaml
service: behaviour_monitor.disable_holiday_mode
```

### behaviour_monitor.snooze
Snooze notifications for a specified duration.

```yaml
service: behaviour_monitor.snooze
data:
  duration: "2_hours"  # Options: 1_hour, 2_hours, 4_hours, 1_day
```

**Example Automation:**
```yaml
automation:
  - alias: "Snooze during care worker visit"
    trigger:
      - platform: state
        entity_id: binary_sensor.care_worker_present
        to: "on"
    action:
      - service: behaviour_monitor.snooze
        data:
          duration: "4_hours"
```

### behaviour_monitor.clear_snooze
Clear active snooze immediately.

```yaml
service: behaviour_monitor.clear_snooze
```

## Dashboard Examples

### Lovelace Card - Quick Controls
```yaml
type: entities
title: Behaviour Monitor Controls
entities:
  - entity: switch.behaviour_monitor_holiday_mode
    name: Holiday Mode
  - entity: select.behaviour_monitor_snooze_notifications
    name: Snooze Duration
```

### Button Card - Quick Snooze
```yaml
type: button
tap_action:
  action: call-service
  service: behaviour_monitor.snooze
  service_data:
    duration: "1_hour"
name: Snooze 1 Hour
icon: mdi:bell-sleep
show_state: false
```

### Conditional Card - Show When Active
```yaml
type: conditional
conditions:
  - entity: switch.behaviour_monitor_holiday_mode
    state: "on"
card:
  type: markdown
  content: |
    ⚠️ **Holiday Mode Active**
    All behaviour tracking is paused.
```

## Sensor Data

All coordinator data now includes holiday mode and snooze status:

```python
coordinator.data = {
    ...
    "holiday_mode": bool,
    "snooze_active": bool,
    "snooze_until": "ISO8601 timestamp" or None,
    ...
}
```

**Access in Templates:**
```yaml
# Check if holiday mode active
{{ state_attr('sensor.behaviour_monitor_last_activity', 'holiday_mode') }}

# Check if snoozed
{{ state_attr('sensor.behaviour_monitor_last_activity', 'snooze_active') }}

# Get snooze end time
{{ state_attr('sensor.behaviour_monitor_last_activity', 'snooze_until') }}
```

## Behavior During Modes

### State Change Handling

**Normal Operation:**
```
State Change → Record in Statistical Analyzer → Update ML → Check Anomalies → Send Notifications
```

**Holiday Mode:**
```
State Change → [IGNORED - all processing skipped]
```

**Snooze Mode:**
```
State Change → Track for ML History → [Skip pattern updates] → [Skip anomaly detection] → [Skip notifications]
```

### What Gets Logged

**Normal:**
```
INFO: Behaviour Monitor: Recorded state change for sensor.motion: off -> on (daily total: 15)
```

**Holiday Mode:**
```
[No log - state change completely ignored]
```

**Snooze:**
```
INFO: Behaviour Monitor: Recorded state change for sensor.motion: off -> on (daily total: 15) [SNOOZED - patterns not updated]
```

## Persistence

Both modes persist across Home Assistant reboots:

**Storage Location:** `.storage/behaviour_monitor.{entry_id}.json`

**Format:**
```json
{
  "coordinator": {
    "holiday_mode": true,
    "snooze_until": "2026-02-01T14:30:00+00:00",
    ...
  }
}
```

**Restoration Behavior:**
- **Holiday Mode:** Restored exactly as saved
- **Snooze:** Only restored if not expired (checked against current time)

## Implementation Details

### Coordinator State Variables
```python
self._holiday_mode: bool = False
self._snooze_until: datetime | None = None
```

### Check Methods
```python
coordinator.holiday_mode -> bool
coordinator.is_snoozed() -> bool
coordinator.snooze_until -> datetime | None
coordinator.get_snooze_duration_key() -> str  # For select entity
```

### Control Methods
```python
await coordinator.async_enable_holiday_mode()
await coordinator.async_disable_holiday_mode()
await coordinator.async_snooze(duration_key: str)
await coordinator.async_clear_snooze()
```

## Example Use Cases

### 1. Weekend Vacation
```yaml
# Before leaving Friday evening
service: behaviour_monitor.enable_holiday_mode

# Upon return Sunday evening
service: behaviour_monitor.disable_holiday_mode
```

### 2. Overnight Guest
```yaml
# Guest arrives 6 PM
service: behaviour_monitor.snooze
data:
  duration: "1_day"

# Snooze automatically expires 6 PM next day
```

### 3. Care Worker Visit
```yaml
# Automation triggers when care worker arrives
service: behaviour_monitor.snooze
data:
  duration: "4_hours"
```

### 4. Planned Unusual Activity
```yaml
# Family gathering scheduled
service: behaviour_monitor.snooze
data:
  duration: "4_hours"

# If they leave early, manually clear:
service: behaviour_monitor.clear_snooze
```

## Migration Notes

### Backward Compatibility
- Old installations without these features will load with modes disabled
- No migration needed - modes default to off/None
- Storage format includes both old and new sections

### Upgrading From v2.6.0
1. Update integration files
2. Restart Home Assistant
3. New entities appear automatically:
   - `switch.behaviour_monitor_holiday_mode`
   - `select.behaviour_monitor_snooze_notifications`
4. Services registered automatically

## Testing

### Verify Holiday Mode
1. Check current daily count: `sensor.behaviour_monitor_daily_activity_count`
2. Enable holiday mode: `switch.behaviour_monitor_holiday_mode` to ON
3. Trigger some monitored sensors
4. Verify daily count doesn't increase
5. Check logs - should show no "Recorded state change" messages
6. Disable holiday mode
7. Trigger sensors again - count should now increase

### Verify Snooze Mode
1. Check current daily count
2. Set snooze: `select.behaviour_monitor_snooze_notifications` to "1 Hour"
3. Trigger monitored sensors
4. Verify daily count doesn't increase (patterns not updated)
5. Check logs - should show "SNOOZED - patterns not updated"
6. Set select to "Off" to clear
7. Trigger sensors - count should increase

### Verify Persistence
1. Enable holiday mode
2. Restart Home Assistant
3. Verify switch still shows ON
4. Set snooze for 1 day
5. Restart Home Assistant
6. Verify select still shows snooze active

## Troubleshooting

### Holiday Mode Not Working
**Symptom:** State changes still being recorded
**Check:**
- Verify switch entity shows "on"
- Check coordinator.data["holiday_mode"] is true
- Review logs for "State change event received"

### Snooze Not Expiring
**Symptom:** Snooze stays active past expiration time
**Check:**
- Verify select entity
- Check coordinator.data["snooze_until"] timestamp
- Check coordinator.data["snooze_active"]
- May need to manually select "Off"

### Modes Not Persisting
**Symptom:** Modes reset after HA restart
**Check:**
- Verify `.storage/behaviour_monitor.{entry_id}.json` contains coordinator section
- Check file permissions
- Review startup logs for "Loaded coordinator state"

## Files Modified

- ✅ `const.py` - Added constants for modes and services
- ✅ `coordinator.py` - Added mode handling and persistence
- ✅ `switch.py` - NEW - Holiday mode switch entity
- ✅ `select.py` - NEW - Snooze duration select entity
- ✅ `__init__.py` - Registered platforms and services
- ✅ `services.yaml` - NEW - Service definitions for UI
