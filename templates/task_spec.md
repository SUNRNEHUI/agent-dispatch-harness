# Task Spec

## Raw User Intent

<!-- Verbatim user words. Do not polish away ambiguity here. -->

## Goal

<!-- System-oriented completion condition. -->

## User-Facing Outcome

<!-- What a human can perceive when done. -->

## Success Is Not (Fake Success / Anti-Success)

<!-- At least 3 items that look done but do not count. -->

1.
2.
3.

## Non-Goals

## Constraints

## Target Call Chain (optional but recommended for path/perf/correctness work)

```text
user action -> ... -> actual terminal success event
```

## Production State Witness (required for state/UI/async/concurrency behavior)

<!-- Link state_witness.md or fill the compact witness: real call-site inputs, producers,
     lifecycle, failing state row, preserved blocking row, and executable test mapping. -->

## Phases (risk-ordered)

### Phase 0

<!-- Measurement / terminal semantics / baseline when improvement-shaped. -->

### Phase 1

### Phase 2

## Acceptance Criteria

<!-- Prefer acceptance_registry.json with pass_algorithm. Summarize here. -->

## Verification Evidence

<!-- Where raw evidence lives; forbid averages-only claims when metrics matter. -->

## Risks

## Budget

## Stop Conditions

## Document Priority

```text
task_spec.md > acceptance_registry.json > run_state.json > tasks/* > review prose
```

## Alignment Packet (for fuzzy goals)

```text
1) Rewritten success (≤3 lines)
2) Fake-success list
3) Default constraints/non-goals (user may veto)
4) Acceptance rules or Phase 0 measurement plan
5) Phase map + first ready task
6) Open decisions with recommended defaults
```

## Artifact Location
