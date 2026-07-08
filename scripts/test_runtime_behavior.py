#!/usr/bin/env python3
"""Runtime behavior checks for packaging, init, validators, and status output."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str], *, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise AssertionError(f"command failed: {' '.join(args)}")
    return result


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_progress_template_is_lightweight() -> None:
    progress = ROOT / "templates" / "progress_ledger.md"
    text = progress.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert_true(len(lines) <= 35, f"progress_ledger.md should stay lightweight, got {len(lines)} lines")
    forbidden = {
        "Run State",
        "Working State",
        "Session State",
        "Execution Log",
        "Memory Boundary",
        "Stage Ledger",
        "Task Ledger",
    }
    headings = {line[3:].strip() for line in lines if line.startswith("## ")}
    assert_true(not (headings & forbidden), f"progress_ledger.md mirrors machine state: {headings & forbidden}")


def test_lite_init_is_minimal() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-lite-"))
    try:
        run(
            [
                "python3",
                "scripts/init_run.py",
                "--mode",
                "lite",
                "--project-root",
                str(temp),
                "--title",
                "lite behavior",
                "--agents",
                "docs,review",
                "--force",
            ]
        )
        artifact_dir = temp / "workspace" / "lite-behavior"
        files = sorted(str(path.relative_to(artifact_dir)) for path in artifact_dir.rglob("*") if path.is_file())
        assert_true(files == ["lite_plan.md", "run_state.json"], f"lite mode generated unexpected files: {files}")

        state = json.loads((artifact_dir / "run_state.json").read_text(encoding="utf-8"))
        assert_true(state["mode"] == "lite", "lite run_state must record mode=lite")
        assert_true("tdd_current_cycle_context" not in state, "lite run_state should not include TDD cycle context")
        layers = state["state_layers"]
        assert_true(set(layers) == {"working_state", "memory_boundary"}, f"lite state_layers are too heavy: {set(layers)}")
    finally:
        shutil.rmtree(temp)


def test_lite_plan_has_single_worker_table() -> None:
    text = (ROOT / "templates" / "lite_plan.md").read_text(encoding="utf-8")
    assert_true("## Workers" in text, "lite_plan.md must contain Workers")
    assert_true("## Scope" not in text, "lite_plan.md should not duplicate Scope and Workers tables")


def test_status_output_from_run_state() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-status-"))
    try:
        run(
            [
                "python3",
                "scripts/init_run.py",
                "--mode",
                "full",
                "--project-root",
                str(temp),
                "--title",
                "status behavior",
                "--agents",
                "docs,review",
                "--force",
            ]
        )
        artifact_dir = temp / "workspace" / "status-behavior"
        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        output = result.stdout
        assert_true("Run: status behavior | Mode: full | Status: intake" in output, output)
        assert_true("Stage 1: initial execution [planned]" in output, output)
        assert_true("1.1 docs planned" in output, output)
        assert_true("Blockers: none" in output, output)
    finally:
        shutil.rmtree(temp)


def test_negative_validators_and_package_check() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-negative-"))
    try:
        bad_review = temp / "lite_review.md"
        bad_review.write_text((ROOT / "templates" / "lite_review.md").read_text(encoding="utf-8").replace("blocked", "maybe"), encoding="utf-8")
        result = run(["python3", "scripts/validate_report.py", str(bad_review), "--type", "lite_review"], check=False)
        assert_true(result.returncode != 0, "invalid lite_review status should fail")
        assert_true("status must be one of" in result.stdout, result.stdout)

        package_dir = temp / "pkg"
        run(["python3", "scripts/package_skill.py", "--output", str(package_dir), "--force"])
        (package_dir / "EXTRA").write_text("x", encoding="utf-8")
        result = run(["python3", "scripts/package_skill.py", "--check", str(package_dir)], check=False)
        assert_true(result.returncode != 0, "package --check should fail on extra files")
        assert_true("extra in install: EXTRA" in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)


def main() -> int:
    tests = [
        test_progress_template_is_lightweight,
        test_lite_init_is_minimal,
        test_lite_plan_has_single_worker_table,
        test_status_output_from_run_state,
        test_negative_validators_and_package_check,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
