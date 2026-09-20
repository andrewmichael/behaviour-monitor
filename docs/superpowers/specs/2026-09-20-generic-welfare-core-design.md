# Generic welfare core: categories, learned models and classed alerts

Date: 2026-09-20
Status: draft for review
Supersedes: none on main (v4.2.1 is the base)

## 1. Purpose

Behaviour Monitor watches a home and alerts when the occupant's behaviour
departs from what the home has learned is normal. This redesign makes the
core generic so it works on any site with any mix of sensors, learns
patterns rather than relying on per-site tuning, and separates three
kinds of alert that need different handling:

1. **Welfare** of the person. The primary product.
2. **Device health**. The sensing itself has degraded.
3. **Statistical**. Unusual, worth knowing, not a welfare concern on its own.

## 2. Goals and non-goals

Goals:

- Six user-assigned entity categories with category-specific event rules.
- Room context taken from Home Assistant areas, used for chain steps,
  explanations and a rooms-visited signal, never for inferring meaning.
- Learning at three levels: whole house, per entity, and ordered chains
  between entities.
- Detection of routines slowing down over time.
- Alert routing decided by class alone, with welfare pushed and repeated,
  device health raised as repair issues, and statistical kept on a sensor.
- A pure Python core with no Home Assistant imports, testable by replaying
  real and synthetic event fixtures.
- Reuse of the existing Home Assistant shell: sensors, config flow, storage,
  translations, switch, select.

Non-goals:

- Automatic category inference. The user assigns every entity.
- Multi-occupant modelling. One site is assumed to have one occupant whose
  welfare is monitored. Visitors appear as extra activity and are tolerated.
- Machine learning beyond running statistics and CUSUM.
- Room adjacency, floor plans, or any meaning attached to a room's name
  or type.

## 3. Evidence from the reference site

The Biddulph Road install informed the defaults. Fifteen Tuya entities:
six PIRs, three door contacts, four power plugs, two panic buttons. No
lights. Observed over the ten day recorder window:

| Observation | Design consequence |
|---|---|
| Every PIR has a fixed hold of about 62 s then retriggers; kitchen fires 153 times a day | Motion debounce, default 90 s |
| Back room TV idles at 85 W, kettle at 0 W and peaks at 2800 W | Plug idle level learned per entity, margin above it |
| Front door opened zero times in ten days; side and back doors daily | Rare entities get no expected windows and are never flagged |
| Back bedroom active 00:00 to 09:00 and 18:00 to 23:00; bathroom at 00:00 and 05:00 | Weekday-hour slots capture the night routine |
| About 20 cloud dropouts in ten days, every device at once, 5 to 15 s each | Health grace period 15 min; site-wide dropout is one alert |
| Existing pair-correlation detector stuck on six false positives with over 1000 consecutive misses | Pair correlation replaced by ordered chains |
| Panic buttons never pressed | Panic liveness is a device health concern, tested synthetically |
| Raw recorder retention is 10 days; long-term statistics are hourly aggregates only | Bootstrap from recorder, then learn live; fixture exported before it rolls off |
| No Tuya entity or device has an area; room appears only in some friendly names, and not at all for the kettle or teas maid | Rooms resolved from areas with friendly-name fallback; areas to be assigned on site |

## 4. Architecture

```
state_changed ──► Normaliser ──► typed ActivityEvent / HealthEvent
                                     │
              ┌──────────────────────┼─────────────────────────┐
              ▼                      ▼                         ▼
      HouseActivityModel     EntityRoutineModel           ChainModel
              │                      │                         │
              │                      │                 DriftDetector (CUSUM)
              │                      │                         │
              └──────────────► Alert list ◄────────────────────┘
                                     │
                          HealthTracker ──► blind spots, degraded
                                     │
                                AlertRouter ──► delivery actions
                                     │
                     Coordinator performs actions, updates sensors
```

Every box above the coordinator is a pure Python module under
`custom_components/behaviour_monitor/core/`, stdlib only, taking
timestamps as arguments. The coordinator is the only file that imports
Home Assistant and does no analysis of its own.

### 4.1 Modules

| Module | Responsibility | Depends on |
|---|---|---|
| `core/events.py` | `ActivityEvent` (with `room`), `HealthEvent`, `Category`, `EventKind` dataclasses and enums | nothing |
| `core/normaliser.py` | Raw state to typed events, per-category rules, debounce, plug idle learning | events |
| `core/house_model.py` | Whole-house gap distribution per weekday-hour slot; welfare signal | events |
| `core/entity_routine.py` | Per-entity slot statistics, expected windows, longest gap; lifted from `routine_model.py` | events |
| `core/chain_model.py` | Ordered pair learning, chain assembly, stall detection, completion timing | events |
| `core/drift_detector.py` | CUSUM on daily activity counts and on chain completion times; moved from top level | nothing |
| `core/health_tracker.py` | Unavailable, site-wide dropout, silent sensor, panic liveness, blind spots | events, entity_routine |
| `core/alerts.py` | `Alert`, `AlertClass`, `Severity` | nothing |
| `core/alert_router.py` | Open alert set, de-duplication, escalation, promotion, delivery actions | alerts |
| `coordinator.py` | Subscribe, bootstrap, resolve rooms from the area registry, feed, poll, persist, perform delivery actions | all of the above, HA |

`acute_detector.py` and `correlation_detector.py` are deleted. Their
useful behaviour lives in `house_model.py` and `chain_model.py`.

## 5. Categories and normalisation

The config entry holds six entity lists. An entity in no list is not
monitored. An entity may appear in only one list.

The normaliser receives `(entity_id, category, old_state, new_state,
timestamp)` and emits zero or one `ActivityEvent` plus zero or one
`HealthEvent`.

| Category | Activity event on | Also recorded | Never activity |
|---|---|---|---|
| motion | rising edge to `on`, debounced | burst start and end | falling edge |
| contact | rising edge to `on` (open) | open duration on close | close |
| plug (numeric) | power rises above idle plus margin | on duration when it falls back | fall |
| plug (switch) | `on` | off | off |
| panic | rising edge to `on` | release | release |
| light | `on` | off | off |
| other | any change between two real states | nothing | nothing |

Rules common to every category:

- A transition to or from `unavailable` or `unknown` emits a `HealthEvent`
  and never an `ActivityEvent`.
- A restart-replay of the same state (old equals new) emits nothing.
- Panic events carry `bypass=True` and are handed to the router before any
  model sees them.

Motion debounce: a rising edge within `motion_debounce_s` of the previous
accepted rising edge on the same entity extends the current burst instead
of starting a new event. Burst end is the last falling edge before the
gap exceeds the window. Burst dwell is end minus start.

Plug idle learning: the normaliser keeps, per numeric plug, a bounded
reservoir of recent readings. Idle is the median of the lowest quintile.
On is `reading > idle + plug_margin_w`. Until the reservoir holds
`plug_min_samples` readings, idle is taken as the minimum seen so far.

### 5.1 Rooms

Every `ActivityEvent` carries a `room` string. The coordinator resolves
it from the entity's area, falling back to the area of the entity's
device, and finally to the entity's friendly name so an entity with no
area is a room of one. Resolution happens outside the core; the
normaliser receives `room` as an argument alongside the state, so the
core stays free of Home Assistant imports.

Rooms are re-resolved when the entity or area registry changes. A room
rename or reassignment does not reset learning: chain nodes are keyed by
room name, so the chain model maps the old name to the new one on the
next nightly recompute and keeps its counts.

Rooms are used for exactly three things: chain nodes (6.3),
rooms-visited-per-day (6.4), and explanation text (7). The models never
attach meaning to a room's name or type. A kitchen and a bedroom are
indistinguishable to every model; what looks like knowledge of sleep or
meals is learned from the timing of events and merely labelled with the
room name.

Display names: the coordinator derives a display name for each room by
stripping the configured site name when it is a leading prefix of the
area name, compared case-insensitively and followed by whitespace. So
with site name "Biddulph Road", the area "Biddulph Road Kitchen" is
displayed as "Kitchen". Areas that do not start with the site name are
displayed unchanged. The stored room key is always the full area name,
so display rules never affect learning. Display names are used in
explanation text and sensor attributes only.

## 6. Learning models

All three models share a slot scheme: 7 weekdays x 24 hours = 168 slots.
All keep a rolling window of `window_days` learned days and report a
confidence in [0, 1] equal to distinct days observed over
`learning_days`, capped at 1. Each model has `record(event)`,
`evaluate(now) -> list[Alert]`, `confidence(now)`, `to_dict()`,
`from_dict()`.

### 6.1 House activity model

State: timestamp of the last activity event from any non-panic entity;
per slot, a bounded list of observed gaps between consecutive activity
events, from which median and median absolute deviation are derived.

Evaluate: `gap = now - last_activity`. Let `expected` be the slot median
for the current slot and `spread` its deviation. Ratio
`r = gap / max(expected, floor_s)`.

| r | Welfare severity |
|---|---|
| below `house_low_ratio` (default 3) | none |
| 3 to 6 | low |
| 6 to 12 | medium |
| above 12 | high |

`floor_s` prevents division by tiny medians in busy slots; default 300 s.
Sustained-evidence rule: a severity must hold for two consecutive polls
before it is raised, and drops one level only after one poll below the
threshold, so a single event does not flap the alert.

Blind spots: entities the health tracker marks as down are excluded when
the coordinator asks which entities contribute; if fewer than
`min_live_fraction` (default 0.5) of activity-capable entities are live,
`evaluate` returns no welfare alerts and reports `degraded=True`.

### 6.2 Entity routine model

Per entity, per slot: event count per day observed, running median gap,
longest gap ever seen. Derived expected windows: slots where the entity
fired on at least `window_min_fraction` (default 0.7) of observed days for
that weekday. A slot whose window has passed without an event produces a
routine note (statistical class, low). Entities with no expected windows
produce nothing.

Exposes `longest_gap(entity_id)` for the health tracker and
`expected_windows(entity_id)` for the status sensor.

### 6.3 Chain model

Nodes are rooms, not entities. An event in room B is a step only if the
previous activity event was in a different room; consecutive events in
the same room extend the current step rather than starting one. So the
kitchen PIR followed by the kettle is one step, and back bedroom,
bathroom, kitchen is a three-step chain satisfied by any sensor in each
room.

Learns ordered pairs of rooms. For each step into room B, every room A
whose last step was within `chain_window_s` (default 900) before B gets
the pair (A, B) incremented, with the hop duration stored. A pair is
significant when its count is at least `chain_min_count` (default 10)
and `P(B follows A) > P(B in any window) * chain_lift` (default 2.0).

Chains are assembled by starting at any room with no significant
predecessor and following the strongest significant successor until none
remains or a cycle would form. Chains are recomputed nightly and stored.
Each chain is named from its member rooms in order.

Live tracking: when a step into a chain's first room occurs, a run
opens. Each
subsequent step must arrive within the learned hop median plus three
deviations. A run whose next step does not arrive in time is a stall,
which produces a routine note naming the chain and the missing step. A
run that completes records its total duration for that weekday type.

### 6.4 Drift detector

The existing CUSUM implementation, moved into `core/`, with two inputs
per day:

- daily activity count per entity, as today;
- completion time per chain, split weekday and weekend;
- distinct rooms with at least one activity event per day.

Each series has its own CUSUM state. A shift that persists for
`drift_min_days` (default 3) is reported as a statistical alert with the
baseline, the current value and the number of days. Chain timing shifts
that persist for `timing_promote_days` (default 7) are promoted by the
router to welfare low.

Per-entity durations from the normaliser, contact open duration and motion
burst dwell, feed the same detector as daily medians.

### 6.5 Combining models into welfare

Only the house model raises welfare on its own. Routine notes and chain
stalls are statistical by default. Escalation rules in the router:

- A house welfare alert with at least one routine note or stall in the
  last `agreement_window_s` (default 3600) is raised one severity level.
- Two or more routine notes or stalls in the same window with no house
  alert open a welfare alert at low.
- Promoted timing drift opens welfare at low.

## 7. Alerts and routing

```python
@dataclass
class Alert:
    key: str            # f"{cls}:{source}:{kind}" for de-duplication
    cls: AlertClass     # WELFARE | HEALTH | STATISTICAL
    severity: Severity  # LOW | MEDIUM | HIGH | CRITICAL
    source: str         # entity_id, chain name or "house"
    kind: str           # inactivity, panic, stall, drift, unavailable ...
    explanation: str    # uses room names, e.g. "No activity in the kitchen since 08:10"
    raised_at: datetime
    details: dict
```

The router keeps the open alert set. `submit(alerts, now)` merges the new
list against the open set and returns delivery actions:

| Class | On open | Repeat | On clear |
|---|---|---|---|
| WELFARE | push if severity at or above `push_min_severity` | every `push_repeat_s` until acknowledged | one push saying cleared |
| HEALTH | create repair issue, update health sensor | never | delete repair issue |
| STATISTICAL | append to anomaly sensor attribute, logbook entry | never | remove from attribute |

Panic: `submit_panic(event, now)` is a separate entry point that returns
a push action immediately, at critical, ignoring snooze and holiday.
Release does not clear the alert; acknowledge does.

Acknowledge clears repeat for a welfare alert but the alert stays open
until its model stops raising it. Snooze suppresses welfare and
statistical delivery until it expires. Holiday suppresses welfare and
statistical alerts and pauses learning. Neither touches health or panic.

## 8. Device health

The health tracker consumes `HealthEvent`s and polls once per cycle.

| Condition | Rule | Severity |
|---|---|---|
| Unavailable | down for longer than `health_grace_s` (default 900) | medium; high for panic |
| Site-wide dropout | more than half of monitored entities go down within 60 s | medium, one alert, count on sensor |
| Silent sensor | no events for more than `silent_multiplier` (default 3) times the entity's longest learned gap, while the house model saw activity in that time | medium |

Blind spots: any entity in an open health condition is reported as down
to the house model. Panic buttons are never silent-sensor candidates.

## 9. Persistence and lifecycle

One store per config entry, `behaviour_monitor.{entry_id}.json`, version
bumped to a new major so v4 files are discarded. Sections: normaliser
(plug idle reservoirs, burst state), house, routines, chains, drift,
health, router open alerts, metadata (first observation, schema
version). Each section deserialises independently; a corrupt section
resets that model only and logs a warning. Saved with a 30 s debounce
after events and on unload.

Bootstrap: on first start, after a store reset, and for any entity newly
added, recorder history for `window_days` is replayed through the
normaliser and the models with timestamps converted to local time. The
router is not fed during bootstrap, so no alerts fire for history.

Rolling window: each model drops learned days older than `window_days`
nightly.

Entity list changes: additions bootstrap that entity; removals drop its
routine, chain links, health state and open alerts; a category change is
a removal then an addition.

Reset service: `behaviour_monitor.reset_learning` with optional
`entity_id`; without it, the whole store resets and bootstrap reruns.

## 10. Home Assistant surface

Config flow, setup step: site name, six category entity selectors,
notify service. Options step, all with defaults:

| Option | Default |
|---|---|
| motion_debounce_s | 90 |
| plug_margin_w | 5 |
| learning_days | 14 |
| window_days | 28 |
| health_grace_s | 900 |
| push_repeat_s | 1800 |
| push_min_severity | medium |
| house_low_ratio | 3 |
| chain_window_s | 900 |
| timing_promote_days | 7 |
| drift_sensitivity | medium |

Entities per config entry:

- `sensor.<site>_welfare_status`: ok, degraded, low, medium, high,
  critical; attributes reasons, recommendation, open alerts.
- `sensor.<site>_house_activity`: seconds since last activity; attributes
  expected gap for this slot, ratio, contributing entities.
- `sensor.<site>_anomaly`: count; attribute list of statistical alerts.
- `sensor.<site>_device_health`: ok or the worst open condition;
  attribute per-entity state.
- `sensor.<site>_learning`: percent; attributes per-model confidence,
  days remaining, first observation.
- `sensor.<site>_entity_status`: summary; attribute per entity with
  category, room, last seen, expected windows, health.
- `sensor.<site>_house_activity` also lists rooms visited today.
- `sensor.<site>_last_activity`, `sensor.<site>_daily_activity_count`,
  `sensor.<site>_last_notification`.
- `switch.<site>_holiday_mode`, `select.<site>_snooze`,
  `button.<site>_acknowledge`.

Services: `acknowledge`, `reset_learning`, `test_panic`.

Repair issues: one per open health condition, and one on upgrade asking
the user to assign categories.

## 11. Testing

Core tests import nothing from Home Assistant.

Fixtures under `tests/fixtures/`:

- `site_real_10d.jsonl`: the Biddulph recorder export, entity ids
  replaced with generic names, categories and rooms in a sidecar file. Exported
  before the recorder purges it.
- Synthetic: panic press; front door first open; silent kitchen PIR
  with activity elsewhere; site-wide dropout; morning chain that stalls
  at the kettle; kettle absent for three days; chain lengthening 2 min
  per day for 14 days; chain jumping from 12 to 25 min on day 8.

`scripts/replay.py` loads a fixture, drives the normaliser, models,
health tracker and router with a simulated clock, and prints the alert
timeline. Tests assert on that timeline: which day a drift is first
reported, that the real fixture raises no welfare alert above low, that
site-wide dropouts produce exactly one health alert each.

Coordinator, sensor, config flow, switch and select tests keep the
existing mocked-HA approach, updated for the new data shape.

## 12. Migration

Store schema major bump discards v4 learned state. Config entry version
bump: existing `monitored_entities` are kept unassigned and a repair
issue asks the user to place them in categories in options. Until they
do, nothing is monitored and the welfare sensor reports `unconfigured`.

## 13. Decisions

- Categories are user-assigned, not inferred. Predictable on every site.
- House-level silence is the only sole source of welfare alerts.
  Per-entity and chain signals escalate but rarely originate.
- Ordered chains replace pair correlation. Chains are directional and
  time-bounded, which is what pair PMI lacked.
- CUSUM is reused for timing drift rather than adding a new detector.
- Panic bypasses every model and every suppression.
- Delivery is decided by class alone so the rule fits in one table.
- Rooms come from Home Assistant areas, never from entity names. Chain
  nodes are rooms so same-room sensors collapse into one step.
- Room display names strip the site name prefix; no extra config key.
  Stored keys stay the full area name.
