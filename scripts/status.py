#!/usr/bin/env python3
"""Print a compact human-readable status summary from run_state.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DONE_TASK_STATUSES = {"passed", "merged"}
BLOCKING_TASK_STATUSES = {"blocked", "verify_failed"}
ACCEPTANCE_STATUSES = ("pass", "pending", "fail", "blocked", "scoped_out")


def load_state(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"run state root must be an object: {path}")
    return data


def load_acceptance_registry(path: Path) -> tuple[str, dict[str, object] | None]:
    if not path.exists():
        return "missing", None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "unreadable", None
    if not isinstance(data, dict):
        return "unreadable", None
    return "available", data


def task_blockers(tasks: list[object]) -> list[str]:
    blockers: list[str] = []
    for item in tasks:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if status in BLOCKING_TASK_STATUSES:
            task_id = item.get("id", "?")
            name = item.get("name", "")
            reason = item.get("stop_reason") or "no stop reason recorded"
            blockers.append(f"{task_id} {name}: {reason}")
    return blockers


def resource_budget_blockers(items: list[object], scope: str = "task") -> list[str]:
    blockers: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        budget = item.get("resource_budget")
        if not isinstance(budget, dict) or not isinstance(budget.get("token_budget"), int):
            continue
        task_id = item.get("id", "?")
        name = item.get("name", "")
        label = f"{scope} {task_id} {name}".strip()
        usage_kind = budget.get("usage_kind")
        if usage_kind == "unknown":
            blockers.append(f"{label}: token budget accounting unavailable")
            continue
        tokens_used = budget.get("tokens_used")
        tokens_remaining = budget.get("tokens_remaining")
        if (
            isinstance(tokens_used, int)
            and tokens_used >= budget["token_budget"]
        ) or (isinstance(tokens_remaining, int) and tokens_remaining <= 0):
            blockers.append(f"{label}: token budget exhausted")
    return blockers


def task_completion(tasks: list[object]) -> tuple[int, int]:
    total = 0
    done = 0
    for item in tasks:
        if not isinstance(item, dict):
            continue
        total += 1
        if item.get("status") in DONE_TASK_STATUSES:
            done += 1
    return done, total


def task_evidence_gaps(tasks: list[object]) -> list[str]:
    gaps: list[str] = []
    for item in tasks:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if status not in DONE_TASK_STATUSES:
            continue
        evidence = item.get("evidence")
        if isinstance(evidence, list) and evidence:
            continue
        task_id = item.get("id", "?")
        gaps.append(f"task {task_id} {status} without evidence")
    return gaps


def acceptance_rollup(registry: dict[str, object] | None) -> tuple[dict[str, int], list[str], bool]:
    counts = {status: 0 for status in ACCEPTANCE_STATUSES}
    gaps: list[str] = []
    if registry is None:
        return counts, gaps, False

    criteria = registry.get("criteria")
    if not isinstance(criteria, list):
        return counts, ["acceptance registry missing criteria list"], True

    for index, item in enumerate(criteria, start=1):
        if not isinstance(item, dict):
            gaps.append(f"acceptance criteria[{index}] is not an object")
            continue
        status = item.get("status")
        if status in counts:
            counts[str(status)] += 1
        else:
            gaps.append(f"acceptance {item.get('id', index)} has unsupported status {status!r}")
        if status in {"pass", "scoped_out"}:
            evidence = item.get("evidence")
            if isinstance(evidence, list) and evidence:
                continue
            gaps.append(f"acceptance {item.get('id', index)} {status} without evidence")
    return counts, gaps, False


def accepted_state_conflicts(run_status: str, acceptance_counts: dict[str, int], registry_error: bool) -> list[str]:
    if run_status != "accepted":
        return []
    conflicts: list[str] = []
    if registry_error:
        conflicts.append("run_state accepted but acceptance registry is malformed")
    if acceptance_counts["pending"]:
        conflicts.append("run_state accepted but acceptance criteria are pending")
    if acceptance_counts["fail"] or acceptance_counts["blocked"]:
        conflicts.append("run_state accepted but acceptance criteria failed or blocked")
    return conflicts


def confidence_level(
    mode: str,
    registry_status: str,
    acceptance_counts: dict[str, int],
    blockers: list[str],
    conflicts: list[str],
    evidence_gaps: list[str],
    registry_error: bool,
    done: int,
    total: int,
) -> str:
    if blockers or conflicts or registry_error or acceptance_counts["fail"] or acceptance_counts["blocked"]:
        return "blocked"
    if mode == "full" and registry_status != "available":
        return "unknown"
    if acceptance_counts["pending"]:
        return "medium" if done == total and total > 0 else "low"
    if evidence_gaps:
        return "medium" if done == total and total > 0 else "low"
    if total > 0 and done == total:
        return "high"
    return "unknown"


def next_verification(
    mode: str,
    registry_status: str,
    acceptance_counts: dict[str, int],
    blockers: list[str],
    conflicts: list[str],
    evidence_gaps: list[str],
    registry_error: bool,
    done: int,
    total: int,
) -> str:
    if blockers:
        return "resolve blockers"
    if registry_error:
        return "repair acceptance_registry.json"
    if conflicts:
        return "repair accepted run state or acceptance registry"
    if mode == "full" and registry_status == "missing":
        return "create or locate acceptance_registry.json"
    if mode == "full" and registry_status == "unreadable":
        return "repair acceptance_registry.json"
    if acceptance_counts["fail"] or acceptance_counts["blocked"]:
        return "repair failing or blocked acceptance criteria"
    if acceptance_counts["pending"]:
        return "resolve pending acceptance criteria"
    if evidence_gaps:
        return "record missing evidence"
    if total and done < total:
        return "finish remaining tasks"
    return "none"


def status_confidence(data: dict[str, object], state_path: Path) -> str:
    mode = str(data.get("mode") or "full")
    status = str(data.get("status") or "unknown")
    raw_tasks = data.get("tasks")
    tasks = raw_tasks if isinstance(raw_tasks, list) else []
    raw_stages = data.get("stages")
    stages = raw_stages if isinstance(raw_stages, list) else []
    registry_status = "not_applicable"
    registry: dict[str, object] | None = None
    if mode == "full":
        registry_status, registry = load_acceptance_registry(state_path.parent / "acceptance_registry.json")
    acceptance_counts, acceptance_gaps, registry_error = acceptance_rollup(registry)
    blockers = [
        *task_blockers(tasks),
        *resource_budget_blockers(tasks),
        *resource_budget_blockers(stages, "stage"),
    ]
    conflicts = accepted_state_conflicts(status, acceptance_counts, registry_error)
    evidence_gaps = [*task_evidence_gaps(tasks), *acceptance_gaps]
    done, total = task_completion(tasks)
    return confidence_level(
        mode,
        registry_status,
        acceptance_counts,
        blockers,
        conflicts,
        evidence_gaps,
        registry_error,
        done,
        total,
    )


def format_status(data: dict[str, object], state_path: Path | None = None) -> str:
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

    done, total = task_completion(tasks)
    lines.append(f"Completion: {done}/{total} tasks done")

    registry_status = "not_applicable"
    registry: dict[str, object] | None = None
    if state_path is not None and mode == "full":
        registry_status, registry = load_acceptance_registry(state_path.parent / "acceptance_registry.json")
    acceptance_counts, acceptance_gaps, registry_error = acceptance_rollup(registry)
    if mode == "full":
        if registry_status == "available":
            lines.append(
                "Acceptance: "
                f"{acceptance_counts['pass']} pass, "
                f"{acceptance_counts['pending']} pending, "
                f"{acceptance_counts['fail']} fail, "
                f"{acceptance_counts['blocked']} blocked, "
                f"{acceptance_counts['scoped_out']} scoped_out"
            )
        else:
            lines.append(f"Acceptance: {registry_status}")

    stage_items = stages if isinstance(stages, list) else []
    blockers = [
        *task_blockers(tasks),
        *resource_budget_blockers(tasks),
        *resource_budget_blockers(stage_items, "stage"),
    ]
    lines.append("Blockers: " + ("; ".join(blockers) if blockers else "none"))

    conflicts = accepted_state_conflicts(status, acceptance_counts, registry_error)
    if conflicts:
        lines.append("State conflicts: " + "; ".join(conflicts))

    evidence_gaps = [*task_evidence_gaps(tasks), *acceptance_gaps]
    lines.append("Evidence gaps: " + ("; ".join(evidence_gaps) if evidence_gaps else "none"))

    confidence = confidence_level(
        mode,
        registry_status,
        acceptance_counts,
        blockers,
        conflicts,
        evidence_gaps,
        registry_error,
        done,
        total,
    )
    lines.append(f"Completion confidence: {confidence}")
    lines.append(
        "Next verification: "
        + next_verification(
            mode,
            registry_status,
            acceptance_counts,
            blockers,
            conflicts,
            evidence_gaps,
            registry_error,
            done,
            total,
        )
    )

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
    parser.add_argument(
        "--require-high-confidence",
        action="store_true",
        help="Exit nonzero unless the run reaches high completion confidence.",
    )
    args = parser.parse_args()

    path = args.path.expanduser().resolve()
    data = load_state(path)
    print(format_status(data, path))
    if args.require_high_confidence:
        confidence = status_confidence(data, path)
        if confidence != "high":
            print("Status gate: requires high completion confidence")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
