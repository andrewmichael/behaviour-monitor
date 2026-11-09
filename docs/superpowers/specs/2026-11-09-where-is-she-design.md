# "Where is she": faster fall detection without outing false alarms

Date: 9 Nov 2026. Status: draft for approval.

## Intent

Tell the family within about an hour when she may have fallen or been taken
ill at home, without alerting every time she goes out.

The scorecard (`scripts/scorecard.py`) on Biddulph Road's real data
(18 Sep to 8 Nov 2026) shows the problem with today's whole-house
inactivity alert. It rarely raises a false alarm (2 in 43 days, both outings),
but a fall takes a median of 3h15m to alert, and afternoon falls up to 6h35m.
The owner wants to know within an hour, with as close to zero false alarms
as possible.

Both false alarms, and every confirmed outing, have the same shape in the
data: an outside door opens, the house goes quiet, and the door opens again
when she comes back. A fall at home looks different: movement in a room, then
silence, with no door in between. Knowing *where she probably is* lets the
monitor be quick when she is at home, and patient when she is out.

## Evidence (throwaway experiment, 9 Nov 2026)

A throwaway detector built on the rules below was replayed over the 25 days
after the 14-day learning period, with 161 injected falls (every hour from
08:00 to 20:00 on ordinary days):

| | False alarms in 25 days | Falls: median time to alert | 90% within |
|---|---|---|---|
| Today's model | 1 (+1 outing) | 3h15m | about 6h |
| This design (TV allowance 90 min) | 1 | 80 min | 90 min |

The one remaining false alarm (18 Oct) was during a guest stay and a
maintenance day. They went out with no door event recorded, most likely
because Home Assistant was restarting. With a 60-minute TV allowance the
median fell to 50 min, but false alarms rose to 8. The owner chose 90
minutes.

The experiment was 25 days for one person, so the numbers must be re-checked
on the scorecard as the InfluxDB history grows.

**Reference.** The experiment's code is kept at
`docs/superpowers/specs/2026-11-09-where-is-she-spike.py`. It is throwaway, not
production code, but it is the reference for the rules below. Where this
document and the spike disagree, this document wins; where this document is
silent, do what the spike does. Run it with `--tv-cap=90 --morning-cap=90`
to reproduce the table.

## Goals

1. Replace the whole-house inactivity welfare alert with one that knows
   whether she is at home moving about, at home with the TV on, in bed, lying
   in, or out.
2. At home: alert within about an hour of stillness. Learn the limit from her
   own stillness at that hour, clamped between 45 and 60 minutes.
3. TV on in the room where she was last seen: allow up to 90 minutes of
   stillness (the owner's choice).
4. Out: never raise a fall alert. Alert only if she is not back well after
   her usual outing length.
5. Night and morning: stillness in bed is normal. Alert if she is not up
   after her usual waking time, and allow a lie-in after she first stirs.
6. Keep holiday mode, snooze, panic, device health, routine, chain and drift
   alerts working as they do now.

## Non-goals

- Detecting a fall outside the house. Indoor sensors can't see it.
- Battery monitoring, dead-sensor detection, restart storms (roadmap item 1,
  separate work).
- Several occupants (household size milestone).
- Changing how events reach Home Assistant. This only changes when the
  welfare alert opens, through the same `behaviour_monitor_alert` events,
  groups and blueprint.

## Anti-goals

- A fall at home while she is moving about must never wait for the "not back
  yet" rule. The out state needs evidence: an outside door, then no indoor
  movement.
- An outing must never raise a fall alert, however long it lasts. Only "not
  back yet" applies.
- A missing or late signal (a restart, an unavailable sensor) must not turn
  into "she's fine". When in doubt the monitor treats her as at home, which
  alerts sooner.

## Design

### States

The engine keeps one of these at all times, from the activity stream it
already gets from the normaliser:

| State | Entered when | Welfare alert |
|---|---|---|
| `home` | any indoor activity (presence, appliance on, a door followed by indoor movement within 10 min) | after stillness exceeds the at-home limit for the current hour |
| `home_tv` | `home`, and a sitting appliance (a TV) in the room where she was last seen is on | after 90 minutes of stillness |
| `asleep` | last seen in a bedroom, from 20:00 until 05:00 | if no activity outside a bedroom by her usual waking time + 60 min |
| `lying_in` | last seen in a bedroom between 05:00 and 11:00, outside `asleep` | after 90 minutes of stillness |
| `out` | an outside door opens and no indoor movement follows within 10 min | if not back after her longest outing so far × 1.25 |

"Activity" means a motion presence, a door opening, or an appliance turning on
(the normaliser's `PRESENCE`, `OPEN`, `APPLIANCE_ON`). Lights (`LIGHT_ON`) and
`GENERIC` events do **not** count for this alert, because lights switched by
automations would keep resetting the clock and hide a fall. The shared
`ACTIVITY_KINDS` used by routines, chains, health and learning is unchanged;
only this alert uses the narrower set. An appliance turning off and a door
closing are not activity.

### Exact rules (as in the spike)

- **Stillness intervals.** Each activity starts a new stillness interval that
  runs until the next activity. The state, room and TV flag are fixed when
  the interval *starts* (from the activity that started it), and the alert
  deadline for that interval is fixed then too.
- **TV flag.** True when a sitting appliance in the room where she was last
  seen is on at the start of the interval. A TV turning off later neither
  resets stillness nor shortens the allowance.
- **Out.** An outside door opening starts an `out` interval when no `PRESENCE`
  follows within 10 minutes. Exception *(my call; the spike counted any
  room)*: presence in the door's own room within the first 2 minutes is her
  walking out and does not count. At Biddulph Road the side and back doors
  are in the utility room, which has no motion sensor, and the front door is
  in the hall.
- **Precedence**, checked in this order: `out`, then `asleep`, then `lying_in`,
  then `home_tv`, then `home`. So a bedroom TV left on at night is `asleep`;
  a fall in the bedroom at 21:00 is only caught by `not_up` in the morning.
  The owner accepted "no alert for stillness in bed at night".
- **Night and morning.**
  - An interval that starts in a bedroom between 20:00 and 05:00 is `asleep`.
    It lasts until the next activity, past 05:00 if she sleeps on. Its
    deadline is her usual waking time + 60 minutes on the following morning
    (the same morning if it started after midnight).
  - An interval that starts in a bedroom between 05:00 and 11:00 is
    `lying_in`, with a 90-minute deadline. Activity in the bedroom after
    05:00, or a trip to the bathroom and back, starts a new interval. The
    `not_up` deadline doesn't apply to `lying_in`.
  - From 11:00, a bedroom is treated like any room: `home` (a nap gets the
    45–60 minute limit) or `home_tv`.
- **Usual waking time** is learned from the first activity of the day outside
  a bedroom after 04:00.

### Learned values (rolling, the same learning window as the other models)

- **At-home limit per hour of day:** the 99.5th percentile of her quiet gaps
  in `home` that start in that hour, clamped to 45–60 minutes. Before
  learning completes, 60 minutes.
- **Usual waking time:** the 95th percentile, over days, of the first
  activity outside a bedroom after 04:00. Before learning, 09:00.
- **Longest outing:** the longest `out` interval seen. Before any outing is
  seen, 4 hours.
- **Bedrooms:** rooms whose name contains "bedroom" (case-insensitive).
  There is no selector for now *(my call)*. At Biddulph Road: Front bedroom
  and Back bedroom.
- **Quiet gaps for the percentile:** the lengths of `home` intervals (not
  `home_tv`, `out`, `asleep` or `lying_in`), grouped by the hour each
  interval started, over the learning window.

### Configuration

Two new optional lists in the options flow, as entity selectors:

- **Outside doors:** contact sensors that lead outside. Default: every
  contact sensor. At Biddulph Road all three contacts are outside doors.
- **Sitting appliances:** plugs whose "on" means she is sitting nearby, such
  as a TV. Default: none. At Biddulph Road: the back room TV
  (`sensor.smart_plug_power`) and the front bedroom TV
  (`sensor.front_bedroom_tv_power`).

Fixed values (not options, for now): 45/60-minute clamp, 90-minute TV
allowance, 90-minute lie-in, 60 minutes after waking time, 10-minute "door
then movement" window, outing × 1.25, night from 20:00 to 05:00, lie-in until
11:00. They live together in one config dataclass so the scorecard can
explore them.

### Alerts

Welfare class, group `attention` through the existing router, replacing the
`house` / `inactivity` alert:

| Kind | Example explanation | Severity |
|---|---|---|
| `still_at_home` | "No movement for 62 min; last seen in the Kitchen at 10:12" | Medium at the limit, High at 1.5× the limit |
| `still_tv` | "No movement for 91 min with the Back room TV on; last seen at 19:05" | Medium, High at 1.5× |
| `not_up` | "Not up yet; usually up by 08:40, last seen in the Back bedroom at 22:30" | Medium, High after a further hour |
| `not_back` | "Out for 4h 30m, longer than usual (longest 3h 35m); left by the Side door at 10:13" | Medium, High after a further hour |

The alert clears when activity resumes, as today. The router's routine-sign
escalation (`_combine`) applies to these kinds the same way it applies to
today's house inactivity alert.

### Missing data

- **Restarts and poll gaps** *(my call)*. Nothing detects these today:
  `restart_clock` only runs when holiday mode ends. The new alert keeps
  counting stillness through a gap shorter than 30 minutes (a normal
  restart), because a reset there delays a real alert. Through a gap of 30
  minutes or more it restarts the clock from when feeding resumed, because
  she may have moved while nothing was recorded. The state (`out` included)
  and its start persist across restarts.
- **Most sensors unavailable** *(my call)*. Today `HouseModel.evaluate`
  suppresses welfare while fewer than half the sensors are live. The new
  alert keeps that suppression. The device-health dropout alert already
  reports the outage, so the site doesn't go silent.
- **Out with no return door:** if indoor movement appears while she is `out`,
  she is `home` again. A missed return door event is harmless.
- **Out with no exit door** (the 18 Oct case): she counts as `home` and may
  alert. That is accepted. It errs towards alerting.

### Snapshot and sensors

The welfare snapshot gains `where` (the state above), `where_since` (ISO
time), `last_room`, and `limit_min` (the stillness limit currently in force,
null when `out` or `asleep`). The Welfare Status sensor exposes them as
attributes, so a dashboard can show "At home (TV on), still for 34 of 90 min".

### Persistence

The state, its start time, and the learned values persist in the engine
store. Old stores load with no state (treated as `home` from the first event
after start) and relearn the values from history. The engine `SCHEMA_VERSION`
may need a bump; if so, the bootstrap from the recorder must still run, as
for any schema change.

## Acceptance

On the Biddulph Road fixture and truth file (local, not in git), with the
same injected falls (every hour from 08:00 to 20:00, ordinary days after
learning):

- injected falls: median time to alert 90 min or less, and 90% within
  100 min;
- welfare alerts the truth file doesn't explain: 2 or fewer over the whole
  replay;
- no welfare alert during a confirmed outing;
- the existing synthetic scenario tests still pass, updated only where they
  assert today's inactivity timings.

The scorecard's injected falls need to cover every hour from 08:00 to 20:00
for this check. Today it uses 10:00 and 15:00 by default; the acceptance run
passes `--fall-times`.

## Calls made in this design (not discussed with the owner)

- Bedrooms come from room names only; no selector.
- Presence in the door's own room in the first 2 minutes after an outside
  door opens doesn't cancel `out`.
- Lights and generic events don't count as activity for this alert.
- Stillness keeps counting through a restart shorter than 30 minutes, and
  restarts after a longer gap. Welfare stays suppressed while fewer than
  half the sensors are live.
- Outside doors default to every contact sensor; sitting appliances default
  to none.
- Lie-in allowance 90 minutes, night 20:00–05:00, lie-in until 11:00.
- Severity becomes High at 1.5× the limit, or one hour past it for `not_up`
  and `not_back`.
- Today's `house` / `inactivity` welfare alert is replaced, not kept
  alongside.

## Left to the builder

- Where the state machine lives: a new core module (`core/whereabouts.py`
  or similar) fed by the engine, or an evolution of `house_model.py`.
- How quiet gaps are stored for the percentile.
- Migration details for the store.
