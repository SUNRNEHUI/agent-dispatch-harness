#!/usr/bin/env python3
"""Validate a Production State Witness before stateful behavior work starts."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_HEADINGS = (
    "## Symptom and terminal condition",
    "## Actual call chain",
    "## State inputs",
    "## Truth table",
    "## Unknowns and instrumentation",
    "## Verification tier",
)
PLACEHOLDER_PATTERNS = (
    re.compile(r"^\s*$"),
    re.compile(r"\.{3}"),
    re.compile(r"\b(?:TODO|TBD|FIXME)\b", re.IGNORECASE),
    re.compile(r"<[^>]+>"),
)


def is_placeholder(value: str | list[str]) -> bool:
    if isinstance(value, list):
        value = " | ".join(value)
    return any(pattern.search(value) for pattern in PLACEHOLDER_PATTERNS)


def section_body(text: str, heading: str) -> str:
    match = re.search(
        rf"^{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s|\Z)",
        text,
        flags=re.MULTILINE,
    )
    return match.group(1).strip() if match else ""


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_separator(line: str) -> bool:
    return bool(re.fullmatch(r"\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)+\|?", line.strip()))


def markdown_table(body: str) -> tuple[list[str], list[list[str]]]:
    lines = [line.strip() for line in body.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        return [], []
    header = split_row(lines[0])
    rows = [split_row(line) for line in lines[1:] if not is_separator(line)]
    return header, rows


def normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def table_rows(body: str) -> tuple[list[str], list[list[str]]]:
    header, rows = markdown_table(body)
    return [normalize_label(value) for value in header], rows


def has_empty_cell(row: list[str]) -> bool:
    cells = [cell.strip() for cell in row]
    return any(not cell for cell in cells)


def contains_locator(value: str) -> bool:
    return bool(
        re.search(
            r"(?:/|::|\b(?:python3?|pytest|xcodebuild|swift\s+test|npm\s+test|cargo\s+test|go\s+test)\b|\.(?:swift|py|js|ts|m|mm|go|rs|java|sh)\b)",
            value,
            flags=re.IGNORECASE,
        )
    )


def validate(path: Path, require_filled: bool) -> list[str]:
    if not path.exists() or not path.is_file():
        return [f"missing witness file: {path}"]
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    if not re.search(r"^# Production State Witness\s*$", text, flags=re.MULTILINE):
        errors.append("missing title: # Production State Witness")
    for heading in REQUIRED_HEADINGS:
        if not re.search(rf"^{re.escape(heading)}\s*$", text, flags=re.MULTILINE):
            errors.append(f"missing heading: {heading}")

    call_chain = section_body(text, "## Actual call chain")
    if call_chain.count("->") < 2:
        errors.append("actual call chain must contain at least two '->' links")

    state_header, state_rows = table_rows(section_body(text, "## State inputs"))
    if not state_rows:
        errors.append("state inputs table has no data rows")
    required_state_columns = {
        "input",
        "producer",
        "lifecycle event",
        "source locator",
        "reported value",
    }
    if not required_state_columns.issubset(set(state_header)):
        errors.append("state inputs table must include Input, Producer, Lifecycle/event, Source locator, and Reported value")

    truth_header, truth_rows = table_rows(section_body(text, "## Truth table"))
    if len(truth_rows) < 3:
        errors.append("truth table must contain failing, fixed, and preserved-block rows")
    required_truth_columns = {"case", "production state", "observed before", "expected after", "executable evidence"}
    if not required_truth_columns.issubset(set(truth_header)):
        errors.append("truth table must include Case, Production state, Observed before, Expected after, and Executable evidence")
    truth_text = "\n".join(" | ".join(row) for row in truth_rows).lower()
    for case_label in ("failing", "fixed", "preserved"):
        if case_label not in truth_text:
            errors.append(f"truth table is missing a '{case_label}' case row")

    if require_filled:
        for heading in REQUIRED_HEADINGS:
            body = section_body(text, heading)
            if not body or is_placeholder(body):
                errors.append(f"section is empty or placeholder-only: {heading}")
        if not contains_locator(call_chain):
            errors.append("actual call chain must include a source or executable locator")
        verification_body = section_body(text, "## Verification tier")
        for label in (
            "Required tier",
            "Observed tier",
            "Review status",
            "Independent reviewer",
            "Review evidence path",
        ):
            if not re.search(rf"^\s*-\s*{re.escape(label)}\s*:\s*\S", verification_body, flags=re.MULTILINE | re.IGNORECASE):
                errors.append(f"verification tier section must include a filled '{label}' field")
        for index, row in enumerate(state_rows, start=1):
            if is_placeholder(row) or has_empty_cell(row):
                errors.append(f"state input row {index} is empty or placeholder-only")
            elif len(row) >= 5 and not contains_locator(row[3]):
                errors.append(f"state input row {index} must include a source locator")
        for index, row in enumerate(truth_rows, start=1):
            if is_placeholder(row) or has_empty_cell(row):
                errors.append(f"truth table row {index} is empty or placeholder-only")
            elif len(row) >= 5 and not contains_locator(row[4]):
                errors.append(f"truth table row {index} must include executable evidence locator")

        if len(truth_header) >= 5 and len(truth_rows) >= 2:
            columns = {name: index for index, name in enumerate(truth_header)}
            failing = next((row for row in truth_rows if "failing" in " ".join(row).casefold()), None)
            fixed = next((row for row in truth_rows if "fixed" in " ".join(row).casefold()), None)
            if failing and fixed:
                state_index = columns.get("production state")
                if state_index is not None and len(failing) > state_index and len(fixed) > state_index:
                    if failing[state_index].strip() != fixed[state_index].strip():
                        errors.append("failing and fixed rows must use the same production state")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Production State Witness.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--require-filled", action="store_true")
    args = parser.parse_args()
    errors = validate(args.path.expanduser().resolve(), args.require_filled)
    if errors:
        for error in errors:
            print(f"FAIL {error}", file=sys.stderr)
        return 1
    print(f"PASS {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
