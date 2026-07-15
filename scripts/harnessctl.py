#!/usr/bin/env python3
"""Validate and mutate Full Harness state through guarded, auditable commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from harness_schema import (
    ACCEPTANCE_STATUSES,
    ACCEPTANCE_TRANSITIONS,
    AGENT_PROFILES,
    CODEX_MODEL_PROFILES,
    DISPATCH_STATUSES,
    DISPATCH_TRANSITIONS,
    EVIDENCE_POLICY,
    QUALIFYING_EVIDENCE_TYPES,
    RUN_STATUSES,
    RUN_TRANSITIONS,
    TASK_STATUSES,
    TASK_TRANSITIONS,
    VERIFICATION_TIERS,
)
from runtime_state import append_jsonl, locked, mutate_json
from state_witness_check import validate as validate_state_witness
from validate_report import validate_acceptance_registry, validate_run_state
from tdd_gate_check import gate_mode_of, latest_gate_decision, load_events, validate_trace as validate_tdd_trace


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def serialized_json(value: dict[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def validate_candidate(
    artifact_dir: Path,
    filename: str,
    value: dict[str, object],
    validator: Callable[[Path], list[str]],
) -> None:
    fd, name = tempfile.mkstemp(prefix=f".{filename}.", suffix=".json", dir=str(artifact_dir))
    path = Path(name)
    try:
        with open(fd, "w", encoding="utf-8", closefd=True) as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        errors = validator(path)
    finally:
        path.unlink(missing_ok=True)
    if errors:
        raise ValueError("; ".join(errors))


def append_unique(values: object, additions: list[str]) -> list[str]:
    result = [str(value).strip() for value in values if str(value).strip()] if isinstance(values, list) else []
    for addition in additions:
        normalized = addition.strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def append_unique_values(values: object, additions: list[object]) -> list[object]:
    result = list(values) if isinstance(values, list) else []
    fingerprints = {json.dumps(value, ensure_ascii=False, sort_keys=True) for value in result}
    for addition in additions:
        fingerprint = json.dumps(addition, ensure_ascii=False, sort_keys=True)
        if fingerprint not in fingerprints:
            result.append(addition)
            fingerprints.add(fingerprint)
    return result


def artifact_evidence_path(artifact_dir: Path, value: str) -> tuple[Path, str]:
    candidate = Path(value).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (artifact_dir / candidate).resolve()
    try:
        normalized = resolved.relative_to(artifact_dir).as_posix()
    except ValueError as exc:
        raise ValueError("evidence file must remain inside artifact directory") from exc
    if not resolved.exists() or not resolved.is_file() or resolved.stat().st_size <= 0:
        raise ValueError(f"evidence file must be a non-empty regular file: {normalized}")
    return resolved, normalized


def build_evidence_additions(
    artifact_dir: Path,
    *,
    subject: str,
    freeform: list[str],
    files: list[str],
    transaction_id: str,
    policy: object,
    verification_tier: str = "policy",
) -> list[object]:
    additions: list[object] = []
    for text in freeform:
        normalized = text.strip()
        if not normalized:
            continue
        if policy == EVIDENCE_POLICY:
            additions.append(
                {
                    "id": f"EV-{uuid.uuid4()}",
                    "type": "legacy_text",
                    "source_role": "manager",
                    "subject": subject,
                    "result": "info",
                    "payload": {"text": normalized},
                    "verification": {
                        "status": "unverified",
                        "method": "legacy_cli_text",
                        "verified_by": "",
                        "verified_at": "",
                        "transaction_id": transaction_id,
                    },
                }
            )
        else:
            additions.append(normalized)
    for value in files:
        path, normalized = artifact_evidence_path(artifact_dir, value)
        additions.append(
            {
                "id": f"EV-{uuid.uuid4()}",
                "type": "artifact_digest",
                "source_role": "manager",
                "subject": subject,
                "result": "pass",
                "verification_tier": verification_tier,
                "payload": {
                    "path": normalized,
                    "sha256": sha256(path.read_bytes()),
                    "size_bytes": path.stat().st_size,
                },
                "verification": {
                    "status": "verified",
                    "method": "hashed_by_harnessctl",
                    "verified_by": "harnessctl",
                    "verified_at": utc_now(),
                    "transaction_id": transaction_id,
                },
            }
        )
    return additions


def qualifying_evidence(
    values: list[object], subject: str, minimum_tier: str = "policy"
) -> list[dict[str, object]]:
    if minimum_tier not in VERIFICATION_TIERS:
        return []
    return [
        value for value in values
        if isinstance(value, dict)
        and value.get("type") in QUALIFYING_EVIDENCE_TYPES
        and value.get("subject") == subject
        and value.get("result") == "pass"
        and isinstance(value.get("verification"), dict)
        and value["verification"].get("status") == "verified"
        and value.get("verification_tier", "policy") in VERIFICATION_TIERS
        and VERIFICATION_TIERS.index(value.get("verification_tier", "policy"))
        >= VERIFICATION_TIERS.index(minimum_tier)
    ]


def reject_self_report(values: list[str]) -> None:
    pattern = re.compile(r"self[- ]?report|worker\s+says|worker.*done|自报|自称完成", re.IGNORECASE)
    if any(pattern.search(value) for value in values):
        raise ValueError("worker self-report cannot satisfy protected evidence")


def find_unique(items: object, item_id: str, label: str, *, key: str = "id") -> dict[str, object]:
    if not isinstance(items, list):
        raise ValueError(f"{label} list is missing")
    matches = [item for item in items if isinstance(item, dict) and item.get(key) == item_id]
    if len(matches) != 1:
        raise ValueError(f"{label} id not found or ambiguous: {item_id}")
    return matches[0]


def resolve_artifact_path(artifact_dir: Path, value: str, label: str, *, must_exist: bool) -> tuple[Path, str]:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label} must be a safe artifact-relative path")
    resolved = (artifact_dir / relative).resolve()
    try:
        normalized = resolved.relative_to(artifact_dir).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} escapes artifact directory") from exc
    if must_exist and (not resolved.exists() or not resolved.is_file()):
        raise ValueError(f"{label} must reference an existing file: {normalized}")
    return resolved, normalized


def state_witness_gate(
    artifact_dir: Path,
    state: dict[str, object],
    *,
    require_review: bool,
) -> list[str]:
    record = state.get("state_witness")
    if not isinstance(record, dict) or not record.get("required"):
        return []

    path_value = str(record.get("path") or "")
    try:
        witness_path, _ = resolve_artifact_path(artifact_dir, path_value, "state witness path", must_exist=True)
    except ValueError as exc:
        return [str(exc)]
    errors = validate_state_witness(witness_path, True)
    sealed_digest = str(record.get("sealed_digest") or "")
    if sealed_digest and sha256(witness_path.read_bytes()) != sealed_digest:
        errors.append("state witness changed after seal")
    if not require_review:
        return errors

    if record.get("review_status") != "pass":
        errors.append("state witness adversarial review must be pass")
    if not str(record.get("reviewer_id") or "").strip():
        errors.append("state witness reviewer_id must be recorded")
    required_tier = str(record.get("required_tier") or "policy")
    observed_tier = str(record.get("observed_tier") or "")
    if required_tier not in VERIFICATION_TIERS or observed_tier not in VERIFICATION_TIERS:
        errors.append("state witness observed_tier must reach a valid required_tier")
    elif VERIFICATION_TIERS.index(observed_tier) < VERIFICATION_TIERS.index(required_tier):
        errors.append(f"state witness tier {observed_tier} is below required {required_tier}")
    if not sealed_digest:
        errors.append("state witness must be sealed before protected acceptance")
    review_evidence = record.get("review_evidence")
    if not qualifying_evidence(
        review_evidence if isinstance(review_evidence, list) else [],
        "state_witness",
        required_tier,
    ):
        errors.append("state witness review requires qualifying evidence at the required tier")
    return errors


def has_state_seal(artifact_dir: Path) -> bool:
    trace_path = artifact_dir / "trace.jsonl"
    if not trace_path.is_file():
        return False
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("event") == "state_sealed":
            return True
    return False


def commit_transition(
    artifact_dir: Path,
    state_path: Path,
    expected: dict[str, object],
    value: dict[str, object],
    event: dict[str, object],
    *,
    transaction_id: str | None = None,
) -> None:
    trace_path = artifact_dir / "trace.jsonl"
    transaction_id = transaction_id or str(uuid.uuid4())
    journal = {
        **event,
        "transaction_id": transaction_id,
        "state_file": state_path.name,
        "before_sha256": sha256(state_path.read_bytes()),
        "after_sha256": sha256(serialized_json(value)),
    }
    started = {**journal, "event": f"{event['event']}_started", "ts": utc_now()}
    committed = {**journal, "ts": utc_now()}
    def guarded_update(current: dict[str, object]) -> dict[str, object]:
        if current != expected:
            raise ValueError(f"concurrent update detected: {state_path.name}")
        append_jsonl(trace_path, started, writer_role="manager", scope="global")
        return value

    mutate_json(state_path, guarded_update, writer_role="manager", scope="global")
    append_jsonl(trace_path, committed, writer_role="manager", scope="global")


def task_set_unlocked(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    state_path = artifact_dir / "run_state.json"
    state = load_object(state_path)
    original_state = deepcopy(state)
    current_errors = validate_run_state(state_path)
    if current_errors:
        raise ValueError("current run_state is invalid: " + "; ".join(current_errors))
    task = find_unique(state.get("tasks"), args.task_id, "task")
    old_status = str(task.get("status") or "")
    allowed = TASK_TRANSITIONS.get(old_status, set())
    if args.status not in allowed:
        raise ValueError(f"invalid task transition: {old_status} -> {args.status}")

    transaction_id = str(uuid.uuid4())
    subject = f"task:{args.task_id}"
    policy = state.get("evidence_policy")
    additions = build_evidence_additions(
        artifact_dir,
        subject=subject,
        freeform=args.evidence,
        files=getattr(args, "evidence_file", []),
        transaction_id=transaction_id,
        policy=policy,
    )
    evidence = append_unique_values(task.get("evidence"), additions)
    if args.status in {"passed", "merged"}:
        reject_self_report(args.evidence)
        if policy == EVIDENCE_POLICY and not qualifying_evidence(evidence, subject):
            raise ValueError(f"task status {args.status} requires qualifying evidence; use --evidence-file")
        if policy != EVIDENCE_POLICY and not evidence:
            raise ValueError(f"task status {args.status} requires evidence")
    if args.status in {"blocked", "verify_failed"} and not args.stop_reason:
        raise ValueError(f"task status {args.status} requires --stop-reason")
    if args.status == "running":
        tasks = state.get("tasks")
        task_map = {
            str(item.get("id")): item
            for item in tasks
            if isinstance(tasks, list) and isinstance(item, dict)
        }
        missing_dependencies = [
            str(dependency)
            for dependency in task.get("dependencies", [])
            if task_map.get(str(dependency), {}).get("status") not in {"passed", "merged"}
        ]
        if missing_dependencies:
            raise ValueError("task dependencies are not complete: " + ", ".join(missing_dependencies))

    task["status"] = args.status
    task["evidence"] = evidence
    task["stop_reason"] = args.stop_reason or ""
    if args.no_test_reason:
        task["verification_gate"]["no_test_reason"] = args.no_test_reason.strip()
    state["updated_at"] = utc_now()
    validate_candidate(artifact_dir, "run_state.json", state, validate_run_state)
    commit_transition(
        artifact_dir,
        state_path,
        original_state,
        state,
        {
            "event": "task_transition",
            "task_id": args.task_id,
            "from_status": old_status,
            "to_status": args.status,
            "evidence": additions,
            "stop_reason": args.stop_reason,
        },
        transaction_id=transaction_id,
    )
    print(f"task_transition=committed {args.task_id} {old_status}->{args.status}")
    return 0


def task_set(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    with locked(artifact_dir / ".harnessctl"):
        ensure_trace_integrity(artifact_dir)
        return task_set_unlocked(args)


def acceptance_set_unlocked(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    registry_path = artifact_dir / "acceptance_registry.json"
    registry = load_object(registry_path)
    original_registry = deepcopy(registry)
    current_errors = validate_acceptance_registry(registry_path)
    if current_errors:
        raise ValueError("current acceptance registry is invalid: " + "; ".join(current_errors))

    criterion = find_unique(registry.get("criteria"), args.criterion_id, "acceptance criterion")
    old_status = str(criterion.get("status") or "")
    allowed = ACCEPTANCE_TRANSITIONS.get(old_status, set())
    if args.status not in allowed:
        raise ValueError(f"invalid acceptance transition: {old_status} -> {args.status}")

    transaction_id = str(uuid.uuid4())
    subject = f"acceptance:{args.criterion_id}"
    policy = registry.get("evidence_policy")
    verification_tier = args.verification_tier
    additions = build_evidence_additions(
        artifact_dir,
        subject=subject,
        freeform=args.evidence,
        files=getattr(args, "evidence_file", []),
        transaction_id=transaction_id,
        policy=policy,
        verification_tier=verification_tier,
    )
    evidence = append_unique_values(criterion.get("evidence"), additions)
    pass_algorithm = args.pass_algorithm.strip() or str(criterion.get("pass_algorithm") or "").strip()
    blocking_issues = append_unique(criterion.get("blocking_issues"), args.blocking_issue)
    if args.status in {"pass", "scoped_out"} and not evidence:
        raise ValueError(f"acceptance status {args.status} requires evidence")
    if args.status == "pass":
        reject_self_report(args.evidence)
        required_tier = str(criterion.get("required_verification_tier") or "policy")
        if policy == EVIDENCE_POLICY and not qualifying_evidence(evidence, subject, required_tier):
            raise ValueError("acceptance status pass requires qualifying evidence; use --evidence-file")
        state = load_object(artifact_dir / "run_state.json")
        witness_errors = state_witness_gate(artifact_dir, state, require_review=True)
        if witness_errors:
            raise ValueError("state witness gate failed: " + "; ".join(witness_errors))
    if args.status == "pass" and not pass_algorithm:
        raise ValueError("acceptance status pass requires pass_algorithm")
    if args.status in {"fail", "blocked"} and not blocking_issues:
        raise ValueError(f"acceptance status {args.status} requires --blocking-issue")

    criterion["status"] = args.status
    criterion["evidence"] = evidence
    criterion["pass_algorithm"] = pass_algorithm
    criterion["blocking_issues"] = blocking_issues if args.status in {"fail", "blocked"} else []
    if args.no_test_reason:
        criterion["verification_gate"]["no_test_reason"] = args.no_test_reason.strip()
    registry["updated_at"] = utc_now()
    validate_candidate(artifact_dir, "acceptance_registry.json", registry, validate_acceptance_registry)
    commit_transition(
        artifact_dir,
        registry_path,
        original_registry,
        registry,
        {
            "event": "acceptance_transition",
            "criterion_id": args.criterion_id,
            "from_status": old_status,
            "to_status": args.status,
            "evidence": additions,
            "blocking_issues": args.blocking_issue,
        },
        transaction_id=transaction_id,
    )
    print(f"acceptance_transition=committed {args.criterion_id} {old_status}->{args.status}")
    return 0


def acceptance_set(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    with locked(artifact_dir / ".harnessctl"):
        ensure_trace_integrity(artifact_dir)
        return acceptance_set_unlocked(args)


def run_set_unlocked(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    state_path = artifact_dir / "run_state.json"
    registry_path = artifact_dir / "acceptance_registry.json"
    state = load_object(state_path)
    original_state = deepcopy(state)
    current_errors = validate_run_state(state_path)
    if current_errors:
        raise ValueError("current run_state is invalid: " + "; ".join(current_errors))

    old_status = str(state.get("status") or "")
    if args.status not in RUN_TRANSITIONS.get(old_status, set()):
        raise ValueError(f"invalid run transition: {old_status} -> {args.status}")
    if args.status == "dispatched" and not has_state_seal(artifact_dir):
        raise ValueError("run dispatch requires a sealed baseline; run harnessctl seal first")
    transaction_id = str(uuid.uuid4())
    subject = "run"
    policy = state.get("evidence_policy")
    evidence = build_evidence_additions(
        artifact_dir,
        subject=subject,
        freeform=args.evidence,
        files=getattr(args, "evidence_file", []),
        transaction_id=transaction_id,
        policy=policy,
        verification_tier=args.verification_tier,
    )

    if args.status in {"accepted", "handed_off"}:
        if not evidence:
            raise ValueError(f"run status {args.status} requires evidence")
        reject_self_report(args.evidence)
        existing_run_evidence = append_unique_values(state.get("run_evidence"), evidence)
        if policy == EVIDENCE_POLICY and not qualifying_evidence(existing_run_evidence, subject):
            raise ValueError(f"run status {args.status} requires qualifying evidence; use --evidence-file")
        tasks = state.get("tasks")
        if not isinstance(tasks, list):
            raise ValueError("run_state tasks must be a list")
        incomplete_tasks = [
            str(item.get("id") or "?")
            for item in tasks if isinstance(item, dict)
            if item.get("status") not in {"passed", "merged"}
        ]
        if incomplete_tasks:
            raise ValueError("run has incomplete tasks: " + ", ".join(incomplete_tasks))
        registry = load_object(registry_path)
        registry_errors = validate_acceptance_registry(registry_path)
        if registry_errors:
            raise ValueError("current acceptance registry is invalid: " + "; ".join(registry_errors))
        criteria = registry.get("criteria")
        if not isinstance(criteria, list):
            raise ValueError("acceptance criteria must be a list")
        unresolved = [
            str(item.get("id") or "?")
            for item in criteria if isinstance(item, dict)
            if item.get("status") not in {"pass", "scoped_out"}
        ]
        if unresolved:
            raise ValueError("run has unresolved acceptance: " + ", ".join(unresolved))
        tdd_errors = validate_active_tdd_gates(artifact_dir, state, registry)
        if tdd_errors:
            raise ValueError("active TDD gate failed: " + "; ".join(tdd_errors))
        witness_errors = state_witness_gate(artifact_dir, state, require_review=True)
        if witness_errors:
            raise ValueError("state witness gate failed: " + "; ".join(witness_errors))
        task_statuses = {
            str(item.get("id")): item.get("status")
            for item in tasks if isinstance(item, dict)
        }
        for stage in state.get("stages", []):
            if not isinstance(stage, dict):
                continue
            linked = stage.get("tasks")
            if isinstance(linked, list) and all(task_statuses.get(str(task_id)) in {"passed", "merged"} for task_id in linked):
                stage["status"] = "passed"
                stage["evidence"] = append_unique_values(stage.get("evidence"), evidence)
        state["status"] = args.status
        dispatch_errors = validate_dispatch_coverage(state)
        if dispatch_errors:
            raise ValueError("durable dispatch gate failed: " + "; ".join(dispatch_errors))

    state["status"] = args.status
    state["run_evidence"] = append_unique_values(state.get("run_evidence"), evidence)
    state["stop_reason"] = args.stop_reason.strip()
    state["updated_at"] = utc_now()
    validate_candidate(artifact_dir, "run_state.json", state, validate_run_state)
    commit_transition(
        artifact_dir,
        state_path,
        original_state,
        state,
        {
            "event": "run_transition",
            "from_status": old_status,
            "to_status": args.status,
            "evidence": evidence,
            "stop_reason": args.stop_reason.strip(),
        },
        transaction_id=transaction_id,
    )
    print(f"run_transition=committed {old_status}->{args.status}")
    return 0


def run_set(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    with locked(artifact_dir / ".harnessctl"):
        ensure_trace_integrity(artifact_dir)
        return run_set_unlocked(args)


def dispatch_create_unlocked(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    state_path = artifact_dir / "run_state.json"
    state = load_object(state_path)
    original_state = deepcopy(state)
    current_errors = validate_run_state(state_path)
    if current_errors:
        raise ValueError("current run_state is invalid: " + "; ".join(current_errors))
    witness_errors = state_witness_gate(artifact_dir, state, require_review=False)
    if witness_errors:
        raise ValueError("state witness gate failed before dispatch: " + "; ".join(witness_errors))
    if state.get("status") not in {"specified", "dispatched"}:
        raise ValueError("worker dispatch requires run status specified or dispatched")
    if not has_state_seal(artifact_dir):
        raise ValueError("worker dispatch requires a sealed baseline; run harnessctl seal first")

    task = find_unique(state.get("tasks"), args.task_id, "task")
    if args.contract_path != task.get("task_path"):
        raise ValueError("contract path must exactly match task_path")
    if args.report_path != task.get("report_path"):
        raise ValueError("report path must exactly match task report_path")
    resolve_artifact_path(artifact_dir, args.contract_path, "contract path", must_exist=True)
    resolve_artifact_path(artifact_dir, args.report_path, "report path", must_exist=False)
    worker_id = args.worker_id.strip()
    if not worker_id or any(ord(character) < 32 for character in worker_id):
        raise ValueError("worker id must be a non-empty opaque string without control characters")
    runtime = args.runtime.strip().casefold()
    requested_model = args.requested_model.strip()
    reasoning_effort = args.reasoning_effort.strip()
    resolved_model = args.resolved_model.strip()
    route_reason = args.route_reason.strip() or f"selected {args.profile} profile"
    if not runtime or any(ord(character) < 32 for character in runtime):
        raise ValueError("runtime must be a non-empty string without control characters")
    if any(ord(character) < 32 for value in (requested_model, reasoning_effort, resolved_model, route_reason) for character in value):
        raise ValueError("model routing values must not contain control characters")
    if args.escalation_count < 0:
        raise ValueError("escalation count must be non-negative")
    if runtime == "codex":
        configured = CODEX_MODEL_PROFILES[args.profile]
        requested_model = requested_model or configured["model"]
        reasoning_effort = reasoning_effort or configured["reasoning_effort"]
        if requested_model != configured["model"] or reasoning_effort != configured["reasoning_effort"]:
            raise ValueError(f"Codex profile {args.profile} must use {configured['model']} {configured['reasoning_effort']}")
        if "terra" in resolved_model.casefold():
            raise ValueError("Codex resolved model must not use disabled Terra models")

    session_state = state.get("state_layers", {}).get("session_state", {})
    dispatches = session_state.get("delegation_state") if isinstance(session_state, dict) else None
    if not isinstance(dispatches, list):
        raise ValueError("delegation_state list is missing")
    if any(
        isinstance(item, dict)
        and item.get("task_id") == args.task_id
        and item.get("status") in {"dispatched", "running"}
        for item in dispatches
    ):
        raise ValueError(f"task already has an active dispatch: {args.task_id}")

    now = utc_now()
    record = {
        "dispatch_id": str(uuid.uuid4()),
        "worker_id": worker_id,
        "task_id": args.task_id,
        "contract_path": args.contract_path,
        "report_path": args.report_path,
        "status": "dispatched",
        "runtime": runtime,
        "profile": args.profile,
        "requested_model": requested_model,
        "resolved_model": resolved_model,
        "reasoning_effort": reasoning_effort,
        "route_reason": route_reason,
        "escalation_count": args.escalation_count,
        "created_at": now,
        "updated_at": now,
        "stop_reason": "",
    }
    dispatches.append(record)
    state["updated_at"] = now
    validate_candidate(artifact_dir, "run_state.json", state, validate_run_state)
    commit_transition(
        artifact_dir,
        state_path,
        original_state,
        state,
        {"event": "dispatch_create", **record},
    )
    print(
        "dispatch_create=committed "
        f"dispatch_id={record['dispatch_id']} task_id={args.task_id} worker_id={worker_id} status=dispatched"
    )
    return 0


def dispatch_create(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    with locked(artifact_dir / ".harnessctl"):
        ensure_trace_integrity(artifact_dir)
        return dispatch_create_unlocked(args)


def dispatch_update_unlocked(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    state_path = artifact_dir / "run_state.json"
    state = load_object(state_path)
    original_state = deepcopy(state)
    current_errors = validate_run_state(state_path)
    if current_errors:
        raise ValueError("current run_state is invalid: " + "; ".join(current_errors))
    session_state = state.get("state_layers", {}).get("session_state", {})
    dispatches = session_state.get("delegation_state") if isinstance(session_state, dict) else None
    record = find_unique(dispatches, args.dispatch_id, "dispatch", key="dispatch_id")
    old_status = str(record.get("status") or "")
    if args.status not in DISPATCH_TRANSITIONS.get(old_status, set()):
        raise ValueError(f"invalid dispatch transition: {old_status} -> {args.status}")
    if args.status == "reported":
        resolve_artifact_path(artifact_dir, str(record.get("report_path") or ""), "report path", must_exist=True)
    if args.status in {"failed", "cancelled"} and not args.stop_reason.strip():
        raise ValueError(f"dispatch status {args.status} requires --stop-reason")

    record["status"] = args.status
    record["updated_at"] = utc_now()
    record["stop_reason"] = args.stop_reason.strip() if args.status in {"failed", "cancelled"} else ""
    state["updated_at"] = utc_now()
    validate_candidate(artifact_dir, "run_state.json", state, validate_run_state)
    commit_transition(
        artifact_dir,
        state_path,
        original_state,
        state,
        {
            "event": "dispatch_update",
            "dispatch_id": args.dispatch_id,
            "task_id": record.get("task_id"),
            "from_status": old_status,
            "to_status": args.status,
            "stop_reason": record["stop_reason"],
        },
    )
    print(f"dispatch_update=committed dispatch_id={args.dispatch_id} {old_status}->{args.status}")
    return 0


def dispatch_update(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    with locked(artifact_dir / ".harnessctl"):
        ensure_trace_integrity(artifact_dir)
        return dispatch_update_unlocked(args)


def recover_artifact(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    trace_path = artifact_dir / "trace.jsonl"
    with locked(artifact_dir / ".harnessctl"):
        jsonl_errors = validate_jsonl(trace_path)
        if jsonl_errors:
            raise ValueError("artifact trace integrity failed: " + "; ".join(jsonl_errors))
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        starts = {
            str(event["transaction_id"]): event
            for event in events
            if isinstance(event, dict)
            and str(event.get("event", "")).endswith("_started")
            and event.get("transaction_id")
        }
        terminals = {
            str(event["transaction_id"])
            for event in events
            if isinstance(event, dict)
            and not str(event.get("event", "")).endswith("_started")
            and event.get("transaction_id")
        }
        pending = [event for transaction_id, event in starts.items() if transaction_id not in terminals]
        if not pending:
            ensure_trace_integrity(artifact_dir)
            print("recovery=no incomplete transactions")
            return 0
        for started in pending:
            transaction_id = str(started["transaction_id"])
            state_file = str(started.get("state_file") or "")
            if not state_file or Path(state_file).name != state_file:
                raise ValueError(f"transaction {transaction_id} has unsafe or missing state_file")
            before_digest = str(started.get("before_sha256") or "")
            after_digest = str(started.get("after_sha256") or "")
            if not before_digest or not after_digest:
                raise ValueError(f"transaction {transaction_id} lacks recovery digests")
            state_path = artifact_dir / state_file
            actual_digest = sha256(state_path.read_bytes())
            base_event = str(started["event"])[: -len("_started")]
            if actual_digest == after_digest:
                terminal_event = base_event
                result = "committed"
            elif actual_digest == before_digest:
                terminal_event = f"{base_event}_aborted"
                result = "aborted"
            else:
                raise ValueError(f"transaction {transaction_id} state digest matches neither before nor after")
            terminal = {**started, "event": terminal_event, "ts": utc_now()}
            append_jsonl(trace_path, terminal, writer_role="manager", scope="global")
            print(f"recovery={result} {transaction_id}")
        ensure_trace_integrity(artifact_dir)
    return 0


def validate_jsonl(path: Path) -> list[str]:
    if not path.exists():
        return [f"missing file: {path.name}"]
    errors: list[str] = []
    content = path.read_text(encoding="utf-8")
    if content and not content.endswith("\n"):
        errors.append(f"{path.name}: missing final newline")
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}: line {line_number} invalid JSON: {exc.msg}")
            continue
        if not isinstance(event, dict):
            errors.append(f"{path.name}: line {line_number} must be an object")
    return errors


def transaction_payload(event: dict[str, object]) -> str:
    value = {key: item for key, item in event.items() if key not in {"event", "ts"}}
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_trace_transactions(path: Path) -> list[str]:
    if not path.exists():
        return []
    started: dict[str, tuple[str, str]] = {}
    committed: dict[str, tuple[str, str]] = {}
    errors: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or not event.get("transaction_id"):
            continue
        transaction_id = str(event["transaction_id"])
        event_name = str(event.get("event", ""))
        if event_name.endswith("_started"):
            base = event_name[: -len("_started")]
            if transaction_id in started:
                errors.append(f"trace.jsonl: duplicate transaction start: {transaction_id}")
            started[transaction_id] = (base, transaction_payload(event))
        else:
            if transaction_id in committed:
                errors.append(f"trace.jsonl: duplicate transaction commit: {transaction_id}")
            committed[transaction_id] = (event_name, transaction_payload(event))
    for transaction_id, (base, payload) in started.items():
        if transaction_id not in committed or committed[transaction_id][0] not in {base, f"{base}_aborted"}:
            errors.append(f"trace.jsonl: incomplete transaction: {transaction_id}")
        elif committed[transaction_id][1] != payload:
            errors.append(f"trace.jsonl: transaction payload mismatch: {transaction_id}")
    for transaction_id in sorted(set(committed) - set(started)):
        errors.append(f"trace.jsonl: commit without start: {transaction_id}")
    return errors


def validate_transaction_digest_chain(path: Path) -> list[str]:
    if not path.exists():
        return []
    expected: dict[str, str] = {}
    pending: dict[str, tuple[str, str, str]] = {}
    errors: list[str] = []
    initialized = 0
    previous_was_start: str | None = None
    digest_pattern = re.compile(r"^[0-9a-f]{64}$")
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        state_digests = event.get("state_digests")
        if event.get("event") in {"run_initialized", "state_sealed"} and isinstance(state_digests, dict):
            if event.get("event") == "run_initialized":
                initialized += 1
                if initialized > 1:
                    errors.append("trace.jsonl: duplicate run_initialized anchor")
            for filename, digest in state_digests.items():
                if isinstance(filename, str) and isinstance(digest, str):
                    if not digest_pattern.fullmatch(digest):
                        errors.append(f"trace.jsonl: invalid canonical digest for {filename}")
                    expected[filename] = digest
            continue
        event_name = str(event.get("event") or "")
        state_file = event.get("state_file")
        transaction_id = str(event.get("transaction_id") or "")
        if event_name.endswith("_started") and isinstance(state_file, str):
            if previous_was_start is not None:
                errors.append(f"trace.jsonl: transaction {previous_was_start} start is not adjacent to its terminal")
            before_digest = str(event.get("before_sha256") or "")
            after_digest = str(event.get("after_sha256") or "")
            if not digest_pattern.fullmatch(before_digest) or not digest_pattern.fullmatch(after_digest):
                errors.append(f"trace.jsonl: transaction {transaction_id} has invalid state digest")
            previous_digest = expected.get(state_file)
            if previous_digest is not None and before_digest != previous_digest:
                errors.append(f"trace.jsonl: {state_file} transaction digest chain is broken")
            pending[transaction_id] = (state_file, before_digest, after_digest)
            previous_was_start = transaction_id
        elif transaction_id in pending:
            if previous_was_start != transaction_id:
                errors.append(f"trace.jsonl: transaction {transaction_id} terminal is not adjacent to its start")
            pending_state_file, before_digest, after_digest = pending[transaction_id]
            expected[pending_state_file] = before_digest if event_name.endswith("_aborted") else after_digest
            previous_was_start = None
        elif previous_was_start is not None:
            errors.append(f"trace.jsonl: transaction {previous_was_start} start is not adjacent to its terminal")
            previous_was_start = None
    return errors


def ensure_trace_integrity(artifact_dir: Path) -> None:
    errors = [
        *validate_jsonl(artifact_dir / "trace.jsonl"),
        *validate_jsonl(artifact_dir / "tdd_trace.jsonl"),
        *validate_trace_transactions(artifact_dir / "trace.jsonl"),
        *validate_transaction_digest_chain(artifact_dir / "trace.jsonl"),
        *validate_canonical_state_digests(artifact_dir),
        *validate_evidence_receipts(artifact_dir),
    ]
    if errors:
        raise ValueError("artifact trace integrity failed: " + "; ".join(errors))


def validate_canonical_state_digests(artifact_dir: Path) -> list[str]:
    trace_path = artifact_dir / "trace.jsonl"
    if not trace_path.exists():
        return []
    expected: dict[str, str] = {}
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("event") in {"run_initialized", "state_sealed"} and isinstance(event.get("state_digests"), dict):
            for filename, digest in event["state_digests"].items():
                if isinstance(filename, str) and isinstance(digest, str):
                    expected[filename] = digest
        event_name = str(event.get("event") or "")
        state_file = event.get("state_file")
        if not isinstance(state_file, str) or not state_file or event_name.endswith("_started"):
            continue
        digest_key = "before_sha256" if event_name.endswith("_aborted") else "after_sha256"
        digest = event.get(digest_key)
        if isinstance(digest, str) and digest:
            expected[state_file] = digest

    errors: list[str] = []
    for filename, digest in expected.items():
        if Path(filename).name != filename:
            errors.append(f"trace.jsonl: unsafe canonical state file: {filename}")
            continue
        path = artifact_dir / filename
        if not path.exists():
            errors.append(f"missing canonical state file: {filename}")
        elif sha256(path.read_bytes()) != digest:
            errors.append(f"{filename}: digest does not match latest committed state")
    return errors


def seal_artifact(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    with locked(artifact_dir / ".harnessctl"):
        structural_errors = [
            *validate_jsonl(artifact_dir / "trace.jsonl"),
            *validate_jsonl(artifact_dir / "tdd_trace.jsonl"),
            *validate_trace_transactions(artifact_dir / "trace.jsonl"),
            *validate_run_state(artifact_dir / "run_state.json"),
            *validate_acceptance_registry(artifact_dir / "acceptance_registry.json"),
        ]
        if structural_errors:
            raise ValueError("cannot seal invalid artifact: " + "; ".join(structural_errors))
        state = load_object(artifact_dir / "run_state.json")
        original_state = deepcopy(state)
        witness_errors = state_witness_gate(artifact_dir, state, require_review=False)
        if witness_errors:
            raise ValueError("cannot seal invalid state witness: " + "; ".join(witness_errors))
        if state.get("status") not in {"intake", "gated", "specified"}:
            raise ValueError("seal is only allowed before dispatch")
        if any(
            isinstance(task, dict) and task.get("status") in {"running", "passed", "merged"}
            for task in state.get("tasks", []) if isinstance(state.get("tasks"), list)
        ):
            raise ValueError("seal requires all tasks to remain pre-execution")
        session_state = state.get("state_layers", {}).get("session_state", {})
        dispatches = session_state.get("delegation_state", []) if isinstance(session_state, dict) else []
        if isinstance(dispatches, list) and dispatches:
            raise ValueError("seal is only allowed before dispatch")
        trace_events = [
            json.loads(line)
            for line in (artifact_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if any(isinstance(event, dict) and event.get("event") == "dispatch_create" for event in trace_events):
            raise ValueError("seal is only allowed before dispatch")
        reason = args.reason.strip()
        if not reason:
            raise ValueError("seal requires --reason")
        state_witness = state.get("state_witness")
        if isinstance(state_witness, dict) and state_witness.get("required"):
            witness_path = artifact_dir / str(state_witness["path"])
            state_witness["sealed_digest"] = sha256(witness_path.read_bytes())
            state["updated_at"] = utc_now()
            validate_candidate(artifact_dir, "run_state.json", state, validate_run_state)
            commit_transition(
                artifact_dir,
                artifact_dir / "run_state.json",
                original_state,
                state,
                {"event": "state_witness_sealed", "reason": reason},
            )
        state_digests = {
            "run_state.json": sha256((artifact_dir / "run_state.json").read_bytes()),
            "acceptance_registry.json": sha256((artifact_dir / "acceptance_registry.json").read_bytes()),
        }
        state_witness = state.get("state_witness")
        if isinstance(state_witness, dict) and state_witness.get("required"):
            state_digests[str(state_witness["path"])] = sha256(
                (artifact_dir / str(state_witness["path"])).read_bytes()
            )
        event = {
            "event": "state_sealed",
            "ts": utc_now(),
            "reason": reason,
            "state_digests": state_digests,
        }
        append_jsonl(artifact_dir / "trace.jsonl", event, writer_role="manager", scope="global")
        print("state_sealed=committed")
        return 0


def witness_set(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    with locked(artifact_dir / ".harnessctl"):
        ensure_trace_integrity(artifact_dir)
        state_path = artifact_dir / "run_state.json"
        state = load_object(state_path)
        original_state = deepcopy(state)
        current_errors = validate_run_state(state_path)
        if current_errors:
            raise ValueError("current run_state is invalid: " + "; ".join(current_errors))
        record = state.get("state_witness")
        if not isinstance(record, dict) or not record.get("required"):
            raise ValueError("state witness is not required for this run")
        if args.status == "pass":
            gate_errors = state_witness_gate(artifact_dir, state, require_review=False)
            if gate_errors:
                raise ValueError("state witness validation failed: " + "; ".join(gate_errors))
            if not args.reviewer_id.strip():
                raise ValueError("witness pass requires --reviewer-id")
            required_tier = str(record.get("required_tier") or "policy")
            if required_tier not in VERIFICATION_TIERS or VERIFICATION_TIERS.index(args.verification_tier) < VERIFICATION_TIERS.index(required_tier):
                raise ValueError(
                    f"witness verification tier {args.verification_tier} is below required {required_tier}"
                )
            transaction_id = str(uuid.uuid4())
            additions = build_evidence_additions(
                artifact_dir,
                subject="state_witness",
                freeform=[],
                files=args.evidence_file,
                transaction_id=transaction_id,
                policy=EVIDENCE_POLICY,
                verification_tier=args.verification_tier,
            )
            if not qualifying_evidence(additions, "state_witness", args.verification_tier):
                raise ValueError("witness pass requires a qualifying --evidence-file")
            record["review_status"] = "pass"
            record["reviewer_id"] = args.reviewer_id.strip()
            record["observed_tier"] = args.verification_tier
            record["review_evidence"] = additions
            record["reviewed_at"] = utc_now()
        else:
            transaction_id = str(uuid.uuid4())
            if not args.reason.strip():
                raise ValueError(f"witness status {args.status} requires --reason")
            record["review_status"] = args.status
            record["reviewer_id"] = args.reviewer_id.strip()
            record["reviewed_at"] = utc_now()
        state["updated_at"] = utc_now()
        validate_candidate(artifact_dir, "run_state.json", state, validate_run_state)
        commit_transition(
            artifact_dir,
            state_path,
            original_state,
            state,
            {
                "event": "state_witness_review",
                "status": args.status,
                "reviewer_id": args.reviewer_id.strip(),
                "reason": args.reason.strip(),
            },
            transaction_id=transaction_id,
        )
        print(f"state_witness=committed status={args.status}")
        return 0


def validate_evidence_receipts(artifact_dir: Path) -> list[str]:
    trace_path = artifact_dir / "trace.jsonl"
    if not trace_path.exists():
        return []
    terminals: dict[str, dict[str, object]] = {}
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_name = str(event.get("event") or "")
        transaction_id = event.get("transaction_id")
        if isinstance(transaction_id, str) and not event_name.endswith("_started") and not event_name.endswith("_aborted"):
            terminals[transaction_id] = event

    records: list[tuple[str, object]] = []
    for filename in ("run_state.json", "acceptance_registry.json"):
        path = artifact_dir / filename
        if not path.exists():
            continue
        try:
            data = load_object(path)
        except ValueError:
            continue
        if filename == "run_state.json":
            tasks = data.get("tasks")
            for task in tasks if isinstance(tasks, list) else []:
                if isinstance(task, dict):
                    for record in task.get("evidence", []) if isinstance(task.get("evidence"), list) else []:
                        records.append((f"task:{task.get('id')}", record))
            for record in data.get("run_evidence", []) if isinstance(data.get("run_evidence"), list) else []:
                records.append(("run", record))
        else:
            criteria = data.get("criteria")
            for criterion in criteria if isinstance(criteria, list) else []:
                if isinstance(criterion, dict):
                    for record in criterion.get("evidence", []) if isinstance(criterion.get("evidence"), list) else []:
                        records.append((f"acceptance:{criterion.get('id')}", record))

    errors: list[str] = []
    seen_ids: set[str] = set()
    for subject, record in records:
        if not isinstance(record, dict):
            continue
        evidence_id = str(record.get("id") or "")
        if evidence_id:
            if evidence_id in seen_ids:
                errors.append(f"duplicate evidence id: {evidence_id}")
            seen_ids.add(evidence_id)
        if record.get("type") not in QUALIFYING_EVIDENCE_TYPES:
            continue
        verification = record.get("verification")
        transaction_id = str(verification.get("transaction_id") or "") if isinstance(verification, dict) else ""
        terminal = terminals.get(transaction_id)
        if terminal is None or record not in terminal.get("evidence", []):
            errors.append(f"{evidence_id or subject}: missing committed evidence receipt")
            continue
        payload = record.get("payload")
        if record.get("type") == "artifact_digest" and isinstance(payload, dict):
            value = str(payload.get("path") or "")
            try:
                path, normalized = artifact_evidence_path(artifact_dir, value)
            except ValueError as exc:
                errors.append(f"{evidence_id or subject}: {exc}")
                continue
            actual = sha256(path.read_bytes())
            if actual != payload.get("sha256"):
                errors.append(f"{evidence_id or subject}: artifact digest mismatch: {normalized}")
            if path.stat().st_size != payload.get("size_bytes"):
                errors.append(f"{evidence_id or subject}: artifact size mismatch: {normalized}")
    return errors


def validate_dispatch_coverage(state: dict[str, object]) -> list[str]:
    if state.get("status") not in {"dispatched", "reported", "evaluating", "accepted", "handed_off"}:
        return []
    tasks = state.get("tasks")
    if not isinstance(tasks, list):
        return []
    session_state = state.get("state_layers", {}).get("session_state", {})
    dispatches = session_state.get("delegation_state", []) if isinstance(session_state, dict) else []
    errors: list[str] = []
    for task in tasks:
        if not isinstance(task, dict) or task.get("owner") in {"manager", "main-agent"}:
            continue
        task_id = str(task.get("id") or "?")
        related = [
            item for item in dispatches
            if isinstance(item, dict) and str(item.get("task_id")) == task_id
        ] if isinstance(dispatches, list) else []
        active = [item for item in related if item.get("status") in {"dispatched", "running"}]
        reported = [item for item in related if item.get("status") == "reported"]
        if task.get("status") == "running" and len(active) != 1:
            errors.append(f"running task lacks active durable dispatch: {task_id}")
        if task.get("status") in {"verify_failed", "passed", "merged"} and (not reported or active):
            errors.append(f"completed task lacks reported durable dispatch: {task_id}")
    return errors


def validate_cross_file_invariants(state_path: Path, registry_path: Path) -> list[str]:
    try:
        state = load_object(state_path)
        registry = load_object(registry_path)
    except ValueError:
        return []
    errors: list[str] = []
    tasks = state.get("tasks")
    if not isinstance(tasks, list):
        tasks = []
    task_statuses = {
        str(item.get("id")): item.get("status")
        for item in tasks if isinstance(item, dict)
    }
    stages = state.get("stages")
    if not isinstance(stages, list):
        stages = []
    for stage in stages:
        if not isinstance(stage, dict) or stage.get("status") not in {"passed", "merged"}:
            continue
        linked = stage.get("tasks")
        incomplete = [
            str(task_id) for task_id in linked if task_statuses.get(str(task_id)) not in {"passed", "merged"}
        ] if isinstance(linked, list) else []
        if incomplete:
            errors.append(
                f"passed stage has incomplete tasks: {stage.get('id', '?')}: " + ", ".join(incomplete)
            )

    errors.extend(validate_dispatch_coverage(state))

    if state.get("status") not in {"accepted", "handed_off"}:
        return errors
    errors.extend(state_witness_gate(state_path.parent, state, require_review=True))
    criteria = registry.get("criteria")
    if not isinstance(criteria, list):
        return errors
    unresolved = [
        str(item.get("id") or "?")
        for item in criteria if isinstance(item, dict)
        if item.get("status") not in {"pass", "scoped_out"}
    ]
    if unresolved:
        errors.append("accepted run has unresolved acceptance: " + ", ".join(unresolved))
    incomplete_tasks = [
        str(item.get("id") or "?")
        for item in tasks if isinstance(item, dict)
        if item.get("status") not in {"passed", "merged"}
    ]
    if incomplete_tasks:
        errors.append("accepted run has incomplete tasks: " + ", ".join(incomplete_tasks))
    incomplete_stages = [
        str(item.get("id") or "?")
        for item in stages if isinstance(item, dict)
        if item.get("status") not in {"passed", "merged"}
    ]
    if incomplete_stages:
        errors.append("accepted run has incomplete stages: " + ", ".join(incomplete_stages))
    return errors


def validate_active_tdd_gates(
    artifact_dir: Path,
    state: dict[str, object],
    registry: dict[str, object],
) -> list[str]:
    active_modes: set[str] = set()
    tasks = state.get("tasks")
    for item in tasks if isinstance(tasks, list) else []:
        if isinstance(item, dict) and item.get("status") in {"passed", "merged"}:
            gate = item.get("verification_gate")
            if isinstance(gate, dict):
                active_modes.add(str(gate.get("mode") or ""))
    criteria = registry.get("criteria")
    for item in criteria if isinstance(criteria, list) else []:
        if isinstance(item, dict) and item.get("status") == "pass":
            gate = item.get("verification_gate")
            if isinstance(gate, dict):
                active_modes.add(str(gate.get("mode") or ""))
    if not active_modes.intersection({"strict_tdd", "test_first_evidence"}):
        return []
    trace_path = artifact_dir / "tdd_trace.jsonl"
    events, parse_errors = load_events(trace_path)
    if parse_errors:
        return [f"tdd_trace.jsonl: {error}" for error in parse_errors]
    gate = latest_gate_decision(events)
    required_mode = "strict_tdd" if "strict_tdd" in active_modes else "test_first_evidence"
    actual_mode = gate_mode_of(gate) if gate is not None else ""
    if actual_mode != required_mode:
        return [f"tdd_trace.jsonl: latest gate mode must be {required_mode}; got {actual_mode or 'missing'}"]
    return [f"tdd_trace.jsonl: {error}" for error in validate_tdd_trace(trace_path, source_paths=[], tolerance_seconds=1.0)]


def validate_artifact(args: argparse.Namespace) -> int:
    artifact_dir = args.artifact_dir.expanduser().resolve()
    validators = (
        (artifact_dir / "run_state.json", validate_run_state),
        (artifact_dir / "acceptance_registry.json", validate_acceptance_registry),
    )
    errors: list[str] = []
    for path, validator in validators:
        if not path.exists():
            errors.append(f"missing file: {path.name}")
        else:
            errors.extend(validator(path))
    errors.extend(validate_jsonl(artifact_dir / "trace.jsonl"))
    errors.extend(validate_jsonl(artifact_dir / "tdd_trace.jsonl"))
    errors.extend(validate_trace_transactions(artifact_dir / "trace.jsonl"))
    errors.extend(validate_transaction_digest_chain(artifact_dir / "trace.jsonl"))
    errors.extend(validate_canonical_state_digests(artifact_dir))
    errors.extend(validate_evidence_receipts(artifact_dir))
    errors.extend(validate_cross_file_invariants(artifact_dir / "run_state.json", artifact_dir / "acceptance_registry.json"))
    if not errors:
        state = load_object(artifact_dir / "run_state.json")
        registry = load_object(artifact_dir / "acceptance_registry.json")
        errors.extend(validate_active_tdd_gates(artifact_dir, state, registry))
    if errors:
        print(f"FAIL {artifact_dir}")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"PASS {artifact_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guarded Full Harness state control.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate protocol JSON and JSONL files.")
    validate_parser.add_argument("artifact_dir", type=Path)
    validate_parser.set_defaults(handler=validate_artifact)

    seal_parser = subparsers.add_parser("seal", help="Authorize and bind pre-dispatch human-authored state.")
    seal_parser.add_argument("artifact_dir", type=Path)
    seal_parser.add_argument("--reason", required=True)
    seal_parser.set_defaults(handler=seal_artifact)

    task_parser = subparsers.add_parser("task-set", help="Apply a guarded task status transition.")
    task_parser.add_argument("artifact_dir", type=Path)
    task_parser.add_argument("--task-id", required=True)
    task_parser.add_argument("--status", required=True, choices=sorted(TASK_STATUSES))
    task_parser.add_argument("--evidence", action="append", default=[])
    task_parser.add_argument("--evidence-file", action="append", default=[])
    task_parser.add_argument("--stop-reason", default="")
    task_parser.add_argument("--no-test-reason", default="")
    task_parser.set_defaults(handler=task_set)

    acceptance_parser = subparsers.add_parser("acceptance-set", help="Apply a guarded acceptance status transition.")
    acceptance_parser.add_argument("artifact_dir", type=Path)
    acceptance_parser.add_argument("--criterion-id", required=True)
    acceptance_parser.add_argument("--status", required=True, choices=sorted(ACCEPTANCE_STATUSES))
    acceptance_parser.add_argument("--evidence", action="append", default=[])
    acceptance_parser.add_argument("--evidence-file", action="append", default=[])
    acceptance_parser.add_argument("--verification-tier", choices=VERIFICATION_TIERS, default="policy")
    acceptance_parser.add_argument("--pass-algorithm", default="")
    acceptance_parser.add_argument("--blocking-issue", action="append", default=[])
    acceptance_parser.add_argument("--no-test-reason", default="")
    acceptance_parser.set_defaults(handler=acceptance_set)

    run_parser = subparsers.add_parser("run-set", help="Apply a guarded top-level run transition.")
    run_parser.add_argument("artifact_dir", type=Path)
    run_parser.add_argument("--status", required=True, choices=sorted(RUN_STATUSES))
    run_parser.add_argument("--evidence", action="append", default=[])
    run_parser.add_argument("--evidence-file", action="append", default=[])
    run_parser.add_argument("--verification-tier", choices=VERIFICATION_TIERS, default="policy")
    run_parser.add_argument("--stop-reason", default="")
    run_parser.set_defaults(handler=run_set)

    witness_parser = subparsers.add_parser("witness-set", help="Record independent state witness review evidence.")
    witness_parser.add_argument("artifact_dir", type=Path)
    witness_parser.add_argument("--status", required=True, choices=("pass", "fail", "blocked"))
    witness_parser.add_argument("--reviewer-id", default="")
    witness_parser.add_argument("--verification-tier", choices=VERIFICATION_TIERS, default="policy")
    witness_parser.add_argument("--evidence-file", action="append", default=[])
    witness_parser.add_argument("--reason", default="")
    witness_parser.set_defaults(handler=witness_set)

    dispatch_create_parser = subparsers.add_parser("dispatch-create", help="Persist a manager-owned worker dispatch.")
    dispatch_create_parser.add_argument("artifact_dir", type=Path)
    dispatch_create_parser.add_argument("--worker-id", required=True)
    dispatch_create_parser.add_argument("--task-id", required=True)
    dispatch_create_parser.add_argument("--contract-path", required=True)
    dispatch_create_parser.add_argument("--report-path", required=True)
    dispatch_create_parser.add_argument("--runtime", default="universal")
    dispatch_create_parser.add_argument("--profile", choices=sorted(AGENT_PROFILES), default="main")
    dispatch_create_parser.add_argument("--requested-model", default="")
    dispatch_create_parser.add_argument("--resolved-model", default="")
    dispatch_create_parser.add_argument("--reasoning-effort", default="")
    dispatch_create_parser.add_argument("--route-reason", default="")
    dispatch_create_parser.add_argument("--escalation-count", type=int, default=0)
    dispatch_create_parser.set_defaults(handler=dispatch_create)

    dispatch_update_parser = subparsers.add_parser("dispatch-update", help="Advance a persisted worker dispatch lifecycle.")
    dispatch_update_parser.add_argument("artifact_dir", type=Path)
    dispatch_update_parser.add_argument("--dispatch-id", required=True)
    dispatch_update_parser.add_argument("--status", required=True, choices=sorted(DISPATCH_STATUSES - {"dispatched"}))
    dispatch_update_parser.add_argument("--stop-reason", default="")
    dispatch_update_parser.set_defaults(handler=dispatch_update)

    recover_parser = subparsers.add_parser("recover", help="Reconcile interrupted journaled transitions.")
    recover_parser.add_argument("artifact_dir", type=Path)
    recover_parser.set_defaults(handler=recover_artifact)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.handler(args))
    except (OSError, ValueError, PermissionError) as exc:
        print(f"ERROR {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
