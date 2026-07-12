#!/usr/bin/env python3
"""Validate a task's cwd, repository root, and branch binding."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


def git_value(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def validate_workspace_binding(task: dict[str, Any], *, observed_cwd: str | Path | None = None) -> list[str]:
    errors: list[str] = []
    # Missing fields are allowed for legacy artifacts; present bindings are strict.
    cwd = Path(observed_cwd or Path.cwd()).expanduser().resolve()
    required_cwd = task.get("required_cwd", "")
    if required_cwd and cwd != Path(required_cwd).expanduser().resolve():
        errors.append(f"cwd mismatch: required {required_cwd}, observed {cwd}")
    root_value = git_value(cwd, "rev-parse", "--show-toplevel")
    root = Path(root_value).resolve() if root_value else None
    required_root = task.get("repository_root", "")
    if required_root and (root is None or root != Path(required_root).expanduser().resolve()):
        errors.append(f"repository root mismatch: required {required_root}, observed {root}")
    branch = git_value(cwd, "branch", "--show-current")
    required_branch = task.get("required_branch", "")
    if required_branch and (not branch or branch != required_branch):
        errors.append(f"branch mismatch: required {required_branch}, observed {branch or '<detached>'}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate task workspace identity binding.")
    parser.add_argument("task", type=Path, help="JSON task object or run_state.json")
    workspace_group = parser.add_mutually_exclusive_group(required=True)
    workspace_group.add_argument("--workspace", dest="workspace", help="Manager-provided observed workspace")
    workspace_group.add_argument("--cwd", dest="workspace", help="Deprecated alias for --workspace")
    parser.add_argument("--task-id", help="Task id when input is run_state.json")
    args = parser.parse_args()
    try:
        data = json.loads(args.task.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"invalid task JSON: {exc}")
        return 2
    if isinstance(data, dict) and "tasks" in data:
        if not args.task_id:
            parser.error("--task-id is required for run_state.json")
        tasks = data["tasks"]
        if not isinstance(tasks, list):
            print("task list must be a JSON array")
            return 2
        matches = [task for task in tasks if isinstance(task, dict) and task.get("id") == args.task_id]
        if len(matches) != 1:
            print(f"task id not found or ambiguous: {args.task_id}")
            return 2
        data = matches[0]
    elif isinstance(data, dict) and isinstance(data.get("task_shape"), dict):
        data = data["task_shape"]
    if not isinstance(data, dict):
        print("task must be a JSON object")
        return 2
    errors = validate_workspace_binding(data, observed_cwd=args.workspace)
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1
    print("workspace_binding=verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
