# Handoff: Behaviour Monitor changes from HA review 17

Three changes for the `behaviour_monitor` integration, found in a review of the Home Assistant instance that runs it at
Biddulph Road (a relative's home with welfare monitoring). Written 4 Nov 2026 against v6.1.1, the installed version; the repo was
3 commits past that tag, planning files only. Finding numbers (262, 287, 288) are the review's. Moved here from the Home Assistant
repo (`docs/handoff/`) on 8 Nov 2026; work from it.

Line numbers are from 4 Nov. Paths are under `custom_components/behaviour_monitor/`. Tests are in `tests/core/`.

Order: 1 is the most important, because a flat panic button is the worst failure here. 2 is small. 3 needs a decision.

## 1. Battery monitoring (finding 262)

**Problem.** Nothing monitors the batteries of the devices Behaviour Monitor depends on: no code in the integration mentions batteries, and on
the HA side no dashboard, helper or automation reads them. Panic buttons are the worst case. `HealthTracker._silent` skips
`Category.PANIC` (`core/health_tracker.py:119`) because a panic button rarely fires, so the battery is the only early sign for a device
that is never pressed. A flat landing button keeps reading Safe, and the first press in a fall does nothing.

**Why here and not in HA.** The integration already owns device health for these sensors, and it can reach the battery from the entities it
is configured with. Doing it here also covers any other site.

**Live data, 4 Nov.** 13 Tuya battery devices, all `sensor.*` with device class `battery`:

| Sensor | Reading |
|---|---|
| `sensor.side_door_battery` | 30 |
| `sensor.kitchen_battery` | 55 |
| `sensor.panic_button_hall_battery` | 80 |
| `sensor.panic_button_landing_battery` | 80 |
| `sensor.front_room_battery`, `back_room_battery`, `front_bedroom_battery`, `bathroom_battery` | 100 |
| `sensor.front_door_battery_2`, `back_door_battery`, `motion_sensor_battery`, `motion_sensor_2_battery` | 100 |
| `sensor.back_bedroom_battery` | 104 (so readings can exceed 100) |

The entity ids do not always match the monitored entity's name (`binary_sensor.front_door_door` has `sensor.front_door_battery_2`), so
match by device, not by name. The plugs have no battery.

**Suggested design.**
- For each configured entity, find a sibling on the same device with device class `battery` through the device and entity registries. No new
  config field is needed for the normal case. Re-check when the entity list changes.
- Ignore `unavailable` and `unknown`, and non-numeric values. Treat anything over 100 as 100.
- Raise an `AlertClass.HEALTH` alert in `HealthTracker.evaluate` when a battery is below its limit. Keep one alert per device, keyed on its
  source so it updates in place and clears when the reading recovers. Follow the existing health alerts at `core/health_tracker.py:175-212`.
- Limits: 25% for general devices, higher for panic buttons (the review suggested a higher limit without fixing a number; 40% is a starting point).
  Make them options.
- Require the low reading to hold, say 6 hours, so a cold-night dip does not alert.
- Add `battery` to each row of the `entities` attribute (`core/engine.py:424`) with the level, or null if there is none, so the dashboard can show it.

**Still to settle.**
- Does a flat Tuya button ever go `unavailable`, or does it just stop reporting? Nobody has seen one go flat. If it stays available, a battery
  reading is all there is, and a Tuya battery value may itself stop updating when flat. Consider also flagging a battery value that has not changed for a long
  time on a panic button.
- A periodic reminder to press-test the panic buttons. Only a real press proves one works. `AlertRouter.submit_test` exists and may help. The cadence is
  for Andrew to choose; monthly was suggested.

## 2. Acknowledge does not stick (finding 287)

**Problem.** Acknowledging a welfare alert stops the repeat pushes, but the page shows 'New alert · tap to acknowledge' again about 10 s later,
because `raised_at` moves forward on every poll.

**Cause.** `routine_agreement` and `inactivity` alerts are rebuilt with `raised_at = now` on each evaluation. `AlertRouter.submit` then replaces the open
alert with the new one at `core/alert_router.py:77`:

```python
rose = alert.severity > cur.alert.severity
cur.alert = alert
```

HA's `binary_sensor.welfare_alert_unacknowledged` compares the Acknowledge press time with each open welfare alert's `raised_at`, so a newer
`raised_at` reads as a new alert. `_Open.acknowledged` is correct inside the router but is not published.

**Evidence.** 1 Nov: Acknowledge pressed 13 times between 13:46:47 and 13:53:02; each time the helper went off, then back on about 10 s later
(13:46:48 off, 13:46:57 on). 3 Nov: pressed 23:29:54, back on 23:30:04, and it stayed on until the alert cleared at midnight.

**Fix.** Keep the original `raised_at` while an alert stays open, unless its severity rose. A rise should count as new, because it resets `acknowledged`
and pushes again:

```python
rose = alert.severity > cur.alert.severity
if not rose:
    alert.raised_at = cur.alert.raised_at
cur.alert = alert
```

Also publish `acknowledged` for each alert in `open_alerts` (`core/engine.py:381`), so HA can read the real state rather than infer it from timestamps.
`Alert` is a plain dataclass, so either add a field or merge the value in where `open_alerts` is built.

**Tests.** In `tests/core/test_alert_router.py`: `raised_at` stays put across repeated `submit` calls; a severity rise updates it and clears `acknowledged`;
`acknowledged` survives a repeated `submit`. Check that the `to_dict` and restore paths still round-trip.

## 3. Drift lines contradict their own numbers (finding 288)

**Problem.** The welfare page shows lines such as 'Back bedroom motion: used less than usual for 16 days (usually 70 a day, yesterday 82)',
in red 'High', under a banner saying 'Everything looks normal'. Four of the six open alerts read like that on 4 Nov. Readers learn to ignore the list, and a
real slow decline would appear on that list.

**Cause.** `core/drift_detector.py`:
- `direction` comes from which CUSUM sum is larger (`:110`). The sums persist after values turn around, so the direction can oppose yesterday's value.
- `sev = Severity.HIGH if st.days_above >= 7 else Severity.MEDIUM` (`:111`). Anything past 7 days goes High and stays there, even if it has settled.

**Live examples, 4 Nov.**
- Back bedroom motion: less than usual for 16 days, usually 70 a day, yesterday 82
- Front room motion: time spent higher for 28 days, usual 73 s, yesterday 62 s
- Back bedroom: time spent higher, usual 68 s, yesterday 62 s
- Front bedroom: time spent higher, usual 65 s, yesterday 62 s

**Options, to choose from.**
- Decay or reset the CUSUM when values cross back over the baseline, so a settled drift clears by itself. This is the real fix. Check it against the
  long-horizon decline milestone: decaying too fast could hide a slow decline, which is what this detector is for.
- Publish a `settled` or `current_direction` value in `details`, so the page can tell 'still drifting' from 'drifted, now back'.
- Do not map days alone to High. Severity could follow how far the value is from the baseline.

**Tests.** In `tests/core/test_drift_detector.py`: a series that drifts and returns stops alerting within a set number of days, and a sustained slow decline
still alerts. `tests/core/test_replay_scenarios.py` may be the place for the second.

## HA side, after a release

These live in the Home Assistant repo, not here, and wait for the integration change:
- Biddulph Road > Welfare > Devices: show the new `battery` values and any low ones (`ha/dashboards/biddulph-road.yaml`).
- 287: `binary_sensor.welfare_alert_unacknowledged` (template helper) reads the published `acknowledged` value if it is added.
- 288: the drift wording and icon in the Open alerts card (`ha/dashboards/biddulph-road.yaml`, the `kind == 'drift'` lines) say 'for N days (usual, yesterday)'
  and use the same red High. Reword it as a trend, with a neutral icon, using whatever the integration publishes.
- `docs/known-and-accepted.md` and `docs/followups.md` get updated when these land.

Things the HA side already does, so they need no change here: the banner shows 'Monitoring paused' in holiday mode, critical alerts are listed in Open
alerts, the sensor-down alert fires if the integration itself stops reporting, and a 'Last activity by sensor' card flags a quiet motion sensor or door.
