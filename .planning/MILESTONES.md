# Milestones

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

