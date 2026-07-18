# Grok Runtime Adapter

Maps the harness protocol onto Grok Build / Grok API sessions. Prefer `SKILL.md` density
rules and `adapters/universal.md` first; this file is Grok-specific control points only.

## Automatic Full Run Entry

When the user opens Grok to continue work from Codex, do not request the old chat or an
artifact path. Before edits, run from the project root:

```bash
python3 <skill-dir>/scripts/harnessctl.py resume . \
  --runtime grok --actor-id <unique-grok-session-id> \
  --takeover-reason "previous Codex session interrupted"
```

The command auto-discovers the unique active Full run, recovers and validates it, fences the
old owner, and emits the required reads, next action, blockers, owner epoch, and worktree
drift. Read those files and inspect any drift before continuing. Include the returned
`--actor-id` and `--owner-epoch` on every state-changing command.

This entry gate is the seamless boundary the harness can guarantee. It does not import
hidden Codex reasoning, provider-internal sessions, or in-flight external side effects, and
it is initiated when Grok starts rather than by a provider quota callback.

## Mode Selection Gate

Skill load ≠ dispatch. If the user says multi-agent for a tiny edit, complete it Direct.
Do not spawn subagents or init Full artifacts unless density rules fire.

Model routing never authorizes delegation. Density first, then profile selection.

## Cost-Aware Model Profiles

Portable profiles resolve to **local Grok config slugs** (the names under `[model.*]` /
`spawn_subagent --model`), not marketing strings alone.

**Default on this install (only 4.5 available):** every profile uses `grok-api`
(upstream `grok-4.5`), including sub-agents. Profile still changes reasoning effort.

| Profile | Grok slug | Effort | Use |
|---|---|---|---|
| `fast` | `grok-api` | `low` | simple **and** mechanically verifiable workers |
| `main` | `grok-api` | `high` | default manager / implementation |
| `planner` | `grok-api` | `high` | fuzzy goals, synthesis, architecture |
| `critical_reviewer` | `grok-api` | `xhigh` | high risk, conflict, ≥2 validation failures |

Assumed install pattern:

- `grok-api` / `grok-build` → upstream `grok-4.5`
- No second cheap model required for harness defaults

Deterministic selection:

```bash
python3 <skill-dir>/scripts/model_router.py --runtime grok --simple --mechanically-verifiable
python3 <skill-dir>/scripts/model_router.py --runtime grok --harness-synthesis
python3 <skill-dir>/scripts/model_router.py --runtime grok --validation-failures 2
```

Optional experiment overrides (not sealed defaults):

```bash
export HARNESS_GROK_FAST_MODEL='some-cheaper-slug'
python3 <skill-dir>/scripts/model_router.py --runtime grok --simple --mechanically-verifiable --allow-env-override
```

Only use a second model when it is actually configured and tool-capable. Until then, keep
sub-agents on `grok-api` and vary effort / scope, not model id.

See optional fragment: `references/examples/grok-fast-model-config.toml` (opt-in only).

## Capability Gate

Record before dispatch:

- whether `spawn_subagent` model override is available in this session
- which local slugs appear in the model picker / config
- whether only sequential stages are possible
- sandbox / approval / network limits

If per-worker model selection is unavailable: workers inherit parent (`grok-api` / 4.5).
Record `resolved_model` as the actual model; do not claim a cheaper model ran.

## Sub-Agents And Workers

Grok subagents:

- inherit parent model unless type/role/persona/spawn override applies
- **default requested model is `grok-api` for all profiles** when only 4.5 is configured
- cannot nest further subagents (depth 1)
- should receive self-contained contracts (goal, scope, verify, stop, report path)

Persist every real worker:

```bash
python3 <skill-dir>/scripts/harnessctl.py dispatch-create <artifact-dir> \
  --worker-id <id> --task-id 1.1 \
  --contract-path tasks/1.1-worker.md --report-path 1.1-worker-report.md \
  --runtime grok --profile fast \
  --requested-model grok-api --reasoning-effort low \
  --route-reason "simple mechanically verifiable batch on 4.5"
```

When the runtime exposes the model that actually ran, store it in `resolved_model`.

## Verification

- Manager re-runs critical checks; worker “已完成” is not PASS.
- Policy routing tests are offline and deterministic; live provider catalog listing is optional.
- UI acceptance still needs browser/screenshot tiers when the product is user-visible (N/A for this skill-only routing change).

## Stop / Fallback

- Only one model (4.5) configured → all workers stay on `grok-api`; do not invent `grok-fast`
- Optional cheap alias missing/404 → keep `grok-api`, record fallback reason
- Tiny Direct task → do not spawn a worker just to exercise routing
