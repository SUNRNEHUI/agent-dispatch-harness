#!/usr/bin/env python3
"""Initialize a multi-agent run artifact directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from datetime import datetime, timezone

from harness_schema import (
    CONTINUATION_PROTOCOL,
    EVIDENCE_POLICY,
    MODEL_ROUTING_POLICY,
    SCHEMA_VERSION,
    VERIFICATION_TIERS,
)


TEMPLATE_MAP = {
    "task_spec.md": "task_spec.md",
    "progress_ledger.md": "progress.md",
    "evaluator_report.md": "evaluator_report.md",
}

LITE_TEMPLATE_MAP = {
    "lite_plan.md": "lite_plan.md",
}


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    value = value.strip("-")
    return value or "multi-agent-task"


def copy_template(template_dir: Path, template_name: str, output_path: Path, force: bool) -> bool:
    if output_path.exists() and not force:
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template_dir / template_name, output_path)
    return True


def write_task_from_template(template_dir: Path, output_path: Path, agent: str, index: int, force: bool) -> bool:
    if output_path.exists() and not force:
        return False
    content = (template_dir / "subagent_task.md").read_text(encoding="utf-8")
    content = content.replace("任务 X.Y: <任务名>", f"任务 1.{index}: {agent}")
    content = content.replace("<artifact-dir>", str(output_path.parent.parent))
    content = content.replace("X.Y-报告.md", f"1.{index}-{agent}-report.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return True


def write_json(path: Path, data: object, force: bool) -> bool:
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def write_text(path: Path, content: str, force: bool) -> bool:
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def default_verification_gate() -> dict[str, str]:
    return {
        "mode": "not_applicable",
        "tdd_trace_path": "",
        "red_command": "",
        "red_result": "",
        "red_failure_reason": "",
        "green_command": "",
        "green_result": "",
        "refactor_check": "",
        "substitute_check": "",
        "no_test_reason": "",
    }


def default_tdd_cycle_context() -> dict[str, object]:
    return {
        "task_id": "",
        "gate_mode": "",
        "phase": "",
        "command": "",
        "result": "",
        "exit_code": None,
        "trace_path": "tdd_trace.jsonl",
        "stdout_tail": "",
        "stderr_tail": "",
        "retry_count": 0,
        "max_retries": 3,
        "updated_at": "",
    }


def default_state_witness(required: bool, tier: str) -> dict[str, object]:
    return {
        "required": required,
        "path": "state_witness.md" if required else "",
        "required_tier": tier if required else "policy",
        "observed_tier": "",
        "review_status": "pending" if required else "not_required",
        "reviewer_id": "",
        "review_evidence": [],
        "sealed_digest": "",
        "reviewed_at": "",
    }


def default_continuation(
    tasks: list[dict[str, object]],
    *,
    project_root: Path,
    created_at: str,
) -> dict[str, object]:
    first = next(
        (task for task in tasks if task.get("status") in {"ready", "planned"}),
        None,
    )
    task_id = str(first.get("id") or "") if first else ""
    task_name = str(first.get("name") or "") if first else ""
    task_path = str(first.get("task_path") or "") if first else ""
    next_action = (
        f"Read {task_path} and complete task {task_id}: {task_name}"
        if task_id and task_path
        else "Inspect task_spec.md and define the next ready task"
    )
    return {
        "protocol": CONTINUATION_PROTOCOL,
        "status": "unclaimed",
        "owner": {
            "actor_id": "",
            "runtime": "",
            "epoch": 0,
            "claimed_at": "",
        },
        "previous_owner": {},
        "takeover_count": 0,
        "checkpoint": {
            "id": "",
            "sequence": 0,
            "checkpointed_at": created_at,
            "actor_id": "",
            "runtime": "",
            "reason": "run initialized",
            "current_task": task_id,
            "next_action": next_action,
            "pending_verification": [],
            "repository": {
                "root": str(project_root),
                "cwd": str(project_root),
                "branch": "",
                "head": "",
                "dirty_paths": [],
                "dirty_entries": {},
                "worktree_digest": "",
            },
        },
        "last_resume": {
            "resumed_at": "",
            "actor_id": "",
            "runtime": "",
            "takeover_reason": "",
            "forced": False,
        },
    }


def default_state_layers(mode: str = "full", state_witness_required: bool = False) -> dict[str, object]:
    if mode == "lite":
        return {
            "working_state": {
                "current_stage": "1",
                "current_task": "",
                "active_blockers": [],
                "updated_at": "",
            },
            "memory_boundary": {
                "policy": "Do not write cross-task memory into run artifacts by default.",
                "memory_candidates": [],
                "promotion_required": "user_approval_or_project_doc_update",
            },
        }

    artifact_paths = {
        "task_spec": "task_spec.md",
        "progress": "progress.md",
        "acceptance_registry": "acceptance_registry.json",
        "trace": "trace.jsonl",
        "tdd_trace": "tdd_trace.jsonl",
    }
    if state_witness_required:
        artifact_paths["state_witness"] = "state_witness.md"

    return {
        "working_state": {
            "current_stage": "1",
            "current_task": "",
            "active_blockers": [],
            "volatile_notes": [],
            "updated_at": "",
        },
        "session_state": {
            "shared_decisions": [],
            "shared_assumptions": [],
            "artifact_paths": artifact_paths,
            "delegation_state": [],
        },
        "execution_log": {
            "trace_path": "trace.jsonl",
            "tdd_trace_path": "tdd_trace.jsonl",
            "append_only": True,
        },
        "memory_boundary": {
            "policy": "Do not write cross-task memory into run artifacts by default.",
            "memory_candidates": [],
            "promotion_required": "user_approval_or_project_doc_update",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a multi-agent artifact directory from templates.")
    parser.add_argument("--project-root", default=".", help="Project root where workspace/<slug> will be created.")
    parser.add_argument("--slug", help="Stable task slug. Derived from --title when omitted.")
    parser.add_argument("--title", default="multi-agent-task", help="Human-readable task title.")
    parser.add_argument("--agents", default="", help="Comma-separated agent task names, e.g. frontend,backend,tests.")
    parser.add_argument("--mode", choices=("direct", "lite", "full"), default="full", help="Artifact mode to initialize.")
    parser.add_argument(
        "--with-synthesis",
        action="store_true",
        help="Seed Spec Synthesis checklist, stage 0.1 task, and ALIGNMENT.md (full mode only).",
    )
    parser.add_argument(
        "--with-state-witness",
        action="store_true",
        help="Require a Production State Witness before dispatch and protected acceptance.",
    )
    parser.add_argument(
        "--required-verification-tier",
        choices=VERIFICATION_TIERS,
        default="flow",
        help="Minimum evidence tier required for a stateful run.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing generated files.")
    args = parser.parse_args()

    if args.mode == "direct":
        print("Direct mode does not need orchestration artifacts.")
        return 0

    if args.with_synthesis and args.mode != "full":
        raise SystemExit("--with-synthesis is only valid with --mode full")

    project_root = Path(args.project_root).resolve()
    slug = slugify(args.slug or args.title)
    artifact_dir = project_root / "workspace" / slug
    template_dir = Path(__file__).resolve().parents[1] / "templates"

    created = []
    skipped = []

    template_map = dict(LITE_TEMPLATE_MAP if args.mode == "lite" else TEMPLATE_MAP)
    if args.with_state_witness:
        template_map["state_witness.md"] = "state_witness.md"
    for template_name, output_name in template_map.items():
        output_path = artifact_dir / output_name
        if copy_template(template_dir, template_name, output_path, args.force):
            created.append(output_path)
        else:
            skipped.append(output_path)

    agents = [slugify(item) for item in args.agents.split(",") if item.strip()]
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    task_items: list[dict[str, object]] = []
    stage_items: list[dict[str, object]] = []

    if args.mode == "full" and args.with_synthesis:
        synth_task_path = artifact_dir / "tasks" / "0.1-spec-synthesis.md"
        synth_body = (
            "# Task 0.1: Spec Synthesis\n\n"
            "## Goal\n\n"
            "Compile fuzzy intent into rewritten success, fake-success list, constraints,\n"
            "pass_algorithm acceptance, risk-ordered phases, and ALIGNMENT packet.\n\n"
            "## Dependencies\n\n"
            "None.\n\n"
            "## Allowed Scope\n\n"
            "- task_spec.md\n"
            "- ALIGNMENT.md\n"
            "- acceptance_registry.json\n"
            "- run_state.json synthesis fields\n"
            "- tasks/* contracts for later stages (define only)\n\n"
            "## Testing Gate / Verification\n\n"
            "- Gate mode: not_applicable (planning)\n"
            "- Substitute: score_harness.py on this artifact dir after fill\n\n"
            "## PASS\n\n"
            "Synthesis checklist all true or waived with recorded override;\n"
            "acceptance items have pass_algorithm or TBD+measurement; first ready task is narrow.\n\n"
            "## Stop\n\n"
            "Cannot define terminal success without user decision on open questions.\n"
        )
        if write_text(synth_task_path, synth_body, args.force):
            created.append(synth_task_path)
        else:
            skipped.append(synth_task_path)
        task_items.append(
            {
                "id": "0.1",
                "name": "spec-synthesis",
                "stage": 0,
                "status": "ready",
                "owner": "manager",
                "allowed_scope": [
                    "task_spec.md",
                    "ALIGNMENT.md",
                    "acceptance_registry.json",
                    "run_state.json",
                    "tasks/*",
                ],
                "task_path": "tasks/0.1-spec-synthesis.md",
                "report_path": "reports/0.1-spec-synthesis.md",
                "dependencies": [],
                "expected_outputs": ["ALIGNMENT.md", "filled task_spec", "pass_algorithm criteria"],
                "verification": ["score_harness optional", "checklist complete"],
                "verification_gate": default_verification_gate(),
                "retry_count": 0,
                "budget": "",
                "runtime_budget_seconds": 1800,
                "required_cwd": "",
                "repository_root": "",
                "required_branch": "",
                "evidence": [],
                "stop_reason": "",
            }
        )
        stage_items.append(
            {
                "id": "0",
                "name": "spec-synthesis-or-measurement",
                "status": "ready",
                "tasks": ["0.1"],
                "budget": "",
                "evidence": [],
                "stop_reason": "",
            }
        )

    if args.mode == "full":
        for index, agent in enumerate(agents, start=1):
            output_path = artifact_dir / "tasks" / f"1.{index}-{agent}.md"
            if write_task_from_template(template_dir, output_path, agent, index, args.force):
                created.append(output_path)
            else:
                skipped.append(output_path)

    impl_tasks = [
        {
            "id": f"1.{index}",
            "name": agent,
            "stage": 1,
            "status": "planned",
            "owner": agent,
            "allowed_scope": [],
            "task_path": f"tasks/1.{index}-{agent}.md" if args.mode == "full" else "",
            "report_path": f"1.{index}-{agent}-report.md" if args.mode == "full" else "",
            "dependencies": ["0.1"] if args.with_synthesis else [],
            "expected_outputs": [],
            "verification": [],
            "verification_gate": default_verification_gate(),
            "retry_count": 0,
            "budget": "",
            "runtime_budget_seconds": 1800,
            "required_cwd": "",
            "repository_root": "",
            "required_branch": "",
            "evidence": [],
            "stop_reason": "blocked_until_synthesis" if args.with_synthesis else "",
        }
        for index, agent in enumerate(agents, start=1)
    ]
    task_items.extend(impl_tasks)
    stage_items.append(
        {
            "id": "1",
            "name": "initial execution",
            "status": "planned" if impl_tasks else "unplanned",
            "tasks": [item["id"] for item in impl_tasks],
            "budget": "",
            "evidence": [],
            "stop_reason": "",
        }
    )

    if args.mode == "lite":
        generated_files = [
            "lite_plan.md",
            "run_state.json",
        ]
    else:
        generated_files = [
            "task_spec.md",
            "progress.md",
            "evaluator_report.md",
            "capability_snapshot.md",
            "acceptance_registry.json",
            "trace.jsonl",
            "tdd_trace.jsonl",
            "run_state.json",
        ]
        if args.with_synthesis:
            generated_files.append("ALIGNMENT.md")
    if args.with_state_witness:
        generated_files.append("state_witness.md")
    generated_files.extend(item["task_path"] for item in task_items if item.get("task_path"))

    current_stage = "0" if args.with_synthesis else ("1" if impl_tasks else "")

    if args.mode == "lite":
        protocol_files = {
            "run_state.json": {
                "version": SCHEMA_VERSION,
                "created_at": now,
                "updated_at": now,
                "title": args.title,
                "mode": "lite",
                "artifact_dir": str(artifact_dir),
                "state_layers": default_state_layers(mode="lite"),
                "state_witness": default_state_witness(True, args.required_verification_tier)
                if args.with_state_witness
                else default_state_witness(False, args.required_verification_tier),
                "status": "intake",
                "current_stage": "1" if impl_tasks else "",
                "stages": stage_items,
                "tasks": task_items,
                "generated_files": generated_files,
                "stop_reason": "",
            },
        }
    else:
        full_state_layers = default_state_layers(
            mode="full",
            state_witness_required=args.with_state_witness,
        )
        if args.with_synthesis:
            full_state_layers["working_state"]["current_stage"] = "0"
            full_state_layers["session_state"]["document_priority"] = [
                "task_spec.md",
                "acceptance_registry.json",
                "run_state.json",
                "tasks/*",
                "review prose",
            ]

        protocol_files = {
            "capability_snapshot.md": (
                "# Capability Snapshot\n\n"
                f"- created_at: {now}\n"
                f"- title: {args.title}\n"
                "- delegation_mechanism:\n"
                "- runtime_identity:\n"
                "- per_agent_model_selection:\n"
                "- available_model_profiles:\n"
                "- model_routing_fallback:\n"
                "- available_tools:\n"
                "- unavailable_tools:\n"
                "- constraints:\n"
                "- verification_environment:\n"
                "- state_layers:\n"
                "  - working_state: current stage/task only\n"
                "  - session_state: run-scoped shared decisions and assumptions\n"
                "  - execution_log: append-only trace files\n"
                "  - memory_boundary: candidates only; no automatic memory promotion\n"
            ),
            "acceptance_registry.json": {
                "version": SCHEMA_VERSION,
                "evidence_policy": EVIDENCE_POLICY,
                "created_at": now,
                "title": args.title,
                "tdd_trace_path": "tdd_trace.jsonl",
                "criteria": [
                    {
                        "id": "AC-001",
                        "description": "",
                        "status": "pending",
                        "required_evidence": [],
                        "required_verification_tier": args.required_verification_tier
                        if args.with_state_witness
                        else "policy",
                        "pass_algorithm": "",
                        "evidence": [],
                        "owner": "main-agent",
                        "verification_gate": default_verification_gate(),
                        "linked_tasks": [item["id"] for item in task_items],
                        "blocking_issues": [],
                    }
                ],
            },
            "trace.jsonl": json.dumps(
                {
                    "ts": now,
                    "event": "run_initialized",
                    "artifact_dir": str(artifact_dir),
                    "title": args.title,
                    "agents": agents,
                    "with_synthesis": bool(args.with_synthesis),
                },
                ensure_ascii=False,
            )
            + "\n",
            "tdd_trace.jsonl": "",
            "run_state.json": {
                "version": SCHEMA_VERSION,
                "evidence_policy": EVIDENCE_POLICY,
                "routing_policy": MODEL_ROUTING_POLICY,
                "created_at": now,
                "updated_at": now,
                "title": args.title,
                "mode": "full",
                "artifact_dir": str(artifact_dir),
                "trace_path": "trace.jsonl",
                "tdd_trace_path": "tdd_trace.jsonl",
                "state_layers": full_state_layers,
                "continuation": default_continuation(
                    task_items,
                    project_root=project_root,
                    created_at=now,
                ),
                "state_witness": default_state_witness(
                    args.with_state_witness,
                    args.required_verification_tier,
                ),
                "tdd_current_cycle_context": default_tdd_cycle_context(),
                "status": "intake",
                "current_stage": current_stage,
                "synthesis": {
                    "status": "required" if args.with_synthesis else "not_started",
                    "fuzzy_goal": bool(args.with_synthesis),
                    "alignment_packet_path": "ALIGNMENT.md" if args.with_synthesis else "",
                    "checklist": {
                        "rewritten_goal": False,
                        "fake_success_list": False,
                        "constraints_nongoals": False,
                        "pass_algorithms": False,
                        "risk_ordered_phases": False,
                        "first_ready_task": False,
                        "stop_conditions": False,
                    },
                    "recommended_defaults": [],
                    "open_questions": [],
                },
                "stages": stage_items,
                "tasks": task_items,
                "generated_files": generated_files,
                "stop_reason": "",
            },
        }

    if args.mode == "full":
        trace_event = json.loads(str(protocol_files["trace.jsonl"]))
        trace_event["state_digests"] = {
            filename: hashlib.sha256(
                (json.dumps(protocol_files[filename], ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            ).hexdigest()
            for filename in ("run_state.json", "acceptance_registry.json")
        }
        protocol_files["trace.jsonl"] = json.dumps(trace_event, ensure_ascii=False) + "\n"

    for output_name, content in protocol_files.items():
        output_path = artifact_dir / output_name
        if isinstance(content, str):
            did_write = write_text(output_path, content, args.force)
        else:
            did_write = write_json(output_path, content, args.force)
        if did_write:
            created.append(output_path)
        else:
            skipped.append(output_path)

    if args.mode == "full" and args.with_synthesis:
        alignment = (
            "# Alignment Packet\n\n"
            f"- title: {args.title}\n"
            f"- created_at: {now}\n\n"
            "## 1) Rewritten success (≤3 lines)\n\n"
            "## 2) Fake-success list\n\n"
            "1.\n2.\n3.\n\n"
            "## 3) Default constraints / non-goals\n\n"
            "## 4) Acceptance rules or Phase 0 measurement plan\n\n"
            "## 5) Phase map + first ready task\n\n"
            "## 6) Open decisions (with recommended defaults)\n\n"
            "See references/spec-synthesis.md in agent-reliability-harness.\n"
        )
        alignment_path = artifact_dir / "ALIGNMENT.md"
        if write_text(alignment_path, alignment, args.force):
            created.append(alignment_path)
        else:
            skipped.append(alignment_path)

    print(f"artifact_dir={artifact_dir}")
    if created:
        print("created:")
        for path in created:
            print(f"- {path}")
    if skipped:
        print("skipped_existing:")
        for path in skipped:
            print(f"- {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
