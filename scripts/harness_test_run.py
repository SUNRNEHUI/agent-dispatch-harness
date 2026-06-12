#!/usr/bin/env python3
"""Run a verification command and append wrapper-generated TDD trace evidence."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WRAPPER_VERSION = 1
TAIL_LINES = 50


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def tail(text: str, max_lines: int = TAIL_LINES) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])


def append_event(trace_path: Path, event: dict[str, Any]) -> None:
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        return {}
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_run_state(
    run_state_path: Path,
    *,
    task_id: str,
    gate_mode: str,
    phase: str,
    command: str,
    result: str,
    exit_code: int,
    trace_path: Path,
    stdout_tail: str,
    stderr_tail: str,
) -> None:
    data = read_json(run_state_path)
    now = utc_now()
    prior_context = data.get("tdd_current_cycle_context")
    retry_count = 0
    if isinstance(prior_context, dict) and prior_context.get("task_id") == task_id:
        previous_retry_count = prior_context.get("retry_count", 0)
        if isinstance(previous_retry_count, int):
            retry_count = previous_retry_count
    if result == "FAIL":
        retry_count += 1

    previous_gate_mode = prior_context.get("gate_mode", "") if isinstance(prior_context, dict) else ""
    data["updated_at"] = now
    data["tdd_current_cycle_context"] = {
        "task_id": task_id,
        "gate_mode": gate_mode or previous_gate_mode,
        "phase": phase,
        "command": command,
        "result": result,
        "exit_code": exit_code,
        "trace_path": str(trace_path),
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "retry_count": retry_count,
        "max_retries": prior_context.get("max_retries", 3) if isinstance(prior_context, dict) else 3,
        "updated_at": now,
    }
    write_json(run_state_path, data)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a test/check command and append wrapper-generated TDD trace evidence."
    )
    parser.add_argument("--trace", required=True, type=Path, help="Path to tdd_trace.jsonl.")
    parser.add_argument("--task-id", required=True, help="Task or cycle id.")
    parser.add_argument("--phase", required=True, help="RED, GREEN, REFACTOR, GAP, or another verification phase.")
    parser.add_argument("--gate-mode", default="", help="Optional gate mode to record before the test run.")
    parser.add_argument("--reason", default="", help="Reason for the gate decision when --gate-mode is set.")
    parser.add_argument("--summary", default="", help="Optional human summary for the test_run event.")
    parser.add_argument("--cwd", type=Path, help="Working directory for the command.")
    parser.add_argument("--run-state", type=Path, help="Optional run_state.json to update with current TDD context.")
    parser.add_argument("--no-test-reason", default="", help="Reason used when recording substitute verification.")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after --.")
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("command is required after --")
    return args


def main() -> int:
    args = parse_args()
    command_text = shlex.join(args.command)
    trace_path = args.trace.expanduser()
    cwd = args.cwd.expanduser() if args.cwd else None

    if args.gate_mode:
        append_event(
            trace_path,
            {
                "ts": utc_now(),
                "event": "gate_decision",
                "task_id": args.task_id,
                "gate_mode": args.gate_mode,
                "reason": args.reason,
                "source": "harness_test_run",
                "wrapper_version": WRAPPER_VERSION,
            },
        )

    completed = subprocess.run(
        args.command,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )
    result = "PASS" if completed.returncode == 0 else "FAIL"
    stdout_tail = tail(completed.stdout)
    stderr_tail = tail(completed.stderr)

    event_name = "substitute_check" if args.no_test_reason else "test_run"
    event = {
        "ts": utc_now(),
        "event": event_name,
        "task_id": args.task_id,
        "phase": args.phase,
        "command": command_text,
        "result": result,
        "exit_code": completed.returncode,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "summary": args.summary,
        "source": "harness_test_run",
        "wrapper_version": WRAPPER_VERSION,
    }
    if args.no_test_reason:
        event["no_test_reason"] = args.no_test_reason
    append_event(trace_path, event)

    if args.run_state:
        update_run_state(
            args.run_state.expanduser(),
            task_id=args.task_id,
            gate_mode=args.gate_mode,
            phase=args.phase,
            command=command_text,
            result=result,
            exit_code=completed.returncode,
            trace_path=trace_path,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
        )

    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
