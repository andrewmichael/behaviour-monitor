# Milestones

## v4.0 Cross-Entity Correlation (Shipped: 2026-04-07)

**Phases completed:** 4 phases, 8 plans, 9 tasks

**Key accomplishments:**

- Fixed classify_tier() to retry on subsequent update cycles when startup confidence is low or median data is unavailable, instead of blocking until midnight
- Correlation constants, AlertType.CORRELATION_BREAK, config UI NumberSelector (30-600s), and v8->v9 migration chain with 459 tests passing
- CorrelationDetector with PMI-based co-occurrence discovery, minimum co-occurrence gating, and to_dict/from_dict persistence
- CorrelationDetector wired into coordinator for event recording, daily PMI recomputation, persistence, and sensor attribute exposure
- check_breaks method on CorrelationDetector with 3-cycle sustained evidence gating and group-level dedup for CORRELATION_BREAK alerts
- check_breaks wired into coordinator _run_detection with welfare exclusion filter for CORRELATION_BREAK alerts
- decay_stale_pairs() and remove_entity() methods on CorrelationDetector for automatic lifecycle management
- Coordinator async_setup wires remove_entity() to purge stale correlation data when entities leave monitored list

---

## v3.1 Activity-Rate Classification (Shipped: 2026-04-03)

**Phases completed:** 5 phases, 5 plans, 10 tasks

**Key accomplishments:**

- ActivityTier enum with HIGH/MEDIUM/LOW classification, tier boundary/floor/boost constants, and format_duration() utility for human-readable duration strings
- EntityRoutine.classify_tier() with median daily rate mapping to HIGH/MEDIUM/LOW tiers, confidence gating, once-per-day guard, and DEBUG-level tier change logging
- Tier-aware inactivity thresholds with HIGH/MEDIUM/LOW boost factors, absolute floors, and format_duration in alert explanations
- Wired tier classification into coordinator: activity_tier in entity_status, daily reclassification on day change, and format_duration replacing inline h/m arithmetic
- Activity tier override SelectSelector in config UI with v7->v8 migration and coordinator wiring

---

## v3.0 Detection Accuracy (Shipped: 2026-03-14)

**Phases completed:** 3 phases, 6 plans, 5 tasks
**Files modified:** 29 | **Lines of code:** ~9,892 Python (2,746 integration + 7,146 tests)
**Git range:** `584782e` (feat(09-01)) → `7cf8b8a` (docs(phase-11))

**Key accomplishments:**

1. Fire-once-then-throttle alert suppression — `_alert_suppression` dict prevents same-condition spam, persisted to HA storage with clear-on-resolve
2. Alert repeat interval configurable in HA options UI (30–1440 min, default 4 h) with seamless v5→v6 migration
3. CUSUM drift baseline split by day-type (weekday vs weekend) — weekend anomalies no longer diluted by 5× more weekday history
4. Exponential decay weighting (0.95/day) makes recent activity dominate over 60+ day stale history
5. Per-entity CV-adaptive inactivity thresholds — regular entities get 1.5× floor, erratic entities up to 10× ceiling; min/max bounds configurable in UI with v6→v7 migration

---

## v2.9 Housekeeping & Config (Shipped: 2026-03-14)

**Phases completed:** 3 phases, 6 plans, 0 tasks

**Key accomplishments:**

- (none recorded)

---

## v2.9 Housekeeping & Config (Shipped: 2026-03-14)

**Phases completed:** 3 phases, 6 plans

**Files modified:** 40 | **Lines of code:** 7,863 Python
**Git range:** `27791e6` (refactor(06-01)) → `51d6049` (docs(08-01))

**Key accomplishments:**

1. Removed deprecated ML sensor stubs (ml_status, cross_sensor_patterns, ml_training_remaining) and dead constants block from const.py
2. Removed unused CONF_* constant definitions (CONF_SENSITIVITY, CONF_ENABLE_ML, CONF_RETRAIN_PERIOD, and others)
3. Exposed learning period (days) and attribute tracking toggle as user-configurable options in the HA config UI
4. Added v4→v5 config migration so existing installs upgrade without manual reconfiguration
5. Fixed missing post-bootstrap _save_data() call — routine model now survives an immediate restart after first load

---

## v1.1 Detection Rebuild (Shipped: 2026-03-13)

**Phases completed:** 3 phases, 9 plans, 2 tasks

**Files modified:** 51 | **Lines of code:** 7,934 Python
**Git range:** `8dc94b2` (feat(03-01)) → `e118dcc` (docs(05-03))

**Key accomplishments:**

1. Built RoutineModel — pure-Python baseline engine with 168 hour×day slots, Welford statistics, and recorder bootstrap from HA history
2. Built AcuteDetector — inactivity and unusual-time detection with sustained-evidence gating (3 consecutive cycles required)
3. Built DriftDetector — bidirectional CUSUM change-point detection with configurable sensitivity tiers (high/medium/low)
4. Rewrote coordinator from 1,213 to 348 lines, wiring all three detection engines with full suppression logic preserved
5. Rewrote config flow for v4 — history window, inactivity multiplier, drift sensitivity; graceful v1.0→v4 migration chain
6. Deleted z-score analyzer, River ML analyzer, and associated tests — zero external ML dependencies

---

## v1.0 False Positive Reduction (Shipped: 2026-03-13)

**Phases completed:** 2 phases, 5 plans, 10 tasks
**Files modified:** 32 | **Lines of code:** 8,827 Python
**Git range:** `d921f26` (feat(01-01)) → `bbd10b4` (docs(phase-2))

**Key accomplishments:**

1. Built notification suppression layer: severity gate, per-entity cooldown, cross-path dedup, and welfare debounce in coordinator
2. Added sparse-bucket guard (MIN_BUCKET_OBSERVATIONS=3) eliminating infinite z-scores from zero-variance buckets
3. Raised default sensitivity from 2.0σ to 2.5σ, reducing statistical false positive rate from ~4.5% to ~1.2%
4. Implemented per-entity adaptive thresholds using coefficient of variation for high-variance entities
5. Added EMA score smoothing (α=0.3) to suppress single-spike ML false positives
6. Tightened ML contamination values and raised cross-sensor co-occurrence threshold from 10 to 30

---
