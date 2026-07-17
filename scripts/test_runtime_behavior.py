#!/usr/bin/env python3
"""Runtime checks for the current packaged harness contract."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"command failed: {' '.join(args)}\n{result.stdout}\n{result.stderr}")
    return result


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def init_artifact(temp: Path, *, mode: str, title: str, state_witness: bool = False) -> Path:
    command = [
        "python3",
        "scripts/init_run.py",
        "--mode",
        mode,
        "--project-root",
        str(temp),
        "--title",
        title,
        "--agents",
        "docs,review" if mode == "full" else "",
        "--force",
    ]
    if state_witness:
        command.extend(["--with-state-witness", "--required-verification-tier", "user_visible"])
    run(command)
    return temp / "workspace" / title.replace(" ", "-")


def mark_full_passed(artifact_dir: Path) -> None:
    """Build a valid accepted fixture through the public controller commands."""
    run(["python3", "scripts/harnessctl.py", "seal", str(artifact_dir), "--reason", "runtime test fixture"])
    state = load_json(artifact_dir / "run_state.json")
    for task in state["tasks"]:
        run(["python3", "scripts/harnessctl.py", "task-set", str(artifact_dir), "--task-id", str(task["id"]), "--status", "ready"])
    for status in ("gated", "specified", "dispatched"):
        run(["python3", "scripts/harnessctl.py", "run-set", str(artifact_dir), "--status", status])

    state = load_json(artifact_dir / "run_state.json")
    for task in state["tasks"]:
        task_id = str(task["id"])
        report_path = artifact_dir / str(task["report_path"])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(f"# Report {task_id}\n\nRuntime fixture evidence.\n", encoding="utf-8")
        run(
            [
                "python3",
                "scripts/harnessctl.py",
                "dispatch-create",
                str(artifact_dir),
                "--worker-id",
                f"worker-{task_id}",
                "--task-id",
                task_id,
                "--contract-path",
                str(task["task_path"]),
                "--report-path",
                str(task["report_path"]),
            ]
        )
        state = load_json(artifact_dir / "run_state.json")
        dispatch = next(
            item
            for item in state["state_layers"]["session_state"]["delegation_state"]
            if item["task_id"] == task_id
        )
        run(
            [
                "python3",
                "scripts/harnessctl.py",
                "dispatch-update",
                str(artifact_dir),
                "--dispatch-id",
                str(dispatch["dispatch_id"]),
                "--status",
                "reported",
            ]
        )
        run(["python3", "scripts/harnessctl.py", "task-set", str(artifact_dir), "--task-id", task_id, "--status", "running"])
        run(
            [
                "python3",
                "scripts/harnessctl.py",
                "task-set",
                str(artifact_dir),
                "--task-id",
                task_id,
                "--status",
                "passed",
                "--evidence-file",
                "progress.md",
                "--no-test-reason",
                "runtime fixture uses substitute verification",
            ]
        )

    run(
        [
            "python3",
            "scripts/harnessctl.py",
            "acceptance-set",
            str(artifact_dir),
            "--criterion-id",
            "AC-001",
            "--status",
            "pass",
            "--evidence-file",
            "progress.md",
            "--pass-algorithm",
            "runtime fixture reaches accepted state",
            "--no-test-reason",
            "runtime fixture uses substitute verification",
        ]
    )
    for status in ("reported", "evaluating"):
        run(["python3", "scripts/harnessctl.py", "run-set", str(artifact_dir), "--status", status])
    run(["python3", "scripts/harnessctl.py", "run-set", str(artifact_dir), "--status", "accepted", "--evidence-file", "progress.md"])


def test_progress_template_is_lightweight() -> None:
    text = (ROOT / "templates" / "progress_ledger.md").read_text(encoding="utf-8")
    headings = {line[3:].strip() for line in text.splitlines() if line.startswith("## ")}
    assert len(text.splitlines()) <= 35
    assert not headings.intersection({"Run State", "Working State", "Session State", "Execution Log", "Task Ledger"})


def test_lite_init_is_minimal_and_state_witness_is_opt_in() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-lite-"))
    try:
        artifact = init_artifact(temp, mode="lite", title="lite behavior")
        assert sorted(str(path.relative_to(artifact)) for path in artifact.rglob("*") if path.is_file()) == [
            "lite_plan.md",
            "run_state.json",
        ]
        state = load_json(artifact / "run_state.json")
        assert state["state_witness"]["required"] is False

        stateful = init_artifact(temp, mode="lite", title="lite stateful", state_witness=True)
        state = load_json(stateful / "run_state.json")
        assert state["state_witness"]["required"] is True
        assert (stateful / "state_witness.md").is_file()
    finally:
        shutil.rmtree(temp)


def test_full_lifecycle_reaches_high_confidence() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-full-"))
    try:
        artifact = init_artifact(temp, mode="full", title="high confidence")
        mark_full_passed(artifact)
        result = run(["python3", "scripts/status.py", str(artifact / "run_state.json")])
        assert "Acceptance: 1 pass, 0 pending, 0 fail, 0 blocked, 0 scoped_out" in result.stdout
        assert "Completion confidence: high" in result.stdout
        assert "Integrity errors: none" in result.stdout
    finally:
        shutil.rmtree(temp)


def test_integrity_breaker_prevents_high_confidence() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-integrity-"))
    try:
        artifact = init_artifact(temp, mode="full", title="integrity breaker")
        state_path = artifact / "run_state.json"
        state = load_json(state_path)
        state["status"] = "accepted"
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = run(["python3", "scripts/status.py", str(state_path)])
        assert "Integrity errors:" in result.stdout
        assert "Completion confidence: high" not in result.stdout
    finally:
        shutil.rmtree(temp)


def test_negative_validator_and_package_check() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-package-"))
    try:
        bad_review = temp / "lite_review.md"
        bad_review.write_text(
            (ROOT / "templates" / "lite_review.md").read_text(encoding="utf-8").replace("blocked", "maybe"),
            encoding="utf-8",
        )
        result = run(["python3", "scripts/validate_report.py", str(bad_review), "--type", "lite_review"], check=False)
        assert result.returncode != 0
        assert "status must be one of" in result.stdout

        package_dir = temp / "pkg"
        run(["python3", "scripts/package_skill.py", "--output", str(package_dir), "--force"])
        (package_dir / "EXTRA").write_text("x", encoding="utf-8")
        result = run(["python3", "scripts/package_skill.py", "--check", str(package_dir)], check=False)
        assert result.returncode != 0
        assert "extra in install: EXTRA" in result.stdout
    finally:
        shutil.rmtree(temp)


def test_runtime_package_contains_state_witness_runtime() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-witness-package-"))
    try:
        package_dir = temp / "pkg"
        run(["python3", "scripts/package_skill.py", "--output", str(package_dir), "--force"])
        for relative in (
            "references/state-witness.md",
            "scripts/state_witness_check.py",
            "templates/state_witness.md",
        ):
            assert (package_dir / relative).is_file(), relative
    finally:
        shutil.rmtree(temp)


def test_trigger_shortcuts_route_without_forcing_full() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8").lower()
    default_prompt = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8").lower()
    master_prompt = (ROOT / "master-prompt.md").read_text(encoding="utf-8").lower()

    for trigger in ("你是主 agent", "写一个 harness", "写一个harness"):
        assert trigger in skill
        assert trigger in default_prompt
        assert trigger in master_prompt
    for text in (default_prompt, master_prompt):
        assert "multi-agent dispatch" in text
        assert "you are the main agent" in text
        assert "do not force full" in text
        for mode in ("direct", "lite", "full"):
            assert mode in text


def test_routing_and_superpowers_policies_are_present() -> None:
    routing = (ROOT / "references" / "model-routing.md").read_text(encoding="utf-8")
    adapter = (ROOT / "adapters" / "codex.md").read_text(encoding="utf-8")
    integration = (ROOT / "references" / "superpowers-integration.md").read_text(encoding="utf-8")
    for term in ("gpt-5.6-luna", "gpt-5.6-sol", "deterministic selector", "validation failures"):
        assert term in routing
    assert "gpt-5.6-luna" in adapter
    for term in ("Do not escalate", "review gates", "separate checks", "Do not copy whole"):
        assert term in integration


def main() -> int:
    tests = [
        test_progress_template_is_lightweight,
        test_lite_init_is_minimal_and_state_witness_is_opt_in,
        test_full_lifecycle_reaches_high_confidence,
        test_integrity_breaker_prevents_high_confidence,
        test_negative_validator_and_package_check,
        test_runtime_package_contains_state_witness_runtime,
        test_trigger_shortcuts_route_without_forcing_full,
        test_routing_and_superpowers_policies_are_present,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
