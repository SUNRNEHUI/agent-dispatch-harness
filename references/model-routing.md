# GPT-5.6 Model Routing

Load this reference only when the runtime can choose a model or reasoning
effort. It is a routing policy, not a guarantee that every Codex surface
exposes the same model IDs or controls.

## Default Policy

| Responsibility | Starting model | Reasoning | Use |
| --- | --- | --- | --- |
| Manager | Inherit the active parent model | Preserve the parent setting | Requirements, scheduling, synthesis, merge, and final acceptance |
| Simple sub-agent | `gpt-5.6-luna` | `low` | Read-only scans, extraction, summarization, simple tests, bounded docs |
| Moderate worker | `gpt-5.6-terra` | `medium` | Separable implementation, broader exploration, or work that needs more context |
| Critical reviewer/evaluator | `gpt-5.6-sol` | `medium` initially | Security, ambiguous requirements, cross-cutting changes, and final risk review |

Use `gpt-5.6-luna` as the default for simple sub-agent work only when the
runtime supports an explicit override. Do not force the manager onto Luna, and
do not silently upgrade every worker to Sol.

## Escalation Rules

- Escalate from Luna when the task is ambiguous, cross-file, security-sensitive,
  write-heavy, or its result determines an irreversible action.
- Use Terra when the task is moderate or context-heavy but does not need
  quality-first reasoning.
- Start Sol at medium. Raise to `high` or `xhigh` only when representative
  evaluation shows a meaningful quality or safety gain. Do not use `max` or
  `xhigh` as a global default.
- Luna has a smaller context window than Sol/Terra in the current GPT-5.6
  guidance. Route large inputs to a model with enough context, or split the
  input into bounded read-only tasks and verify the synthesis.
- If model or reasoning selection is unavailable, use the inherited runtime
  configuration and record that the requested override was unavailable. Never
  claim that Luna, Terra, or Sol actually ran without runtime evidence.

Codex may expose `agents.max_threads` and `agents.max_depth`; treat the current
six-thread and depth-one defaults as capability ceilings, not as a reason to
fill every slot. The task budget remains the source of truth for fan-out.

## Dispatch Budget

- Start with one wave: at most two workers for Lite and three for Full unless
  the task spec names more independent surfaces and the budget allows it.
- Keep agent nesting at depth one: workers do not spawn descendants.
- Give each worker only task-local context: goal, scope, inputs, constraints,
  evidence, stop conditions, budget, and return format. Do not replay the full
  manager transcript or full protocol into every worker.
- Prefer parallel read-heavy work. Keep dependent decisions and shared-file
  writes sequential under a named owner.
- Allow at most one follow-up per worker. Stop when results are redundant, the
  manager cannot synthesize them cheaply, or coordination cost exceeds the
  expected quality or latency benefit.
- Return compact summaries and durable report paths; do not send raw logs to the
  manager unless a failure or acceptance criterion requires them.

## Truthful Route States

Keep the requested route separate from what the runtime proved:

- `requested`: the manager asked for a model or reasoning override;
- `accepted`: the active tool accepted the exact override;
- `used and confirmed`: runtime metadata proves the child model/provider/effort;
- `inherited root`: the override was unavailable or not accepted, so the child
  used the inherited configuration.

Child prose, prompt text, or a model name in a report is not runtime proof.
Direct model overrides keep the parent provider; a different provider requires
an already configured, authenticated, provider-pinned agent. Never weaken
permissions or claim a cross-provider route from a prompt preference alone.

## Measurement

Do not claim token or cost savings from this policy alone. When runtime metrics
are available, compare representative tasks for success, evidence quality,
total tokens, latency, tool calls, retries, and cost. Keep a policy change only
when the quality and safety gates still pass.

## Token Accounting Contract

Each generated stage/task `resource_budget` may record:

- `token_budget`: the allowed input/output budget, or `null` when no limit was
  supplied;
- `tokens_used`: actual or estimated usage, or `null`;
- `tokens_remaining`: remaining usage, or `null`;
- `usage_kind`: `actual`, `estimated`, or `unknown`;
- `accounting_note`: how the value was obtained or why it is unavailable;
- `exhaustion_action`: fixed to `stop_and_record_decision`.

When `token_budget` is set, exhausted or unaccountable usage is a blocker: do
not mark the run accepted, append the evidence/decision to trace, and either
reduce scope, continue with an approved budget decision, or hand off blocked.
`unknown` means unavailable; it never permits inferring tokens from characters,
tool-call count, or model name.

Sources:

- [GPT-5.6 migration guidance](https://developers.openai.com/api/docs/guides/upgrading-to-gpt-5p6-sol.md)
- [GPT-5.6 prompting guidance](https://developers.openai.com/api/docs/guides/prompt-guidance-gpt-5p6.md)
- [Codex manual: multi-agent operations](https://developers.openai.com/codex/codex-manual.md)
