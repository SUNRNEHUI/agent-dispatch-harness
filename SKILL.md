---
name: agent-reliability-harness
description: >
  Use when a task explicitly requests multi-agent, sub-agent, DAG, worktree, or parallel
  delegation; when a vague or improvement-shaped goal is easy to fake-complete; or when
  long, resumable, high-risk work needs durable evidence and acceptance across sessions.
  Former names: Agent Dispatch Harness; Multi-Agent Dispatcher.
---

# Agent Reliability Harness

**What this is:** a runtime-agnostic **task OS** — precise execution with intelligent
proportional process. Not “always multi-agent”, not “always write a big harness”.

**Works on:** Codex, Claude Code, Grok, and any agent that can read files, run
commands, and follow a short protocol. Runtime adapters are optional polish, not required.

```text
User intent  →  density decision  →  Spec/State Witness when needed  →  execute  →  evidence  →  done
```

## 0. Non-negotiables

1. **Proportionality** — use the lightest mode that still makes false completion hard.
2. **Evidence over self-report** — commands, diffs, logs, tests, screenshots; never “我觉得完成了”.
3. **Terminal success is defined** — if success is easy to fake, define fake-success first.
4. **User owns intent + veto; you own compilation + verification.**
5. **Do not spend tokens on ceremony** that does not reduce risk or enable resume.
6. **Production-state fidelity** — a passing policy test is not evidence unless its inputs
   are traced to a real production call site and state combination.

## 1. Density decision (when to write a harness)

Answer in order. **Stop at the first match.**

| If… | Mode | Write on disk? | Token budget |
|-----|------|----------------|--------------|
| Typo, one file, obvious command, narrow bug, pure Q&A | **Direct** | **No** harness files | Just do + verify |
| Clear goal, 2–5 steps, one owner, low false-completion risk | **Direct+** | Optional 5–10 line plan **in chat only** | No `workspace/` |
| Fuzzy goal **or** easy fake success **or** improvement-shaped (faster/better) | **Synthesize first** | Compact in chat, or Lite notes, or Full files — see §2 | Synthesis short; Full only if long |
| Medium work, clean parallel ownership, user OK with workers | **Lite** | Short plan + compact reports; **no** full registry by default | Bounded workers |
| Long / multi-stage / resumable / multi-session / high risk / need evaluator | **Full** | Durable `workspace/<slug>/` artifacts | Worth the tokens |

**Hard rules**

- Multi-agent **words** ≠ must dispatch. Tiny task + “用多 agent” → still Direct (say so once).
- **Single owner** + medium steps → **Direct+** (chat plan), even if user said multi-agent — Lite only when parallel ownership is real.
- Fuzzy goal ≠ Full harness. Prefer **compact synthesis** (§2) then Direct/Lite.
- Improvement-shaped (latency, cost, accuracy) → at least terminal metric + baseline plan before “optimize”.
- State/UI/async/concurrency symptoms (blank, spinner, stale, stuck, race) → require a
  Production State Witness before implementation or dispatch.
- If coordination cost > implementation cost → do not dispatch.

**Do NOT create** `run_state.json` / full artifact dirs for small or medium tasks unless Full triggers fire.

### Cost-aware model routing (after density)

Model choice never justifies dispatch. Finish a tiny task in the current thread; use a
cheaper worker only when repeated/parallel work outweighs coordination cost.

| Profile | Model / effort | Route |
|---|---|---|
| `fast` | Luna `medium` | simple + mechanically verifiable |
| `main` | Luna `xhigh` | default high-frequency manager/executor |
| `planner` | Sol `high` | fuzzy goals, planning, harness synthesis |
| `critical_reviewer` | Sol `xhigh` | high risk, conflict, two validation failures |

Terra is not used by this Codex policy. Run `scripts/model_router.py` when uncertain. Persist
the runtime/profile/model/reason in every real Full dispatch. Deep rules and CLI:
`references/model-routing.md`.

## 2. Spec Synthesis (fuzzy → executable)

When the user cannot fully specify success, **you compile** — user reviews/vetoes.

### Compact (default — chat or `synthesis_notes.md`)

```text
1) Success: user-facing + system condition (≤3 lines)
2) Not success: ≥3 fake-success items (if risk)
3) Non-goals / constraints (defaults OK, mark recommended)
4) Accept: pass rule OR “TBD after measure: …” (never invent SLOs)
5) Steps: risk-ordered (measure before optimize when needed)
6) First action + stop conditions
```

### Full (only if §1 says Full)

Durable files under `<project>/workspace/<slug>/`. Prefer:

```bash
python3 <skill-dir>/scripts/init_run.py --project-root <project> --title "<title>" --with-synthesis
```

Then **fill** templates (empty headings ≠ plan). Stage `0` synthesis stays ready before impl tasks.

Deep guide: read `references/spec-synthesis.md` **only when** doing Full or stuck on synthesis quality.
Quality bar example: `references/examples/fuzzy-goal-full-harness.md`.

**Document priority (Full):**
`task_spec` > `acceptance_registry` > `run_state` > `tasks/*` > review prose.

### Production State Witness (stateful behavior)

Before changing a policy, gate, queue, token, generation, async callback, or UI state path,
write `state_witness.md` (Full) or the equivalent section in the Lite plan. It must trace:

- the user-visible symptom and terminal success condition;
- the actual production call chain that produces the decision;
- each Boolean/enum input, its producer, lifecycle, and current value in the reported path;
- a truth table containing the real failing combination, the intended fix, and preserved
  blocking combinations;
- the executable test or fixture that maps to each critical row.

Do not use a convenient synthetic combination merely because it makes a unit test pass.
If the witness cannot identify the real combination, mark the task as investigation or
blocked and add targeted logging before claiming a fix.

## 3. Execution modes

### Direct

- No workers, no harness artifacts.
- Do the work; run the smallest real check; summarize.

### Lite

- Short plan: owners, scope, outputs, verification.
- Workers only with **disjoint** ownership and self-contained prompts.
- Reports: compact file or short status — not essay spam.
- Fuzzy override lives in plan / `synthesis_notes.md`, **not** a fake Full `run_state`.

### Full

```text
Intake → Density/Mode → Synthesis? → State Witness? → Capability → Artifacts → DAG
  → Workers → State → Adversarial Review → Verify → Stop? → Merge → Handoff
```

- Manager owns state, merge, final acceptance.
- Workers own bounded slices only.
- `init_run --with-synthesis`: impl tasks stay `planned` until synthesis checklist done.
- Before dispatch, validate filled specs with `validate_report.py ... --type spec --require-filled`.
- For stateful behavior, validate that `state_witness.md` names the real call-site inputs
  and at least one executable check covers the reported state row before implementation.
- Run `python3 <skill-dir>/scripts/state_witness_check.py <artifact-dir>/state_witness.md --require-filled`
  before `seal` or dispatch when the witness trigger fires.
- After human-authored Full JSON/spec edits and before execution, run `harnessctl.py seal <artifact-dir> --reason <why>` to bind the reviewed baseline.
- Record every real worker with `dispatch-create` immediately after spawn and advance it with `dispatch-update`; chat-only worker IDs are not resumable state.
- Mutate run, task, and acceptance statuses through `harnessctl.py`; direct JSON edits are not accepted evidence.
- Protected PASS uses controller-generated typed receipts such as `--evidence-file`; free-form `--evidence` is supporting context only and cannot complete a new Full run.
- Run `harnessctl.py validate <artifact-dir>` before resume, evaluation, and final acceptance.
- After GREEN and before final acceptance, run an adversarial call-site review. It must try
  to find a production state combination missing from the tests. A finding reopens a new
  RED → GREEN → REFACTOR cycle; it is not a prose footnote.

Capability / worktree / TDD details: load only when needed (`references/tdd-gates.md`, adapters).

## 4. Worker contract (any model)

Prompt must be **self-contained**: goal, allowed scope, constraints, outputs, verify, stop, report path.
No “as discussed above”.

Worker returns **only**:

```text
状态：已完成 / 失败 / 需要决策
报告：<path>
产出：N 个文件（路径）
决策点：一句话或无
```

Implementation reports need gate mode + RED/GREEN or substitute (+ no-test reason).
`已完成` ≠ final PASS — manager/evaluator accepts on evidence.

Optional: `python3 <skill-dir>/scripts/validate_report.py <report> --type subagent`

## 5. Verification & stop (precision)

**Accept only with external evidence:** tests, typecheck, build, logs, browser, API readback. In Full mode, retain the checked output/report inside the artifact and pass it through `--evidence-file` so the controller records its digest and transaction receipt.
Reject stubs/TODOs/mocks as “done”. UI paths need browser/screenshot when available.

For user-visible state/UI bugs, separate evidence tiers:

1. **Policy tier** — the decision function returns the intended result for the witness rows.
2. **Flow tier** — the real producer-to-store/queue/token path consumes that result and
   reaches the expected cache/render/terminal state.
3. **User-visible tier** — browser, screenshot, device, or controlled fixture confirms the
   reported symptom is gone.

Policy-tier evidence alone may support a mitigation, but cannot close a user-visible
acceptance criterion. If a higher tier is unavailable, keep the criterion `blocked` and
state the exact substitute boundary.

**Manager re-verify (required):** before PASS, the manager (or evaluator) must **re-run or re-check** the critical command/diff themselves. Copying a worker’s “已完成” or a self-written `VERIFY_OK` string is **not** evidence. For docs, check concrete content (not only heading presence).

**`score_harness` is never product acceptance.** It only rates plan/harness quality. Synthesis “aligned” requires filled contracts + human-meaningful rules; a high score alone does not finish the user task.

**Accept rules must be semantic when risk matters:** prefer “contains concrete policy defaults (retry/timeout numbers)” over substring-only `## Policy` checks that hollow text can pass.

**Stop** (do not thrash): scope explosion; same failure twice without new diagnosis; destructive/prod/paid ops; ownership clash; missing env; budget blown. Record `stop_reason` + decision needed. After synthesis passes, clear stale `blocked_until_synthesis` on ready impl tasks.

**High-impact** (prod data, publish, permissions): stop for confirmation — not a multi-agent trigger by itself.

## 6. Token discipline (smart, not cheap)

| Do | Don't |
|----|--------|
| Decide density in ≤10 lines of thought | Paste full Full-harness templates into chat |
| **Direct:** this file only (0 extra refs unless blocked) | Read all of `references/` for a typo |
| Load **one** reference when blocked | Load every adapter + eval_cases by default |
| Keep Full state on disk; chat = status | Dump entire `run_state` into every message |
| One alignment question with recommended default | Interrogate the user for a perfect brief |
| Score harness only when judging plan quality | Equate high `score_harness` with product done |
| After Full `init_run`, fill or delete empty skeletons | Leave blank `progress`/template shells that drag integrity |

```bash
# Optional: score a Full artifact dir (plan quality ≠ product success)
python3 <skill-dir>/scripts/score_harness.py --fixture <artifact-dir> --pretty
```

## 7. Progressive reference load

| Situation | Read |
|-----------|------|
| Fuzzy / fake-success design | `references/spec-synthesis.md` |
| Density edge cases | `references/proportionality.md` |
| TDD / RED-GREEN chronology | `references/tdd-gates.md` |
| Roles manager/worker/evaluator/state witness | `references/roles.md` |
| Stateful/UI/async bug or policy gate | `references/state-witness.md` |
| Stop / rollback detail | `references/stop-conditions.md` |
| Bugfix vs feature lane | `references/bugfix-lane.md` / `feature-spec-lane.md` |
| Protocol depth | `references/harness-protocol.md` |
| Codex / Claude specifics | `adapters/codex.md` / `adapters/claude-code.md` |
| Universal runtime notes | `adapters/universal.md` |
| Cost/model routing | `references/model-routing.md` + runtime adapter |
| Eval / regression of this skill | `references/eval_cases.md` |

**Default:** this file + maybe one reference. That is enough for most runs.

## 8. Manager handoff shape (end of turn)

- Mode used (Direct / Lite / Full) + why (one line)
- What changed / evidence
- Residual risk + next step
If Full: point to artifact paths, not paste everything.

---

*Agent Reliability Harness v7.2.0 | 2026-07-15*
