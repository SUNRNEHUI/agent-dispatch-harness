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


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def full_artifact(title: str = "status behavior") -> tuple[Path, Path]:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-status-"))
    run(
        [
            "python3",
            "scripts/init_run.py",
            "--mode",
            "full",
            "--project-root",
            str(temp),
            "--title",
            title,
            "--agents",
            "docs,review",
            "--force",
        ]
    )
    return temp, temp / "workspace" / title.replace(" ", "-")


def mark_full_passed(artifact_dir: Path) -> None:
    state_path = artifact_dir / "run_state.json"
    state = load_json(state_path)
    state["status"] = "accepted"
    for task in state["tasks"]:
        task["status"] = "passed"
        task["evidence"] = [f"evidence for {task['id']}"]
    write_json(state_path, state)

    registry_path = artifact_dir / "acceptance_registry.json"
    registry = load_json(registry_path)
    registry["criteria"][0]["status"] = "pass"
    registry["criteria"][0]["required_evidence"] = ["test"]
    registry["criteria"][0]["evidence"] = ["python3 scripts/test_runtime_behavior.py"]
    write_json(registry_path, registry)


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
    temp = Path(tempfile.mkdtemp(prefix="adh-test-basic-status-"))
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


def test_status_high_confidence_when_tasks_and_acceptance_pass() -> None:
    temp, artifact_dir = full_artifact("high confidence")
    try:
        mark_full_passed(artifact_dir)
        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        output = result.stdout
        assert_true("Completion: 2/2 tasks done" in output, output)
        assert_true("Acceptance: 1 pass, 0 pending, 0 fail, 0 blocked, 0 scoped_out" in output, output)
        assert_true("Completion confidence: high" in output, output)
        assert_true("Evidence gaps: none" in output, output)
    finally:
        shutil.rmtree(temp)


def test_status_acceptance_pending_prevents_high_confidence() -> None:
    temp, artifact_dir = full_artifact("pending acceptance")
    try:
        state = load_json(artifact_dir / "run_state.json")
        for task in state["tasks"]:
            task["status"] = "passed"
            task["evidence"] = [f"evidence for {task['id']}"]
        write_json(artifact_dir / "run_state.json", state)

        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        output = result.stdout
        assert_true("Acceptance: 0 pass, 1 pending, 0 fail, 0 blocked, 0 scoped_out" in output, output)
        assert_true("Completion confidence: high" not in output, output)
        assert_true("Next verification: resolve pending acceptance criteria" in output, output)
    finally:
        shutil.rmtree(temp)


def test_status_reports_evidence_gap_for_passed_task_without_evidence() -> None:
    temp, artifact_dir = full_artifact("missing evidence")
    try:
        mark_full_passed(artifact_dir)
        state = load_json(artifact_dir / "run_state.json")
        state["tasks"][0]["evidence"] = []
        write_json(artifact_dir / "run_state.json", state)

        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        output = result.stdout
        assert_true("Evidence gaps: task 1.1 passed without evidence" in output, output)
        assert_true("Completion confidence: high" not in output, output)
    finally:
        shutil.rmtree(temp)


def test_status_blocked_when_task_or_acceptance_blocked() -> None:
    temp, artifact_dir = full_artifact("blocked status")
    try:
        mark_full_passed(artifact_dir)
        state = load_json(artifact_dir / "run_state.json")
        state["tasks"][1]["status"] = "verify_failed"
        state["tasks"][1]["stop_reason"] = "review failed"
        write_json(artifact_dir / "run_state.json", state)

        registry = load_json(artifact_dir / "acceptance_registry.json")
        registry["criteria"][0]["status"] = "blocked"
        registry["criteria"][0]["blocking_issues"] = ["review failed"]
        write_json(artifact_dir / "acceptance_registry.json", registry)

        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        output = result.stdout
        assert_true("Blockers: 1.2 review: review failed" in output, output)
        assert_true("Acceptance: 0 pass, 0 pending, 0 fail, 1 blocked, 0 scoped_out" in output, output)
        assert_true("Completion confidence: blocked" in output, output)
    finally:
        shutil.rmtree(temp)


def test_status_malformed_or_missing_registry_cannot_be_high_confidence() -> None:
    temp, artifact_dir = full_artifact("bad registry")
    try:
        mark_full_passed(artifact_dir)
        (artifact_dir / "acceptance_registry.json").write_text("{bad json", encoding="utf-8")
        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        output = result.stdout
        assert_true("Acceptance: unreadable" in output, output)
        assert_true("Completion confidence: unknown" in output, output)
        assert_true("Completion confidence: high" not in output, output)

        (artifact_dir / "acceptance_registry.json").unlink()
        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        output = result.stdout
        assert_true("Acceptance: missing" in output, output)
        assert_true("Completion confidence: unknown" in output, output)
    finally:
        shutil.rmtree(temp)


def test_status_passed_acceptance_without_evidence_cannot_be_high_confidence() -> None:
    temp, artifact_dir = full_artifact("acceptance evidence gap")
    try:
        mark_full_passed(artifact_dir)
        registry = load_json(artifact_dir / "acceptance_registry.json")
        registry["criteria"][0]["required_evidence"] = []
        registry["criteria"][0]["evidence"] = []
        write_json(artifact_dir / "acceptance_registry.json", registry)

        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        output = result.stdout
        assert_true("Evidence gaps: acceptance AC-001 pass without evidence" in output, output)
        assert_true("Completion confidence: high" not in output, output)
    finally:
        shutil.rmtree(temp)


def test_status_schema_malformed_registry_is_blocked() -> None:
    temp, artifact_dir = full_artifact("registry schema gap")
    try:
        mark_full_passed(artifact_dir)
        registry = load_json(artifact_dir / "acceptance_registry.json")
        registry["criteria"] = {}
        write_json(artifact_dir / "acceptance_registry.json", registry)

        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        output = result.stdout
        assert_true("Evidence gaps: acceptance registry missing criteria list" in output, output)
        assert_true("Completion confidence: blocked" in output, output)
        assert_true("Next verification: repair acceptance_registry.json" in output, output)
    finally:
        shutil.rmtree(temp)


def test_status_reports_accepted_run_with_pending_acceptance_conflict() -> None:
    temp, artifact_dir = full_artifact("accepted conflict")
    try:
        mark_full_passed(artifact_dir)
        registry = load_json(artifact_dir / "acceptance_registry.json")
        registry["criteria"][0]["status"] = "pending"
        registry["criteria"][0]["evidence"] = []
        write_json(artifact_dir / "acceptance_registry.json", registry)

        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        output = result.stdout
        assert_true("State conflicts: run_state accepted but acceptance criteria are pending" in output, output)
        assert_true("Completion confidence: blocked" in output, output)
        assert_true("Next verification: repair accepted run state or acceptance registry" in output, output)
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
        test_status_high_confidence_when_tasks_and_acceptance_pass,
        test_status_acceptance_pending_prevents_high_confidence,
        test_status_reports_evidence_gap_for_passed_task_without_evidence,
        test_status_blocked_when_task_or_acceptance_blocked,
        test_status_malformed_or_missing_registry_cannot_be_high_confidence,
        test_status_passed_acceptance_without_evidence_cannot_be_high_confidence,
        test_status_schema_malformed_registry_is_blocked,
        test_status_reports_accepted_run_with_pending_acceptance_conflict,
        test_negative_validators_and_package_check,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
