# Milestones

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

