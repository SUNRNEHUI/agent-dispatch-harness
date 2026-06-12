#!/usr/bin/env python3
"""Validate required Markdown sections for multi-agent artifacts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIRED_SECTIONS = {
    "subagent": [
        "Goal",
        "Files Touched",
        "Commands Run",
        "Test-First Or Substitute Verification",
        "Evidence",
        "Unresolved Risks",
        "Assumptions Affecting Merge",
        "Stub TODO Mock Or Unverified Path",
        "Return Summary",
    ],
    "evaluator": [
        "Scope Checked",
        "Testing Gate Evidence Checked",
        "Evidence",
        "Blocking Issues",
        "Non-Blocking Issues",
        "Stub Or Placeholder Check",
        "Required Fixes",
        "Residual Risk",
    ],
    "progress": [
        "Artifact Location",
        "Current Goal",
        "Completed",
        "Changed Files",
        "Decisions",
        "Commands And Evidence",
        "Verification",
        "Open Risks",
        "Stop Conditions Checked",
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
}


VALID_RESULTS = {"PASS", "FAIL", "BLOCKED"}
VALID_ACCEPTANCE_STATUSES = {"pending", "pass", "fail", "blocked", "scoped_out"}
VALID_RUN_STATUSES = {
    "intake",
    "gated",
    "specified",
    "dispatched",
    "reported",
    "evaluating",
    "accepted",
    "handed_off",
    "blocked",
    "needs_decision",
    "failed",
    "unplanned",
}
VALID_TASK_STATUSES = {
    "planned",
    "ready",
    "running",
    "blocked",
    "verify_failed",
    "passed",
    "merged",
    "cancelled",
    "unplanned",
}
VALID_VERIFICATION_GATE_MODES = {
    "strict_tdd",
    "test_first_evidence",
    "substitute",
    "not_applicable",
}
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


def extract_headings(markdown: str) -> set[str]:
    headings = set()
    for line in markdown.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            headings.add(match.group(1).strip())
    return headings


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


def validate_verification_gate(value: object, prefix: str) -> list[str]:
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
    return errors


def validate_acceptance_registry(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON: {exc}"]

    if not isinstance(data, dict):
        return [f"{path.name}: root must be an object"]
    if data.get("version") != 1:
        errors.append(f"{path.name}: version must be 1")
    criteria = data.get("criteria")
    if not isinstance(criteria, list):
        errors.append(f"{path.name}: criteria must be a list")
        return errors
    if not criteria:
        errors.append(f"{path.name}: criteria must not be empty")
        return errors

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
            "evidence",
            "owner",
            "verification_gate",
        ):
            if key not in item:
                errors.append(f"{prefix} missing {key}")
        if "status" in item:
            if not isinstance(item["status"], str):
                errors.append(f"{prefix}.status must be a string")
            elif item["status"] not in VALID_ACCEPTANCE_STATUSES:
                errors.append(f"{prefix}.status unsupported status {item['status']!r}")
        if "evidence" in item and not isinstance(item["evidence"], list):
            errors.append(f"{prefix}.evidence must be a list")
        if "required_evidence" in item and not isinstance(item["required_evidence"], list):
            errors.append(f"{prefix}.required_evidence must be a list")
        if "verification_gate" in item:
            errors.extend(validate_verification_gate(item["verification_gate"], f"{prefix}.verification_gate"))
    return errors


def validate_run_state(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON: {exc}"]

    if not isinstance(data, dict):
        return [f"{path.name}: root must be an object"]
    if data.get("version") != 1:
        errors.append(f"{path.name}: version must be 1")
    if not isinstance(data.get("status"), str):
        errors.append(f"{path.name}: status must be a string")
    elif data["status"] not in VALID_RUN_STATUSES:
        errors.append(f"{path.name}: unsupported status {data['status']!r}")

    stages = data.get("stages")
    tasks = data.get("tasks")
    if not isinstance(stages, list):
        errors.append(f"{path.name}: stages must be a list")
        stages = []
    if not isinstance(tasks, list):
        errors.append(f"{path.name}: tasks must be a list")
        tasks = []

    task_ids = set()
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
            task_ids.add(item["id"])
        if "status" in item and item["status"] not in VALID_TASK_STATUSES:
            errors.append(f"{prefix}: unsupported status {item['status']!r}")
        if "evidence" in item and not isinstance(item["evidence"], list):
            errors.append(f"{prefix}.evidence must be a list")
        for key in ("allowed_scope", "dependencies", "expected_outputs", "verification"):
            if key in item and not isinstance(item[key], list):
                errors.append(f"{prefix}.{key} must be a list")
        if "verification_gate" in item:
            errors.extend(validate_verification_gate(item["verification_gate"], f"{prefix}.verification_gate"))
        if "retry_count" in item and not isinstance(item["retry_count"], int):
            errors.append(f"{prefix}.retry_count must be an integer")

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
    parser.add_argument("path", help="Markdown file to validate.")
    parser.add_argument(
        "--type",
        choices=sorted(REQUIRED_SECTIONS),
        required=True,
        help="Artifact type to validate.",
    )
    args = parser.parse_args()

    path = Path(args.path).resolve()
    if not path.exists():
        print(f"FAIL missing file: {path}")
        return 2

    markdown = path.read_text(encoding="utf-8")
    headings = extract_headings(markdown)
    required = set(REQUIRED_SECTIONS[args.type])
    missing = sorted(required - headings)
    errors = [f"missing section: {section}" for section in missing]

    if args.type == "evaluator":
        result = extract_result(markdown)
        if result is None:
            errors.append("missing Result line")
        elif result not in VALID_RESULTS:
            errors.append(f"Result must be one of {', '.join(sorted(VALID_RESULTS))}; got {result!r}")
        errors.extend(validate_evaluator_gate_section(markdown))
    elif args.type == "subagent":
        errors.extend(validate_tdd_report_section(markdown))

    if args.type in {"progress", "evaluator", "spec"}:
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
