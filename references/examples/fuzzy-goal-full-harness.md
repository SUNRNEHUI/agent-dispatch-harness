# Example: Fuzzy Goal → Full Harness Quality Bar

This example is **domain-agnostic**. It captures the quality bar demonstrated by strong synthesis runs (including performance-style instances) without binding the skill to a single product.

## User raw intent

```text
关键路径太慢了，要专业一点，别搞坏现在的正确性。
```

## Bad compilation

```text
Goal: make it faster
Tasks: optimize everything
Acceptance: feels faster, tests pass
```

## Good compilation (shape)

### Rewritten success

- User-facing: after confirm, the real result is visible on the primary surface.
- System: same generation, terminal `presented` ack, required compute happens once.
- Not success: placeholders, job-complete without present, worker self-report, microbenchmark-only.

### Constraints / non-goals

- Do not change correctness semantics or export parity for speed.
- Do not redesign unrelated UI.
- Do not claim wins without baseline.

### Risk-ordered phases

0. Timing + visible terminal contract + baseline measurement
1. Remove proven stalls / duplicate work
2. Structural path changes
3. Final device/product acceptance

### Acceptance snippet

```json
{
  "id": "AC-001",
  "description": "Confirm-to-presented latency improves vs baseline",
  "required_evidence": ["raw runs", "summary with p50/p95"],
  "pass_algorithm": "cold p50 and p95 both better than Phase 0 baseline; every valid run has presented ack"
}
```

### First ready task

Only define timing/presentation contracts and tests (strict TDD). No optimizer work yet.

## What managers should copy

1. Terminal semantics before optimization
2. Fake-success blacklist
3. pass_algorithm
4. Measure then change
5. Narrow allowed_scope per task
6. Document priority

## What managers should not copy blindly

- Specific vendor codecs, device UDIDs, or product file paths
- Sample sizes and SLOs from another project without re-deriving them
- Full ceremony when Direct/Lite is enough
