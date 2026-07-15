# Production State Witness

Use this reference for state/UI/async/concurrency bugs and policy or gate changes.

## Purpose

The witness prevents a green test from proving the wrong Boolean/enum combination. It is
about semantic reachability: test inputs must come from the production call site that the
user actually traverses.

## Required record

Create `state_witness.md` before production edits. Keep it short and concrete.
See `references/examples/state-witness-example.md` for a filled example.

```markdown
# Production State Witness

## Symptom and terminal condition
- Symptom:
- Success observable:

## Actual call chain
user action -> callback/task -> state producer -> decision function -> queue/store/view

## State inputs
| Input | Producer | Lifecycle/event | Reported value |
|---|---|---|---|

## Truth table
| Case | Production state | Expected decision | Executable evidence |
|---|---|---|---|
| failing path | ... | ... | ... |
| fixed path | ... | ... | ... |
| preserved block | ... | ... | ... |

## Unknowns and instrumentation
- Unknown:
- Log/fixture needed:

## Verification tier
- policy / flow / user-visible
```

## Investigation method

1. Start from the user-visible symptom, not the policy function.
2. Find every call site of the decision function.
3. For each input, find the producer and the event that changes it.
4. Follow the reported path until the value is consumed by the queue/store/view.
5. Write the real failing row before writing the regression test.
6. Add at least one preserved-blocking row; for example, a critical import window must
   remain blocked while a presentation receipt may be released.

Do not infer that two flags are coupled because their names sound related. If a state is
only a one-shot receipt, verify where it is created and cleared. If clearing it does not
trigger a refresh, record that as a flow risk and test the refresh event separately.

## Adversarial review questions

- Does the test use the same enum/Boolean values the production guard can reach?
- Did a test set a flag that is impossible in the real user path?
- Are there independent gates that the implementation only partially releases?
- Does the unblock event actually flush/restart the queue?
- Can an old token/generation callback reach the current store/view?
- Does the evidence prove cache/flow/user-visible completion, or only a policy return value?

If any answer is unknown, the reviewer returns FAIL or marks the acceptance boundary
blocked. A passing policy test cannot override this review.

## Observability for hangs and spinners

When the symptom is blank, spinning, stuck, or never-completes, add targeted logs for:

- token/generation;
- gate inputs and computed decision;
- queue pending/inflight/cache counts;
- start, unblock, terminal success, cancellation, and stale-return events.

The log must make both “why blocked” and “when complete” observable. Completion timing alone
is insufficient when completion never occurs.
