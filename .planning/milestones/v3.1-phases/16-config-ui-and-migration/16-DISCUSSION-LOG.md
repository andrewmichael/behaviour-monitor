# Phase 16: Config UI and Migration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-03
**Phase:** 16-config-ui-and-migration
**Areas discussed:** Tier override UI design, Migration v7 to v8 strategy, Override application point

---

## Tier Override UI Design

| Option | Description | Selected |
|--------|-------------|----------|
| Auto / High / Medium / Low | Four options matching ActivityTier values. Follows drift_sensitivity pattern. | |
| Auto / Force High / Force Low only | Three options, skip medium. | |
| You decide | Let Claude pick during planning. | ✓ |

**User's choice:** You decide
**Notes:** Deferred to Claude's discretion.

---

## Migration v7 to v8 Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Simple setdefault to 'auto' | New additive key, doesn't interact with existing multiplier. | |
| You decide | Let Claude pick. | ✓ |

**User's choice:** You decide
**Notes:** Deferred to Claude's discretion.

---

## Override Application Point

| Option | Description | Selected |
|--------|-------------|----------|
| Coordinator overrides after classification | Classification runs, override replaces result. Preserves diagnostic data. | |
| Skip classification when override set | Don't call classify_tier(). Simpler but loses diagnostic data. | |
| You decide | Let Claude pick. | ✓ |

**User's choice:** You decide
**Notes:** Deferred to Claude's discretion.

---

## Claude's Discretion

- All three areas deferred to Claude's judgment during planning.

## Deferred Ideas

None — discussion stayed within phase scope.
