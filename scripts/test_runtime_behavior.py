#!/usr/bin/env python3
"""Runtime behavior checks for packaging, init, validators, and status output."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
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


def test_timeout_records_timeout_context() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-timeout-"))
    try:
        trace = temp / "trace.jsonl"
        state = temp / "run_state.json"
        write_json(state, {"tasks": [{"id": "1.1", "runtime_budget_seconds": 1}]})
        result = run([
            "python3", "scripts/harness_test_run.py", "--trace", str(trace),
            "--task-id", "1.1", "--phase", "GREEN", "--run-state", str(state),
            "--timeout", "0.05", "--", sys.executable, "-c", "import time; time.sleep(1)",
        ], check=False)
        assert_true(result.returncode == 124, f"timeout should return 124: {result.returncode}")
        event = json.loads(trace.read_text(encoding="utf-8").strip())
        assert_true(event["result"] == "TIMEOUT", event)
        assert_true(event["timeout_seconds"] == 0.05, event)
        context = load_json(state)["tdd_current_cycle_context"]
        assert_true(context["result"] == "TIMEOUT", context)
    finally:
        shutil.rmtree(temp)


def test_non_manager_state_writer_is_rejected() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-writer-"))
    try:
        state = temp / "run_state.json"
        write_json(state, {"status": "intake"})
        result = run([
            "python3", "-c",
            "import sys; sys.path.insert(0, 'scripts'); from runtime_state import update_json; "
            f"update_json({str(state)!r}, {{'status': 'running'}}, writer_role='worker')",
        ], check=False)
        assert_true(result.returncode != 0, "worker state writer must be rejected")
        assert_true(load_json(state)["status"] == "intake", "rejected writer changed state")
    finally:
        shutil.rmtree(temp)


def test_writer_scope_is_explicit_and_task_local_worker_allowed() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-scope-"))
    try:
        state = temp / "run_state.json"
        trace = temp / "task.jsonl"
        write_json(state, {"tasks": [{"id": "1.1", "runtime_budget_seconds": 1800}]})
        omitted = run(["python3", "-c", "import sys; sys.path.insert(0,'scripts'); from runtime_state import update_json; update_json('" + str(state) + "', {'x': 1})"], check=False)
        assert_true(omitted.returncode != 0, "omitted writer role must fail")
        manager_scope_omitted = run(["python3", "-c", "import sys; sys.path.insert(0,'scripts'); from runtime_state import update_json; update_json('" + str(state) + "', {'x': 2}, writer_role='manager')"], check=False)
        assert_true(manager_scope_omitted.returncode != 0, "manager must provide explicit scope")
        worker = run(["python3", "-c", "import sys; sys.path.insert(0,'scripts'); from runtime_state import append_jsonl; append_jsonl('" + str(trace) + "', {'x': 1}, writer_role='worker', scope='task-local')"])
        assert_true(worker.returncode == 0, worker.stderr)
        global_worker = run(["python3", "-c", "import sys; sys.path.insert(0,'scripts'); from runtime_state import append_jsonl; append_jsonl('" + str(trace) + "', {'x': 2}, writer_role='worker', scope='global')"], check=False)
        assert_true(global_worker.returncode != 0, "worker global trace must fail")
    finally:
        shutil.rmtree(temp)


def test_concurrent_failures_preserve_retry_count_and_full_output() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-retry-"))
    try:
        state = temp / "run_state.json"
        trace = temp / "trace.jsonl"
        write_json(state, {"tasks": [{"id": "1.1", "runtime_budget_seconds": 1800}]})
        commands = []
        for _ in range(30):
            commands.append(subprocess.Popen(["python3", "scripts/harness_test_run.py", "--trace", str(trace), "--task-id", "1.1", "--phase", "GREEN", "--run-state", str(state), "--", sys.executable, "-c", """import sys; print('\\n'.join(f'OUT{i}' for i in range(60))); sys.stderr.write('ERR-no-newline') ; raise SystemExit(1)"""], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        for process in commands:
            process.communicate()
        context = load_json(state)["tdd_current_cycle_context"]
        assert_true(context["retry_count"] == 30, context)
        output = run(["python3", "scripts/harness_test_run.py", "--trace", str(trace), "--task-id", "2.1", "--phase", "GREEN", "--", sys.executable, "-c", """import sys; print('\\n'.join(f'OUT{i}' for i in range(60))); sys.stderr.write('ERR-no-newline')"""], check=False)
        assert_true("OUT0" in output.stdout and "OUT59" in output.stdout, "normal stdout must not be tailed")
        assert_true("ERR-no-newline" in output.stderr, output.stderr)
    finally:
        shutil.rmtree(temp)


def test_workspace_cli_reads_real_git_and_run_state_task() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-git-"))
    try:
        run(["git", "init", "-q"], cwd=temp)
        run(["git", "config", "user.email", "test@example.com"], cwd=temp)
        run(["git", "config", "user.name", "Test"], cwd=temp)
        (temp / "x").write_text("x", encoding="utf-8")
        run(["git", "add", "x"], cwd=temp)
        run(["git", "commit", "-qm", "init"], cwd=temp)
        run(["git", "branch", "-M", "bound"], cwd=temp)
        task = {"required_cwd": str(temp), "repository_root": str(temp), "required_branch": "bound"}
        state = temp / "run_state.json"
        write_json(state, {"tasks": [{"id": "1.1", **task}]})
        ok = run(["python3", str(ROOT / "scripts/validate_workspace.py"), str(state), "--task-id", "1.1", "--workspace", str(temp)])
        assert_true(ok.returncode == 0, ok.stdout + ok.stderr)
        fake = run(["python3", str(ROOT / "scripts/validate_workspace.py"), str(state), "--task-id", "1.1", "--cwd", str(temp), "--branch", "bound"], check=False)
        assert_true(fake.returncode != 0, "CLI must not accept spoofed branch input")
        for malformed in ({"tasks": None}, {"tasks": {"id": "1.1"}}):
            malformed_state = temp / "malformed-run-state.json"
            write_json(malformed_state, malformed)
            result = run(["python3", str(ROOT / "scripts/validate_workspace.py"), str(malformed_state), "--task-id", "1.1", "--workspace", str(temp)], check=False)
            assert_true(result.returncode == 2 and "Traceback" not in result.stderr, result.stderr)
        missing = run(["python3", str(ROOT / "scripts/validate_workspace.py"), str(state), "--task-id", "missing", "--workspace", str(temp)], check=False)
        assert_true(missing.returncode == 2 and "Traceback" not in missing.stderr, missing.stderr)
    finally:
        shutil.rmtree(temp)


def test_timeout_budget_and_corrupt_state_rejection() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-budget-"))
    try:
        trace = temp / "trace.jsonl"
        bad_state = temp / "bad.json"
        bad_state.write_text("{bad", encoding="utf-8")
        result = run(["python3", "scripts/harness_test_run.py", "--trace", str(trace), "--task-id", "1", "--phase", "GREEN", "--run-state", str(bad_state), "--", sys.executable, "-c", "pass"], check=False)
        assert_true(result.returncode != 0 and bad_state.read_text(encoding="utf-8") == "{bad", "corrupt state must be preserved")
        invalid = run(["python3", "scripts/harness_test_run.py", "--trace", str(trace), "--task-id", "1", "--phase", "GREEN", "--timeout-seconds", "2", "--runtime-budget-seconds", "1", "--", sys.executable, "-c", "pass"], check=False)
        assert_true(invalid.returncode == 2 and "Traceback" not in invalid.stderr and "NameError" not in invalid.stderr, invalid.stderr)
    finally:
        shutil.rmtree(temp)


def test_run_state_task_and_budget_errors_are_controlled() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-bound-budget-"))
    try:
        trace = temp / "trace.jsonl"
        state = temp / "run_state.json"
        write_json(state, {"tasks": [{"id": "known", "runtime_budget_seconds": 1}]})
        cases = [
            ["--task-id", "unknown"],
            ["--task-id", "known", "--runtime-budget-seconds", "2"],
            ["--task-id", "known", "--timeout-seconds", "2"],
        ]
        for extra in cases:
            result = run(["python3", "scripts/harness_test_run.py", "--trace", str(trace), "--phase", "GREEN", "--run-state", str(state), *extra, "--", sys.executable, "-c", "pass"], check=False)
            assert_true(result.returncode == 2, (extra, result.returncode, result.stderr))
            assert_true("Traceback" not in result.stderr and "NameError" not in result.stderr, result.stderr)
        state.write_text(json.dumps({"tasks": [{"id": "known", "runtime_budget_seconds": 0}]}), encoding="utf-8")
        invalid = run(["python3", "scripts/harness_test_run.py", "--trace", str(trace), "--phase", "GREEN", "--run-state", str(state), "--task-id", "known", "--", sys.executable, "-c", "pass"], check=False)
        assert_true(invalid.returncode == 2 and "Traceback" not in invalid.stderr, invalid.stderr)
        state.write_text(json.dumps({"tasks": None}), encoding="utf-8")
        malformed_tasks = run(["python3", "scripts/harness_test_run.py", "--trace", str(trace), "--phase", "GREEN", "--run-state", str(state), "--task-id", "known", "--", sys.executable, "-c", "pass"], check=False)
        assert_true(malformed_tasks.returncode == 2 and "Traceback" not in malformed_tasks.stderr, malformed_tasks.stderr)
    finally:
        shutil.rmtree(temp)


def test_concurrent_state_and_trace_writes_are_complete() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-concurrent-"))
    try:
        state = temp / "run_state.json"
        trace = temp / "trace.jsonl"
        write_json(state, {})
        def worker(index: int) -> None:
            run(["python3", "-c", "import sys; sys.path.insert(0, 'scripts'); "
                 "from runtime_state import update_json, append_jsonl; "
                 f"update_json({str(state)!r}, {{'index': {index}}}, writer_role='manager', scope='global'); "
                 f"append_jsonl({str(trace)!r}, {{'index': {index}}}, writer_role='manager', scope='global')"])
        threads = [threading.Thread(target=worker, args=(index,)) for index in range(12)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        assert_true(isinstance(load_json(state)["index"], int), "state JSON was corrupted")
        lines = trace.read_text(encoding="utf-8").splitlines()
        assert_true(len(lines) == 12, f"expected 12 JSONL records, got {len(lines)}")
        assert_true(all(isinstance(json.loads(line)["index"], int) for line in lines), "JSONL record corrupted")
    finally:
        shutil.rmtree(temp)


def test_full_task_schema_has_runtime_and_workspace_binding() -> None:
    temp, artifact_dir = full_artifact("schema binding")
    try:
        state = load_json(artifact_dir / "run_state.json")
        task = state["tasks"][0]
        for key in ("runtime_budget_seconds", "required_cwd", "repository_root", "required_branch"):
            assert_true(key in task, f"task missing {key}")
        assert_true(task["runtime_budget_seconds"] == 1800, task)
    finally:
        shutil.rmtree(temp)


def test_workspace_binding_validator_accepts_and_rejects() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-binding-"))
    try:
        branch = run(["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        task = {"required_cwd": str(ROOT), "repository_root": str(ROOT), "required_branch": branch}
        task_path = temp / "task.json"
        write_json(task_path, task)
        ok = run(["python3", "scripts/validate_workspace.py", str(task_path), "--cwd", str(ROOT)], check=False)
        assert_true(ok.returncode == 0, ok.stdout + ok.stderr)
        bad = run(["python3", "scripts/validate_workspace.py", str(task_path), "--cwd", "/tmp"], check=False)
        assert_true(bad.returncode != 0, "workspace mismatch should fail")
        missing = run(["python3", "scripts/validate_workspace.py", str(task_path)], check=False)
        assert_true(missing.returncode == 2 and "Traceback" not in missing.stderr, missing.stderr)
    finally:
        shutil.rmtree(temp)


def test_tdd_trace_template_passes_gate() -> None:
    result = run(["python3", "scripts/tdd_gate_check.py", "templates/tdd_trace.jsonl"], check=False)
    assert_true(result.returncode == 0, result.stdout + result.stderr)


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
        test_writer_scope_is_explicit_and_task_local_worker_allowed,
        test_concurrent_failures_preserve_retry_count_and_full_output,
        test_workspace_cli_reads_real_git_and_run_state_task,
        test_timeout_budget_and_corrupt_state_rejection,
        test_timeout_records_timeout_context,
        test_non_manager_state_writer_is_rejected,
        test_concurrent_state_and_trace_writes_are_complete,
        test_full_task_schema_has_runtime_and_workspace_binding,
        test_workspace_binding_validator_accepts_and_rejects,
        test_run_state_task_and_budget_errors_are_controlled,
        test_tdd_trace_template_passes_gate,
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
