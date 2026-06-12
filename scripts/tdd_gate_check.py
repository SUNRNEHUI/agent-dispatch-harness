#!/usr/bin/env python3
"""Validate runtime-neutral TDD gate traces."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUPPORTED_EVENTS = {
    "gate_decision",
    "test_run",
    "file_modified",
    "substitute_check",
    "review_result",
    "verification_complete",
}
VALID_GATE_MODES = {
    "strict_tdd",
    "test_first_evidence",
    "substitute",
    "not_applicable",
}


@dataclass(frozen=True)
class TraceEvent:
    line_no: int
    index: int
    name: str
    data: dict[str, Any]


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_key(value: object) -> str:
    return normalize_text(value).lower().replace("-", "_")


def normalize_result(value: object) -> str:
    return normalize_text(value).upper()


def first_text(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if normalize_text(value):
            return normalize_text(value)
    return ""


def result_of(event: TraceEvent) -> str:
    return normalize_result(first_text(event.data, "result", "status", "outcome"))


def parse_ts(value: object) -> float | None:
    text = normalize_text(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def phase_of(event: TraceEvent) -> str:
    return normalize_key(first_text(event.data, "phase", "stage"))


def gate_mode_of(event: TraceEvent) -> str:
    return normalize_key(first_text(event.data, "gate_mode", "mode"))


def load_events(path: Path) -> tuple[list[TraceEvent], list[str]]:
    errors: list[str] = []
    events: list[TraceEvent] = []

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [], [f"cannot read file: {exc}"]

    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_no}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(data, dict):
            errors.append(f"line {line_no}: event must be a JSON object")
            continue
        event_name = normalize_key(data.get("event"))
        if not event_name:
            errors.append(f"line {line_no}: missing event")
            continue
        if event_name not in SUPPORTED_EVENTS:
            continue
        events.append(TraceEvent(line_no=line_no, index=len(events), name=event_name, data=data))

    return events, errors


def latest_gate_decision(events: list[TraceEvent]) -> TraceEvent | None:
    for event in reversed(events):
        if event.name == "gate_decision":
            return event
    return None


def first_event(events: list[TraceEvent], name: str) -> TraceEvent | None:
    for event in events:
        if event.name == name:
            return event
    return None


def source_mtime_errors(
    source_paths: list[Path],
    *,
    red_event: TraceEvent | None,
    verification_events: list[TraceEvent],
    tolerance_seconds: float,
) -> list[str]:
    if not source_paths:
        return []
    errors: list[str] = []
    if red_event is None:
        return ["mtime validation requires a RED test_run FAIL event"]
    red_ts = parse_ts(red_event.data.get("ts"))
    if red_ts is None:
        return [f"mtime validation requires parseable RED ts at line {red_event.line_no}"]

    verification_times = [
        parsed
        for event in verification_events
        if (parsed := parse_ts(event.data.get("ts"))) is not None
    ]
    if not verification_times:
        errors.append("mtime validation requires parseable GREEN/REFACTOR/verification PASS timestamp")

    for path in source_paths:
        try:
            mtime = path.stat().st_mtime
        except OSError as exc:
            errors.append(f"cannot stat source path {path}: {exc}")
            continue
        if mtime + tolerance_seconds < red_ts:
            red_display = datetime.fromtimestamp(red_ts, timezone.utc).isoformat().replace("+00:00", "Z")
            mtime_display = datetime.fromtimestamp(mtime, timezone.utc).isoformat().replace("+00:00", "Z")
            errors.append(
                f"source path {path} mtime {mtime_display} is before RED {red_display}; "
                "strict TDD mtime evidence is invalid"
            )
        if verification_times and not any(verified + tolerance_seconds >= mtime for verified in verification_times):
            mtime_display = datetime.fromtimestamp(mtime, timezone.utc).isoformat().replace("+00:00", "Z")
            errors.append(f"source path {path} mtime {mtime_display} has no later GREEN/REFACTOR/verification PASS")
    return errors


def matching_test_runs(
    events: list[TraceEvent],
    *,
    phase: str,
    result: str,
    after_index: int | None = None,
    before_index: int | None = None,
) -> list[TraceEvent]:
    phase_key = normalize_key(phase)
    result_key = normalize_result(result)
    matches = []
    for event in events:
        if event.name != "test_run":
            continue
        if phase_of(event) != phase_key or result_of(event) != result_key:
            continue
        if after_index is not None and event.index <= after_index:
            continue
        if before_index is not None and event.index >= before_index:
            continue
        matches.append(event)
    return matches


def has_substitute_pass(events: list[TraceEvent]) -> bool:
    return any(event.name == "substitute_check" and result_of(event) == "PASS" for event in events)


def has_verification_pass(events: list[TraceEvent], after_index: int | None = None) -> bool:
    for event in events:
        if event.name != "verification_complete" or result_of(event) != "PASS":
            continue
        if after_index is not None and event.index <= after_index:
            continue
        return True
    return False


def has_gap_evidence(events: list[TraceEvent]) -> bool:
    for event in events:
        if first_text(event.data, "gap_evidence", "gap"):
            return True
        for key in ("evidence_type", "kind", "category", "phase"):
            if normalize_key(event.data.get(key)) == "gap":
                return True
    return False


def has_no_test_reason(events: list[TraceEvent]) -> bool:
    return any(first_text(event.data, "no_test_reason") for event in events)


def validate_strict_tdd(
    events: list[TraceEvent],
    *,
    source_paths: list[Path],
    tolerance_seconds: float,
) -> list[str]:
    errors: list[str] = []
    first_modified = first_event(events, "file_modified")

    if first_modified is None and not source_paths:
        errors.append("strict_tdd requires a file_modified event")

    red_before_edit = []
    if first_modified is not None:
        red_before_edit = matching_test_runs(events, phase="RED", result="FAIL", before_index=first_modified.index)
    elif source_paths:
        red_before_edit = matching_test_runs(events, phase="RED", result="FAIL")
    if not red_before_edit:
        if source_paths:
            errors.append("strict_tdd requires a RED test_run FAIL before source mtime validation")
        else:
            errors.append("strict_tdd requires a RED test_run FAIL before the first file_modified event")

    green_after_edit = []
    if first_modified is not None:
        green_after_edit = matching_test_runs(events, phase="GREEN", result="PASS", after_index=first_modified.index)
    elif source_paths:
        green_after_edit = matching_test_runs(events, phase="GREEN", result="PASS")
    if not green_after_edit:
        if source_paths:
            errors.append("strict_tdd requires a GREEN test_run PASS after source edits")
        else:
            errors.append("strict_tdd requires a GREEN test_run PASS after file_modified")

    refactor_ok = False
    after_green_index = green_after_edit[0].index if green_after_edit else None
    if after_green_index is not None:
        refactor_ok = bool(matching_test_runs(events, phase="REFACTOR", result="PASS", after_index=after_green_index))
        refactor_ok = refactor_ok or has_verification_pass(events, after_index=after_green_index)
    if not refactor_ok:
        errors.append("strict_tdd requires a REFACTOR test_run PASS or verification_complete PASS after GREEN")

    red_event = red_before_edit[0] if red_before_edit else None
    verification_events = green_after_edit + matching_test_runs(events, phase="REFACTOR", result="PASS")
    verification_events.extend(
        event for event in events if event.name == "verification_complete" and result_of(event) == "PASS"
    )
    errors.extend(
        source_mtime_errors(
            source_paths,
            red_event=red_event,
            verification_events=verification_events,
            tolerance_seconds=tolerance_seconds,
        )
    )

    return errors


def validate_test_first_evidence(events: list[TraceEvent]) -> list[str]:
    errors: list[str] = []
    red_fail = matching_test_runs(events, phase="RED", result="FAIL")
    if not red_fail and not has_gap_evidence(events):
        errors.append("test_first_evidence requires a RED test_run FAIL or GAP evidence")
    if not matching_test_runs(events, phase="GREEN", result="PASS"):
        errors.append("test_first_evidence requires a GREEN test_run PASS")
    return errors


def validate_substitute(events: list[TraceEvent]) -> list[str]:
    errors: list[str] = []
    if not has_no_test_reason(events):
        errors.append("substitute requires no_test_reason")
    if not has_substitute_pass(events):
        errors.append("substitute requires a substitute_check PASS")
    return errors


def validate_not_applicable(gate: TraceEvent) -> list[str]:
    if not first_text(gate.data, "reason", "applicability_reason"):
        return ["not_applicable requires reason"]
    return []


def validate_trace(path: Path, *, source_paths: list[Path], tolerance_seconds: float) -> list[str]:
    events, errors = load_events(path)
    if errors:
        return errors

    gate = latest_gate_decision(events)
    if gate is None:
        return ["missing gate_decision event"]

    gate_mode = gate_mode_of(gate)
    if gate_mode not in VALID_GATE_MODES:
        choices = ", ".join(sorted(VALID_GATE_MODES))
        return [f"gate_decision gate_mode must be one of {choices}; got {gate_mode!r}"]

    if gate_mode == "strict_tdd":
        return validate_strict_tdd(events, source_paths=source_paths, tolerance_seconds=tolerance_seconds)
    if gate_mode == "test_first_evidence":
        return validate_test_first_evidence(events)
    if gate_mode == "substitute":
        return validate_substitute(events)
    if gate_mode == "not_applicable":
        return validate_not_applicable(gate)
    return [f"unsupported gate_mode: {gate_mode}"]


def expand_inputs(inputs: list[str]) -> tuple[list[Path], list[tuple[Path, list[str]]]]:
    files: list[Path] = []
    input_errors: list[tuple[Path, list[str]]] = []

    for raw_path in inputs:
        path = Path(raw_path)
        if not path.exists():
            input_errors.append((path, ["path does not exist"]))
        elif path.is_dir():
            matches = sorted(path.rglob("tdd_trace.jsonl"))
            if matches:
                files.extend(matches)
            else:
                input_errors.append((path, ["directory contains no tdd_trace.jsonl files"]))
        elif path.is_file():
            files.append(path)
        else:
            input_errors.append((path, ["path is neither a file nor a directory"]))

    return files, input_errors


def print_result(path: Path, errors: list[str]) -> None:
    if errors:
        print(f"FAIL {path}")
        print("errors:")
        for error in errors:
            print(f"- {error}")
    else:
        print(f"PASS {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate TDD gate trace JSONL files.")
    parser.add_argument(
        "--source-path",
        action="append",
        default=[],
        help="Source file modified in this TDD cycle. Enables physical mtime checks for strict_tdd.",
    )
    parser.add_argument(
        "--mtime-tolerance-seconds",
        type=float,
        default=1.0,
        help="Clock/filesystem tolerance for source mtime comparisons.",
    )
    parser.add_argument("paths", nargs="+", help="tdd_trace.jsonl files or directories containing them.")
    args = parser.parse_args()
    source_paths = [Path(raw).expanduser() for raw in args.source_path]

    files, input_errors = expand_inputs(args.paths)
    failed = False

    for path, errors in input_errors:
        print_result(path, errors)
        failed = True

    for path in files:
        errors = validate_trace(
            path,
            source_paths=source_paths,
            tolerance_seconds=args.mtime_tolerance_seconds,
        )
        print_result(path, errors)
        failed = failed or bool(errors)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
