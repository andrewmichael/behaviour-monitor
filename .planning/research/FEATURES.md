# Feature Research

**Domain:** Routine-based anomaly detection — home automation welfare monitoring
**Researched:** 2026-03-13
**Confidence:** MEDIUM (web research + code review; no proprietary benchmark data available)

---

## Context: What Already Exists (Do Not Re-Build)

The following features are already implemented and must be preserved by the v1.1 rebuild.
They are NOT in scope for this research — they are listed only to clarify dependencies.

| Existing Feature | Sensor / Component | Must Remain |
|------------------|--------------------|-------------|
| 14 sensor entity types (entity IDs stable) | `sensor.py` | YES — users have automations |
| Config flow UI (entity selection, sensitivity, learning period) | `config_flow.py` | YES — extend, not replace |
| Persistent storage (JSON, `.storage/`) | `__init__.py` + coordinator | YES — format may change |
| Notification services + persistent_notification | `coordinator.py` | YES |
| Holiday mode | `switch.py` + coordinator | YES |
| Snooze (1h / 2h / 4h / 1d) | `select.py` + coordinator | YES |
| Welfare status (ok / check_recommended / concern / alert) | coordinator + sensor | YES |
| Welfare status debounce (3-cycle hysteresis) | coordinator | YES — replicate in new coordinator |
| Per-entity notification cooldown | coordinator | YES |
| Snooze and holiday suppression | coordinator | YES |

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features that any routine-based home monitoring system must have to be considered trustworthy and complete. Missing these makes the system feel broken or unusable.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Routine learning from history** | System must know what "normal" looks like before it can flag deviations. Users expect a defined learning window, not indefinite calibration. | MEDIUM | 4-week default (per PROJECT.md). Must handle binary sensors (motion, doors) and numeric sensors (power, climate) differently. Per-entity rolling history, not global buckets. |
| **Acute inactivity alert** | Core use case: someone may have fallen or be unwell. The alert fires when a monitored person has been unusually inactive. Without this, the system has no safety value. | MEDIUM | Inactivity is measured against the person's own learned typical-interval, not a fixed threshold. Configurable inactivity multiplier (e.g. 2x typical quiet period triggers alert). |
| **Configurable inactivity threshold** | Different households and care contexts need different sensitivity. A single hardcoded threshold produces either alert fatigue or missed events. | LOW | Expose as config option: number of standard deviations or a multiplier of typical inter-event interval. Default must be conservative (LOW false positive rate). |
| **Learning period gate** | No alerts until baseline is established. Users expect to be told the system is still learning. Already exists — must be preserved with new model. | LOW | Existing 14-sensor `statistical_training_remaining` must remain meaningful with the new routine model's learning window. |
| **Drift alert (gradual change)** | Users caring for elderly relatives need to know if behavior has been quietly deteriorating over days or weeks — not just acute crises. | HIGH | Distinct from acute alert. Different notification type, lower urgency, different cadence. Must not fire on a single unusual day — requires sustained evidence (e.g., N consecutive days below baseline). |
| **Separate notification types for acute vs. drift** | Users need to know whether to act immediately (acute) or schedule a check-in (drift). If both use the same notification, users cannot calibrate their response. | LOW | Acute: high urgency, immediate. Drift: lower urgency, "noticed over last N days". Both use existing notify services. |
| **Support for binary entities (motion, doors)** | These are the most common welfare sensor types. The routine model must handle event-count-per-window and inter-event-interval, not just state values. | MEDIUM | Binary entities: track events per time window, inter-event intervals. Numeric entities: track mean/variance of readings. |
| **Support for numeric entities (climate, power)** | Power consumption patterns (kettle, TV) and climate (heating patterns) are strong welfare indicators. | MEDIUM | Numeric: rolling mean/std over same time window. Change point detection on rolling stats is the drift mechanism. |
| **Routine model persistence** | If HA restarts, the learned routine must survive. Users will not wait another 4 weeks for re-learning after a restart. | MEDIUM | Serialize routine model to `.storage/`. Existing storage layer can be reused with new keys. |
| **Baseline confidence indicator** | Users need to know whether the model has enough history to be trustworthy. The existing `baseline_confidence` sensor must remain meaningful. | LOW | Map learning window completion % and data density to confidence score. Existing sensor entity ID preserved. |
| **Acute alert requires sustained evidence before firing** | The fundamental reason for replacing z-score: a single unusual reading must NOT fire an alert. Literature and the project's own v1.0 experience confirm this. | MEDIUM | Require N consecutive coordinator cycles (e.g., 3–5 × 60s = 3–5 minutes) of sustained anomaly before acute alert fires. Or: require the inactivity period to exceed threshold continuously, not just at one polling moment. |

### Differentiators (Competitive Advantage)

Features that distinguish this system from a basic motion-sensor inactivity timer or a Home Assistant automation. Should align with the core value: "alerts are trustworthy."

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Learned typical inter-event interval (per entity, per day-of-week)** | Generic inactivity timers use fixed thresholds (e.g., "alert after 8 hours of no motion"). A learned interval adapts to the person's own routine — meaning Monday mornings aren't confused with Sunday afternoons. | MEDIUM | Per-entity, per-day-of-week rolling inter-event interval stats. Requires ~4 weeks of history for reliable DOW estimates. HIGH confidence this is the correct approach — supported by literature on personalized smart home monitoring. |
| **Drift detection using change point / CUSUM on rolling baseline** | Gradual decline is clinically significant but hard to notice. A sustained shift in the routine metric over 7–14 days is a meaningful signal. CUSUM is a standard industrial method for this — lightweight, no external dependencies. | HIGH | CUSUM (Cumulative Sum) accumulates deviations until evidence crosses a threshold. Can be implemented in pure Python (~20 lines). Avoids `ruptures` library dependency (which is out of scope per PROJECT.md constraint). |
| **Per-entity drift tracking (not just global)** | A person might stop using the kettle (dietary change, illness) while motion patterns remain normal. Entity-level drift enables targeted alerts ("no kettle activity in 5 days, was daily before"). | MEDIUM | Each entity maintains its own drift accumulator. Drift alert includes which entity/entities diverged and by how much. |
| **Context in notifications** | "No motion detected for 6 hours (typical: 2 hours)" is actionable. "Anomaly detected" is not. Existing sensor attributes already carry `time_since_activity` and `typical_interval` — these feed notification messages. | LOW | Reuse existing coordinator notification infrastructure. Template the message to include entity name, actual elapsed time, and learned typical interval. |
| **Drift alert suppression during known absence** | Holiday mode (existing) should suppress drift alerts, not just acute ones. A 2-week holiday will look like a drift change. | LOW | Drift accumulator resets on holiday mode enable. This prevents a false drift alarm on return from holiday. |
| **Gradual confidence ramp-up** | During the first N days of learning, the detection sensitivity is progressively relaxed — no alerts at all in week 1, conservative in week 2, full sensitivity from week 3+. Prevents alert flood during initial setup. | LOW | Multiply detection threshold by a confidence ramp factor that decreases as learning progresses. Simple linear or sqrt ramp over learning window. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem appealing but create problems in this domain. Explicitly excluding them prevents scope creep.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Fixed inactivity threshold (e.g., "alert after 8 hours")** | Simple to explain and configure | One size fits no one. A night-owl sleeps until noon; an early riser is up at 6am. A fixed threshold either constantly fires false alarms or misses genuine events. | Learned typical inter-event interval per entity per day-of-week — adapts to the individual. |
| **Population-level normative baseline** | "What is normal for a 70-year-old?" research exists | This integration monitors one specific household. Population norms have no relevance to one individual's idiosyncratic routine. Complex to implement, wrong for the use case. | Per-entity, per-household learned baseline. |
| **Deep learning / neural routine model** | High accuracy in research papers | Requires large datasets (weeks of labeled data minimum), significant compute on HA hardware (Raspberry Pi, NUC), and external ML dependencies — all ruled out by PROJECT.md constraint (no new dependencies, pure Python). | Statistical routine model: rolling mean/std + CUSUM. Good enough for this use case, proven in literature, zero dependencies. |
| **Real-time activity recognition (what are they doing?)** | Interesting feature; useful in research | Requires labeling training data with activity types (eating, sleeping, walking). Impossible without a manual labeling step. Adds complexity with no practical welfare benefit over entity-level anomaly detection. | Monitor what is NOT happening (inactivity) rather than what IS happening. Privacy-preserving, simpler, proven approach. |
| **Daily digest / summary notification** | Caregivers want a morning briefing | Out of scope per PROJECT.md. Adds scheduling logic, new UI, and notification format complexity. Core value is trustworthy alerts, not reporting. | Defer to future milestone. Existing `routine_progress` sensor exposes data for users to build their own dashboards. |
| **Per-entity sensitivity UI in config flow** | Power users want fine control | N entities × 3 threshold parameters = complex UI. Users won't know correct values without empirical data. Risk of over-tuning and missing real events. | Global sensitivity setting (Low/Med/High) already exists. Advanced users can apply HA automations to filter sensor outputs. |
| **Correlation-based cross-entity anomalies** | "Motion without lights" type detections — clever | Cross-sensor correlation requires many co-occurrence samples to be reliable. Was a source of false positives in v1.0 (threshold had to be raised to 30 co-occurrences). The v1.1 routine model is explicitly replacing this approach. | Each entity has its own routine model. Correlations are implicit (if person does routine A, entity X and Y will both show normal; if not, both will show anomalous). |

---

## Feature Dependencies

```
Routine model (per-entity rolling baseline)
    └──required by──> Acute detection engine
    └──required by──> Drift detection engine (CUSUM accumulator needs baseline)

Acute detection engine
    └──requires──> Sustained evidence window (N cycles before firing)
    └──requires──> Configurable inactivity threshold (multiplier of learned interval)

Drift detection engine
    └──requires──> Routine model (needs rolling baseline to compute deviation)
    └──requires──> Minimum learning window (CUSUM needs stable baseline before accumulating)
    └──enhanced by──> Holiday mode reset (existing) — drift accumulator resets on holiday enable

Rebuilt coordinator
    └──requires──> Routine model, acute engine, drift engine
    └──must preserve──> Holiday mode, snooze, notification cooldown, welfare debounce

Config flow extensions
    └──requires──> Rebuilt coordinator (to surface new config keys)
    └──must preserve──> All existing config keys (migration required)

Persistent storage (new schema)
    └──requires──> Routine model serialization format defined
    └──must migrate──> Existing config entries gracefully

Sensor layer (14 sensors, stable entity IDs)
    └──requires──> Rebuilt coordinator to provide new data dict keys
    └──must preserve──> All 14 entity IDs and their state semantics
```

### Dependency Notes

- **Routine model is the foundation:** Both acute and drift engines consume per-entity baseline stats. Must be designed and tested before either engine is implemented.
- **Acute engine requires sustained evidence, not single-cycle detection:** The key architectural constraint. Detection accumulates across polling cycles; a single anomalous reading does not fire.
- **Coordinator rebuilds around the new engines:** The existing coordinator.py is being replaced. It must re-implement all existing suppression logic (holiday, snooze, cooldown, debounce) around the new engines.
- **Sensor entity IDs are immutable:** Any data dict keys the sensors read from coordinator output must be preserved or aliased. Changing what `welfare_status` or `routine_progress` return will break existing user dashboards.
- **Config migration is blocking:** Users cannot be asked to re-configure from scratch. The new options (history window, inactivity multiplier, drift sensitivity) must have safe defaults and must not break existing entries.

---

## MVP Definition

### Launch With (v1.1)

Minimum set needed to replace z-score/ML analyzers with the routine model and deliver trustworthy acute + drift detection.

- [ ] **Routine model** — per-entity rolling baseline (binary: event intervals; numeric: mean/std). Configurable history window (default 4 weeks). Persistent. — *Core foundation; nothing else works without it.*
- [ ] **Acute detection engine** — sustained inactivity exceeding learned typical interval by configurable multiplier. Requires N consecutive cycles (not single-point). — *Primary safety use case.*
- [ ] **Drift detection engine** — CUSUM accumulation on per-entity daily activity metrics. Alert requires sustained deviation (N consecutive days), not a single unusual day. — *Secondary welfare use case.*
- [ ] **Rebuilt coordinator** — manages both engines, re-implements holiday mode, snooze, cooldown, welfare debounce, notification dispatch. — *Integration glue; all existing suppression logic must be preserved.*
- [ ] **Binary + numeric entity support** — event-count/interval model for binary; mean/std model for numeric. — *Required for the sensor types users already have configured.*
- [ ] **Config flow extensions** — history window (weeks), inactivity threshold multiplier (float), drift sensitivity (Low/Med/High). Existing entries migrate gracefully. — *Required for configuration.*
- [ ] **Sensor data dict compatibility** — rebuilt coordinator output must supply all keys the existing 14 sensors consume. Sensor layer is not changed. — *Required to preserve entity IDs and user automations.*

### Add After Validation (v1.x)

Features to add once core routine model is proven in production.

- [ ] **Day-of-week learned intervals** — week 1 of learning uses a single mean; after 4+ weeks, per-DOW intervals become available. Add as an enhancement once the simpler per-entity global interval is validated. — *Trigger: user reports that weekend vs weekday variation causes false positives.*
- [ ] **Drift alert context detail** — "no kettle activity for 5 days (was daily)" notification. The infrastructure exists; this is message templating. — *Trigger: first user feedback requests that drift alerts are too vague.*
- [ ] **Confidence ramp-up during learning** — suppress or weaken alerts during first half of learning window. — *Trigger: users report alert floods on fresh setup.*

### Future Consideration (v2+)

Features to defer until the routine model is stable.

- [ ] **Daily digest notification** — explicitly out of scope per PROJECT.md. — *Defer: requires scheduling and new notification format.*
- [ ] **Per-entity sensitivity tuning** — useful for power users but adds config complexity. — *Defer: validate that global sensitivity is sufficient first.*
- [ ] **Seasonal calendar awareness** — school terms, regional holidays, seasonal patterns. — *Defer: high complexity, uncertain value for the primary welfare monitoring use case.*

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Routine model (per-entity rolling baseline) | HIGH | MEDIUM | P1 |
| Acute detection engine (inactivity) | HIGH | MEDIUM | P1 |
| Rebuilt coordinator (holiday, snooze, cooldown) | HIGH | MEDIUM | P1 |
| Binary entity support (motion, doors) | HIGH | MEDIUM | P1 |
| Sensor layer compatibility (14 sensors unchanged) | HIGH | LOW | P1 |
| Config flow extensions + migration | HIGH | LOW | P1 |
| Drift detection engine (CUSUM) | HIGH | HIGH | P1 |
| Numeric entity support (climate, power) | MEDIUM | MEDIUM | P1 |
| Persistent routine model storage | HIGH | LOW | P1 |
| Day-of-week learned intervals | MEDIUM | MEDIUM | P2 |
| Drift alert context (entity-specific messages) | MEDIUM | LOW | P2 |
| Confidence ramp-up during learning | MEDIUM | LOW | P2 |
| Per-entity sensitivity tuning | LOW | HIGH | P3 |
| Daily digest notification | LOW | HIGH | P3 |
| Seasonal calendar awareness | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for launch (v1.1 milestone)
- P2: Should have, add when P1 is validated
- P3: Nice to have, future milestone

---

## Domain Patterns: How Routine-Based Detection Works in Practice

Research across the IoT welfare monitoring literature (2024–2025) converges on the following patterns. These inform implementation decisions.

### Acute Detection

**Standard approach:** Inactivity-based alerting is the dominant method in home welfare monitoring. Systems monitor motion and activity sensors; when the elapsed time since last activity exceeds a learned individual norm, an alert fires.

**Evidence requirement:** Literature uniformly emphasizes that a single anomalous reading must not trigger an alert. Sustained evidence over minutes (for acute inactivity) or days (for drift) is required. This is the key distinction from z-score detection.

**Inactivity threshold design:** Per-individual learned intervals outperform fixed thresholds. A person's typical quiet period (e.g., 4 hours at night, 2 hours in afternoon) must be learned, and the alert fires when actual inactivity exceeds that learned period by a configurable multiplier. Default multiplier in the literature is typically 2–3x the learned interval.

**False positive controls:**
- Require continuous inactivity (not just "was inactive at polling time")
- Apply minimum threshold floors (e.g., never alert for inactivity under 60 minutes regardless of learned interval, to avoid nuisance alerts)
- Respect suppression modes (holiday, snooze)

### Drift Detection

**Standard approach:** CUSUM (Cumulative Sum Control Chart) is the preferred lightweight method for gradual change detection in time-series welfare monitoring. It accumulates evidence of deviation without requiring external libraries and operates on rolling summary statistics.

**Key design principle:** Drift alerts must distinguish a single unusual day (a visit from family, a late night) from a sustained change. Literature recommends requiring N ≥ 5–7 consecutive days of below-baseline activity before a drift alert fires.

**Drift sensitivity levels:** Research recommends two thresholds — a "warning" (early drift signal, not yet actionable) and "alert" (sustained drift, warrants caregiver contact). This maps to the existing Low/Med/High sensitivity concept.

**Reset behavior:** Drift accumulators should reset when:
- Holiday mode is enabled (known absence)
- Snooze is activated for ≥ 1 day
- A significant acute event has already been flagged (avoid dual-alerting on the same situation)

### User-Facing Behavior Expectations

| Alert Type | Urgency | Expected Cadence | User Action |
|------------|---------|------------------|-------------|
| Acute (possible fall / sudden inactivity) | HIGH — check immediately | Rare (ideally < 1/month in normal monitoring) | Contact monitored person or emergency services |
| Drift (gradual behavior change) | MEDIUM — schedule check-in | Uncommon (ideally < 1/week) | Plan welfare visit or medical appointment |
| Learning in progress | INFO — no action | Once at setup | Wait for learning window to complete |
| Holiday / snooze active | INFO — no action | On mode change | Reminder that monitoring is suppressed |

**Alert fatigue is the primary failure mode.** If acute alerts fire too often, users disable notifications or the integration. Research confirms this is the dominant reason smart home welfare monitoring systems are abandoned. The core value statement — "when a notification fires, it should represent something genuinely unusual" — must take precedence over sensitivity.

---

## Competitor Feature Analysis

| Feature | Existing HA `alert` integration | `carePredict` / commercial systems | Our Approach |
|---------|---------------------------------|-------------------------------------|--------------|
| Inactivity detection | Fixed threshold template + binary sensor | AI-based, cloud, expensive | Learned per-entity interval, local |
| Drift / gradual change | Not available | Commercial black box | CUSUM on rolling entity baseline |
| Learning period | Not available | 2–4 weeks typical | 4 weeks default, configurable |
| Binary entity support | Yes (native) | Proprietary sensors | Yes — HA native entity types |
| Holiday / snooze | Not available | "Away mode" | Existing holiday + snooze preserved |
| False positive controls | Minimal (template logic only) | Proprietary | Sustained-evidence requirement + existing suppression |
| Privacy | Local | Cloud-dependent | Local — HA-native, no cloud |

---

## Sources

- [Anomaly Detection Technologies for Dementia Care — Narrative Review, 2025 (Sage Journals)](https://journals.sagepub.com/doi/10.1177/07334648251357031) — MEDIUM confidence, peer-reviewed 2025
- [IoT Edge Intelligence Framework for Elderly Monitoring, PMC 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC11944996/) — MEDIUM confidence, peer-reviewed 2025
- [Smart Home Anomaly Detection for Older Adults — deep learning, PMC 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12106144/) — MEDIUM confidence, peer-reviewed 2025
- [Algorithm to Detect Abnormally Long Inactivity in a Home (ResearchGate)](https://www.researchgate.net/publication/221234469_Algorithm_to_automatically_detect_abnormally_long_periods_of_inactivity_in_a_home) — HIGH confidence, foundational method
- [Inactivity Patterns and Alarm Generation in Senior Citizens' Houses (ResearchGate)](https://www.researchgate.net/publication/281804588_Inactivity_patterns_and_alarm_generation_in_senior_citizens'_houses) — HIGH confidence, directly relevant
- [Behavioral Drift Detection — Identity Management Institute](https://identitymanagementinstitute.org/behavioral-drift-detection/) — MEDIUM confidence, pattern description
- [ruptures: Change Point Detection in Python (PyPI)](https://pypi.org/project/ruptures/) — HIGH confidence, library reference (considered and excluded per no-new-dependencies constraint)
- [What Users Value Most in Smart Homes — NN/g](https://www.nngroup.com/articles/smart-homes-user-value/) — MEDIUM confidence, UX research
- Code review: `custom_components/behaviour_monitor/sensor.py`, `const.py` (2026-03-13) — HIGH confidence, primary source

---
*Feature research for: Routine-based anomaly detection — home automation welfare monitoring*
*Researched: 2026-03-13*
