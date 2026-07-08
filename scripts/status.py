#!/usr/bin/env python3
"""Print a compact human-readable status summary from run_state.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_state(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"run state root must be an object: {path}")
    return data


def task_blockers(tasks: list[object]) -> list[str]:
    blockers: list[str] = []
    for item in tasks:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if status in {"blocked", "verify_failed"}:
            task_id = item.get("id", "?")
            name = item.get("name", "")
            reason = item.get("stop_reason") or "no stop reason recorded"
            blockers.append(f"{task_id} {name}: {reason}")
    return blockers


def format_status(data: dict[str, object]) -> str:
    title = str(data.get("title") or "untitled")
    mode = str(data.get("mode") or "full")
    status = str(data.get("status") or "unknown")
    lines = [f"Run: {title} | Mode: {mode} | Status: {status}"]

    current_stage = str(data.get("current_stage") or "")
    stages = data.get("stages")
    if isinstance(stages, list):
        for item in stages:
            if not isinstance(item, dict):
                continue
            stage_id = str(item.get("id") or "?")
            prefix = "Stage"
            if current_stage and stage_id == current_stage:
                prefix = "Stage"
            lines.append(f"{prefix} {stage_id}: {item.get('name', '')} [{item.get('status', 'unknown')}]")

    tasks = data.get("tasks")
    if isinstance(tasks, list):
        for item in tasks:
            if not isinstance(item, dict):
                continue
            lines.append(f"  {item.get('id', '?')} {item.get('name', '')} {item.get('status', 'unknown')}")
    else:
        tasks = []

    blockers = task_blockers(tasks)
    lines.append("Blockers: " + ("; ".join(blockers) if blockers else "none"))

    state_layers = data.get("state_layers")
    if isinstance(state_layers, dict):
        memory_boundary = state_layers.get("memory_boundary")
        if isinstance(memory_boundary, dict):
            candidates = memory_boundary.get("memory_candidates")
            if isinstance(candidates, list):
                lines.append(f"Memory candidates: {len(candidates)}")

    generated_files = data.get("generated_files")
    if isinstance(generated_files, list):
        lines.append("Generated files: " + ", ".join(str(item) for item in generated_files))

    stop_reason = data.get("stop_reason")
    if stop_reason:
        lines.append(f"Stop reason: {stop_reason}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a compact run status from run_state.json.")
    parser.add_argument("path", type=Path, help="Path to run_state.json")
    args = parser.parse_args()

    data = load_state(args.path.expanduser().resolve())
    print(format_status(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
