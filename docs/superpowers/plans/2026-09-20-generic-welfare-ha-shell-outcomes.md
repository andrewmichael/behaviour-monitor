# Part 2 outcomes: rulings and deferred items

Source: the SDD ledger for docs/superpowers/plans/2026-09-20-generic-welfare-ha-shell.md, closed at commit 2895518 (169 tests). Real-site fixture export still pending credentials: run scripts/export_fixture.py on site.

## Rulings (in order)

- Ruling P1 below.
- Ruling P1: Task 1 also deletes the v4 modules routine_model.py, acute_detector.py, drift_detector.py (top level), correlation_detector.py, alert_result.py and their tests plus tests/test_coordinator_correlation.py and scripts/v2_storage.json, so the tree never holds modules importing removed constants. coordinator/sensor/switch/select/init/config_flow and their tests remain broken between T1 and T5; implementers run their own task's tests until T5, then the full suite. Cost if wrong: a few commits with a red full suite on the branch.
- Ruling P2: accept the __init__ shim and the const stubs as a bridge; Task 5 (rewrites __init__) must delete the const stubs and the shim, and its review must verify no v4 constant names remain in const.py. Cost if wrong: dead names linger in const.py.
- Ruling P3: category keys absent from the options submission mean cleared ([]); site name and notify service still fall back. Fix round 1/5 dispatched; FIX_BASE 6052b8c. Remainder requested.
- Ruling P4: Task 5 passes `config_entry=entry` to DataUpdateCoordinator and the conftest mock accepts **kwargs. Cost if wrong: none.
- Ruling P5: subclass Store with a migrate hook returning {} (discard v4 state, spec 12) and guard async_load; recorder replay by string entity id with no_attributes; post-bootstrap poll actions are queued in _pending and delivered on the first flush. Cost if wrong: none identified.
- Ruling P6: registry updates compare area ids: same area id with a new name → rename_room; area id changed or absent → set_entities only. Cost if wrong: a rename of an area that also moves the device is treated as a move (learning for the old room name is orphaned, not merged).
- Ruling P7: Task 8's gate review is folded into the final whole-branch review (docs and version only). Cost if wrong: a docs error reaches the final review instead of a task gate.
- Ruling P8: withdraw spec 12's `unconfigured` welfare sensor — no entities until categories are assigned; repair issue is the signal. Cost if wrong: a dashboard card bound to the welfare sensor shows unavailable until configured.
- Ruling P9: hacs.json minimum HA 2025.1.0. Cost if wrong: users on 2024.x cannot install v5 via HACS.

## Deferred items (final-review triage)

- Task 2 review remainder: only the one Critical. Minor (deferred): _split_input splits data/options by "not in OPTION_DEFAULTS" rather than an explicit data-key whitelist.
- Task 4: complete (commits bfe3c6c..a2bef5f, review clean; minors deferred: device_health empty-state "ok"; ATTR_SNOOZE_* local to select.py; brief's sensor test coverage thinner than v4's).
- Task 3 review remainder: Important 4 async_shutdown skips super()/saver shutdown; 5 no failure isolation in setup (recorder get_instance raises KeyError when absent); 6 room rename vs move by name comparison; 7 bootstrap replays unavailable rows into health; 8 bootstrap/store/_render untested. Minor (deferred): schema-mismatch restore skips bootstrap silently; flush/poll interleave; single welfare notification id; test_panic acknowledges immediately (push_clear seconds later); unknown snooze key clears; reset clears holiday/snooze; monitored-id set per event; unknown action silently dropped; old.state not coerced; one tautological assert.
- Task 5: complete (commit 4b0357c, review clean; minors deferred: services re-registered on every entry setup (harmless fan-out); assign_categories issue re-raised on every setup of an unconfigured entry). Suite at 167 with concurrent commits.
- Task 3: fix round 1/5 (8 addressed, 0 open; commits bfe3c6c..74a3b2a). Minor (deferred): RuntimeWarning "coroutine never awaited" from mock_hass.async_create_task = MagicMock() in tests; no backstop drain of _pending in _async_update_data; serial recorder fetches at bootstrap.
- Task 3: complete (review clean after 1 fix round, 10+ minors deferred)
- Final review P2 remainder: Important — device-registry updates not subscribed; reset clears holiday/snooze; hacs.json HA floor too low (2024.1.0); spec 12 `unconfigured` sensor unimplemented; stale-schema store restores blank then skips bootstrap. Minor — no `recommendation` attr on welfare sensor; log_clear dropped; only `reasons` display-rendered; category change does not re-bootstrap; friendly-name room changes on rename; Makefile misses export_fixture.py; tests/fixtures/v2_storage.json leftover; real fixture unexported; en.json entity block inert without translation_key; Debouncer save not covered by HA's final-write (use Store.async_delay_save); _flush_actions unguarded ServiceNotFound; listens to all state_changed; options save reloads twice. Rulings P1-P7 hold. Verdict: ready after listed fixes.
