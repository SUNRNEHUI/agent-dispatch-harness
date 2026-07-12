#!/usr/bin/env python3
"""Run a verification command and append wrapper-generated TDD trace evidence."""

from __future__ import annotations

import argparse
import json
import math
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from runtime_state import append_jsonl, atomic_write_json, mutate_json
except ImportError:  # pragma: no cover - supports `import scripts.harness_test_run`
    from .runtime_state import append_jsonl, atomic_write_json, mutate_json


WRAPPER_VERSION = 1
TAIL_LINES = 50


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def tail(text: str | bytes | None, max_lines: int = TAIL_LINES) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])


def append_event(trace_path: Path, event: dict[str, Any]) -> None:
    append_jsonl(trace_path, event, writer_role="manager", scope="global")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        return {}
    return value


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
    timeout_seconds: float | None = None,
) -> None:
    now = utc_now()
    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        prior_context = data.get("tdd_current_cycle_context")
        retry_count = prior_context.get("retry_count", 0) if isinstance(prior_context, dict) and prior_context.get("task_id") == task_id else 0
        if not isinstance(retry_count, int):
            retry_count = 0
        if result == "FAIL": retry_count += 1
        previous_gate_mode = prior_context.get("gate_mode", "") if isinstance(prior_context, dict) else ""
        context = {"task_id": task_id, "gate_mode": gate_mode or previous_gate_mode, "phase": phase, "command": command,
                   "result": result, "exit_code": exit_code, "trace_path": str(trace_path), "stdout_tail": stdout_tail,
                   "stderr_tail": stderr_tail, "retry_count": retry_count,
                   "max_retries": prior_context.get("max_retries", 3) if isinstance(prior_context, dict) else 3, "updated_at": now}
        if timeout_seconds is not None: context["timeout_seconds"] = timeout_seconds
        data["updated_at"] = now
        data["tdd_current_cycle_context"] = context
        return data
    mutate_json(run_state_path, mutate, writer_role="manager", scope="global")


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
    parser.add_argument("--timeout-seconds", "--timeout", dest="timeout_seconds", type=float)
    parser.add_argument("--runtime-budget-seconds", type=float)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after --.")
    args = parser.parse_args()
    args.timeout_explicit = args.timeout_seconds is not None
    args.runtime_budget_explicit = args.runtime_budget_seconds is not None
    args.timeout_seconds = 1800 if args.timeout_seconds is None else args.timeout_seconds
    args.runtime_budget_seconds = 1800 if args.runtime_budget_seconds is None else args.runtime_budget_seconds
    if not math.isfinite(args.timeout_seconds) or not math.isfinite(args.runtime_budget_seconds) or args.timeout_seconds <= 0 or args.runtime_budget_seconds <= 0 or args.timeout_seconds > args.runtime_budget_seconds:
        parser.error("timeout-seconds must be positive and <= runtime-budget-seconds")
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

    if args.run_state:
        try:
            state = json.loads(args.run_state.expanduser().read_text(encoding="utf-8"))
            raw_tasks = state.get("tasks", []) if isinstance(state, dict) else []
            tasks = raw_tasks if isinstance(raw_tasks, list) else []
            task = next((item for item in tasks if isinstance(item, dict) and item.get("id") == args.task_id), None)
            if task is None:
                print(f"error: task id not found in run_state.tasks: {args.task_id}", file=sys.stderr)
                return 2
            if "runtime_budget_seconds" in task:
                budget = task["runtime_budget_seconds"]
                if not isinstance(budget, (int, float)) or isinstance(budget, bool) or not math.isfinite(budget) or budget <= 0:
                    raise ValueError("task runtime_budget_seconds must be a positive finite number")
                if args.runtime_budget_explicit and args.runtime_budget_seconds > budget:
                    print("error: runtime budget cannot exceed task binding", file=sys.stderr)
                    return 2
                if not args.runtime_budget_explicit:
                    args.runtime_budget_seconds = budget
                if not args.timeout_explicit:
                    args.timeout_seconds = budget
                if args.timeout_seconds > budget:
                    print("error: timeout-seconds must be <= task runtime budget", file=sys.stderr)
                    return 2
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

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

    timed_out = False
    try:
        completed = subprocess.run(
            args.command,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            check=False,
            timeout=args.timeout_seconds,
        )
        return_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        return_code = 124
        stdout = exc.stdout
        stderr = exc.stderr
    result = "TIMEOUT" if timed_out else ("PASS" if return_code == 0 else "FAIL")
    stdout_tail = tail(stdout)
    stderr_tail = tail(stderr)

    event_name = "substitute_check" if args.no_test_reason else "test_run"
    event = {
        "ts": utc_now(),
        "event": event_name,
        "task_id": args.task_id,
        "phase": args.phase,
        "command": command_text,
        "result": result,
        "exit_code": return_code,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "summary": args.summary,
        "source": "harness_test_run",
        "wrapper_version": WRAPPER_VERSION,
    }
    if timed_out:
        event["timeout_seconds"] = args.timeout_seconds
    if args.no_test_reason:
        event["no_test_reason"] = args.no_test_reason
    if args.run_state:
        try:
            update_run_state(args.run_state.expanduser(), task_id=args.task_id, gate_mode=args.gate_mode, phase=args.phase,
                             command=command_text, result=result, exit_code=return_code, trace_path=trace_path,
                             stdout_tail=stdout_tail, stderr_tail=stderr_tail,
                             timeout_seconds=args.timeout_seconds if timed_out else None)
        except Exception as exc:
            append_event(trace_path, {"ts": utc_now(), "event": "state_update_failed", "task_id": args.task_id,
                                      "result": "ERROR", "error": str(exc), "source": "harness_test_run", "wrapper_version": WRAPPER_VERSION})
            return 1
    append_event(trace_path, event)

    def output_text(value: str | bytes) -> str:
        return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value

    if stdout:
        sys.stdout.write(output_text(stdout))
    if stderr:
        sys.stderr.write(output_text(stderr))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
