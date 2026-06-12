#!/usr/bin/env python3
"""Initialize a multi-agent run artifact directory."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from datetime import datetime, timezone


TEMPLATE_MAP = {
    "task_spec.md": "task_spec.md",
    "progress_ledger.md": "progress.md",
    "evaluator_report.md": "evaluator_report.md",
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a multi-agent artifact directory from templates.")
    parser.add_argument("--project-root", default=".", help="Project root where workspace/<slug> will be created.")
    parser.add_argument("--slug", help="Stable task slug. Derived from --title when omitted.")
    parser.add_argument("--title", default="multi-agent-task", help="Human-readable task title.")
    parser.add_argument("--agents", default="", help="Comma-separated agent task names, e.g. frontend,backend,tests.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing generated files.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    slug = slugify(args.slug or args.title)
    artifact_dir = project_root / "workspace" / slug
    template_dir = Path(__file__).resolve().parents[1] / "templates"

    created = []
    skipped = []

    for template_name, output_name in TEMPLATE_MAP.items():
        output_path = artifact_dir / output_name
        if copy_template(template_dir, template_name, output_path, args.force):
            created.append(output_path)
        else:
            skipped.append(output_path)

    agents = [slugify(item) for item in args.agents.split(",") if item.strip()]
    for index, agent in enumerate(agents, start=1):
        output_path = artifact_dir / "tasks" / f"1.{index}-{agent}.md"
        if write_task_from_template(template_dir, output_path, agent, index, args.force):
            created.append(output_path)
        else:
            skipped.append(output_path)

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    task_items = [
        {
            "id": f"1.{index}",
            "name": agent,
            "stage": 1,
            "status": "planned",
            "owner": agent,
            "allowed_scope": [],
            "task_path": f"tasks/1.{index}-{agent}.md",
            "report_path": f"1.{index}-{agent}-report.md",
            "dependencies": [],
            "expected_outputs": [],
            "verification": [],
            "verification_gate": default_verification_gate(),
            "retry_count": 0,
            "budget": "",
            "evidence": [],
            "stop_reason": "",
        }
        for index, agent in enumerate(agents, start=1)
    ]
    stage_items = [
        {
            "id": "1",
            "name": "initial execution",
            "status": "planned" if task_items else "unplanned",
            "tasks": [item["id"] for item in task_items],
            "budget": "",
            "evidence": [],
            "stop_reason": "",
        }
    ]

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
    generated_files.extend(item["task_path"] for item in task_items)

    protocol_files = {
        "capability_snapshot.md": (
            "# Capability Snapshot\n\n"
            f"- created_at: {now}\n"
            f"- title: {args.title}\n"
            "- delegation_mechanism:\n"
            "- available_tools:\n"
            "- unavailable_tools:\n"
            "- constraints:\n"
            "- verification_environment:\n"
        ),
        "acceptance_registry.json": {
            "version": 1,
            "created_at": now,
            "title": args.title,
            "tdd_trace_path": "tdd_trace.jsonl",
            "criteria": [
                {
                    "id": "AC-001",
                    "description": "",
                    "status": "pending",
                    "required_evidence": [],
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
            },
            ensure_ascii=False,
        )
        + "\n",
        "tdd_trace.jsonl": "",
        "run_state.json": {
            "version": 1,
            "created_at": now,
            "updated_at": now,
            "title": args.title,
            "artifact_dir": str(artifact_dir),
            "trace_path": "trace.jsonl",
            "tdd_trace_path": "tdd_trace.jsonl",
            "tdd_current_cycle_context": default_tdd_cycle_context(),
            "status": "intake",
            "current_stage": "1" if stage_items else "",
            "stages": stage_items,
            "tasks": task_items,
            "generated_files": generated_files,
            "stop_reason": "",
        },
    }

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
