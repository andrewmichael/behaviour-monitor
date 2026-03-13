---
phase: quick
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - custom_components/behaviour_monitor/__init__.py
  - custom_components/behaviour_monitor/analyzer.py
  - custom_components/behaviour_monitor/switch.py
  - custom_components/behaviour_monitor/config_flow.py
  - tests/conftest.py
  - tests/test_analyzer.py
  - tests/test_ml_analyzer.py
  - tests/test_sensor.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "make lint (ruff check) passes with zero errors"
    - "Sensitivity labels in config flow match actual sigma thresholds from const.py"
    - "All existing tests still pass"
  artifacts:
    - path: "custom_components/behaviour_monitor/config_flow.py"
      provides: "Corrected sensitivity labels"
      contains: "2.5"
  key_links: []
---

<objective>
Fix all 14 ruff lint warnings and update stale sensitivity labels in config_flow.py.

Purpose: Clean lint output and correct user-facing labels that became stale after Phase 2 changed SENSITIVITY_MEDIUM from 2.0 to 2.5 sigma.
Output: Zero ruff errors, accurate config flow labels.
</objective>

<execution_context>
@/Users/abourne/.claude/get-shit-done/workflows/execute-plan.md
@/Users/abourne/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@custom_components/behaviour_monitor/const.py
@custom_components/behaviour_monitor/config_flow.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Fix all ruff lint warnings</name>
  <files>
    custom_components/behaviour_monitor/__init__.py,
    custom_components/behaviour_monitor/analyzer.py,
    custom_components/behaviour_monitor/switch.py,
    tests/conftest.py,
    tests/test_analyzer.py,
    tests/test_ml_analyzer.py,
    tests/test_sensor.py
  </files>
  <action>
Run `ruff check --fix custom_components/ tests/` to auto-fix the 10 fixable warnings (unused imports F401, f-string without placeholders F541).

Then manually fix the remaining non-auto-fixable warnings:
1. tests/conftest.py line 22: Remove the `mock_ha_components = MagicMock()` assignment (F841 unused variable). Verify nothing downstream references it.
2. tests/test_analyzer.py: The DAY_NAMES and pytest imports may have been auto-fixed. If any remain, remove manually.

Do NOT use --unsafe-fixes; review each removal to ensure nothing breaks.
  </action>
  <verify>
    <automated>source venv/bin/activate && ruff check custom_components/ tests/</automated>
  </verify>
  <done>ruff check returns 0 errors, exit code 0</done>
</task>

<task type="auto">
  <name>Task 2: Update stale sensitivity labels in config_flow.py</name>
  <files>custom_components/behaviour_monitor/config_flow.py</files>
  <action>
Update the sensitivity dropdown labels in BOTH async_step_user (line ~115) and async_step_init (line ~311) to match the actual thresholds in const.py SENSITIVITY_THRESHOLDS:

Old labels -> New labels:
- "Low (3 sigma)" -> keep as-is (3.0 sigma is correct)
- "Medium (2 sigma)" -> "Medium (2.5 sigma)" (was changed from 2.0 to 2.5 in Phase 2)
- "High (1 sigma)" -> keep as-is (1.0 sigma is correct)

There are exactly two places these labels appear (config flow setup and options flow). Update both identically. Use the sigma symbol consistently — the existing code uses the unicode character, so keep that style: "Medium (2.5σ)".
  </action>
  <verify>
    <automated>source venv/bin/activate && grep -n "Medium" custom_components/behaviour_monitor/config_flow.py | grep -c "2.5"</automated>
  </verify>
  <done>Both sensitivity dropdown menus show "Medium (2.5σ)" matching the actual SENSITIVITY_MEDIUM threshold of 2.5 in const.py</done>
</task>

<task type="auto">
  <name>Task 3: Run full test suite to confirm no regressions</name>
  <files></files>
  <action>
Run `make test` to verify all existing tests pass after the import removals and label changes. If any test fails due to a removed import that was actually needed, restore it and find an alternative fix.
  </action>
  <verify>
    <automated>source venv/bin/activate && make test</automated>
  </verify>
  <done>All tests pass with zero failures</done>
</task>

</tasks>

<verification>
- `ruff check custom_components/ tests/` returns 0 errors
- `make test` passes all tests
- `grep "Medium" custom_components/behaviour_monitor/config_flow.py` shows "2.5σ" not "2σ"
</verification>

<success_criteria>
- Zero ruff lint errors across the entire codebase
- Sensitivity labels in config_flow.py accurately reflect const.py thresholds
- All existing tests pass without modification to test logic
</success_criteria>

<output>
After completion, create `.planning/quick/1-fix-lint-warnings-and-stale-config-flow-/1-SUMMARY.md`
</output>
