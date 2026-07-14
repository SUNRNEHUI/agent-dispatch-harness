# Cost-Aware Model Routing

This reference applies model choice **after** the density decision. A tiny task remains
Direct; starting a cheaper worker for a one-line edit can cost more than finishing it in
the current main thread.

## Codex Default Policy

This repository intentionally does not route through Terra. The configured GPT-5.6
profiles are:

| Profile | Model | Reasoning | Use |
|---|---|---|---|
| `fast` | `gpt-5.6-luna` | `medium` | Simple, mechanically verifiable work; repeated read-only batches |
| `main` | `gpt-5.6-luna` | `xhigh` | High-frequency manager, implementation, integration |
| `planner` | `gpt-5.6-sol` | `high` | Fuzzy intent, architecture, Spec Synthesis, harness design |
| `critical_reviewer` | `gpt-5.6-sol` | `xhigh` | High risk, repeated validation failure, worker conflict |

Run the deterministic selector when the route is not obvious:

```bash
python3 <skill-dir>/scripts/model_router.py --simple --mechanically-verifiable
python3 <skill-dir>/scripts/model_router.py --harness-synthesis
python3 <skill-dir>/scripts/model_router.py --validation-failures 2
```

## Selection Rules

Apply these in order:

1. High risk, worker conflict, or two validation failures → `critical_reviewer`.
2. Fuzzy goal or harness/spec synthesis → `planner`.
3. Simple **and** mechanically verifiable → `fast`.
4. Everything else → `main`.

Do not treat `xhigh` as a replacement for model capability. Luna xhigh is the normal
execution manager because this policy optimizes for the owner's observed value, while
Sol owns open-ended judgment and critical review.

## Dispatch And Audit

Model routing does not authorize delegation. First choose Direct / Direct+ / Lite / Full.
When a real worker is justified, persist the route:

```bash
python3 <skill-dir>/scripts/harnessctl.py dispatch-create <artifact-dir> \
  --worker-id <runtime-id> --task-id 1.1 \
  --contract-path tasks/1.1-worker.md --report-path 1.1-worker-report.md \
  --runtime codex --profile fast \
  --requested-model gpt-5.6-luna --reasoning-effort medium \
  --route-reason "simple mechanically verifiable batch"
```

Record the resolved model separately when the runtime exposes it. A requested model is
not proof that the runtime honored the request.

## Cross-Runtime Rule

The profile names are portable; the model mapping is not. Claude Code, Grok, or another
runtime must define its own adapter mapping and availability checks. If the active runtime
cannot select per-worker models, keep the profile in the trace and use the runtime's safe
fallback rather than claiming a model switch occurred.
