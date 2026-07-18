#!/usr/bin/env python3
"""Validate required Markdown sections for multi-agent artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from harness_schema import (
    ACCEPTANCE_STATUSES,
    AGENT_PROFILES,
    CONTINUATION_PROTOCOL,
    CONTINUATION_STATUSES,
    DISPATCH_STATUSES,
    EVIDENCE_POLICY,
    MODES,
    MODEL_ROUTING_POLICY,
    QUALIFYING_EVIDENCE_TYPES,
    RUN_STATUSES,
    SCHEMA_VERSION,
    STATE_WITNESS_REVIEW_STATUSES,
    TASK_STATUSES,
    VERIFICATION_TIERS,
    VERIFICATION_GATE_MODES,
    model_profiles_for,
)
from state_witness_check import validate as validate_state_witness


REQUIRED_SECTIONS = {
    "subagent": [
        "Goal",
        "Files Touched",
        "Commands Run",
        "Test-First Or Substitute Verification",
        "Production State Witness",
        "Evidence",
        "Unresolved Risks",
        "Assumptions Affecting Merge",
        "Stub TODO Mock Or Unverified Path",
        "Return Summary",
    ],
    "evaluator": [
        "Scope Checked",
        "Testing Gate Evidence Checked",
        "Production State Witness Checked",
        "Verification Tier",
        "Evidence",
        "Blocking Issues",
        "Non-Blocking Issues",
        "Stub Or Placeholder Check",
        "Required Fixes",
        "Residual Risk",
    ],
    "progress": [
        "Snapshot",
        "Completed",
        "Changed Files",
        "Decisions",
        "Commands And Evidence",
        "Verification",
        "Open Risks",
        "Next Step",
    ],
    "spec": [
        "Goal",
        "User-Facing Outcome",
        "Non-Goals",
        "Constraints",
        "Acceptance Criteria",
        "Verification Evidence",
        "Risks",
        "Budget",
        "Stop Conditions",
        "Artifact Location",
    ],
    "lite_plan": [
        "Goal",
        "Workers",
        "Production State Witness",
        "Merge Plan",
        "Verification Evidence",
        "Blocking Issues",
        "Next Step",
    ],
    "lite_review": [
        "Status",
        "Scope Reviewed",
        "Evidence",
        "Unverified Paths",
        "Blocking Issues",
        "Required Fixes",
    ],
}


VALID_RESULTS = {"PASS", "FAIL", "BLOCKED"}
VALID_ACCEPTANCE_STATUSES = ACCEPTANCE_STATUSES
VALID_RUN_STATUSES = RUN_STATUSES
VALID_TASK_STATUSES = TASK_STATUSES
VALID_MODES = MODES
VALID_LITE_REVIEW_STATUSES = {"pass", "fail", "blocked"}
VALID_PROGRESS_VERIFICATION_STATUSES = {"pending", "running", "pass", "fail", "blocked"}
PROGRESS_SNAPSHOT_LABELS = (
    "stage",
    "active_task",
    "owner",
    "blocker",
    "verification_status",
    "next_step",
)
VALID_VERIFICATION_GATE_MODES = VERIFICATION_GATE_MODES
VERIFICATION_GATE_FIELDS = (
    "mode",
    "tdd_trace_path",
    "red_command",
    "red_result",
    "red_failure_reason",
    "green_command",
    "green_result",
    "refactor_check",
    "substitute_check",
    "no_test_reason",
)
TDD_SECTION_LABELS = (
    "Gate mode",
    "Trace path",
    "Chronology summary",
    "First production edit",
    "Applicability reason",
    "RED command",
    "RED result",
    "RED failure reason",
    "GREEN command",
    "GREEN result",
    "Refactor check",
    "Substitute check",
    "No-test reason",
    "Unverified critical path",
)
TDD_TRACE_REQUIRED_LABELS = (
    "Trace path",
    "Chronology summary",
    "First production edit",
    "Unverified critical path",
)
TDD_RED_GREEN_LABELS = (
    "RED command",
    "RED result",
    "RED failure reason",
    "GREEN command",
    "GREEN result",
)
EVALUATOR_GATE_LABELS = (
    "TDD trace path",
    "Trace chronology checked",
    "RED before GREEN",
    "First production edit after RED",
    "Gate records reviewed",
    "Missing or invalid gate records",
    "Strict TDD evidence accepted",
    "Substitute verification accepted",
    "Substitute reason checked",
    "Review gate evidence checked",
)
STATE_WITNESS_LABELS = (
    "Witness path",
    "Actual call chain verified",
    "State producers/lifecycle verified",
    "Failing state row covered",
    "Preserved blocking row covered",
    "Adversarial call-site review result",
    "Missing or unreachable state combinations",
)
VERIFICATION_TIER_LABELS = (
    "Policy tier",
    "Flow tier",
    "User-visible tier",
    "Exact blocked boundary, if any",
)
SUBAGENT_STATE_WITNESS_LABELS = (
    "Required for this task",
    "Witness path or compact matrix",
    "Real call-site inputs verified",
    "Failing state row",
    "Preserved blocking row",
    "Adversarial review handoff",
)


def is_qualifying_evidence(value: object, subject: str, minimum_tier: str = "policy") -> bool:
    if minimum_tier not in VERIFICATION_TIERS:
        return False
    if not isinstance(value, dict) or value.get("type") not in QUALIFYING_EVIDENCE_TYPES:
        return False
    verification = value.get("verification")
    return (
        value.get("subject") == subject
        and value.get("result") == "pass"
        and isinstance(verification, dict)
        and verification.get("status") == "verified"
        and bool(str(verification.get("transaction_id") or "").strip())
        and str(value.get("verification_tier") or "policy") in VERIFICATION_TIERS
        and VERIFICATION_TIERS.index(str(value.get("verification_tier") or "policy"))
        >= VERIFICATION_TIERS.index(minimum_tier)
    )


def validate_evidence_list(
    values: object,
    prefix: str,
    *,
    subject: str,
    protected: bool,
    policy: object,
) -> list[str]:
    if not isinstance(values, list):
        return [f"{prefix} must be a list"]
    errors: list[str] = []
    for index, value in enumerate(values, start=1):
        item_prefix = f"{prefix}[{index}]"
        if isinstance(value, str):
            if policy == EVIDENCE_POLICY and protected:
                errors.append(f"{item_prefix} legacy text cannot satisfy protected status")
            continue
        if not isinstance(value, dict):
            errors.append(f"{item_prefix} must be a string or evidence object")
            continue
        for key in ("id", "type", "source_role", "subject", "result", "payload", "verification"):
            if key not in value:
                errors.append(f"{item_prefix} missing {key}")
        if value.get("subject") != subject:
            errors.append(f"{item_prefix}.subject must be {subject!r}")
        if not isinstance(value.get("payload"), dict):
            errors.append(f"{item_prefix}.payload must be an object")
        if "verification_tier" in value and value["verification_tier"] not in VERIFICATION_TIERS:
            errors.append(f"{item_prefix}.verification_tier must be one of {', '.join(VERIFICATION_TIERS)}")
        verification = value.get("verification")
        if not isinstance(verification, dict):
            errors.append(f"{item_prefix}.verification must be an object")
        elif value.get("type") in QUALIFYING_EVIDENCE_TYPES:
            for key in ("status", "method", "verified_by", "verified_at", "transaction_id"):
                if not str(verification.get(key) or "").strip():
                    errors.append(f"{item_prefix}.verification missing {key}")
    if protected and policy == EVIDENCE_POLICY and not any(
        is_qualifying_evidence(value, subject) for value in values
    ):
        errors.append(f"{prefix} requires qualifying verified evidence for {subject}")
    return errors

SECTION_ALIASES = {
    "spec": {
        "Goal": ("目标",),
        "User-Facing Outcome": ("用户可见结果", "用户面向结果"),
        "Non-Goals": ("非目标",),
        "Constraints": ("约束", "不可改变的约束"),
        "Acceptance Criteria": ("验收标准", "最终成功标准"),
        "Verification Evidence": ("验证证据",),
        "Risks": ("风险",),
        "Budget": ("预算",),
        "Stop Conditions": ("停止条件",),
        "Artifact Location": ("Artifact 位置", "产物位置"),
    },
    "progress": {
        "Snapshot": ("快照",),
        "Completed": ("已完成",),
        "Changed Files": ("修改文件",),
        "Decisions": ("决策",),
        "Commands And Evidence": ("命令与证据",),
        "Verification": ("验证",),
        "Open Risks": ("未决风险", "开放风险"),
        "Next Step": ("下一步",),
    },
}


def extract_headings(markdown: str) -> set[str]:
    headings = set()
    for line in markdown.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            headings.add(match.group(1).strip())
    return headings


def without_fenced_blocks(markdown: str) -> str:
    lines: list[str] = []
    fence: str | None = None
    for line in markdown.splitlines(keepends=True):
        match = re.match(r"^[ \t]*(`{3,}|~{3,})", line)
        marker = match.group(1) if match else ""
        if fence is None and marker:
            fence = marker[0]
            lines.append("\n" if line.endswith("\n") else "")
        elif fence is not None:
            if marker and marker[0] == fence:
                fence = None
            lines.append("\n" if line.endswith("\n") else "")
        else:
            lines.append(line)
    return "".join(lines)


def normalize_heading(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip()
    numeral = r"0-9一二三四五六七八九十百千万零〇甲乙丙丁"
    prefixes = (
        rf"第[{numeral}]+[章节部篇]",
        rf"\([{numeral}]+\)",
        rf"\d+(?:\.\d+)*(?:[.、:：-]|\s+)",
        rf"[{numeral.replace('0-9', '')}]+(?:[.、:：-]|\s+)",
    )
    value = re.sub(rf"^\s*(?:{'|'.join(prefixes)})\s*", "", value, count=1)
    value = re.sub(r"[-_/]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.casefold()


def extract_semantic_sections(markdown: str, artifact_type: str) -> tuple[dict[str, str], list[str]]:
    markdown = without_fenced_blocks(markdown)
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", markdown, re.MULTILINE))
    aliases = SECTION_ALIASES.get(artifact_type, {})
    lookup: dict[str, str] = {}
    for canonical in REQUIRED_SECTIONS.get(artifact_type, []):
        for candidate in (canonical, *aliases.get(canonical, ())):
            lookup[normalize_heading(candidate)] = canonical

    sections: dict[str, str] = {}
    errors: list[str] = []
    for index, match in enumerate(matches):
        raw_heading = match.group(1).strip()
        canonical = lookup.get(normalize_heading(raw_heading), raw_heading)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        if canonical in sections:
            errors.append(f"duplicate section: {canonical}")
            continue
        sections[canonical] = markdown[match.end() : end]
    return sections, errors


def section_has_meaningful_content(section: str) -> bool:
    without_comments = re.sub(r"<!--.*?-->", "", section, flags=re.DOTALL)
    placeholders = re.compile(
        r"^(?:(?:todo|tbd|待补充|待填写|待定)(?:\s*[:：].*)?|\.\.\.|<[^>]+>)$",
        re.IGNORECASE,
    )
    for line in without_comments.splitlines():
        candidate = line.strip()
        candidate = re.sub(r"^(?:[-*+]\s*|\d+[.)]\s*)", "", candidate).strip()
        candidate = re.sub(r"^\[[ xX]\]\s*", "", candidate).strip()
        candidate = re.sub(r"^#{1,6}\s*", "", candidate).strip()
        candidate = candidate.strip("`*_~ ")
        if not candidate or re.fullmatch(r"\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)+\|?", candidate) or placeholders.fullmatch(candidate):
            continue
        return True
    return False


def section_has_concrete_content(section: str, heading: str, artifact_type: str) -> bool:
    """Reject heading echoes and generic completion words while preserving localized prose."""
    without_comments = re.sub(r"<!--.*?-->", "", section, flags=re.DOTALL)
    aliases = SECTION_ALIASES.get(artifact_type, {}).get(heading, ())
    heading_forms = {normalize_heading(value) for value in (heading, *aliases)}
    generic_forms = {
        "done",
        "pass",
        "passed",
        "complete",
        "completed",
        "none",
        "n a",
        "完成",
        "已完成",
        "通过",
        "无",
    }
    for line in without_comments.splitlines():
        candidate = line.strip()
        candidate = re.sub(r"^(?:[-*+]\s*|\d+[.)]\s*)", "", candidate).strip()
        candidate = re.sub(r"^\[[ xX]\]\s*", "", candidate).strip()
        candidate = re.sub(r"^#{1,6}\s*", "", candidate).strip()
        candidate = candidate.strip("`*_~ ")
        if not candidate:
            continue
        normalized = normalize_heading(re.sub(r"[^\w\u4e00-\u9fff]+", " ", candidate))
        if not normalized:
            continue
        words = normalized.split()
        if normalized in heading_forms or normalized in generic_forms:
            continue
        if words and len(set(words)) == 1 and words[0] in heading_forms:
            continue
        return True
    return False


def validate_reused_spec_content(sections: dict[str, str]) -> list[str]:
    """Reject template-like reuse without treating two legitimate restatements as an error."""
    signatures: dict[str, list[str]] = {}
    for heading in REQUIRED_SECTIONS["spec"]:
        without_comments = re.sub(r"<!--.*?-->", "", sections.get(heading, ""), flags=re.DOTALL)
        normalized = unicodedata.normalize("NFKC", without_comments).casefold()
        normalized = re.sub(r"(?:^|\n)\s*(?:[-*+]\s*|\d+[.)]\s*)", " ", normalized)
        normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if normalized:
            signatures.setdefault(normalized, []).append(heading)
    errors: list[str] = []
    for headings in signatures.values():
        if len(headings) >= 3:
            errors.append("reused identical content across sections: " + ", ".join(headings))
    return errors


def extract_result(markdown: str) -> str | None:
    for line in markdown.splitlines():
        match = re.match(r"^Result:\s*(\S+)\s*$", line.strip())
        if match:
            return match.group(1).strip()
    return None


def extract_section(markdown: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(markdown)
    if match is None:
        return ""
    start = match.end()
    next_heading = re.search(r"^##\s+", markdown[start:], re.MULTILINE)
    if next_heading is None:
        return markdown[start:]
    return markdown[start : start + next_heading.start()]


def extract_label_value(section: str, label: str) -> str | None:
    pattern = re.compile(rf"^[ \t]*-[ \t]+{re.escape(label)}:[ \t]*(.*?)[ \t]*$", re.MULTILINE)
    match = pattern.search(section)
    if match is None:
        return None
    return match.group(1).strip()


def validate_tdd_report_section(markdown: str) -> list[str]:
    section_name = "Test-First Or Substitute Verification"
    section = extract_section(markdown, section_name)
    if not section:
        return [f"missing section: {section_name}"]

    errors: list[str] = []
    for label in TDD_SECTION_LABELS:
        if extract_label_value(section, label) is None:
            errors.append(f"{section_name}: missing field {label!r}")

    mode = extract_label_value(section, "Gate mode")
    if mode and mode not in VALID_VERIFICATION_GATE_MODES:
        choices = ", ".join(sorted(VALID_VERIFICATION_GATE_MODES))
        errors.append(f"{section_name}: Gate mode must be one of {choices}; got {mode!r}")
    elif mode in {"strict_tdd", "test_first_evidence"}:
        for label in (*TDD_TRACE_REQUIRED_LABELS, *TDD_RED_GREEN_LABELS):
            if not extract_label_value(section, label):
                errors.append(f"{section_name}: {mode} requires non-empty field {label!r}")
    elif mode == "substitute":
        for label in (*TDD_TRACE_REQUIRED_LABELS, "Substitute check", "No-test reason"):
            if not extract_label_value(section, label):
                errors.append(f"{section_name}: substitute requires non-empty field {label!r}")
    return errors


def validate_evaluator_gate_section(markdown: str) -> list[str]:
    section_name = "Testing Gate Evidence Checked"
    section = extract_section(markdown, section_name)
    if not section:
        return [f"missing section: {section_name}"]

    errors: list[str] = []
    for label in EVALUATOR_GATE_LABELS:
        if extract_label_value(section, label) is None:
            errors.append(f"{section_name}: missing field {label!r}")
    return errors


def validate_label_section(markdown: str, section_name: str, labels: tuple[str, ...]) -> list[str]:
    section = extract_section(markdown, section_name)
    if not section:
        return [f"missing section: {section_name}"]
    return [
        f"{section_name}: missing field {label!r}"
        for label in labels
        if extract_label_value(section, label) is None
    ]


def validate_progress_snapshot(markdown: str, section: str = "") -> list[str]:
    section_name = "Snapshot"
    section = section or extract_section(markdown, section_name)
    if not section:
        return [f"missing section: {section_name}"]

    errors: list[str] = []
    for label in PROGRESS_SNAPSHOT_LABELS:
        value = extract_label_value(section, label)
        if value is None:
            errors.append(f"{section_name}: missing field {label!r}")
        elif value == "":
            errors.append(f"{section_name}: field {label!r} must not be empty; use n/a if unknown")

    verification_status = extract_label_value(section, "verification_status")
    if verification_status and verification_status not in VALID_PROGRESS_VERIFICATION_STATUSES:
        choices = ", ".join(sorted(VALID_PROGRESS_VERIFICATION_STATUSES))
        errors.append(f"{section_name}: verification_status must be one of {choices}; got {verification_status!r}")
    return errors


def validate_lite_review_status(markdown: str) -> list[str]:
    section_name = "Status"
    section = extract_section(markdown, section_name)
    if not section:
        return [f"missing section: {section_name}"]

    status = extract_label_value(section, "status")
    if status is None:
        return [f"{section_name}: missing field 'status'"]
    if status not in VALID_LITE_REVIEW_STATUSES:
        choices = ", ".join(sorted(VALID_LITE_REVIEW_STATUSES))
        return [f"{section_name}: status must be one of {choices}; got {status!r}"]
    return []


def validate_verification_gate(value: object, prefix: str, *, active: bool = False) -> list[str]:
    if not isinstance(value, dict):
        return [f"{prefix} must be an object"]

    errors: list[str] = []
    for field in VERIFICATION_GATE_FIELDS:
        if field not in value:
            errors.append(f"{prefix} missing {field}")
        elif not isinstance(value[field], str):
            errors.append(f"{prefix}.{field} must be a string")

    mode = value.get("mode")
    if isinstance(mode, str) and mode not in VALID_VERIFICATION_GATE_MODES:
        choices = ", ".join(sorted(VALID_VERIFICATION_GATE_MODES))
        errors.append(f"{prefix}.mode must be one of {choices}; got {mode!r}")
    if active and mode in {"strict_tdd", "test_first_evidence"}:
        required = (
            "tdd_trace_path",
            "red_command",
            "red_result",
            "red_failure_reason",
            "green_command",
            "green_result",
        )
        if mode == "strict_tdd":
            required = (*required, "refactor_check")
        for field in required:
            if not isinstance(value.get(field), str) or not str(value[field]).strip():
                errors.append(f"{prefix}: {mode} requires non-empty {field}")
    elif active and mode == "substitute":
        for field in ("substitute_check", "no_test_reason"):
            if not isinstance(value.get(field), str) or not str(value[field]).strip():
                errors.append(f"{prefix}: substitute requires non-empty {field}")
    elif active and mode == "not_applicable":
        if not isinstance(value.get("no_test_reason"), str) or not str(value["no_test_reason"]).strip():
            errors.append(f"{prefix}: not_applicable requires non-empty no_test_reason")
    return errors


def validate_state_layers(value: object, prefix: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{prefix} must be an object"]

    errors: list[str] = []
    mode = "full"
    if isinstance(value.get("_mode"), str):
        mode = str(value["_mode"])

    if mode == "lite":
        required_layers = (
            "working_state",
            "memory_boundary",
        )
    else:
        required_layers = (
            "working_state",
            "session_state",
            "execution_log",
            "memory_boundary",
        )
    for layer in required_layers:
        if layer not in value:
            errors.append(f"{prefix} missing {layer}")
        elif not isinstance(value[layer], dict):
            errors.append(f"{prefix}.{layer} must be an object")

    memory_boundary = value.get("memory_boundary")
    if isinstance(memory_boundary, dict):
        candidates = memory_boundary.get("memory_candidates")
        if candidates is None:
            errors.append(f"{prefix}.memory_boundary missing memory_candidates")
        elif not isinstance(candidates, list):
            errors.append(f"{prefix}.memory_boundary.memory_candidates must be a list")
        if "promotion_required" not in memory_boundary:
            errors.append(f"{prefix}.memory_boundary missing promotion_required")
        for forbidden in ("durable_memory", "cross_task_memory"):
            if forbidden in memory_boundary:
                errors.append(f"{prefix}.memory_boundary must not contain {forbidden}; use memory_candidates")

    execution_log = value.get("execution_log")
    if isinstance(execution_log, dict):
        if mode != "lite":
            if execution_log.get("trace_path") != "trace.jsonl":
                errors.append(f"{prefix}.execution_log.trace_path must be 'trace.jsonl'")
            if execution_log.get("tdd_trace_path") != "tdd_trace.jsonl":
                errors.append(f"{prefix}.execution_log.tdd_trace_path must be 'tdd_trace.jsonl'")
            if execution_log.get("append_only") is not True:
                errors.append(f"{prefix}.execution_log.append_only must be true")

    session_state = value.get("session_state")
    if mode != "lite" and isinstance(session_state, dict):
        artifact_paths = session_state.get("artifact_paths")
        if not isinstance(artifact_paths, dict):
            errors.append(f"{prefix}.session_state.artifact_paths must be an object")
        else:
            expected_paths = {
                "task_spec": "task_spec.md",
                "progress": "progress.md",
                "acceptance_registry": "acceptance_registry.json",
                "trace": "trace.jsonl",
                "tdd_trace": "tdd_trace.jsonl",
            }
            for key, expected in expected_paths.items():
                if artifact_paths.get(key) != expected:
                    errors.append(f"{prefix}.session_state.artifact_paths.{key} must be {expected!r}")
        delegation_state = session_state.get("delegation_state")
        if not isinstance(delegation_state, list):
            errors.append(f"{prefix}.session_state.delegation_state must be a list")
    return errors


def validate_continuation(value: object, prefix: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{prefix} must be an object"]

    errors: list[str] = []
    if value.get("protocol") != CONTINUATION_PROTOCOL:
        errors.append(f"{prefix}.protocol must be {CONTINUATION_PROTOCOL!r}")
    status = value.get("status")
    if status not in CONTINUATION_STATUSES:
        errors.append(f"{prefix}.status has unsupported status {status!r}")

    owner = value.get("owner")
    if not isinstance(owner, dict):
        errors.append(f"{prefix}.owner must be an object")
        owner = {}
    for key in ("actor_id", "runtime", "claimed_at"):
        if not isinstance(owner.get(key), str):
            errors.append(f"{prefix}.owner.{key} must be a string")
    epoch = owner.get("epoch")
    if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 0:
        errors.append(f"{prefix}.owner.epoch must be a non-negative integer")
    if status in {"active", "ready"}:
        for key in ("actor_id", "runtime", "claimed_at"):
            if not str(owner.get(key) or "").strip():
                errors.append(f"{prefix}.owner.{key} must not be empty for status {status}")
        if not isinstance(epoch, int) or epoch < 1:
            errors.append(f"{prefix}.owner.epoch must be positive for status {status}")

    previous_owner = value.get("previous_owner")
    if not isinstance(previous_owner, dict):
        errors.append(f"{prefix}.previous_owner must be an object")
    takeover_count = value.get("takeover_count")
    if not isinstance(takeover_count, int) or isinstance(takeover_count, bool) or takeover_count < 0:
        errors.append(f"{prefix}.takeover_count must be a non-negative integer")

    checkpoint = value.get("checkpoint")
    if not isinstance(checkpoint, dict):
        errors.append(f"{prefix}.checkpoint must be an object")
        checkpoint = {}
    for key in ("id", "checkpointed_at", "actor_id", "runtime", "reason", "current_task", "next_action"):
        if not isinstance(checkpoint.get(key), str):
            errors.append(f"{prefix}.checkpoint.{key} must be a string")
    sequence = checkpoint.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        errors.append(f"{prefix}.checkpoint.sequence must be a non-negative integer")
    if not str(checkpoint.get("next_action") or "").strip():
        errors.append(f"{prefix}.checkpoint.next_action must not be empty")
    if not isinstance(checkpoint.get("pending_verification"), list):
        errors.append(f"{prefix}.checkpoint.pending_verification must be a list")
    repository = checkpoint.get("repository")
    if not isinstance(repository, dict):
        errors.append(f"{prefix}.checkpoint.repository must be an object")
    else:
        for key in ("root", "cwd", "branch", "head"):
            if not isinstance(repository.get(key), str):
                errors.append(f"{prefix}.checkpoint.repository.{key} must be a string")
        dirty_paths = repository.get("dirty_paths")
        if not isinstance(dirty_paths, list) or not all(isinstance(item, str) for item in dirty_paths):
            errors.append(f"{prefix}.checkpoint.repository.dirty_paths must be a string list")
        dirty_entries = repository.get("dirty_entries")
        if dirty_entries is not None and (
            not isinstance(dirty_entries, dict)
            or not all(
                isinstance(key, str) and isinstance(item, str)
                for key, item in dirty_entries.items()
            )
        ):
            errors.append(f"{prefix}.checkpoint.repository.dirty_entries must be a string map")
        worktree_digest = repository.get("worktree_digest")
        if worktree_digest is not None and not isinstance(worktree_digest, str):
            errors.append(f"{prefix}.checkpoint.repository.worktree_digest must be a string")

    last_resume = value.get("last_resume")
    if not isinstance(last_resume, dict):
        errors.append(f"{prefix}.last_resume must be an object")
    else:
        for key in ("resumed_at", "actor_id", "runtime", "takeover_reason"):
            if not isinstance(last_resume.get(key), str):
                errors.append(f"{prefix}.last_resume.{key} must be a string")
        if not isinstance(last_resume.get("forced"), bool):
            errors.append(f"{prefix}.last_resume.forced must be a boolean")
    return errors


def validate_state_witness_record(value: object, prefix: str, run_state_path: Path, run_status: object) -> list[str]:
    if not isinstance(value, dict):
        return [f"{prefix} must be an object"]

    errors: list[str] = []
    required = value.get("required")
    if not isinstance(required, bool):
        errors.append(f"{prefix}.required must be a boolean")
        required = False
    path_value = value.get("path")
    if not isinstance(path_value, str):
        errors.append(f"{prefix}.path must be a string")
        path_value = ""
    required_tier = value.get("required_tier")
    if required_tier not in VERIFICATION_TIERS:
        errors.append(f"{prefix}.required_tier must be one of {', '.join(VERIFICATION_TIERS)}")
    observed_tier = value.get("observed_tier")
    if observed_tier not in ("", *VERIFICATION_TIERS):
        errors.append(f"{prefix}.observed_tier must be empty or one of {', '.join(VERIFICATION_TIERS)}")
    review_status = value.get("review_status")
    if review_status not in STATE_WITNESS_REVIEW_STATUSES:
        errors.append(f"{prefix}.review_status has unsupported status {review_status!r}")
    for key in ("reviewer_id", "sealed_digest", "reviewed_at"):
        if not isinstance(value.get(key), str):
            errors.append(f"{prefix}.{key} must be a string")
    errors.extend(
        validate_evidence_list(
            value.get("review_evidence"),
            f"{prefix}.review_evidence",
            subject="state_witness",
            protected=review_status == "pass",
            policy=EVIDENCE_POLICY,
        )
    )

    if not required:
        if path_value or review_status != "not_required":
            errors.append(f"{prefix}: non-required witness must have empty path and not_required review_status")
        return errors

    if not path_value or Path(path_value).is_absolute() or ".." in Path(path_value).parts:
        errors.append(f"{prefix}.path must be a safe relative path when required")
    else:
        witness_path = (run_state_path.parent / path_value).resolve()
        if not witness_path.is_file():
            errors.append(f"{prefix}.path does not exist: {path_value}")
        else:
            errors.extend(f"{prefix}: {error}" for error in validate_state_witness(witness_path, True))
            sealed_digest = str(value.get("sealed_digest") or "")
            if sealed_digest and hashlib.sha256(witness_path.read_bytes()).hexdigest() != sealed_digest:
                errors.append(f"{prefix}.sealed_digest does not match {path_value}")

    if run_status in {"accepted", "handed_off"}:
        if review_status != "pass":
            errors.append(f"{prefix}.review_status must be pass before run status {run_status}")
        if not str(value.get("reviewer_id") or "").strip():
            errors.append(f"{prefix}.reviewer_id is required before run status {run_status}")
        if observed_tier in VERIFICATION_TIERS and required_tier in VERIFICATION_TIERS:
            if VERIFICATION_TIERS.index(observed_tier) < VERIFICATION_TIERS.index(required_tier):
                errors.append(f"{prefix}.observed_tier must reach required_tier before run status {run_status}")
    return errors


def validate_acceptance_registry(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON: {exc}"]

    if not isinstance(data, dict):
        return [f"{path.name}: root must be an object"]
    if data.get("version") != SCHEMA_VERSION:
        errors.append(f"{path.name}: version must be {SCHEMA_VERSION}")
    evidence_policy = data.get("evidence_policy")
    if evidence_policy not in {None, EVIDENCE_POLICY}:
        errors.append(f"{path.name}: unsupported evidence_policy {evidence_policy!r}")
    criteria = data.get("criteria")
    if not isinstance(criteria, list):
        errors.append(f"{path.name}: criteria must be a list")
        return errors
    if not criteria:
        errors.append(f"{path.name}: criteria must not be empty")
        return errors

    criterion_ids: set[str] = set()
    for index, item in enumerate(criteria, start=1):
        prefix = f"{path.name}: criteria[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for key in (
            "id",
            "description",
            "status",
            "required_evidence",
            "required_verification_tier",
            "pass_algorithm",
            "evidence",
            "owner",
            "verification_gate",
        ):
            if key not in item:
                errors.append(f"{prefix} missing {key}")
        criterion_id = item.get("id")
        if isinstance(criterion_id, str):
            if criterion_id in criterion_ids:
                errors.append(f"{prefix}.id duplicates {criterion_id!r}")
            criterion_ids.add(criterion_id)
        if "status" in item:
            if not isinstance(item["status"], str):
                errors.append(f"{prefix}.status must be a string")
            elif item["status"] not in VALID_ACCEPTANCE_STATUSES:
                errors.append(f"{prefix}.status unsupported status {item['status']!r}")
        if "evidence" in item:
            errors.extend(
                validate_evidence_list(
                    item["evidence"],
                    f"{prefix}.evidence",
                    subject=f"acceptance:{criterion_id}",
                    protected=item.get("status") == "pass",
                    policy=evidence_policy,
                )
            )
            if item.get("status") == "scoped_out" and not item["evidence"]:
                errors.append(f"{prefix}.evidence must not be empty for status 'scoped_out'")
        if "required_evidence" in item and not isinstance(item["required_evidence"], list):
            errors.append(f"{prefix}.required_evidence must be a list")
        if item.get("required_verification_tier") not in VERIFICATION_TIERS:
            errors.append(
                f"{prefix}.required_verification_tier must be one of {', '.join(VERIFICATION_TIERS)}"
            )
        if "pass_algorithm" in item and not isinstance(item["pass_algorithm"], str):
            errors.append(f"{prefix}.pass_algorithm must be a string")
        if item.get("status") == "pass" and not str(item.get("pass_algorithm") or "").strip():
            errors.append(f"{prefix}.pass_algorithm must not be empty for status {item.get('status')!r}")
        if "verification_gate" in item:
            errors.extend(
                validate_verification_gate(
                    item["verification_gate"],
                    f"{prefix}.verification_gate",
                    active=item.get("status") == "pass",
                )
            )
    return errors


def validate_run_state(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON: {exc}"]

    if not isinstance(data, dict):
        return [f"{path.name}: root must be an object"]
    if data.get("version") != SCHEMA_VERSION:
        errors.append(f"{path.name}: version must be {SCHEMA_VERSION}")
    evidence_policy = data.get("evidence_policy")
    if evidence_policy not in {None, EVIDENCE_POLICY}:
        errors.append(f"{path.name}: unsupported evidence_policy {evidence_policy!r}")
    routing_policy = data.get("routing_policy")
    if routing_policy not in {None, MODEL_ROUTING_POLICY}:
        errors.append(f"{path.name}: unsupported routing_policy {routing_policy!r}")
    mode = data.get("mode", "full")
    if not isinstance(mode, str):
        errors.append(f"{path.name}: mode must be a string")
        mode = "full"
    elif mode not in VALID_MODES:
        choices = ", ".join(sorted(VALID_MODES))
        errors.append(f"{path.name}: mode must be one of {choices}; got {mode!r}")
    if not isinstance(data.get("status"), str):
        errors.append(f"{path.name}: status must be a string")
    elif data["status"] not in VALID_RUN_STATUSES:
        errors.append(f"{path.name}: unsupported status {data['status']!r}")
    if "state_witness" not in data:
        errors.append(f"{path.name}: missing state_witness")
    else:
        errors.extend(
            validate_state_witness_record(
                data["state_witness"],
                f"{path.name}: state_witness",
                path,
                data.get("status"),
            )
        )
    if "state_layers" in data:
        state_layers = data["state_layers"]
        if isinstance(state_layers, dict):
            state_layers = dict(state_layers)
            state_layers["_mode"] = mode
        errors.extend(validate_state_layers(state_layers, f"{path.name}: state_layers"))
    else:
        errors.append(f"{path.name}: missing state_layers")
    if "continuation" in data:
        errors.extend(validate_continuation(data["continuation"], f"{path.name}: continuation"))

    stages = data.get("stages")
    tasks = data.get("tasks")
    if not isinstance(stages, list):
        errors.append(f"{path.name}: stages must be a list")
        stages = []
    if not isinstance(tasks, list):
        errors.append(f"{path.name}: tasks must be a list")
        tasks = []

    task_ids: set[str] = set()
    for index, item in enumerate(tasks, start=1):
        prefix = f"{path.name}: tasks[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for key in (
            "id",
            "name",
            "stage",
            "status",
            "owner",
            "allowed_scope",
            "dependencies",
            "expected_outputs",
            "verification",
            "verification_gate",
            "retry_count",
            "evidence",
            "stop_reason",
        ):
            if key not in item:
                errors.append(f"{prefix} missing {key}")
        if isinstance(item.get("id"), str):
            if item["id"] in task_ids:
                errors.append(f"{prefix}.id duplicates {item['id']!r}")
            task_ids.add(item["id"])
        if "status" in item and item["status"] not in VALID_TASK_STATUSES:
            errors.append(f"{prefix}: unsupported status {item['status']!r}")
        if "evidence" in item:
            errors.extend(
                validate_evidence_list(
                    item["evidence"],
                    f"{prefix}.evidence",
                    subject=f"task:{item.get('id')}",
                    protected=item.get("status") in {"passed", "merged"},
                    policy=evidence_policy,
                )
            )
        for key in ("allowed_scope", "dependencies", "expected_outputs", "verification"):
            if key in item and not isinstance(item[key], list):
                errors.append(f"{prefix}.{key} must be a list")
        if "verification_gate" in item:
            errors.extend(
                validate_verification_gate(
                    item["verification_gate"],
                    f"{prefix}.verification_gate",
                    active=item.get("status") in {"passed", "merged"},
                )
            )
        if "retry_count" in item and not isinstance(item["retry_count"], int):
            errors.append(f"{prefix}.retry_count must be an integer")
        budget = item.get("runtime_budget_seconds")
        if budget is not None:
            if not isinstance(budget, (int, float)) or isinstance(budget, bool) or budget <= 0 or not __import__("math").isfinite(budget):
                errors.append(f"{prefix}.runtime_budget_seconds must be a positive finite number")
        for key in ("required_cwd", "repository_root", "required_branch"):
            if key in item and not isinstance(item[key], str):
                errors.append(f"{prefix}.{key} must be a string")

    session_state = data.get("state_layers", {}).get("session_state", {}) if isinstance(data.get("state_layers"), dict) else {}
    dispatches = session_state.get("delegation_state", []) if isinstance(session_state, dict) else []
    dispatch_ids: set[str] = set()
    active_tasks: set[str] = set()
    task_map = {str(item.get("id")): item for item in tasks if isinstance(item, dict)}
    if isinstance(dispatches, list):
        for index, item in enumerate(dispatches, start=1):
            prefix = f"{path.name}: delegation_state[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{prefix} must be an object")
                continue
            for key in (
                "dispatch_id", "worker_id", "task_id", "contract_path", "report_path",
                "status", "created_at", "updated_at", "stop_reason",
            ):
                if key not in item:
                    errors.append(f"{prefix} missing {key}")
            if routing_policy == MODEL_ROUTING_POLICY:
                for key in (
                    "runtime", "profile", "requested_model", "resolved_model",
                    "reasoning_effort", "route_reason", "escalation_count",
                ):
                    if key not in item:
                        errors.append(f"{prefix} missing {key}")
            dispatch_id = item.get("dispatch_id")
            if isinstance(dispatch_id, str):
                if dispatch_id in dispatch_ids:
                    errors.append(f"{prefix}.dispatch_id duplicates {dispatch_id!r}")
                dispatch_ids.add(dispatch_id)
            for key in ("dispatch_id", "worker_id", "task_id", "contract_path", "report_path", "status", "created_at", "updated_at", "stop_reason"):
                if key in item and not isinstance(item[key], str):
                    errors.append(f"{prefix}.{key} must be a string")
            for key in ("runtime", "profile", "requested_model", "resolved_model", "reasoning_effort", "route_reason"):
                if key in item and not isinstance(item[key], str):
                    errors.append(f"{prefix}.{key} must be a string")
            profile = item.get("profile")
            if isinstance(profile, str) and profile not in AGENT_PROFILES:
                errors.append(f"{prefix}.profile unsupported profile {profile!r}")
            escalation_count = item.get("escalation_count")
            if escalation_count is not None and (
                not isinstance(escalation_count, int) or isinstance(escalation_count, bool) or escalation_count < 0
            ):
                errors.append(f"{prefix}.escalation_count must be a non-negative integer")
            if routing_policy == MODEL_ROUTING_POLICY:
                runtime = str(item.get("runtime") or "").strip()
                if not runtime:
                    errors.append(f"{prefix}.runtime must not be empty")
                elif runtime != runtime.casefold():
                    errors.append(f"{prefix}.runtime must be lowercase")
                if not str(item.get("route_reason") or "").strip():
                    errors.append(f"{prefix}.route_reason must not be empty")
                sealed_profiles = model_profiles_for(runtime)
                if sealed_profiles is not None and isinstance(profile, str) and profile in sealed_profiles:
                    configured = sealed_profiles[profile]
                    runtime_label = runtime.casefold()
                    if item.get("requested_model") != configured["model"]:
                        errors.append(f"{prefix}.requested_model must match {runtime_label} profile {profile!r}")
                    if item.get("reasoning_effort") != configured["reasoning_effort"]:
                        errors.append(f"{prefix}.reasoning_effort must match {runtime_label} profile {profile!r}")
                    if runtime_label == "codex" and "terra" in str(item.get("resolved_model") or "").casefold():
                        errors.append(f"{prefix}.resolved_model must not use disabled Terra models")
            if not str(item.get("worker_id") or "").strip():
                errors.append(f"{prefix}.worker_id must not be empty")
            status = item.get("status")
            if isinstance(status, str) and status not in DISPATCH_STATUSES:
                errors.append(f"{prefix}.status unsupported status {status!r}")
            task_id = str(item.get("task_id") or "")
            task = task_map.get(task_id)
            if task is None:
                errors.append(f"{prefix}.task_id references unknown task {task_id!r}")
            else:
                if item.get("contract_path") != task.get("task_path"):
                    errors.append(f"{prefix}.contract_path must match task_path")
                if item.get("report_path") != task.get("report_path"):
                    errors.append(f"{prefix}.report_path must match task report_path")
            for key in ("contract_path", "report_path"):
                value = item.get(key)
                if isinstance(value, str) and (Path(value).is_absolute() or ".." in Path(value).parts):
                    errors.append(f"{prefix}.{key} must be a safe artifact-relative path")
            if status in {"dispatched", "running"}:
                if task_id in active_tasks:
                    errors.append(f"{prefix}: task has more than one active dispatch {task_id!r}")
                active_tasks.add(task_id)
            if status in {"failed", "cancelled"} and not str(item.get("stop_reason") or "").strip():
                errors.append(f"{prefix}.stop_reason is required for status {status!r}")

    stage_ids: set[str] = set()
    for item in stages:
        if isinstance(item, dict) and isinstance(item.get("id"), (str, int)):
            stage_id = str(item["id"])
            if stage_id in stage_ids:
                errors.append(f"{path.name}: duplicate stage id {stage_id!r}")
            stage_ids.add(stage_id)

    current_stage = data.get("current_stage")
    if current_stage not in {None, ""} and str(current_stage) not in stage_ids:
        errors.append(f"{path.name}: current_stage references unknown stage {current_stage!r}")

    for index, item in enumerate(tasks, start=1):
        if not isinstance(item, dict):
            continue
        prefix = f"{path.name}: tasks[{index}]"
        if item.get("stage") is not None and str(item["stage"]) not in stage_ids:
            errors.append(f"{prefix}.stage references unknown stage {item.get('stage')!r}")
        dependencies = item.get("dependencies")
        if isinstance(dependencies, list):
            for dependency in dependencies:
                if dependency not in task_ids:
                    errors.append(f"{prefix}.dependencies references unknown task {dependency!r}")
                if dependency == item.get("id"):
                    errors.append(f"{prefix}.dependencies must not reference itself")

    for index, item in enumerate(stages, start=1):
        prefix = f"{path.name}: stages[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for key in ("id", "name", "status", "tasks", "evidence", "stop_reason"):
            if key not in item:
                errors.append(f"{prefix} missing {key}")
        if "status" in item and item["status"] not in VALID_TASK_STATUSES:
            errors.append(f"{prefix}: unsupported status {item['status']!r}")
        if "tasks" in item and not isinstance(item["tasks"], list):
            errors.append(f"{prefix}.tasks must be a list")
        elif isinstance(item.get("tasks"), list):
            for task_id in item["tasks"]:
                if task_id not in task_ids:
                    errors.append(f"{prefix}.tasks references unknown task {task_id!r}")
        if "evidence" in item and not isinstance(item["evidence"], list):
            errors.append(f"{prefix}.evidence must be a list")

    task_map = {
        str(item.get("id")): item
        for item in tasks if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    stage_map = {
        str(item.get("id")): item
        for item in stages if isinstance(item, dict) and isinstance(item.get("id"), (str, int))
    }
    for task_id, task in task_map.items():
        stage_id = str(task.get("stage"))
        stage = stage_map.get(stage_id)
        if stage is not None and isinstance(stage.get("tasks"), list) and task_id not in stage["tasks"]:
            errors.append(f"{path.name}: task {task_id!r} is missing from declared stage {stage_id!r}")
        if task.get("status") == "running" and isinstance(task.get("dependencies"), list):
            incomplete = [
                str(dependency)
                for dependency in task["dependencies"]
                if task_map.get(str(dependency), {}).get("status") not in {"passed", "merged"}
            ]
            if incomplete:
                errors.append(
                    f"{path.name}: running task {task_id!r} has incomplete dependencies: " + ", ".join(incomplete)
                )
    for stage_id, stage in stage_map.items():
        if not isinstance(stage.get("tasks"), list):
            continue
        for task_id in stage["tasks"]:
            task = task_map.get(str(task_id))
            if task is not None and str(task.get("stage")) != stage_id:
                errors.append(
                    f"{path.name}: stage {stage_id!r} lists task {task_id!r} declared in stage {task.get('stage')!r}"
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        if task_id in visiting:
            errors.append(f"{path.name}: task dependency cycle includes {task_id!r}")
            return
        visiting.add(task_id)
        dependencies = task_map[task_id].get("dependencies")
        if isinstance(dependencies, list):
            for dependency in dependencies:
                if isinstance(dependency, str) and dependency in task_map:
                    visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in task_map:
        visit(task_id)
    return errors


def validate_protocol_files(artifact_dir: Path) -> list[str]:
    errors: list[str] = []
    validators = {
        "acceptance_registry.json": validate_acceptance_registry,
        "run_state.json": validate_run_state,
    }
    for filename, validator in validators.items():
        path = artifact_dir / filename
        if path.exists():
            errors.extend(validator(path))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a multi-agent Markdown artifact.")
    parser.add_argument("path", help="Artifact file to validate.")
    parser.add_argument(
        "--type",
        choices=sorted([*REQUIRED_SECTIONS, "acceptance", "run_state"]),
        required=True,
        help="Artifact type to validate.",
    )
    parser.add_argument(
        "--require-filled",
        action="store_true",
        help="Require semantic content in every required Markdown section.",
    )
    args = parser.parse_args()

    path = Path(args.path).resolve()
    if not path.exists():
        print(f"FAIL missing file: {path}")
        return 2

    if args.type in {"acceptance", "run_state"}:
        validator = validate_acceptance_registry if args.type == "acceptance" else validate_run_state
        errors = validator(path)
        if errors:
            print(f"FAIL {path}")
            print("errors:")
            for error in errors:
                print(f"- {error}")
            return 1
        print(f"PASS {path}")
        return 0

    markdown = path.read_text(encoding="utf-8")
    sections, section_errors = extract_semantic_sections(markdown, args.type)
    headings = set(sections)
    required = set(REQUIRED_SECTIONS[args.type])
    missing = sorted(required - headings)
    errors = [*section_errors, *(f"missing section: {section}" for section in missing)]
    if args.require_filled:
        for section in sorted(required & headings):
            if not section_has_meaningful_content(sections[section]):
                errors.append(f"section must not be empty: {section}")
            elif args.type == "spec" and not section_has_concrete_content(sections[section], section, args.type):
                errors.append(f"section lacks concrete content: {section}")
        if args.type == "spec":
            errors.extend(validate_reused_spec_content(sections))

    if args.type == "evaluator":
        result = extract_result(markdown)
        if result is None:
            errors.append("missing Result line")
        elif result not in VALID_RESULTS:
            errors.append(f"Result must be one of {', '.join(sorted(VALID_RESULTS))}; got {result!r}")
        errors.extend(validate_evaluator_gate_section(markdown))
        errors.extend(validate_label_section(markdown, "Production State Witness Checked", STATE_WITNESS_LABELS))
        errors.extend(validate_label_section(markdown, "Verification Tier", VERIFICATION_TIER_LABELS))
    elif args.type == "subagent":
        errors.extend(validate_tdd_report_section(markdown))
        errors.extend(validate_label_section(markdown, "Production State Witness", SUBAGENT_STATE_WITNESS_LABELS))
    elif args.type == "progress":
        errors.extend(validate_progress_snapshot(markdown, sections.get("Snapshot", "")))
    elif args.type == "lite_review":
        result = extract_result(markdown)
        if result is not None and result not in VALID_RESULTS:
            errors.append(f"Result must be one of {', '.join(sorted(VALID_RESULTS))}; got {result!r}")
        errors.extend(validate_lite_review_status(markdown))

    if args.type in {"progress", "evaluator", "spec", "lite_plan", "lite_review"}:
        errors.extend(validate_protocol_files(path.parent))

    if errors:
        print(f"FAIL {path}")
        print("errors:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"PASS {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
