# Project Research Summary

**Project:** Behaviour Monitor — False Positive Reduction Milestone
**Domain:** Home Assistant anomaly detection / notification quality
**Researched:** 2026-03-13
**Confidence:** HIGH

## Executive Summary

The Behaviour Monitor integration has a solid dual-analyzer architecture (z-score statistical detection + River HalfSpaceTrees ML) that is functionally correct. The false positive problem is not a design flaw — it is a set of three distinct, fixable gaps: no notification cooldown in the coordinator, sparse time-bucket z-scores that produce infinite values on regular entities, and sensitivity defaults calibrated for laboratory conditions rather than real home use. Research is grounded entirely in the codebase with HIGH confidence; no external tools were available but every finding is traceable to specific lines.

The recommended approach is a two-phase fix. Phase 1 targets the coordinator's notification dispatch — adding per-type cooldown, a minimum severity gate, and welfare status hysteresis. These changes are purely additive (no existing behavior removed) and will produce the most immediate user-visible improvement. Phase 2 tightens the analyzers themselves — minimum bucket observation guards to eliminate infinite z-scores, raised default sensitivity, tighter ML contamination, and cross-sensor correlation thresholds. Phase 2 reduces the volume of anomalies reaching the coordinator, complementing Phase 1's suppression logic.

The primary risk is scatter-shot threshold bumping: the commit history already shows four rounds of threshold loosening (v2.8.6–v2.8.8) without root-cause isolation. That pattern must not continue. Each change in this milestone must be attributed to a specific detection path, and the `anomaly_detected` sensor state must be validated after every threshold change to prevent automation regressions.

---

## Key Findings

### Recommended Stack

No new dependencies are required. All false positive reduction work operates within the existing Python stack and River 0.19.0+ dependency. The four files that need changes are `coordinator.py`, `analyzer.py`, `ml_analyzer.py`, and `const.py`. All recommended threshold constants belong in `const.py` for testability — values buried inline in logic methods are the root cause of the current untraceable threshold drift.

**Core technologies:**
- `coordinator.py`: notification dispatch and deduplication — owns all send-or-suppress decisions
- `analyzer.py`: z-score computation and bucket statistics — owns observation count guards and sensitivity thresholds
- `ml_analyzer.py`: HalfSpaceTrees scoring and cross-sensor patterns — owns contamination threshold and correlation gates
- `const.py`: single source of truth for all numeric constants — every tunable value must live here

### Expected Features

**Must have (table stakes):**
- **Notification cooldown (per type)** — `_last_notification_time` exists but is never read before re-firing; an anomaly that persists 30 minutes currently sends 30 mobile pushes
- **Minimum bucket observation count** — buckets with count < 4 produce wildly unstable z-scores; a bucket with count=1 produces `float("inf")` on any deviation, making perfectly regular entities the most alarming
- **Severity minimum for notifications** — the severity classification system (`minor`/`moderate`/`significant`/`critical`) already exists but is unused in the notification path; `minor` anomalies (1.5–2.5σ) should update sensor state only, not push notifications
- **Welfare status hysteresis** — status transitions at the boundary (ok ↔ check_recommended) oscillate, firing a notification on each crossing

**Should have (differentiators):**
- **Consecutive anomaly confirmation** — require 2+ consecutive detection cycles before raising an anomaly to notification-worthy (eliminates single-interval noise spikes)
- **Cross-path deduplication** — when both statistical and ML paths flag the same entity in the same cycle, send one notification, not two
- **Minimum mean activity guard** — buckets with mean < 0.3 events/interval generate high z-scores from single events; add a floor alongside the observation count guard
- **Inactivity asymmetric threshold** — unusual inactivity is naturally more variable than activity; apply a 1.5× z-score multiplier for inactivity anomalies

**Defer (v2+):**
- Per-entity sensitivity tuning UI — out of scope per PROJECT.md; global threshold improvements achieve most benefit
- User feedback / thumbs-up-down loop — requires persistent feedback storage and weeks of work
- Seasonal/calendar awareness (school terms, regional holidays) — high complexity, adds new dependencies
- Adaptive baselines (EWMA on bucket means) — significant architecture change not needed to solve the immediate flood
- Daily digest / summary mode — explicitly deferred in PROJECT.md

### Architecture Approach

The existing architecture requires no structural changes. False positive reduction is a series of layered gates added at precisely-defined points in the existing pipeline. The guiding principle — **each component owns what it produces; the coordinator owns what gets sent** — is already correct and must be preserved. Threshold logic stays in the analyzers (not the coordinator), and coordinator-level concerns (cooldown, dedup, severity filter) stay in `_async_update_data()`.

**Major components and where changes land:**
1. `const.py` — add `MIN_BUCKET_OBSERVATIONS`, `MIN_MEAN_ACTIVITY_THRESHOLD`, `NOTIFICATION_COOLDOWN_SECONDS`, `MIN_NOTIFICATION_SEVERITY`, `WELFARE_STATUS_DEBOUNCE_CYCLES`, updated `SENSITIVITY_THRESHOLDS`, updated `ML_CONTAMINATION`
2. `analyzer.py` — add observation count and mean activity guards in `check_for_anomalies()` before z-score computation
3. `ml_analyzer.py` — raise `co_occurrence_count` minimum (10 → 20), raise `correlation_strength` minimum (0.5 → 0.6), widen expected window multiplier (2× → 3×)
4. `coordinator.py` — add per-type cooldown guard before each `_send_*` call; add severity filter for stat anomalies; add welfare debounce state; add cross-path dedup check

**Data flow with all gates active:**
```
check_for_anomalies()
  [GATE 1] bucket.count < MIN_BUCKET_OBSERVATIONS → skip
  [GATE 2] expected_mean < MIN_MEAN_ACTIVITY_THRESHOLD → skip
  [GATE 3] z_score <= sensitivity_threshold → skip
    → AnomalyResult list with severity labels
[GATE 4] severity < MIN_NOTIFICATION_SEVERITY → suppress notification (sensor updates only)
[GATE 5] (entity_id, anomaly_type, time_slot) seen recently → skip
[GATE 6] last_notification_time + cooldown > now → skip
  → _send_notification()
```

### Critical Pitfalls

1. **Scatter-shot threshold bumping** — v2.8.6 through v2.8.8 show four rounds of simultaneous threshold changes; the inline "was X" comments prove this pattern. Before changing any threshold, instrument which detection path produced the false positives. Only tune the responsible layer.

2. **No notification cooldown** — `_last_notification_time` is stored but never read before re-firing. Every 60-second update cycle that finds anomalies sends a notification. A 30-minute cooldown per notification type is the single highest-impact change available.

3. **Infinite z-scores from zero-variance regular entities** — `analyzer.py:448` sets `z_score = float("inf")` when `expected_std == 0` and `actual != expected_mean`. This fires for entities that activate with perfect consistency — the exact opposite of anomalous behavior. No threshold increase can suppress infinity.

4. **Welfare oscillation** — `current_welfare != last_welfare_status` with no hysteresis causes rapid ok → concern → ok transitions near threshold boundaries, each triggering a notification. Require N=3 consecutive cycles at the new status before confirming a transition.

5. **Dual-path duplicate notifications** — statistical and ML paths each send independent notifications; an event triggering both paths sends two mobile pushes within the same 60-second cycle. Cross-path dedup or notification consolidation is required.

---

## Implications for Roadmap

Based on research, the work divides cleanly into two phases plus a prerequisite instrumentation step.

### Phase 0: Diagnosis Instrumentation (Optional but Strongly Recommended)
**Rationale:** The commit history shows the project has already burned four rounds of threshold tuning without root-cause isolation. Without per-source counters, Phase 1 and Phase 2 changes cannot be validated. Even simple log aggregation (which detection path fired, how many suppressions) prevents regression to the scatter-shot pattern.
**Delivers:** Observable per-path alert counts; ability to verify Phase 1 and Phase 2 impact; protection against inadvertent over-suppression
**Avoids:** Pitfall 1 (scatter-shot tuning)
**Note:** This can be as lightweight as adding log entries at each gate with a consistent prefix for easy filtering. Full diagnostic sensors are a nice-to-have.

### Phase 1: Coordinator Notification Suppression
**Rationale:** This phase has the highest immediate user-visible impact and zero risk of detection regression — it suppresses notifications without changing what the analyzers detect. It must come before Phase 2 so that Phase 2's threshold changes can be evaluated against a stable notification baseline.
**Delivers:** Elimination of notification floods; welfare oscillation fix; cross-path duplicate suppression
**Addresses:**
- Notification cooldown per type (`NOTIFICATION_COOLDOWN_SECONDS = 1800`)
- Severity minimum gate (`MIN_NOTIFICATION_SEVERITY = "moderate"`)
- Welfare status hysteresis (`WELFARE_STATUS_DEBOUNCE_CYCLES = 3`)
- Cross-path deduplication (statistical + ML same entity same cycle)
**Avoids:** Pitfall 2 (no cooldown), Pitfall 3 (welfare oscillation), Pitfall 5 (dual-path duplicates)
**Test requirement:** New coordinator tests must inject pre-built anomaly lists and verify suppression behavior at each gate. Verify `anomaly_detected` sensor behavior does not change unexpectedly (Pitfall 9).

### Phase 2: Analyzer Threshold and Guard Tightening
**Rationale:** Phase 1 suppresses notifications for anomalies that slip through; Phase 2 reduces the volume of anomalies produced in the first place. Doing this second ensures the coordinator-level gates are working correctly before reducing raw detection sensitivity.
**Delivers:** Elimination of infinite z-score false positives; tighter ML cross-sensor correlation; reduced steady-state anomaly volume for new and existing installs
**Addresses:**
- Minimum bucket observation guard (`MIN_BUCKET_OBSERVATIONS = 4` in `analyzer.py`)
- Minimum mean activity guard (`MIN_MEAN_ACTIVITY_THRESHOLD = 0.3` in `analyzer.py`)
- Raise default sensitivity (`DEFAULT_SENSITIVITY` → `SENSITIVITY_LOW` / 3.0σ for new installs)
- ML contamination tightening (MEDIUM: 0.05 → 0.02; LOW: 0.01 → 0.005)
- Cross-sensor gates (co_occurrence: 10 → 20; correlation_strength: 0.5 → 0.6; window: 2× → 3×)
**Avoids:** Pitfall 4 (infinite z-scores), Pitfall 10 (ML contamination mismatch), Pitfall 11 (spurious cross-sensor correlation)
**Test requirement:** For every threshold constant changed, verify at least one test exercises the exact boundary using the constant (not a hardcoded literal). See Pitfall 12.

### Phase 3: Validation and Refinement (if needed)
**Rationale:** After Phases 1 and 2, empirical validation against real data will reveal whether the specific threshold values chosen were correct. Some values (ML contamination targets, welfare debounce cycle count) are directionally correct but need live calibration.
**Delivers:** Tuned threshold values backed by observed alert rates; documentation updates for sensitivity level labels (rename "Low/Medium/High" → "Cautious/Standard/Sensitive" to reduce confusion)
**Addresses:** Inactivity asymmetric threshold (1.5× z-score multiplier for unusual_inactivity if needed); consecutive anomaly confirmation (MIN_CONSECUTIVE_ANOMALIES = 2) if noise persists after Phase 2
**Avoids:** Pitfall 8 (threshold changes without pattern data quality audit)

### Phase Ordering Rationale

- **Phase 1 before Phase 2** — coordinator suppression must be validated before reducing raw anomaly volume, so each layer's contribution can be measured independently
- **const.py changes first within each phase** — extracting threshold values to named constants before touching logic preserves testability and avoids hardcoded literals accumulating in test files
- **Welfare changes isolated from z-score changes** — welfare status uses different logic paths than z-score detection; tuning them together makes it impossible to attribute alert rate changes to the correct subsystem
- **No structural architecture changes** — the existing component boundaries are correct; all changes are additive gates within existing methods

### Research Flags

Phases with standard patterns (skip research-phase):
- **Phase 1 (Coordinator suppression):** Well-understood notification deduplication and cooldown patterns; implementation details are unambiguous from the codebase; no domain-specific unknowns
- **Phase 2 (Threshold tightening):** All changes are constant adjustments or simple conditional guards in existing methods; no new algorithms or integration patterns required

Phases that may benefit from empirical validation before finalizing:
- **Phase 3 (Refinement):** ML contamination optimal values and welfare debounce cycle counts are empirically determined; if Phase 0 instrumentation is implemented, real data will inform Phase 3 values directly

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All findings from direct codebase analysis; no new dependencies recommended; traceable to specific lines |
| Features | HIGH | Must-have features confirmed by code gaps (absence of cooldown guard, presence of float("inf") branch); anti-features grounded in PROJECT.md scope constraints |
| Architecture | HIGH | Component boundaries directly readable from source; no structural changes required; all change locations confirmed |
| Pitfalls | HIGH | Critical pitfalls (cooldown gap, infinite z-score, welfare oscillation) are directly observable in code; moderate pitfalls grounded in commit history; minor pitfalls from statistical reasoning |

**Overall confidence:** HIGH

### Gaps to Address

- **ML contamination exact values:** The recommended values (LOW: 0.005, MEDIUM: 0.02, HIGH: 0.05) are directionally correct but optimal values for home sensors are empirically determined. Implement Phase 0 instrumentation to measure ML false positive rate before and after Phase 2. If Phase 0 is skipped, treat contamination values as provisional and plan a Phase 3 calibration.
- **Welfare debounce cycle count:** N=3 cycles (3 minutes) is a reasonable starting point but may need tuning based on how quickly welfare status legitimately changes in practice. Document this as a configurable constant, not a magic number.
- **Inactivity asymmetric threshold:** Listed as a "should have" differentiator but not included in the core two-phase plan because it requires empirical validation of the 1.5× multiplier value. Include in Phase 3 if unusual_inactivity false positives remain after Phases 1 and 2.
- **Existing user migration for default sensitivity change:** Raising `DEFAULT_SENSITIVITY` only affects new installs. Existing users who configured at MEDIUM (2.0σ) will not benefit. Consider adding a note in the release that users should reconfigure, or add a migration step to bump existing MEDIUM configs to the new recommended default.

---

## Sources

### Primary (HIGH confidence)
- `custom_components/behaviour_monitor/analyzer.py` — direct code analysis; threshold values, z-score logic, welfare computation, Welford accumulator
- `custom_components/behaviour_monitor/coordinator.py` — notification send logic, absence of cooldown guards, welfare status transition handling
- `custom_components/behaviour_monitor/ml_analyzer.py` — HalfSpaceTrees configuration, cross-sensor correlation logic
- `custom_components/behaviour_monitor/const.py` — complete threshold inventory
- Git commit history v2.8.6–v2.8.8 — documents pattern of prior threshold changes and their motivations

### Secondary (MEDIUM confidence)
- Training knowledge: z-score statistics, notification deduplication patterns, River HalfSpaceTrees documentation (knowledge cutoff August 2025) — used for technique rationale and threshold recommendations

### Tertiary (not available)
- External web search and WebFetch were unavailable for this research session; River official docs and published anomaly detection benchmarks could not be consulted. Recommendations for exact threshold values (Techniques 3, 5) would benefit from external validation.

---
*Research completed: 2026-03-13*
*Ready for roadmap: yes*
