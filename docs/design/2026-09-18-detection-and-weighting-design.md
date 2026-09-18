# Behaviour Monitor — detection and weighting design

18 Sept 2026 · Andrew Bourne

> Ingested verbatim from the author's design document. This is the source of truth for the
> v6 detection work; the gap analysis and sub-project decomposition live in
> `docs/design/2026-09-18-detection-gap-analysis.md`.

## Purpose and principles

This specifies detection and weighting logic for the behaviour_monitor integration, written to work in any deployment. No entity IDs, room names or thresholds are hardcoded.

The figures quoted throughout come from a reference deployment monitored over seven days (11–18 September 2026) and cross-checked against published passive-monitoring research. They justify the defaults, not the behaviour. Every one is configurable, and most should converge on their own.

### Principles

**Self-calibrating over configured.** Anything derivable from observed history should be derived. A weight, threshold or baseline someone has to maintain by hand goes stale silently, and a silently wrong value is worse than none because the output still looks authoritative.

**Semantic roles, not entity IDs.** The logic reasons about "a bathroom motion sensor" and "an exterior door", never about a specific entity. Installations differ in room count, sensor placement and naming.

**Absence is the signal.** The failure mode that matters is nothing happening. An anomaly detector looks for unusual events; this system must look for expected events that did not occur.

**Explainable over accurate.** When an alert fires at 3am the responder needs to see which inputs drove it. A detector nobody can interrogate will not be trusted, and an untrusted alert is an ignored one.

**Degrade loudly.** The system must be able to detect that it is blind. A monitor reporting normal while receiving no data is the worst possible failure, and it has already happened once in the reference deployment.

### Deployment assumptions

Single primary resident. Multiple occupants break most inference here — sequence rules in particular assume one person moving through the house. Where a deployment has two residents, detection should degrade to liveness and panic only rather than produce confident nonsense.

## Entity model

Each configured entity is assigned a role at setup. Roles carry semantics; entity IDs do not.

| Role | Purpose | Cardinality |
|---|---|---|
| motion.bathroom | Overstay detection, nocturia counting | 0–n |
| motion.bedroom | Sleep window, night waking | 0–n |
| motion.living | Daytime occupancy | 0–n |
| motion.kitchen | Meal-time anchors | 0–n |
| motion.transit | Hall, landing; used for routing only | 0–n |
| door.exterior | Away state, excursions | 0–n |
| door.interior | Routing, room transitions | 0–n |
| appliance | Activity evidence, subject to weighting | 0–n |
| panic | Emergency, bypasses all logic | 0–n |

Roles are advisory where possible. A deployment with no bathroom sensor simply loses the rules that depend on one, and must say so in the entity status rather than silently skipping them.

### Adjacency graph

Optional but unlocks several rules. Each exterior door names the room it is reached through; rooms name their neighbours.

```yaml
adjacency:
  door.side: [motion.kitchen]
  door.back: [motion.kitchen, motion.living_rear]
  motion.kitchen: [motion.living_rear, motion.hall]
```

Without it, transit timing and door-adjacency validation are unavailable. With it, both come free from existing sensors. Consider deriving it automatically from observed transition frequencies after a training period, and offering it for confirmation rather than asking the installer to draw it.

### Configuration

All thresholds live in the options flow with the defaults given in this document. None appear as literals in code.

Entities below the training minimum are excluded and reported as training, never defaulted to a middle value.

### Time model

The sleep window is derived, not configured — the observed daily period with lowest activity across the training set. In the reference deployment this was 22:00–07:00, with zero door events across all seven nights. Do not ship that as a constant; a different resident will have a different window, and deriving it costs nothing.

## Event pipeline

Raw state changes are not activity events. Four stages sit between them, in this order.

### 1. Discard artifacts

Integration reloads write synthetic states to every entity at once. In the reference deployment all six motion sensors were set to on in the same second on reload, and a separate resync cleared three of them to off in the same second. Neither was motion.

- Discard any batch where three or more entities change within the same second
- Ignore all events for 60–120 seconds after homeassistant_start

Without this, every restart injects a false burst across the whole house and corrupts the baseline.

### 2. Debounce

Motion: 2 minutes, per entity. Never per category. In the reference deployment a single person walked through three rooms in 29 seconds — a category-wide debounce would collapse that into one event and destroy the sequence, which is the strongest signal these sensors produce.

Doors: 60 seconds, per entity. Shorter, because contacts do not retrigger the way PIRs do.

Retrigger noise is separate and shorter. Sensors commonly emit an off/on pair milliseconds apart — observed at 23ms in the reference data. Collapse anything under 5 seconds before debouncing.

### 3. Preserve last_seen

Debounce suppresses counting, never last_seen. Time-since-activity is the load-bearing welfare metric and must reflect the most recent report. Otherwise someone moving around a single room reads as quieter than they are.

### 4. Group into excursions

Two exterior doors firing within 60 seconds of each other is one through-trip, not two events. The reference deployment logged eleven door events in 26 minutes that were four such pairs plus three singles — one person making repeated trips outside.

Emit a single excursion event with a duration. Otherwise a trip to the bin outscores an hour of indoor activity.

### Door open duration

Classify rather than discard; the distribution is bimodal in practice.

| Class | Duration | Meaning |
|---|---|---|
| Brief | < 15s | Normal passage |
| Extended | 15–120s | Carrying, loading |
| Prolonged | > 120s | Noteworthy by day; escalate at night |

Reference deployment: most events 5–9 seconds, two at 40 and 49 seconds.

## Weighting

Inputs are not equally indicative of human activity. Some fire identically every day whether or not anyone is awake — counting those means the monitor can report normal behaviour for a house nobody is moving in.

The discriminator is variance in firing time, not device type. In the reference deployment a teasmade fired at 07:00 on all seven days with no variation, while a kettle on the same circuit type varied its first boil across two hours and its daily count from two to four. Same category, opposite value.

### Formula

Bucket each entity's activations by time of day over the training window and take the normalised entropy of that distribution:

H_norm = ( -Σ_i p_i log p_i ) / log n

where p_i is the proportion of activations in bucket i and n is the number of non-empty buckets. A timer concentrates in one bucket, giving H near 0. Human activity spreads, giving H nearer 1. Weight is H_norm, subject to a floor.

Entropy rather than standard deviation, because human patterns are multi-modal. A kettle used morning, afternoon and evening has high deviation for the wrong reason and would be indistinguishable from genuine irregularity. Entropy over buckets handles clusters correctly.

### Parameters

| Parameter | Default | Notes |
|---|---|---|
| Bucket width | 60 min | 30 min viable with higher event volume |
| Training window | 14 days | Minimum 7; below this, exclude |
| Weight floor | 0.05 | Non-zero so a timer still acts as a device liveness check |
| Recompute | Daily, rolling | Not once at setup — the point is that it tracks change |

### Constraints

- Compute weight over debounced activations, so retrigger noise is not rewarded as irregularity.
- Weighting applies to activity scoring only. It must never gate a panic event or a liveness check.
- Categories carry no implicit weight. A per-category default would reintroduce exactly the hand-assignment problem this replaces.
- Surface the computed weight per entity in the status attributes. A weighting system nobody can see is one nobody can debug.
- A zero-weight entity still needs liveness monitoring. A timer that stops firing says nothing about the resident but everything about the device.

## Derived state and detection rules

### Away state

Doors resolve the ambiguity motion alone cannot: a quiet house means either "went out" or "something is wrong". Without this distinction every shopping trip looks like a welfare event, and loosening thresholds in response is what makes a monitor miss the real thing.

- Enter away: door.exterior event, then no motion anywhere for 15 minutes. Suspend all absence-based rules.
- Exit away: door event followed by motion within 2 minutes.
- Inconsistency: motion resuming with no preceding door event while away means a door sensor missed an entry. Log as sensor health, not activity.

### Transit timing as a gait proxy

Where adjacency is configured, record transit time for ordered adjacent room pairs where the gap is under 60 seconds with no intervening trigger elsewhere. Reference deployment observed 19s and 10s between adjacent rooms on a single walk-through.

The individual measurement is noise. The rolling median per room pair over weeks is the signal, and walking speed is an established predictor of decline and falls risk. This must never trigger an alert — it belongs in a trend view for a human to read.

No new hardware required, and computable retrospectively against existing history.

### Rules

| # | Rule | Default trigger | Requires |
|---|---|---|---|
| 1 | Bathroom overstay | Bathroom activation, then no activation in any other room for 20 min | motion.bathroom |
| 2 | Night bathroom frequency | 3-night rolling count exceeds 14-day baseline | motion.bathroom, sleep window |
| 3 | Morning chain broken | Bedroom fires, no bathroom within 45 min | bedroom + bathroom |
| 4 | Expected anchor missed | Derived per-anchor time + 90 min | training window |
| 5 | Night-time exterior door | Any door.exterior during sleep window | door.exterior |
| 6 | Daytime inactivity | No motion during the derived active window | any motion |

Rule 1 condition is no activation in any other room, not "bathroom clears". Someone on the floor stops triggering the bathroom sensor too.

Rule 2 must not alert on a single night. The reference deployment recorded five night wakings on one night, well within normal variation. The signal is sustained elevation against the rolling baseline. This matters because urinary tract infections in older adults often present as confusion or falls rather than urinary symptoms, so the behavioural change can precede any complaint.

Rule 4 anchors are derived from the training window, not configured. Anchors must be motion-based: a timer-driven appliance firing proves nothing about the resident.

Rule 5 is high-signal where the derived sleep window is clean. Undebounced and unweighted.

### Visitor context

An exterior door with near-zero historical usage — the reference deployment's front door had zero openings in seven days — is useless as activity and valuable as an event. Tag the day as having had a visitor; an unusual routine on a visitor day is probably the visitor, and flagging it avoids chasing false anomalies.

## Escalation

Alert on concurrent deviation across several markers, not on any single threshold crossing. Research into delirium detection from home sensor data found detected episodes cluster in time with multiple markers deteriorating together, matching the clinical pattern of two to three symptoms preceding an episode.

This is the organising principle, not one rung of the ladder. A single late anchor is weak evidence. A late anchor plus elevated night waking plus a missed meal pattern is strong evidence.

| Level | Condition | Response |
|---|---|---|
| Watch | One marker deviating, or anchor 30 min late | Logged, no notification |
| Soft | Two markers concurrently, or anchor 90 min late | Notification, normal priority |
| Escalate | Three or more markers, bathroom overstay, or night-time exterior door | Critical alert, bypasses snooze |
| Panic | Panic role triggered | Immediate, bypasses everything |

A single binary flag forces a choice between tolerating false positives and setting thresholds so loose they miss things. Graded levels keep the critical channel rare enough to stay trusted.

### Panic path

A separate path, not high-weight activity. It must ignore weighting, debounce, snooze, holiday mode, away state, baseline confidence and any still-training gate. No condition should ever be able to swallow a panic press.

On iOS, use interruption-level: critical with critical: 1 in the sound block so it breaks through the silent switch and Do Not Disturb. This requires critical alerts to be enabled for the companion app in iOS settings. Use a distinct notification tag from welfare alerts, so a panic notification is never silently replaced by a later message.

### Notification targets

Configurable per level. At minimum: a target for soft alerts and a separate, always-critical target for escalate and panic. Do not assume one recipient — a deployment may need a family member and a carer on different levels.

## System integrity

In the reference deployment the monitor reported ok for several hours while all of its configured entities had been deleted. It could not detect that it was blind. This is the highest-severity class of defect in a welfare system and should be addressed before any detection work lands.

### Self-reporting

- Unresolvable entity IDs must be loud. A configured entity that does not exist raises a repair issue; it is never silently skipped.
- Input loss lowers the score, it does not renormalise. Renormalising across surviving inputs makes a blind monitor permanently indistinguishable from a healthy one.
- The status summary must count what the producer emits. In the reference deployment it reported 0 OK, 0 Need Attention while its own attributes held fifteen entities with statuses the counter did not recognise.
- Never report ok without qualification. Welfare status should carry the number of contributing entities, so "ok" and "ok, but from nothing" are distinguishable.

### Per-entity silence thresholds

Each entity needs a maximum plausible silence period derived from its own history, not a global constant. In the reference deployment one motion sensor logged 1,469 state changes in a week and another 253 — twelve hours of silence means something different for each.

The entropy calculation already produces the distribution this needs.

### Deliberate disconnection

Field research with homecare professionals found service users switch telecare off themselves: disabling door sensors to avoid bothering staff, and unplugging devices as part of an evening habit of unplugging everything. Disconnecting linked devices takes the alarms down along with the sensors.

This bears on any deployment using smart plugs as inputs. Treat device silence as potentially deliberate rather than purely a fault, and keep the alerting path independent of the sensing path wherever the platform allows.

### Panic device liveness

An untested panic button is worse than none, because it is trusted. Panic entities need a battery and heartbeat check with its own alert, separate from the panic path, and ideally a periodic press test with a reminder if it lapses.

In the reference deployment both panic buttons showed last_seen: None — their working state was unknown and nothing surfaced that.

## Validation, evidence and open questions

### Replay testing

Write the pipeline, weighting and rules as pure functions over a timestamped event stream — (entity_id, role, timestamp, state) in, weights and levels out — with no Home Assistant state access inside them.

This makes recorder history replayable offline, which is a far better test than synthetic fixtures. A deployment with a week of history can answer: does a known timer converge to near-zero weight; is the debounce window right; do known-normal days stay below alert thresholds; do known-abnormal days rise above them.

It also makes the defaults in this document falsifiable rather than asserted.

### Evidence basis

The rules draw on published passive-monitoring research, but that literature is thinner than its confidence suggests. Evidence remains limited to a few research groups, studies are small — one widely cited cohort followed 24 people — and most results are proof-of-concept rather than validated in practice.

This argues for simple, explainable rules over a sophisticated anomaly detector. Explainability is itself a finding: work on UTI prediction emphasises that letting a clinician see which data points drove a prediction is what makes the output usable.

Acceptability research consistently finds that comfort with home monitoring rises with the resident's own perceived need for it, and that privacy concerns are significant. Worth confirming any deployment is understood and welcome at the monitored end — which also determines whether sensors stay switched on.

### Sources

- Potential of Ambient Sensor Systems for Early Detection of Health Problems in Older Adults — PIR plus bed sensor, 24 participants over 1–2 years
- Early detection of health decline using personalized normals — motion sensors, bed sensor and in-home gait
- Passive smart home monitoring for delirium-relevant anomaly detection — temporal clustering, concurrent marker deterioration
- Digital remote monitoring for early detection of UTIs — night bathroom frequency and sleep disturbance as predictors
- Safety for older adults using telecare: perceptions of homecare professionals — users disabling sensors and alarms
- Engaging older adults to guide passive home health monitoring — acceptability and privacy preferences

Sources were identified by search and cited from abstracts and summaries rather than full review.

### Open questions

- Is 20 minutes right for bathroom overstay? Chosen as long enough for a bath, short enough to matter. No deployment data yet validates it.
- What counts as a marker for escalation? The concurrent-deviation model needs an explicit marker list before implementation.
- Can the adjacency graph be derived rather than configured? Transition frequencies after a training period should reveal it.
- How should multi-occupant deployments degrade? Currently specified as liveness and panic only; needs a detection method for the condition.

## Out of scope

- Bed sensors. The most significant hardware gap — published work pairs PIR with a bed sensor recording heart rate, respiration and sleep quality, and a bedroom PIR cannot distinguish lying awake from sleeping. Worth supporting as a role later.
- Fall detection proper. Bathroom overstay is a proxy; real detection needs different hardware.
- Baseline reset semantics. A release that redefines what an event is should probably reset deliberately rather than carry forward incompatible history — but that should be a decision, not a side effect.
