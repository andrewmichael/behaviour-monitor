# Really Unusual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the noisy routine notes with three learned card kinds
(`not_yet_today`, `trip_missed`, `unusual_now`) and two learned night pushes
(`night_downstairs`, `night_door`).

**Architecture:** A new pure-stdlib module `core/unusual.py` holds the
learning and evaluation for all five kinds. It reads whereabouts, routines
and health through arguments, never through stored references, so
`Engine.from_dict` can swap models freely. The router hides `routine_missed`
and `chain_stall` after `_combine` (they stay internal escalation signs) and
stops creating `routine_agreement`. The shell adds the Upstairs rooms tick
list and the night-trip minutes option, migrates the config entry to
version 14, and rebuilds the new history from the recorder on the first
start after upgrade.

**Tech Stack:** Python 3 stdlib (`core/`), Home Assistant custom integration
(shell), pytest.

**Spec:** `docs/superpowers/specs/2026-11-10-really-unusual-design.md`

## Global Constraints

- `core/` stays stdlib only, with no Home Assistant imports. Every core
  function takes the time as an argument and never reads the clock.
- No fixed clock times anywhere in the logic. Every time of day comes from
  learned values (`Whereabouts.night_start()`, `night_end(day)`, learned
  first-use times, learned outing bins). Only the spec's Constants table
  values are fixed.
- Constants, verbatim from the spec:
  - `usual_fraction=0.90`
  - `allowance_floor_min=60`
  - `trip_fraction=0.75`
  - `trip_min_days=4`
  - `trip_slack_min=60`
  - `unusual_neighbour_h=1`
  - `unusual_ttl_min=120`
  - `went_up_within_min=5`
  - `bedtime_quiet_min=30`
  - `trip_end_quiet_min=5`
  - `night_normal_fraction=0.10`
  - `min_days=14`
- The night-trip option is `night_trip_min`: default 30, range 10–120, step 5,
  unit "min".
- `SCHEMA_VERSION` stays 3, and the store version is unchanged. New stored
  fields load with tolerant defaults. An old store must load with its
  learning kept.
- Config entry version goes 13 → 14. The migration adds
  `upstairs_rooms: []`.
- Card kinds: `AlertClass.STATISTICAL`, `Severity.LOW`. Night kinds:
  `AlertClass.WELFARE`, `Severity.MEDIUM`, `source="night"`.
- `routine_missed`, `chain_stall` and `routine_agreement` are never
  published anywhere: no event, no logbook, no sensor attribute.
- Commits use `feat:` for the feature (a minor release), `fix:` for fixes
  and `docs:` for docs. Never `!` or `BREAKING`. Never hand-edit the version
  in `manifest.json`. End every commit with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Verify with `source venv/bin/activate && make test`,
  `ruff check custom_components tests scripts` and
  `black --check custom_components tests`. Run black from the venv: the
  pyenv black formats differently.
- Never commit anything under `exports/`.

## Review Focus

1. **HA restart in the middle of the night.** A store saved at 02:00 during a
   night trip must restore the trip, so the 30-minute push still fires once.
   No new trip may start, and night must not end. Test in Task 3.
2. **Bedtime after midnight.** The house goes up at 00:30 when the learned
   `night_start` is 23:00. Night must still start, using noon-based
   ordering, and the night is keyed to the previous evening's date.
   Test in Task 3.
3. **A poll gap during a night trip.** With no polls from 02:10 to 02:55,
   the first poll after must raise `night_downstairs` exactly once. Test in
   Task 3.
4. **Clocks change.** On the October clock-change day, first-use minutes and
   night times use local time. A 01:30 that occurs twice must not end or
   restart the night. Test in Task 3 with a `zoneinfo` Europe/London fixture.
5. **Holiday.** Nights and days during holiday mode are not learned, so
   they don't count toward `min_days` or the 10% normal fraction. Night
   state is cleared when holiday ends. Test in Task 5.

---

### Task 1: Whereabouts outing spans, sitting rooms, health down-today

**Files:**
- Modify: `custom_components/behaviour_monitor/core/whereabouts.py`
  (`__init__`, `_close`, `prune`, `to_dict`, `from_dict`, new public
  methods)
- Modify: `custom_components/behaviour_monitor/core/health_tracker.py`
  (`_EntityHealth`, `record_health`, new method)
- Test: `tests/core/test_whereabouts.py`, `tests/core/test_health_tracker.py`

**Interfaces:**
- Produces:
  - `Whereabouts.out_spans(day: date) -> list[tuple[int, int]]`: closed OUT
    intervals that started on `day`, as (start minute, end minute) after
    local midnight. The end is clipped to 1440.
  - `Whereabouts.is_out(now: datetime) -> bool`: true when `current(now)`
    is `Where.OUT`.
  - `Whereabouts.sitting_rooms() -> set[str]`: rooms with a sitting
    appliance on.
  - `Whereabouts.adopt_out_spans(spans: dict[str, list[tuple[int, int]]]) -> None`:
    replaces the stored spans. Task 5's rebuild uses it.
  - `HealthTracker.down_today(now: datetime) -> set[str]`: entities down now,
    or that went down at any time on `now.date()`.

- [ ] **Step 1: Write failing tests.**
  - `test_out_spans_record_closed_outings_by_start_day`: door open at 10:00,
    presence at 12:30. Assert `out_spans(day) == [(600, 750)]`.
  - `test_out_spans_survive_round_trip_and_old_store`: `to_dict` then
    `from_dict` keeps the spans. A dict without `"out_spans"` loads with `{}`
    and keeps `_outs`.
  - `test_out_spans_pruned_with_window`.
  - `test_is_out_and_sitting_rooms`: OUT after 10 min. A TV plug on in
    "Back room" gives `{"Back room"}`.
  - `test_down_today_includes_recovered_entity`: down at 08:00 and back at
    08:10. `down_today(13:00)` contains it, and the next day does not.
- [ ] **Step 2: Run them; they should fail.** Run
  `pytest tests/core/test_whereabouts.py tests/core/test_health_tracker.py -q`.
- [ ] **Step 3: Implement.**
  - In `_close`, append to `self._out_spans[iso_day(iv.start.date())]` in
    the same branch that appends `_outs`.
  - Add `last_down: datetime | None` to `_EntityHealth`, set where
    `down_since` is set. It isn't persisted; a restart forgets it.
- [ ] **Step 4: Run the tests; they should pass.** Run `make test`.
- [ ] **Step 5: Commit** with
  `feat: whereabouts keeps outing times and health knows who was down today`.

### Task 2: `core/unusual.py` card kinds

**Files:**
- Create: `custom_components/behaviour_monitor/core/unusual.py`
- Test: `tests/core/test_unusual.py`

**Interfaces:**
- Consumes (Task 1):
  - `Whereabouts.out_spans`, `is_out`, `night_end(day)`
  - `HealthTracker.down_today`
- Consumes (existing):
  - `EntityRoutineModel.get(eid).slot_days`
  - `EntityRoutine.days_seen`
- Produces:
  - `UnusualConfig`, frozen. Fields: the spec constants above, plus
    `night_trip_min: float = 30.0`, `window_days: int = 28` and
    `upstairs: frozenset[str] = frozenset()`.
  - `Unusual(config)` with:
    - `record(ev: ActivityEvent, where: Whereabouts) -> None`. The engine
      calls it **before** `where.record(ev)`, so `where` reflects the moment
      just before the event.
    - `finalise_day(day: date, entity_ids: Iterable[str], active: bool) -> None`
    - `evaluate(now, where, routines, down: set[str], names: Callable[[str], str], categories: dict[str, Category]) -> list[Alert]`
    - `remove(entity_id)`, `prune(before: date)`
    - `to_dict()` and `from_dict(data, config)`. `from_dict` is tolerant and
      returns a fresh instance on bad data.

**Behaviour, per the spec's "How each is learned":**
- **First use.** `record` stores each entity's first activity minute per
  local day, at or after `where.night_end(day)`.
  - `finalise_day(day, ids, active=True)` writes `None` for ids with no use
    that day.
  - `active=False` (no activity in the house) records nothing, so the day
    doesn't count.
  - Learned days are the active days inside `window_days`, excluding today.
- **`not_yet_today`.**
  - The entity needs at least `min_days` learned days and use on at least
    `usual_fraction` of them.
  - `T` is the P90 of first-use minutes. `A = max(allowance_floor_min, P90 − P50)`.
  - The alert is raised when `now` minutes ≥ `T + A`, the entity has no
    first use today, it isn't in `down`, and its category isn't panic.
  - Explanation: `f"{names(eid)} not used yet today; usually by {T:%H:%M}"`.
  - Details: `room`, `usual_by` ("HH:MM") and
    `went_out_today = bool(where.out_spans(today)) or where.is_out(now)`.
- **`trip_missed`.**
  - Over the active same-weekday learned days (at least `trip_min_days`),
    each `out_spans` day marks 15-minute bins within ±`trip_slack_min` of an
    outing.
  - Bins marked on at least `trip_fraction` of those days form windows,
    where consecutive bins merge.
  - The alert is raised once `now` passes the window end plus
    `trip_slack_min` with no outing today overlapping the window ±slack
    (closed spans plus `is_out` now).
  - `source=f"trip:{start:%H%M}"`.
  - Explanation: `f"Usual {weekday} outing (around {start} to {end}) didn't happen"`.
- **`unusual_now`.**
  - `record` notes the first activity per (entity, local hour) today.
  - The entity needs at least `min_days` of its own `days_seen` (excluding
    today) in the window.
  - It qualifies if no learned day has a slot in hours h−1, h or h+1 (mod 24,
    using that day's weekday for the slot index).
  - The alert is open from the activity time until 120 min after it,
    skipping entities in `down`.
  - Explanation: `f"{names(eid)} active at {t:%H:%M}, unusual for this time"`.
  - One open per entity: the latest wins.

- [ ] **Step 1: Write failing tests** with hand-fed `ActivityEvent`s, a real
  `Whereabouts` and a real `EntityRoutineModel`. Train 20 days unless the
  test says otherwise.
  - `test_not_yet_today_fires_after_usual_plus_allowance`: kettle first use
    is 07:00–07:40 across days. Nothing at P90 + A − 1 min, an alert at
    P90 + A, and it clears once the kettle fires.
  - `test_not_yet_today_allowance_grows_with_spread`: first uses spread
    06:00–10:00 give `A = P90 − P50` (more than 60).
  - `test_not_yet_today_needs_fraction_and_min_days`: used on 85% of days
    gives no alert; 13 learned days gives no alert.
  - `test_not_yet_today_skips_down_and_panic`.
  - `test_not_yet_today_went_out_flag`.
  - `test_trip_missed_learns_weekday_window_and_fires_after_slack`: 4
    Fridays out 10:00–12:30. A 5th Friday at home raises at 13:30 + slack.
    A Friday with an outing raises nothing.
  - `test_trip_missed_needs_four_days_and_doors`: 3 Fridays give nothing,
    and no OUT history gives nothing.
  - `test_unusual_now_fires_only_outside_learned_hours_and_ttl`: the back
    door is learned 08–20. A door at 02:14 raises; one at 21:00 doesn't
    (neighbour of 20). The 02:14 alert is gone at 04:15.
  - `test_unusual_now_new_sensor_and_down_sensor_silent`: an entity with
    13 days of history, and an entity in `down`.
  - `test_round_trip_and_tolerant_from_dict`.
- [ ] **Step 2: Run** `pytest tests/core/test_unusual.py -q`; the tests should
  fail.
- [ ] **Step 3: Implement** `unusual.py` card parts. Reuse `_quantile` from
  `whereabouts` (import it) and `iso_day` from `slots`.
- [ ] **Step 4: Run the tests; they should pass.**
- [ ] **Step 5: Commit** with
  `feat: learn what is really unusual: not yet today, missed trips, unusual times`.

### Task 3: `core/unusual.py` night detection and pushes

**Files:**
- Modify: `custom_components/behaviour_monitor/core/unusual.py`
- Test: `tests/core/test_unusual.py`

**Interfaces:**
- Consumes:
  - `Whereabouts.is_bedroom`, `night_start()`, `night_end(day)`, `is_out`,
    `sitting_rooms`
  - `WhereaboutsConfig.outside_doors`
  - `UnusualConfig.upstairs`, `night_trip_min`
- Produces: `evaluate` additionally returns the `night_downstairs` and
  `night_door` alerts. `Unusual.night_since -> datetime | None` is a
  property for tests and the snapshot.

**Behaviour, per the spec's "Night" sections:**
- **Room classes.**
  - A night room is `where.is_bedroom(room)` or a room in `upstairs`.
  - An OPEN from an outside door is a door event.
  - Every other activity is a day room.
- **Going up.** Outside night, day-room activity sets `last_day_at` and
  clears `went_up_at`. Night-room activity within `went_up_within_min` of
  `last_day_at`, while `went_up_at` is None, sets `went_up_at`.
- **Night starts** (checked in a private `_advance(now, where)` run at the
  start of `record` and `evaluate`) when all of these hold:
  - `went_up_at` is set;
  - `now − went_up_at ≥ bedtime_quiet_min`;
  - there's been no day-room activity since;
  - `where.sitting_rooms()` has no day room;
  - `went_up_at` lies between `night_start()` and `night_end` in
    noon-based order.

  Then `night_since = went_up_at`.
- **Night ends** at day-room activity at or after `night_end(that date)` on
  the morning side of `night_since`. A 20-hour cap is a safety net. When it
  ends, the night record is finalised under the evening's date.
- **Trips.**
  - In night, day-room activity starts a trip (if none) and updates
    `trip_last_day`.
  - Night-room activity after `trip_last_day` sets `trip_up_at`.
  - In `_advance`, a trip ends when `trip_up_at > trip_last_day` and
    `now − trip_last_day ≥ trip_end_quiet_min`. Its length,
    `trip_last_day − trip_start`, goes into the night record's max.
- **Door.** In night, a door OPEN while `not where.is_out(ts)` records the
  hour in the night record and sets `door_at`. It clears at night-room
  activity after `door_at`, or at night end.
- **Normal for this house.** This needs at least `min_days` finalised nights
  in the window.
  - A long trip is normal if more than 10% of those nights have a trip of at
    least `night_trip_min`.
  - A door at hour h is normal if more than 10% have a door in h±1.
  - Below `min_days` nights, both pushes are withheld (owner's option A).
- **`night_downstairs`.** Open while a trip is in progress and
  `now − trip_start ≥ night_trip_min` and the trip isn't normal.
  - Explanation: `f"Someone has been downstairs for {mins} min during the night (since {start:%H:%M}, in the {room})"`.
  - Details: `room` and `since`.
- **`night_door`.** Open while `door_at` is set and not normal.
  - Explanation: `f"{names(door)} opened during the night at {t:%H:%M}"`.
- **Persistence.** `to_dict` includes the in-progress night state (all the
  timestamps above) and the night records.

- [ ] **Step 1: Write failing tests.** The helper `_night_house()` trains 20
  nights: day rooms until about 21:55, then a bedroom within 2 min, a TV
  plug in the back room, and a 0–10 min kitchen trip some nights.
  - `test_night_starts_only_after_going_up_and_quiet_and_tv_off`. Assert
    `night_since` is back-dated to the bedroom event.
  - `test_tv_on_doze_is_not_night`.
  - `test_quiet_read_without_going_up_is_not_night`.
  - `test_first_to_bed_while_other_downstairs_is_not_night`: two
    occupants, one goes up at 20:30 while the back room is active until
    22:00.
  - `test_long_night_trip_pushes_once_at_30_min_and_clears_back_upstairs`.
  - `test_short_trip_sends_nothing`.
  - `test_night_door_while_home_pushes_and_while_out_does_not`.
  - `test_regular_2330_back_door_is_learned_normal`: a door in the 23:00
    hour on 30% of nights gives no push.
  - `test_regular_long_trip_is_learned_normal`.
  - `test_no_push_before_14_nights`.
  - `test_bungalow_bedrooms_only`: `upstairs` is empty and a bathroom
    counts as a day room. A 3-minute bathroom trip sends nothing.
  - `test_morning_ends_night_at_learned_night_end`.
  - The Review Focus tests:
    - `test_restart_mid_night_keeps_trip`
    - `test_bedtime_after_midnight`
    - `test_poll_gap_during_trip_fires_once`
    - `test_clock_change_night`
- [ ] **Step 2: Run them; they should fail.**
- [ ] **Step 3: Implement** the night parts.
- [ ] **Step 4: Run the tests; they should pass.**
- [ ] **Step 5: Commit** with
  `feat: learn when the house has gone to bed and push long night trips and night doors`.

### Task 4: Router hides noisy kinds and counts the new sign

**Files:**
- Modify: `custom_components/behaviour_monitor/core/alert_router.py`
  (`_combine`, `submit`)
- Modify: `tests/core/test_alert_router.py`, `tests/core/test_engine.py`,
  and any assertion in `tests/test_sensor.py` or `tests/test_coordinator.py`
  that expects these kinds to be published.

**Interfaces:**
- Produces: the module constant `HIDDEN_KINDS = frozenset({"routine_missed", "chain_stall"})`.
- Change to `_combine`:
  - A sign is `chain_stall` (counted by key, as now), `routine_missed` with
    `fired_today`, or `not_yet_today` with `went_out_today is False`.
  - Notes are counted by **source**, so one entity is one sign.
  - Escalation is unchanged: any stall, or two or more notes.
  - The `routine_agreement` branch is deleted.
- `submit` drops `HIDDEN_KINDS` from the combined list before opening or
  updating, so they never open. Open alerts of these kinds restored from an
  old store clear at the first submit: they get a cleared event, but
  `_on_clear` must not emit `log_clear` for `HIDDEN_KINDS`.

- [ ] **Step 1: Write failing tests.**
  - `test_routine_missed_and_chain_stall_are_never_published`: no event,
    and no log or log_clear action.
  - `test_routine_agreement_no_longer_raised`.
  - `test_not_yet_today_home_escalates_whereabouts_with_another_sign`.
  - `test_not_yet_today_after_going_out_is_not_a_sign`.
  - `test_same_entity_hourly_and_daily_miss_counts_once`.
  - `test_restored_hidden_alert_clears_quietly`.
- [ ] **Step 2: Run them; they should fail.** Then update the existing
  tests that asserted the old behaviour so they assert the new.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `make test`; all tests should pass.
- [ ] **Step 5: Commit** with
  `feat: routine notes and stalls become internal signs only`.

### Task 5: Engine wiring, persistence and upgrade rebuild

**Files:**
- Modify: `custom_components/behaviour_monitor/core/engine.py`
- Test: `tests/core/test_engine.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces:
  - `EngineConfig.unusual: UnusualConfig`. `from_options` reads
    `upstairs_rooms` into `upstairs`, `night_trip_min`, and
    `learning_days`/`window_days` into `min_days`/`window_days`.
  - `Engine.needs_unusual_history: bool`. It's true after `from_dict` reads
    a store with no `"unusual"` key; otherwise false.
  - `Engine.rebuild_unusual(rows: list[tuple[datetime, str, str | None, str]], now: datetime) -> None`.
    `rows` has the same shape the coordinator's bootstrap builds.
    - It replays the rows in time order through a scratch `Normaliser` and a
      scratch `Whereabouts` (same configs) into a fresh `Unusual`, calling
      `finalise_day` for each finished day (active = that day had activity).
    - Then it calls `self._where.adopt_out_spans(scratch._out_spans)`,
      swaps in the new `Unusual` and clears the flag.
    - It raises no alerts and touches no other model.
- Wiring:
  - `_learn` calls `self._unusual.record(ev, self._where)` just before
    `self._where.record(ev)`.
  - `_finalise_day` calls `finalise_day(day, ids, active=bool(self._house.rooms_visited(day)))`.
  - The poll's learned branch extends alerts with `self._unusual.evaluate(...)`.
    It passes `down=self._health.down_today(now)`, `names` from
    `drift_names()`, and categories from the specs.
  - Prune with the house.
  - `set_entities` removal calls `unusual.remove`.
  - A single-entity `reset` calls `unusual.remove(eid)`. A full reset gets a
    fresh model through `__init__`.
  - Holiday: nothing is recorded (`_learn` returns early, as it does today).
    When holiday ends, call `self._unusual.clear_night()`, which drops
    in-progress night state.
  - `to_dict` gains `"unusual"`. `from_dict` loads it tolerantly.
  - The snapshot's `"whereabouts"` block gains
    `"night_since": iso or None`.

- [ ] **Step 1: Write failing tests.**
  - `test_unusual_alerts_flow_through_poll_after_learning`
  - `test_no_unusual_alerts_while_learning_or_on_holiday`
  - `test_holiday_nights_not_learned_and_night_cleared_on_return`
    (Review Focus 5)
  - `test_old_store_without_unusual_keeps_learning_and_flags_rebuild`:
    strip `"unusual"` from a trained `to_dict()`. `from_dict` keeps
    `days_seen` and sets `needs_unusual_history`.
  - `test_rebuild_unusual_from_rows_learns_without_alerts`: after rebuild,
    the flag is false, `poll` returns no new actions for the replayed
    period, and `out_spans` is populated.
  - `test_reset_entity_forgets_unusual_learning`
- [ ] **Step 2: Run them; they should fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `make test`; all tests should pass.
- [ ] **Step 5: Commit** with
  `feat: wire really-unusual learning into the engine, rebuilt from history on upgrade`.

### Task 6: Shell: options, migration, upstairs rooms and the rebuild call

**Files:**
- Modify: `const.py` (`CONF_UPSTAIRS_ROOMS = "upstairs_rooms"`,
  `CONF_NIGHT_TRIP_MIN = "night_trip_min"`, `OPTION_DEFAULTS[...] = 30`,
  `CONFIG_VERSION = 14`)
- Modify: `config_flow.py`
  - Add `CONF_UPSTAIRS_ROOMS` to `WHEREABOUTS_KEYS`. In
    `_whereabouts_schema`, it's a fourth `_tick_list` over the same `rooms`
    with the same labels, suggested from the saved value or else
    `upstairs_suggestions`.
  - In `_options_schema`, `_number(CONF_NIGHT_TRIP_MIN, 10, 120, 5, "min")`.
- Modify: `rooms.py` with
  `upstairs_suggestions(hass, entity_ids: Iterable[str]) -> list[str]`.
  - It returns the sorted rooms whose area's floor `level` is greater than
    the lowest level among the site's floors.
  - It returns `[]` when no site area has a floor, or only one level is
    used.
  - Use `homeassistant.helpers.floor_registry`, guarded with `getattr` so
    older HA versions (or test stubs) without floors give `[]`.
- Modify: `__init__.py`, migrating 13 → 14 with
  `options.setdefault("upstairs_rooms", [])`.
- Modify: `coordinator.py`
  - Extract the history fetch from `_bootstrap_entities` into
    `async def _fetch_history(self, entity_ids) -> list[tuple[datetime, str, str | None, str]]`.
    Bootstrap uses it unchanged.
  - After a stored engine loads, if `self._engine.needs_unusual_history`,
    call `self._engine.rebuild_unusual(await self._fetch_history(all_ids), dt_util.now())`
    and save. Failure is logged and learning carries on from now, as the
    bootstrap does.
  - A room rename remaps `upstairs_rooms` exactly as it remaps `bedrooms`.
- Modify: `translations/en.json`, using string replacement and not a
  `json.dump` rewrite.
  - The whereabouts step data label is "Upstairs rooms".
  - Its description is "Rooms people go up to at bedtime. A trip from
    these to the rest of the house during the night is a night trip."
  - Use the same wording in config and options.
  - The options label is "Night-time downstairs alert (minutes)".
- Tests: `tests/test_config_flow.py`, `tests/test_init.py`,
  `tests/test_coordinator.py`, `tests/test_translations.py`, and
  `tests/test_const.py` (`CONFIG_VERSION == 14`).

- [ ] **Step 1: Write failing tests.**
  - `test_whereabouts_step_offers_upstairs_tick_list_suggested_from_floors`
    (floors at levels 0 and 1).
  - `test_upstairs_suggestions_empty_without_floors`.
  - `test_options_offer_night_trip_minutes_default_30`.
  - `test_migrate_13_to_14_adds_empty_upstairs`.
  - `test_upgrade_store_without_unusual_rebuilds_from_recorder_once`: the
    mock recorder rows feed `rebuild_unusual`. A second load doesn't call
    it.
  - `test_rename_remaps_upstairs_rooms`.
  - `test_translations_have_upstairs_and_night_trip_labels`.
- [ ] **Step 2: Run them; they should fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `make test`, ruff and black (from the venv).
- [ ] **Step 5: Commit** with
  `feat: upstairs rooms and night trip minutes in the options, rebuilt on upgrade`.

### Task 7: Docs, scorecard and acceptance replay

**Files:**
- Modify: `README.md`
  - Replace the routine-note text with the five kinds.
  - Add the Upstairs rooms list and the `night_trip_min` option rows.
  - Add an Upgrading note (quote the released tag, not a number chosen now): routine notes, stalls and agreement
    events are no longer sent; the new history rebuilds from the recorder
    and the night pushes start after 14 learned nights; tick the upstairs
    rooms.
- Modify: `CLAUDE.md`: config entry version 14, and `unusual` in the module
  lists.
- Modify: `scripts/scorecard.py` and `tests/test_scorecard.py`: count the
  five new kinds in place of `routine_missed`, `routine_agreement` and
  `chain_stall`.
- Modify: `docs/superpowers/specs/2026-11-10-really-unusual-design.md` by
  appending an "Acceptance results" section.
- Local only: in `exports/fixture/biddulph_road.sidecar.json` options, add
  `"upstairs_rooms": ["Bathroom", "Landing", "Box room"]`. Back it up first
  to `.sidecar.json.bak2`. Never commit it.

- [ ] **Step 1: Run the replay and scorecard** on the Biddulph fixture. Run
  `python scripts/replay.py exports/fixture/biddulph_road.jsonl --json` and
  the scorecard against the truth file.
- [ ] **Step 2: Check against the spec's Acceptance.**
  - Card total ≤ 1 per 3 days over 3 Oct–8 Nov, excluding the recorder gap.
  - `not_yet_today` about 5.
  - `trip_missed` 0.
  - `unusual_now` ≤ 2, with the hall and landing sensors silent in their
    first weeks.
  - 0 night pushes across 40 nights.
  - Whereabouts figures unchanged: falls 130/130, welfare alerts 3.

  If a figure misses, stop and report it with the alerts behind it. Don't
  tune constants to pass.
- [ ] **Step 3: Write the README, CLAUDE.md and scorecard changes,** and
  the acceptance section with the measured figures.
- [ ] **Step 4: Run** `make test`, ruff and black.
- [ ] **Step 5: Commit** with
  `docs: really unusual alerts, upstairs rooms and acceptance results`.
