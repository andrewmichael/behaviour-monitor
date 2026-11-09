# Where Is She Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the whole-house inactivity welfare alert with one that tracks where she probably is (home, home with the TV on, asleep, lying in, out) and alerts within about an hour of stillness at home without alerting on outings.

**Architecture:** A new pure-stdlib module `core/whereabouts.py` holds the state machine, its learned values and its alerts. `Engine` feeds it the same activity events the other models get and submits its alerts through the existing router in place of the `house`/`inactivity` alert. `HouseModel` keeps learning (it still drives the learning progress, the House Activity sensor and the `rooms` drift) but no longer raises alerts. The Home Assistant shell gets one new config/options step with three lists.

**Tech Stack:** Python 3.13, stdlib only in `core/`; Home Assistant config flow selectors; pytest.

**Spec:** `docs/superpowers/specs/2026-11-09-where-is-she-design.md` (reference rules: `docs/superpowers/specs/2026-11-09-where-is-she-spike.py`; where the spec is silent, do what the spike does).

## Global Constraints

- `core/` is stdlib only and never reads the clock; every method takes `now`/timestamps.
- Activity for this alert is only `EventKind.PRESENCE`, `EventKind.OPEN`, `EventKind.APPLIANCE_ON`. `ACTIVITY_KINDS` in `core/events.py` is unchanged.
- Fixed values, all in one frozen `WhereaboutsConfig` dataclass: home limit clamp 45–60 min (60 before learning); TV allowance 90 min; lie-in 90 min; `not_up` at usual waking + 60 min; door-then-movement window 10 min; door's own room ignored for the first 2 min; outing deadline longest outing × 1.25 (240 min before any outing); fallback night 20:00 → 05:00, lie-in until 11:00; home quantile 0.995; waking quantile 0.95; night-start quantile 0.05 minus 60 min, clamp 18:00–01:00; night-end = 5th percentile of waking minus 60 min, clamp 03:00–09:00; lie-in end = waking 95th + 120 min, clamp to [night end + 120 min, 13:00]; main sleep searched between 18:00 and 04:00; poll gap that restarts the clock 30 min; minimum 3 days of samples before any learned value replaces its fallback.
- Alert class `WELFARE`, source `"whereabouts"`, kinds `still_at_home`, `still_tv`, `not_up`, `not_back`. Severity MEDIUM at the deadline; HIGH at 1.5× the limit for `still_at_home`/`still_tv`/lying-in, and one hour past the deadline for `not_up`/`not_back`.
- Every alert's `details` carries `"room"` (last room) so the event payload's `room` is set.
- Explanations follow the spec table wording exactly (see Task 3).
- Welfare alerts are only raised once learning is complete (`Engine` gate unchanged) and never while fewer than `min_live_fraction` (0.5) of sensors are live, on holiday, or (via the router) while snoozed.
- Never hand-edit `manifest.json`'s version. Conventional commits. Don't push.

## Review Focus

1. **A trip away without holiday mode** (an `out` interval of days) must not become the "longest outing" and silence `not_back` for a month. Ruling: `out` intervals of 24 h or more are not learned. Test in Task 2.
2. **An outside door opened by mistake while she stays in a room with no sensor** reads as `out` after 10 min. Accepted by the spec; nothing to pin beyond Task 1's door tests.
3. **Hall motion right after the front door opens** must not cancel `out`, but hall motion 3 minutes later must. Test in Task 1.
4. **A Home Assistant restart of under 30 min mid-stillness** must not delay an alert; one of 30 min or more restarts the clock but keeps `out`. Test in Task 4.
5. **An area renamed in Home Assistant** must keep a renamed bedroom a bedroom. Test in Task 5.

---

### Task 1: Whereabouts state machine

**Files:**
- Create: `custom_components/behaviour_monitor/core/whereabouts.py`
- Test: `tests/core/test_whereabouts.py`

**Interfaces:**
- Produces:
  - `class Where(str, Enum)`: `HOME = "home"`, `HOME_TV = "home_tv"`, `ASLEEP = "asleep"`, `LYING_IN = "lying_in"`, `OUT = "out"`.
  - `@dataclass(frozen=True) class WhereaboutsConfig` with every fixed value from Global Constraints as a named field (minutes as `float`, times of day as minutes after midnight `int`), plus `outside_doors: frozenset[str] = frozenset()`, `sitting_appliances: frozenset[str] = frozenset()`, `bedrooms: frozenset[str] | None = None` (`None` means "rooms whose name contains 'bedroom', case-insensitive"; an empty set means "no bedrooms chosen").
  - `class Whereabouts(config: WhereaboutsConfig)` with:
    - `record(ev: ActivityEvent) -> None`
    - `current(now: datetime) -> Interval | None`
    - `is_bedroom(room: str | None) -> bool`
  - `@dataclass(frozen=True) class Interval`: `start: datetime`, `where: Where`, `room: str | None` (last room), `tv: bool`, `door: str | None` (entity id that started it, if any).

Rules (from the spec's "Exact rules"; the night boundaries come from Task 2's learned values, so in this task call `self.night_start()`, `self.night_end()`, `self.lie_in_end()` methods that return the fallbacks 20:00, 05:00, 11:00):

- Only `PRESENCE`, `OPEN`, `APPLIANCE_ON` start a new interval. `APPLIANCE_OFF` of a sitting appliance only updates which TVs are on.
- `PRESENCE` and `APPLIANCE_ON` set the last room; `OPEN` does not.
- An `OPEN` of an outside door starts an interval with `door=<entity_id>`. While that interval is current, `PRESENCE` in the door's own room within the first 2 minutes is ignored completely (no new interval, last room unchanged). The interval reads as `OUT` once 10 minutes have passed without another activity; before that it reads as `HOME`.
- `OPEN` of any other contact is ordinary activity.
- Otherwise the state is fixed at the interval start by precedence `ASLEEP` > `LYING_IN` > `HOME_TV` > `HOME`:
  - `ASLEEP` if the room is a bedroom and the start's time of day is in [night start, night end) (wrapping midnight);
  - `LYING_IN` if the room is a bedroom and the start is in [night end, lie-in end);
  - `HOME_TV` if a sitting appliance in the last room is on at the start;
  - else `HOME`.
- With `bedrooms` an empty set, every room counts as a bedroom for `ASLEEP`/`LYING_IN` (spec: "No bedrooms chosen").
- Events older than the current interval's start are ignored.

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_whereabouts.py — helpers build ActivityEvent(entity_id, category, kind, room, ts)
DOORS = frozenset({"binary_sensor.front_door"})
TVS = frozenset({"sensor.tv"})
CFG = WhereaboutsConfig(outside_doors=DOORS, sitting_appliances=TVS)

def test_presence_starts_home_interval_in_that_room():
    w = Whereabouts(CFG); w.record(_presence(T(10, 0), "Kitchen"))
    iv = w.current(T(10, 30))
    assert (iv.where, iv.room, iv.start) == (Where.HOME, "Kitchen", T(10, 0))

def test_lights_and_generic_and_close_do_not_start_intervals():
    # LIGHT_ON, GENERIC, CLOSE, APPLIANCE_OFF after presence at 10:00 -> start stays 10:00

def test_tv_on_in_last_room_gives_home_tv_and_turning_off_does_not_reset():
    # presence Backroom 19:00, tv APPLIANCE_ON Backroom 19:01 -> HOME_TV start 19:01
    # tv APPLIANCE_OFF 19:30 -> still HOME_TV, start 19:01

def test_tv_in_another_room_is_plain_home():

def test_outside_door_then_quiet_is_out_after_ten_minutes():
    # OPEN front door 10:00 -> current(10:09).where == HOME, current(10:10).where == OUT, door == "binary_sensor.front_door"

def test_presence_in_door_room_within_two_minutes_is_ignored():
    # door in Hall opens 10:00, Hall presence 10:01 -> current(10:15).where == OUT, start 10:00

def test_presence_in_door_room_after_two_minutes_brings_her_home():
    # door in Hall opens 10:00, Hall presence 10:03 -> HOME, start 10:03

def test_presence_elsewhere_within_ten_minutes_is_home():

def test_non_outside_contact_is_plain_activity():

def test_bedroom_at_night_is_asleep_and_morning_is_lying_in_and_afternoon_is_home():
    # Back Bedroom presence 22:30 -> ASLEEP; 06:30 -> LYING_IN; 11:30 -> HOME

def test_asleep_wins_over_bedroom_tv():
    # Front bedroom TV on, presence Front bedroom 21:00 -> ASLEEP

def test_bedrooms_none_matches_names_and_explicit_set_overrides():
    # default: "Front Bedroom" is bedroom; bedrooms=frozenset({"Box room"}): "Front Bedroom" is not, "Box room" is

def test_no_bedrooms_chosen_applies_night_rules_to_every_room():
    # bedrooms=frozenset(): presence Lounge 23:00 -> ASLEEP
```

Write each test body to the assertions in its comment.

- [ ] **Step 2: Run them to see them fail**

Run: `pytest tests/core/test_whereabouts.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `core/whereabouts.py` to the rules above**

Keep the TV on-set as `dict[str, str]` (appliance entity → room) of appliances currently on.

- [ ] **Step 4: Run the tests to see them pass**

Run: `pytest tests/core/test_whereabouts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/behaviour_monitor/core/whereabouts.py tests/core/test_whereabouts.py
git commit -m "feat: whereabouts state machine for the welfare alert"
```

### Task 2: Learned values and persistence

**Files:**
- Modify: `custom_components/behaviour_monitor/core/whereabouts.py`
- Test: `tests/core/test_whereabouts.py`

**Interfaces:**
- Consumes: Task 1's `Whereabouts`, `Interval`, `Where`.
- Produces on `Whereabouts`:
  - `home_limit_min(hour: int) -> float`
  - `usual_waking_min() -> int`
  - `earliest_waking_min() -> int`
  - `longest_out_min() -> float | None`
  - `night_start() -> int`, `night_end() -> int`, `lie_in_end() -> int` (minutes after midnight)
  - `prune(before: date) -> None`
  - `restart_clock(now: datetime) -> None` (current interval keeps its `where`, `room`, `tv`, `door`; its `start` becomes `now`)
  - `to_dict() -> dict[str, Any]` and `@classmethod from_dict(data: dict[str, Any], config: WhereaboutsConfig) -> Whereabouts` (bad or missing data returns a fresh instance, like the other models).

What is learned, all keyed by ISO day for pruning (the same window as the other models):

- When an interval ends (the next interval starts), record its length:
  - `HOME` intervals go into per-hour samples keyed by start hour, one list per day;
  - `OUT` intervals go into outing lengths, but only if under 24 h (Review Focus 1).
- The main sleep for each night is the longest interval that starts between 18:00 and 04:00 in a bedroom (any room if no bedrooms are chosen). Its night key is the evening's date (a start before 04:00 belongs to the previous date). Keep its start time.
- Waking per day is the first activity at or after 04:00 outside a bedroom. With no bedrooms chosen, use the end of that morning's main sleep.

Each learned value falls back until it has samples from at least 3 distinct days:

| Value | Rule | Fallback |
|---|---|---|
| `home_limit_min(h)` | clamp(q(samples of hour `h`, 0.995), 45, 60) | 60 |
| `usual_waking_min()` | q(waking, 0.95) | 540 |
| `earliest_waking_min()` | q(waking, 0.05) | night end + 60 |
| `longest_out_min()` | max of outing lengths | `None`; the deadline then uses 240 |
| `night_start()` | q(main-sleep starts measured from noon, 0.05) − 60, clamp 18:00–01:00 | 20:00 |
| `night_end()` | `earliest_waking_min()` − 60, clamp 03:00–09:00 | 05:00 |
| `lie_in_end()` | `usual_waking_min()` + 120, clamp to [night end + 120, 13:00] | 11:00 |

`q(xs, p)` is `sorted(xs)[min(len-1, int(p*len))]`, as in the spike.

- [ ] **Step 1: Write the failing tests**

```python
def test_home_limit_learns_995th_percentile_clamped_to_45_60():
    # 3 days of 10:xx HOME intervals of 20/50/70 min -> home_limit_min(10) == 60; all 20 min -> 45; one day only -> 60

def test_usual_waking_is_95th_percentile_of_first_non_bedroom_activity_after_4am():
    # days with first Kitchen presence 07:00, 07:30, 08:40 (Bedroom presence 05:00 each day ignored) -> 520

def test_learned_night_bounds_and_their_clamps():
    # main sleeps start 21:30, 22:00, 22:15; waking 06:30, 07:00, 08:00
    # -> night_start == 20*60+30, night_end == 5*60+30, lie_in_end == 10*60
    # main sleeps start 16:00-ish are not candidates; waking 02:00 clamps night_end to 180

def test_fallback_night_before_three_days():
    assert (w.night_start(), w.night_end(), w.lie_in_end()) == (1200, 300, 660)

def test_learned_night_changes_state_of_a_bedroom_interval():
    # learned night_end 05:30: Bedroom presence 05:15 -> ASLEEP (fallback would say LYING_IN)

def test_longest_outing_ignores_trips_of_a_day_or_more():
    # outs of 90 min and 30 h -> longest_out_min() == 90

def test_restart_clock_keeps_state_and_moves_start():

def test_round_trip_and_prune():
    # to_dict/from_dict preserves current interval, tv set and learned values; prune drops days before cutoff; from_dict({"junk": 1}) is fresh
```

- [ ] **Step 2: Run them to see them fail**

Run: `pytest tests/core/test_whereabouts.py -v`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement the learning, `prune`, `restart_clock`, `to_dict`/`from_dict`**

Replace Task 1's fixed night methods with the learned ones.

- [ ] **Step 4: Run all whereabouts tests**

Run: `pytest tests/core/test_whereabouts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -am "feat: whereabouts learns home limits, waking time, night and outings"
```

### Task 3: Whereabouts alerts

**Files:**
- Modify: `custom_components/behaviour_monitor/core/whereabouts.py`
- Test: `tests/core/test_whereabouts.py`

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces:
  - `@dataclass(frozen=True) class WhereAssessment`: `where: Where | None`, `since: datetime | None`, `room: str | None`, `limit_min: float | None`, `deadline: datetime | None`, `alert: Alert | None`, `degraded: bool`.
  - `Whereabouts.evaluate(now: datetime, live_fraction: float = 1.0, names: Callable[[str], str] | None = None) -> WhereAssessment`. `names` maps a door or appliance entity id to a readable name; the default is the entity id.

Deadlines and limits:

| State | Limit | Deadline | Kind | HIGH from |
|---|---|---|---|---|
| `HOME` | `home_limit_min(start.hour)` | start + limit | `still_at_home` | start + 1.5 × limit |
| `HOME_TV` | 90 | start + 90 min | `still_tv` | start + 135 min |
| `LYING_IN` | 90 | start + 90 min | `not_up` | start + 135 min |
| `ASLEEP` | `None` | usual waking + 60 min, on the morning after the start (the same morning if it started before noon) | `not_up` | deadline + 60 min |
| `OUT` | `None` | start + 1.25 × (longest outing, or 240) | `not_back` | deadline + 60 min |

**Ruling (plan):** the spec's table has no kind for `lying_in`. It alerts as `not_up`, with the lying-in wording below.

An alert exists when `now >= deadline`, unless `live_fraction < 0.5`; then `degraded=True` and there is no alert. It has severity MEDIUM until the HIGH point, then HIGH. `Alert(AlertClass.WELFARE, "whereabouts", kind, severity, text, now, details)`, with `details` holding `room`, `where`, `since` (ISO), `limit_min` and `minutes` (stillness so far, whole minutes).

The text, with times as `%H:%M` and durations as `"{h}h {m}m"` at 60 min or more, `"{m} min"` otherwise:

- `still_at_home`: `"No movement for {dur}; last seen in the {room} at {since}"`
- `still_tv`: `"No movement for {dur} with the {room} TV on; last seen at {since}"`
- `not_up` (asleep): `"Not up yet; usually up by {waking}, last seen in the {room} at {since}"`
- `not_up` (lying in): `"Not up yet; stirred in the {room} at {since}, no movement for {dur}"`
- `not_back`: `"Out for {dur}, longer than usual (longest {longest}); left by the {door name} at {since}"`. Without a learned outing, use `"(usual limit 4h 0m)"` in place of `"(longest …)"`.

`limit_min` in the assessment is `None` for `ASLEEP` and `OUT`.

- [ ] **Step 1: Write the failing tests**

```python
def test_still_at_home_opens_medium_at_limit_and_high_at_one_and_a_half():
    # HOME 10:00, limit 60 -> 10:59 no alert; 11:00 MEDIUM still_at_home "No movement for 1h 0m; last seen in the Kitchen at 10:00"; 11:30 HIGH

def test_still_tv_uses_ninety_minutes():

def test_lying_in_alerts_as_not_up_after_ninety_minutes():

def test_asleep_alerts_at_usual_waking_plus_an_hour_next_morning():
    # fallback waking 09:00: Bedroom 22:30 -> no alert 09:59 next day; MEDIUM at 10:00; HIGH at 11:00

def test_out_alerts_not_back_after_longest_outing_times_one_and_a_quarter():
    # no outings learned -> 240 min; text contains "left by the Front door at 10:00"

def test_degraded_suppresses_alert():
    assert w.evaluate(T(12, 0), live_fraction=0.4).alert is None and ....degraded

def test_details_carry_room_and_limit():
```

- [ ] **Step 2: Run them to see them fail**

Run: `pytest tests/core/test_whereabouts.py -v`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement `evaluate`**

- [ ] **Step 4: Run the whereabouts tests**

Run: `pytest tests/core/test_whereabouts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -am "feat: whereabouts raises still_at_home, still_tv, not_up and not_back"
```

### Task 4: Engine wiring, replacing the house inactivity alert

**Files:**
- Modify:
  - `custom_components/behaviour_monitor/core/engine.py`
  - `custom_components/behaviour_monitor/core/house_model.py`
  - `custom_components/behaviour_monitor/core/alert_router.py`
- Test:
  - `tests/core/test_engine.py`
  - `tests/core/test_house_model.py`
  - `tests/core/test_alert_router.py`
  - `tests/core/test_replay_scenarios.py`
  - `tests/core/synth.py`

**Interfaces:**
- Consumes: `Whereabouts`, `WhereaboutsConfig`, `WhereAssessment` (Tasks 1–3).
- Produces:
  - `EngineConfig.whereabouts: WhereaboutsConfig`.
  - `EngineConfig.from_options` reads three option keys:
    - `"outside_doors"`: list of entity ids;
    - `"sitting_appliances"`: list of entity ids;
    - `"bedrooms"`: list of room names, or absent/`None` for the name rule.
  - `SCHEMA_VERSION = 3`.
  - Snapshot key `"whereabouts": {"where", "where_since", "last_room", "limit_min"}`. The values are a string or `None`, an ISO string or `None`, a string or `None`, and a float or `None`.

Changes:

1. **`Engine`**
   - Holds `self._where = Whereabouts(config.whereabouts)`.
   - `_learn` calls `self._where.record(ev)`, which ignores non-whereabouts kinds itself.
   - `poll` replaces the `house`/`inactivity` alert block with `self._where.evaluate(now, live, names=...)`. `names` uses `drift_names()`, falling back to the entity id. The resulting alert is appended under the same `learned and not holiday` gate.
   - `self._degraded` comes from the whereabouts assessment.
2. **Restarts and gaps**
   - On holiday end, call `self._where.restart_clock(now)` beside `self._house.restart_clock(now)`.
   - Persist `last_poll` (ISO datetime) in `meta`. At the start of `poll`, when `last_poll` is set and `now - last_poll >= 30 min`, call `self._where.restart_clock(now)`. Then set `last_poll = now`.
   - Prune whereabouts with the other models.
3. **`to_dict`/`from_dict`** include `"whereabouts"`. Bumping `SCHEMA_VERSION` to 3 makes the coordinator relearn from the recorder on upgrade, through its existing schema check.
4. **`HouseModel`** stops raising alerts. Delete `evaluate`, `_sustain`, `HouseAssessment`, the severity ladder fields, `restart_clock`'s ladder reset, and the `low/medium/high_ratio`, `floor_s`, `sustain_polls`, `min_live_fraction` config fields.
   - Keep recording, `expected_gap`, `last_activity`, `last_room`, `rooms_visited`, `days_observed`, `prune` and persistence. Leave the `"current"` key out of `to_dict`, and ignore it in `from_dict`.
   - `min_live_fraction` moves to `WhereaboutsConfig` (0.5).
   - Delete the house-ratio wiring in `from_options`. The `house_low_ratio` option goes away in Task 5.
5. **`AlertRouter._combine`** matches `a.cls is AlertClass.WELFARE and a.source == "whereabouts"` where it matched `source == "house" and kind == "inactivity"`. `routine_agreement` keeps source `"house"`.
6. **`snapshot`**
   - Adds the `"whereabouts"` block from the latest assessment (store it on `self._last_where` in `poll`).
   - `house.expected_s` stays.
7. **Tests**
   - **`synth`:** `write_fixture` puts `outside_doors: ["binary_sensor.side_door"]` and `sitting_appliances: ["sensor.tv_power"]` into the sidecar options.
   - **Inactivity tests:** update those that assert `kind == "inactivity"` or today's timings to the whereabouts kinds:
     - `test_engine.py:125`, `:161–165` and `:267`;
     - `test_replay_scenarios.py:59` and `:79`.

     The chain-stall scenario must still raise a welfare push before midday.
   - **House model:** delete the house-model tests for removed methods (`test_severity_ladder_and_sustain`, `test_restart_clock_resets_gap_and_ladder`, `test_floor_prevents…`, `test_unknown_slot…`, `test_degraded…` ×2, `test_default_floor…`).

- [ ] **Step 1: Write the failing engine tests**

```python
def test_kitchen_stillness_raises_still_at_home_within_an_hour(...):
    # learned engine (14+ days synth), last presence Kitchen 10:00, poll to 11:05 -> attention opened, kind still_at_home, source whereabouts, details["room"] contains Kitchen

def test_outing_through_side_door_raises_no_fall_alert():
    # learned engine, side door OPEN 10:00, no activity, poll to 13:00 -> no welfare attention opened

def test_short_poll_gap_keeps_counting_and_long_gap_restarts():
    # last presence 10:00; poll 10:20; next poll 10:45 (25 min gap) then 11:05 -> alert open
    # same with next poll 10:50 (30 min gap): no alert at 11:05; alert by 11:50+ (limit from 10:50)
    # an OUT interval through a 40-min gap stays OUT (snapshot where == "out")

def test_snapshot_has_whereabouts_block():
    assert set(snap["whereabouts"]) == {"where", "where_since", "last_room", "limit_min"}

def test_router_escalates_whereabouts_alert_on_routine_signs():  # in test_alert_router.py, mirror the existing house escalation test with source "whereabouts", kind "still_at_home"

def test_schema_3_round_trip_keeps_whereabouts_state():
```

- [ ] **Step 2: Run them to see them fail**

Run: `pytest tests/core -v`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement changes 1–6 and update the existing tests per 7**

- [ ] **Step 4: Run the core suite**

Run: `pytest tests/core -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A custom_components/behaviour_monitor/core tests/core
git commit -m "feat!: whereabouts alert replaces the whole-house inactivity alert"
```

### Task 5: Home Assistant shell (setup step, migration, sensor)

**Files:**
- Create: `custom_components/behaviour_monitor/rooms.py`
- Modify:
  - `custom_components/behaviour_monitor/const.py`
  - `custom_components/behaviour_monitor/config_flow.py`
  - `custom_components/behaviour_monitor/__init__.py`
  - `custom_components/behaviour_monitor/coordinator.py`
  - `custom_components/behaviour_monitor/sensor.py`
  - `custom_components/behaviour_monitor/translations/en.json`
- Test:
  - `tests/test_config_flow.py`
  - `tests/test_init.py`
  - `tests/test_coordinator.py`
  - `tests/test_sensor.py`
  - `tests/test_translations.py`
  - `tests/test_const.py`

**Interfaces:**
- Consumes:
  - option keys `"outside_doors"`, `"sitting_appliances"`, `"bedrooms"` (Task 4);
  - snapshot `"whereabouts"` (Task 4).
- Produces:
  - **`const.py`:**
    - `CONF_OUTSIDE_DOORS = "outside_doors"`;
    - `CONF_SITTING_APPLIANCES = "sitting_appliances"`;
    - `CONF_BEDROOMS = "bedrooms"`;
    - `CONFIG_VERSION = 13`;
    - `CONF_HOUSE_LOW_RATIO` moves to the legacy section as `LEGACY_CONF_HOUSE_LOW_RATIO`.
  - **`rooms.py`:**
    - `resolve_room(hass, entity_id) -> tuple[str, str | None]`, moved from `BehaviourMonitorCoordinator._room_for`, with the same behaviour;
    - `bedroom_suggestions(rooms: Iterable[str]) -> list[str]`, the rooms whose name contains "bedroom" (case-insensitive), sorted.

Changes:

1. **Config flow.** `async_step_user` validates as today, keeps the data, then goes to a new `async_step_whereabouts`. This step is shared by the options flow, after `async_step_init`. Its schema:
   - `outside_doors`: `EntitySelector(multiple=True, include_entities=<configured contact entities>)`. Default `[]` (current value in options).
   - `bedrooms`: `SelectSelector(multiple=True, options=[{"value": room, "label": display room}])` over the resolved rooms of the configured entities. Default: the current value, or `bedroom_suggestions(rooms)` when unset.
   - `sitting_appliances`: `EntitySelector(multiple=True, include_entities=<configured plug entities>)`. Default `[]`.
   - Validation: a door that isn't a configured contact gives error `door_not_contact`, and an appliance that isn't a configured plug gives `appliance_not_plug`. This protects against a stale list after the categories change.
   - The three values are stored in `entry.options`. `CONF_HOUSE_LOW_RATIO` is removed from `OPTION_DEFAULTS` and the options form.
2. **Migration to v13** in `async_migrate_entry` runs for any entry below 13:
   - options get `outside_doors: []` and `sitting_appliances: []`;
   - `bedrooms` is left unset, so the engine applies the name rule;
   - `house_low_ratio` is popped.

   The existing v11/v12 paths still run first for older entries.
3. **Coordinator**
   - Uses `rooms.resolve_room`.
   - **Area rename** (Review Focus 5): when `_async_registry_updated` takes the rename path and the old room is in `entry.options["bedrooms"]`, replace it with the new name through `hass.config_entries.async_update_entry`. The resulting reload is acceptable.
4. **Sensor.** Welfare Status attributes gain:
   - `where`;
   - `where_since`;
   - `last_room` (display name);
   - `limit_min`.
5. **Translations**
   - `config.step.whereabouts` and `options.step.whereabouts` get a title.
   - The description explains each list in one sentence:
     - outside doors: "Doors that lead outside. Don't pick fridge, cupboard or internal doors: they would hold back fall alerts.";
     - bedrooms: "Rooms she sleeps in. Stillness here at night is normal.";
     - sitting appliances: "Plugs, like a TV, that mean she is sitting nearby when on."
   - Error strings for both new codes.
   - Remove `house_low_ratio`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_user_step_then_whereabouts_step_creates_entry_with_lists(hass): # options contain the three lists
async def test_bedrooms_default_to_rooms_named_bedroom(hass):                 # form default == ["Back Bedroom"] for the synth-like rooms
async def test_options_flow_whereabouts_step_rejects_door_not_contact(hass):
async def test_migrate_v12_to_v13_adds_empty_lists_and_drops_house_low_ratio(hass): # bedrooms not in options
async def test_area_rename_renames_bedroom_option(hass):
def test_welfare_status_exposes_whereabouts_attributes():
```

Also update every `tests/test_coordinator.py` fixture that builds an `inactivity` alert, using `source="whereabouts"` and `kind="still_at_home"`.

- [ ] **Step 2: Run them to see them fail**

Run: `pytest tests -v --ignore=tests/core`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement changes 1–5**

- [ ] **Step 4: Run the full suite and lint**

Run: `make test && make lint`
Expected: all tests pass; ruff and mypy clean.

- [ ] **Step 5: Commit**

```bash
git add -A custom_components tests
git commit -m "feat: setup step for outside doors, bedrooms and sitting appliances"
```

### Task 6: Acceptance on Biddulph Road and docs

**Files:**
- Modify:
  - `README.md`, adding a "Where she is" section. It describes the three lists, the five states, the four alert kinds and the upgrade note: "Set outside doors and sitting appliances after upgrading".
  - `CLAUDE.md`, changing "Config entry version is 12" to 13 and adding `whereabouts` to the core module list.
  - `custom_components/behaviour_monitor/CLAUDE.md`, adding `whereabouts` to the module list.
- Local only (git-ignored): `exports/fixture/biddulph_road.sidecar.json` gets `"options": {"outside_doors": ["binary_sensor.front_door_door", "binary_sensor.back_door_door", "binary_sensor.side_door_door"], "sitting_appliances": ["sensor.smart_plug_power", "sensor.front_bedroom_tv_power"]}`. Bedrooms are left to the name rule, which gives Front bedroom and Back bedroom.

- [ ] **Step 1: Run the acceptance scorecard**

Run: `python scripts/scorecard.py exports/fixture/biddulph_road.jsonl --truth exports/fixture/biddulph_road.truth.yaml --fall-times 08:00,09:00,10:00,11:00,12:00,13:00,14:00,15:00,16:00,17:00,18:00,19:00,20:00 --fall-days 25`

Expected (the spec's acceptance criteria):
- injected falls: median 90 min or less, and 90% within 100 min;
- unexplained welfare alerts: 2 or fewer;
- no welfare alert inside a truth `out` window.

- [ ] **Step 2: If it misses, stop and report**

Report the numbers, which falls were slow and which alerts were unexplained. Don't tune the fixed values to pass. Changing them is the owner's decision.

- [ ] **Step 3: Write the docs changes above**

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md custom_components/behaviour_monitor/CLAUDE.md
git commit -m "docs: where she is, setup lists and upgrade note"
```
