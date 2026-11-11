# Really unusual: quieter information, two night pushes

Status: design, approved in conversation 10 Nov 2026, not yet planned.
Release: minor (`feat:`), no breaking change.

## Why

The information card on the dashboard is mostly noise. Replaying Biddulph Road
(26 days with enough history, 3 Oct to 8 Nov 2026), the current core put up
338 `routine_missed`, 95 `routine_agreement`, 30 `chain_stall` and 4 `drift`:
about 18 a day. A `routine_missed` fires when a sensor that fired in some
hour on 3 of the last 4 matching weekdays misses that hour once. With two
occupants moving between rooms, that happens most days.

The owner wants the card to show **only what is really unusual**, so that
anything on it is worth reading, and wants two night-time situations pushed
to the phone.

The house has two occupants who look out for each other. Alerts stay
household-level: the sensors can't tell people apart.

## Goals

What counts as really unusual, in the owner's words, with their decisions:

1. **Something would have happened by now and hasn't.** A whole sensor's use
   for the day, not one hour: "the kettle hasn't been used yet today, and by
   now it nearly always has". Card only.
2. **A usual trip out didn't happen.** For example, a regular weekday-morning
   outing where nobody went out. Card only.
3. **Something is happening that isn't usual right now.** Activity at a time
   it essentially never happens. It could be something wrong or an
   unexpected guest. Card only.
4. **A miss while nobody went out is more worrying than a miss while the
   house was empty.** When the house is also already too quiet, the existing
   whereabouts alert is escalated, and that pushes as it does today.
5. **Night pushes, only when it's more than a quick trip downstairs:**
   - someone downstairs for **30 minutes or more** during the night (the 30
     is the owner's figure);
   - **an outside door opening** during the night.

   A cup of tea and back to bed sends nothing.

Everything except 4 and 5 is dashboard only. The owner's words: "dashboard
is fine, unless its really serious".

## Must be generic and learned (owner's constraint)

Nothing may be tuned to Biddulph Road's clock. No fixed hours like "after
22:00" or "by 10:00" appear anywhere. Every time and every "usual" is learned
per house from that house's own history. The only fixed numbers are
thresholds on how rare or how long something is, named in the Constants
table below and settable in `WhereaboutsConfig`/`RoutineConfig`-style frozen
configs, not options (except the 30 min, see Options).

## Non-goals and anti-goals

- No per-person tracking or counting of people.
- No new pushes for anything in goals 1–3.
- **Anti-goal:** a push that wakes someone for a normal night. In the replay
  the design must give zero night pushes on Biddulph Road's 40 nights (see
  Acceptance). A night push that fires on a normal evening is a failure even
  if the logic is "right".
- **Anti-goal:** losing the existing escalation. Missed routines raising an
  open whereabouts alert one severity step (`AlertRouter._combine`) must keep
  working.
- Not changing drift. Drift stays as it is (4 in 26 days).

## What changes on the card

**Removed from publication:**
- `routine_missed`
- `routine_agreement`
- `chain_stall`

They are no longer published anywhere: not on the card, no `behaviour_monitor_alert`
event, not in `information`, no logbook entry, and not in any sensor attribute (*my call*). The filter sits in the router after `_combine`. `routine_missed` and `chain_stall` are still
computed internally as "signs", because they feed the whereabouts escalation
in `_combine`. `routine_agreement` is dropped entirely.

*My call:* `chain_stall` goes too. It wasn't discussed by name, but at about
1 a day it's the same kind of noise the owner wants gone.

**Routing (*my call*):** routing is fixed per kind.
- The three card kinds are `STATISTICAL`, so they are never pushed and never
  change the welfare status, whatever `attention_min_severity` is set to.
- The two night kinds are `WELFARE` MEDIUM and follow that option like every
  other welfare alert. A user who raises it to HIGH has chosen fewer pushes.

**Added (information group, LOW, card only):**

| Kind | Goal | Shown when | Clears when |
|---|---|---|---|
| `not_yet_today` | 1 | The entity's learned "usual by" time plus its allowance has passed, and it hasn't fired today | It fires, or the day ends |
| `trip_missed` | 2 | A learned usual outing window for this weekday has ended with no OUT interval overlapping it | The day ends |
| `unusual_now` | 3 | An entity fires in an hour where it has never fired on any learned day, ±1 h | 2 hours later, or the day ends (*my call*) |

**Added (attention group, MEDIUM, pushed):**

| Kind | Goal | Shown when | Clears when |
|---|---|---|---|
| `night_downstairs` | 5 | A night trip has lasted 30 min | The house is back to night rooms only, or morning starts |
| `night_door` | 5 | An outside door opens during the night | Night-room activity resumes after the door, or morning starts |

Explanations follow the existing readable naming (`drift_names()`):
- "Kettle not used yet today; usually by 07:40"
- "Usual Friday outing (around 10:00 to 12:30) didn't happen"
- "Back door opened at 02:14, unusual for this time"
- "Someone has been downstairs for 30 min during the night (since 02:10, in the kitchen)"
- "Front door opened during the night at 02:14"

The times in these explanations are the learned and observed values for that
house.

## How each is learned

All of these need the entity, or the house, to have at least `min_days`
(14) of its own history inside the 28-day window. That's the same as the
routine learning period, so a sensor added last week can't produce an alert.
Sensors currently unavailable, or unavailable at any point today, are
skipped for goals 1–3. That case is device health's job.

### 1. `not_yet_today`

Per entity, keep each learned day's **first activity after that day's
morning start** (minutes after midnight, local). The morning start is the
learned `night_end` from `whereabouts`, so it isn't a fixed 04:00. A day with
no activity is recorded as "none".

The rule applies to an entity only if it was used on at least 90% of learned
days. Its "usual by" time `T` is the 90th percentile of the first-use times.
The allowance `A` is `max(60 min, P90 − P50)`, so a sensor whose first use
varies a lot gets more slack. The alert shows at `T + A` if the entity hasn't
fired today.

- *Builder's call:* whether to pool by weekday or across all days. The replay
  used all days, and pooling by weekday gives only 4 samples per weekday in
  28 days, which is what made `routine_missed` noisy. Pool across all days
  unless the replay shows otherwise.
- **The house-out distinction (goal 4):** the alert's details carry
  `went_out_today: bool`, from whereabouts OUT intervals since the morning
  start. An entity that missed while nobody went out counts as a sign for
  `_combine`, the same way `routine_missed` with `fired_today` does today.
  An entity that missed while the house was out is shown but never counts as
  a sign.
- **Escalation rules (*my call*):**
  - `not_yet_today` uses `went_out_today == False` as its gate in place of
    `fired_today`.
  - `routine_missed` keeps its existing `fired_today` gate.
  - Signs still count once per source entity, so an entity with both an
    hourly and a daily miss counts once.
  - The thresholds are unchanged: one stall, or two or more notes, escalate
    an open whereabouts alert.

- **Controller's ruling (after the first acceptance run):** `not_yet_today`
  is held while the house is out (`where.is_out(now)`). On a day with an
  outing, its due time is `max(T + A, R + 60 min)`, where `R` is the end of
  the latest closed outing today (`where.out_spans(today)`) that ended
  before now and 60 min is `allowance_floor_min`. `went_out_today` is
  unchanged.
- **Unavailable today** includes an outage that began the day before and
  ended today (the health tracker's `down_today`).
- **Controller's ruling (final review):** the same wait applies when data
  resumes. On the first poll after holiday mode ends, after a poll gap of
  `POLL_GAP` (30 min) or more, or after a restart from a store whose last
  poll is that old, the engine tells `Unusual` the time; for that day the
  due time is at least that time plus `allowance_floor_min`. It is kept in
  the store so a restart inside the wait keeps it.
- **Controller's ruling (final review):** `out_spans(day)` returns every
  closed outing overlapping the day, clipped to it, so an outing from 18:00
  to 11:00 the next day counts as going out on both days (for the return
  wait and for `trip_missed`). Old stores' spans, clipped at midnight, still
  load.

### 2. `trip_missed`

Per weekday, take the learned same-weekday days that have whereabouts OUT
intervals. A **usual outing window** is a stretch of 15-minute bins where the
house was out within ±60 min on at least 75% of those days. There must be at
least 4 such days (*my call*; the replay used 3, and that produced one false
14:15 window). If a window passes with no OUT overlapping it ±60 min, raise
`trip_missed`.

Out-of-house time comes from `whereabouts`, so a house with no outside doors
ticked has no OUT intervals and never raises this alert.

**Controller's ruling (after the first acceptance run):** a learned window
whose core, the window with the slack taken back off both sides, is shorter
than one 15-minute bin is discarded. It comes from outings that never
overlapped in time, such as the "14:15 to 14:15" Friday window at Biddulph
Road.

### 3. `unusual_now`

Per entity, per hour of day pooled across all days: if the entity fires in
hour `h`, and on none of its learned days did it fire in `h − 1`, `h` or
`h + 1`, raise `unusual_now`. Raise it once per entity per hour per day.

Night-time activity is also eligible. It is card only; the night pushes are
separate.

### Night: when it starts and ends (goal 5)

**Night rooms** are the bedrooms (the existing `CONF_BEDROOMS`, resolved as
today) plus the new **Upstairs rooms** list (see Options). Every other
monitored room is a **day room**. Outside doors are never rooms for this
purpose.

**Night starts** when all of these hold:

1. Day-room activity is followed within 5 min by night-room activity
   (someone went up).
2. No day-room activity for 30 min after that. The night start is then dated
   back to the night-room activity in step 1.
3. No sitting appliance in a day room is on. This reuses `CONF_SITTING_APPLIANCES`.

There is also an earliest point: none of this can start night before the
learned `night_start` from `whereabouts`. That stops an afternoon nap
starting night.

**Night ends** at the first day-room activity at or after the learned
`night_end` (earliest waking). Day-room activity before `night_end` is a
night trip, not morning.

These conditions are a sequence of events, not clock times. The learned
`night_start` and `night_end` only bound the night.

**Controller's ruling (final review):** a night trip needs someone to have
come down: night-room activity within 5 min (`went_up_within_min`) before
the trip's first day-room activity. Day-room activity during the night
without it means someone was still downstairs (one partner up, the other
reading quietly with the TV off). The night is cancelled: nothing is
recorded for it, the trip state is cleared (an open night door stays open,
see below), and bedtime is looked for again from that activity.

**Controller's rulings (second fix wave):**
- During the night only motion counts as day-room activity for trips, the
  coming-down check and cancelling: a presence, or a day-room burst end at
  its activity time. An appliance turning on or off, or a light, does not
  start a trip or cancel the night. On Biddulph Road a TV plug's two-minute
  standby wake around 01:00–03:30 had cancelled 10 of 37 nights. Outside
  the night nothing changes: appliances still count for bedtime and a
  sitting appliance that is on still blocks the night starting.
- A night-room burst end counts as the coming-down, at its activity time
  (the fall, but no later than the last rise plus `burst_activity_max_min`).
  A bedroom sensor held on while someone is in bed falls as they leave. It
  does nothing else: it doesn't start a trip or count as going up.
- **Controller's ruling (third fix wave):** the normaliser only sends a
  burst end on a poll after its 90 s debounce, so the bedroom's burst end
  arrives after the first kitchen presence. Downstairs motion with no
  coming-down therefore waits `came_down_grace_min` (3 min) before the
  night is cancelled. If a night-room burst end arrives in that time and its
  activity time is within `went_up_within_min` before the motion, it is the
  coming-down, and the motion starts a trip at its own time. Otherwise the
  first event or poll at or after motion + grace cancels as before. The
  waiting state is kept in the store.

**Evidence from the replay** (40 evenings):
- Requiring the TV off prevented 40 false bedtimes: someone sitting still
  for 30 minutes or more with the back room TV on.
- Requiring someone to go up first prevented the other 2: 30 minutes of
  stillness with the TV off and nobody going upstairs.
- Bedtime itself was the same every night: the last downstairs room, then a
  bedroom or the bathroom within 1–2 min.

The `ASLEEP` state in `whereabouts` is **not** night. It starts when the
first person goes to bed. With two occupants, the other is often downstairs
for another 1–2 hours. Using `ASLEEP` would have given 5 false 30-minute
pushes and 1 false door push in 40 evenings.

### Night trips and the two pushes

A **night trip** starts at the first day-room activity during the night. It
ends when there has been night-room activity and no day-room activity for
5 min (*my call*).

- **`night_downstairs`:** fires when a trip reaches 30 min.
- **`night_door`:** fires when an outside door opens during the night,
  unless the whereabouts state was OUT at the time. In that case it's someone
  coming home late: a return, not a night event.
- **Owner's decision (third fix wave; replaces the door hold of the final
  review, the second wave's "any night-room activity drops the held door"
  and its "door then downstairs stays silent" decision):** the owner doesn't
  live at the property. Pushes go to their phone remotely, and the
  occupants are elderly. Late returns and going out at night are unlikely,
  and a missed night event matters more than an occasional push that
  wasn't needed. So a night door pushes at once, with `raised_at` the door
  time, unless the house was OUT just before it or a door in that hour ±1
  is normal (more than 10% of at least 14 learned nights). Its hour is
  recorded in the night as before. It clears at night-room activity after
  the door, at the night's end, or after `unusual_ttl_min` (120 min). It
  outlives a cancelled night: the push has gone, so it doesn't clear at
  once. `door_hold_min` is gone; stores that carry the hold state still
  load.

Both are suppressed when they're normal for this house, which the owner
agreed: "if someone always lets the dog out at 23:30, that's learned".

- A 30-minute night trip is normal if one happened on more than 10% of
  learned nights.
- A door opening is normal for night hour `h` if a door opened in `h ± 1` on
  more than 10% of learned nights.

Holiday mode stops both and snooze holds both, as for every other attention
alert. They need the learning period (14 days) like the rest, because night
can't be detected until the house's `night_start` and `night_end` are
learned.

## Options

- **New tick list "Upstairs rooms":** on the existing "Doors, bedrooms and
  TVs" step, in the same tick-list style (`_tick_list`, friendly names,
  suggested values only).
  - When a site's areas have HA floors, suggest the rooms on floors above
    the lowest `level`.
  - Biddulph Road has no floors in HA, so for it the list starts empty and
    the owner ticks Bathroom, Landing and Box room.
  - Default empty. With nothing ticked, night rooms are the bedrooms only.
    That suits a bungalow, and a trip to the bathroom then counts as a short
    night trip.
- **New number option "Night-time downstairs alert (minutes)":** default 30,
  range 10–120.
- Config entry version 13 → 14. **Controller's ruling (final review):** the
  migration bumps the version only. A missing upstairs list means none
  ticked, so an upgraded site on several HA floors still gets the floor
  suggestion in the options form.

## State and upgrade

- **New learned state:** per-entity first-use-by-day, per-day OUT bins (or
  reuse the whereabouts intervals if they're kept long enough), and per-night
  records of trips and door openings.
- **Upgrading must not throw away learning.** Today a `SCHEMA_VERSION`
  mismatch makes the coordinator relearn from the recorder, which holds
  only 10 days at Biddulph. Add the new fields with tolerant
  `from_dict` defaults, as `room_rise` was added, and keep
  `SCHEMA_VERSION` unless the builder finds that impossible. Where the new
  history can be rebuilt from what's already stored, rebuild it. For
  example, first-use per day can come from `slot_days` at hour resolution
  until minute data accrues. *Builder's call*, but state the choice.
- **After an upgrade (owner's decision, option A):**
  - On the first start after upgrading, the coordinator rebuilds the new
    history (first use per day, outing bins, night records) from the
    recorder. That's about 10 days at Biddulph, replayed through the new
    models only, in time order, as the bootstrap does.
  - The existing learning is kept. Each new kind then stays silent until it
    has its own `min_days` (14) of history; the night pushes additionally
    need 14 learned nights.
  - At Biddulph that means about 4 more days after the upgrade. The owner
    chose quiet at first over pushing before "normal for this house" is
    known.
  - A fresh install or a reset learns everything this same way.
- The store version follows the existing rules.

## Dashboard and docs

- **README:** replace the routine-note text with the five kinds, the
  Upstairs rooms list and the 30 min option. Note that `routine_missed`,
  `routine_agreement` and `chain_stall` events are no longer sent, for
  anyone who automated on them.
- **Biddulph Road dashboard** (live HA, after release, with the owner's
  go-ahead):
  - the information card gets icons for the three new kinds;
  - the footnote changes from "checked each midnight" to cover them;
  - the attention card needs nothing.

## Constants (configurable in core config, not options)

| Constant | Value | Used by |
|---|---|---|
| `usual_fraction` | 0.90 | 1 (used on at least this share of days; P90) |
| `allowance_floor_min` | 60 | 1 |
| `trip_fraction` | 0.75 | 2 |
| `trip_min_days` | 4 | 2 |
| `trip_slack_min` | 60 | 2 |
| `unusual_neighbour_h` | 1 | 3 |
| `unusual_ttl_min` | 120 | 3 |
| `went_up_within_min` | 5 | night start |
| `bedtime_quiet_min` | 30 | night start |
| `trip_end_quiet_min` | 5 | night trip end |
| `night_normal_fraction` | 0.10 | both pushes |
| `min_days` | 14 | all |

## Acceptance (Biddulph Road replay, same fixture and truth file)

The current core gives about 18 a day.

**Card:**
- **`not_yet_today`:** about 5 in 26 days. The replay rule with a fixed
  2-hour allowance gave 5, and the learned allowance should land close to
  that.
- **`trip_missed`:** 0 on the 4 Fridays with data, all of which had the
  outing.
- **`unusual_now`:** ≤ 2 in 26 days, counting from each entity's own 14
  learned days. The hall and landing sensors added on 19 Oct must not fire
  in their first weeks.
- **Total:** ≤ 1 every 3 days on average.

**Night pushes:** 0 across the 40 nights. The longest night trip after the
real bedtime was 11 min, and no outside door opened after the real bedtime.

**No regressions:**
- the `where-is-she` acceptance figures (falls 130/130, welfare alerts 3);
- the whereabouts escalation still works;
- panic, health and battery are untouched;
- `make test` is green.

**Synthetic tests:**
- two occupants, one goes to bed early;
- a TV-on doze;
- a TV-off quiet read with nobody going up;
- a 2 a.m. 40-minute downstairs trip;
- a 2 a.m. front-door opening while home, and while OUT;
- a regular nightly 23:30 back door that is learned as normal;
- a bungalow with no upstairs rooms;
- a new sensor with under 14 days of history;
- a sensor unavailable today.

## Left to the builder

- Module placement: a new `core/unusual.py` alongside `whereabouts`, versus
  extending `entity_routine` and `whereabouts`.
- Pooling choice for goal 1 (see above).
- How OUT history is kept for goal 2.
- How the upgrade rebuilds new history (see State and upgrade).
- Exact wording of explanations, within the readable-naming style.

## Acceptance results (measured 10 Nov 2026, re-run after the final review)

Biddulph Road fixture (18 Sep – 9 Nov), upstairs rooms Bathroom, Landing and
Box room. Counted from `opened` events in the scorecard's replay, with
holiday mode over the truth file's gaps and polls on Europe/London local
time. The evaluation window is 3 Oct – 8 Nov without the 19–29 Oct recorder
gap: 26 days. The truth file's gap now ends at the first data after it
(29 Oct 07:53, not 04:13). The baseline is main's engine (c8a2dac) run with
the same, fixed, scripts on the same data.

Re-run after the final-review rulings (data resuming, outings across
midnight, the coming-down rule), the second fix wave (motion only at night,
a night-room burst end as the coming-down) and the third (the night door
pushes at once, a 3-minute grace for a late burst end). "Before the final
fixes" is this branch at 2c0da9d; "first final-fix run" is 33dfd90.

| Figure | Target | Baseline (main) | Before the final fixes | First final-fix run | This branch |
|---|---|---|---|---|---|
| Information opened, whole run | | 158 (3.6 a day) | 12 (0.3 a day) | 9 | 9 (0.2 a day) |
| `routine_missed` / `routine_agreement` / `chain_stall` | not sent | 97 / 22 / 32 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `not_yet_today` in the window | about 5 | | 4 | 1 | 1 |
| `trip_missed` in the window | 0 | | 0 | 0 | 0 |
| `unusual_now` in the window | ≤ 2 | | 1 | 1 | 1 |
| Card total in the window | ≤ 1 every 3 days | | 5 (1 every 5.2 days) | 2 | 2 (1 every 13 days) |
| Night pushes, whole run | 0 | | 0 | 0 | 0 |
| Welfare alerts that would push | unchanged | 2 | 2 (the same two) | 2 | 2 (the same two) |
| Injected falls caught | unchanged | 20 / 20, median 1h25m, worst 3h45m | 20 / 20, same | 20 / 20, same | 20 / 20, median 1h25m, worst 3h45m |
| Device health opened | unchanged | 167 | 167 | 167 | 167 |
| Evenings that reached night, whole run | | | 37 | 37 | 37 |
| Nights recorded, whole run | | | 37 | 27 | 37 |
| Nights cancelled (coming-down rule) | | | | 18 on 16 evenings | 1 |
| Evenings cancelled and never recorded | | | | 10 | 0 |

All card and push targets are met. Night pushes stay at 0 because no
outside door opened during any night in the data: the three small-hours
openings (27 Sep 04:58, 28 Sep 05:46, 29 Sep 05:54) came after the night
had ended. The cards in the window:

- 15 Oct 20:15, back door not used yet today (usually by 15:42). It wasn't
  used at all that day.
- 5 Nov 22:10, `unusual_now`: back door at 22:06. The hall and landing
  sensors added on 19 Oct stayed silent.

The three 29 Oct 07:55 cards from missing data are gone: data resumes at
07:53, so nothing is due before 08:53, and by then the sensors had fired.

**The coming-down rule on real sensors.** In the first final-fix run, 17 of
the 18 cancels were the back room TV plug drawing 16–18 W for about two
minutes in the small hours. Nobody was downstairs; it looks like a standby
wake. With motion only at night, one cancel is left: front room motion at
23:25 on 23 Sep, 10 minutes after bedroom motion. The night started again
later that evening and was recorded.

The first run, before the fixes, gave 14 cards (12 `not_yet_today`, 1
`trip_missed`, 1 `unusual_now`). Four causes were found:

- The replay's poll clock kept the first event's UTC offset, so after the
  clocks went back every poll read an hour ahead.
- The truth file's gap ended before the data resumed.
- Cards fired during and just after the Friday outings.
- There was a zero-length Friday trip window.

A side-door card on 12 Oct was the door's first opening after an overnight
"unavailable" in the CSV export. That opening is rightly not counted as
activity, and the door now counts as down that day.
