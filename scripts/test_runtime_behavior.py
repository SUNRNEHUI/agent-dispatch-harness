#!/usr/bin/env python3
"""Runtime behavior checks for packaging, init, validators, and status output."""

from __future__ import annotations

import json
import hashlib
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

        unterminated = temp / "unterminated.jsonl"
        unterminated.write_text('{"index": 0}', encoding="utf-8")
        run(
            [
                "python3", "-c",
                "import sys; sys.path.insert(0, 'scripts'); from runtime_state import append_jsonl; "
                f"append_jsonl({str(unterminated)!r}, {{'index': 1}}, writer_role='manager', scope='global')",
            ]
        )
        records = [json.loads(line) for line in unterminated.read_text(encoding="utf-8").splitlines()]
        assert_true(records == [{"index": 0}, {"index": 1}], records)
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


def test_tdd_trace_template_is_empty_and_not_evidence() -> None:
    template = ROOT / "templates" / "tdd_trace.jsonl"
    assert_true(template.read_text(encoding="utf-8").strip() == "", "template must not ship fake test evidence")
    result = run(["python3", "scripts/tdd_gate_check.py", str(template)], check=False)
    assert_true(result.returncode != 0, "an empty runtime trace must not satisfy the TDD gate")


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


def mark_tasks_passed(artifact_dir: Path) -> Path:
    evidence_dir = artifact_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    state = load_json(artifact_dir / "run_state.json")
    for task in state["tasks"]:
        created = run(
            [
                "python3", "scripts/harnessctl.py", "dispatch-create", str(artifact_dir),
                "--worker-id", f"fixture/{task['id']}", "--task-id", str(task["id"]),
                "--contract-path", str(task["task_path"]), "--report-path", str(task["report_path"]),
            ]
        )
        dispatch_id = created.stdout.split("dispatch_id=", 1)[1].split()[0]
        evidence_path = evidence_dir / f"task-{task['id']}.txt"
        evidence_path.write_text(f"manager verified task {task['id']}\n", encoding="utf-8")
        base = [
            "python3", "scripts/harnessctl.py", "task-set", str(artifact_dir),
            "--task-id", str(task["id"]),
        ]
        run([*base, "--status", "ready"])
        run([*base, "--status", "running"])
        run(
            [
                "python3", "scripts/harnessctl.py", "dispatch-update", str(artifact_dir),
                "--dispatch-id", dispatch_id, "--status", "running",
            ]
        )
        report_path = artifact_dir / str(task["report_path"])
        report_path.write_text(f"# Report {task['id']}\n\nVerified fixture output.\n", encoding="utf-8")
        run(
            [
                "python3", "scripts/harnessctl.py", "dispatch-update", str(artifact_dir),
                "--dispatch-id", dispatch_id, "--status", "reported",
            ]
        )
        run(
            [
                *base, "--status", "passed", "--evidence-file", str(evidence_path),
                "--no-test-reason", "status summary fixture",
            ]
        )
    return evidence_dir


def mark_full_passed(artifact_dir: Path) -> None:
    evidence_dir = mark_tasks_passed(artifact_dir)

    acceptance_path = evidence_dir / "acceptance.txt"
    acceptance_path.write_text("manager verified acceptance\n", encoding="utf-8")
    run(
        [
            "python3", "scripts/harnessctl.py", "acceptance-set", str(artifact_dir),
            "--criterion-id", "AC-001", "--status", "pass",
            "--evidence-file", str(acceptance_path),
            "--pass-algorithm", "pass if the recorded artifact digest remains valid",
            "--no-test-reason", "status summary fixture",
        ]
    )
    for status in ("gated", "specified", "dispatched", "reported", "evaluating"):
        run(["python3", "scripts/harnessctl.py", "run-set", str(artifact_dir), "--status", status])
    run(
        [
            "python3", "scripts/harnessctl.py", "run-set", str(artifact_dir),
            "--status", "accepted", "--evidence-file", str(acceptance_path),
        ]
    )


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
        mark_tasks_passed(artifact_dir)

        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        output = result.stdout
        assert_true("Acceptance: 0 pass, 1 pending, 0 fail, 0 blocked, 0 scoped_out" in output, output)
        assert_true("Completion confidence: high" not in output, output)
        assert_true("Next verification: resolve pending acceptance criteria" in output, output)
    finally:
        shutil.rmtree(temp)


def test_status_completed_tasks_pending_run_state_is_not_high() -> None:
    temp, artifact_dir = full_artifact("pending final run transition")
    try:
        mark_full_passed(artifact_dir)
        state_path = artifact_dir / "run_state.json"
        state = load_json(state_path)
        state["status"] = "intake"
        state["stages"][0]["status"] = "planned"
        write_json(state_path, state)
        result = run(["python3", "scripts/status.py", str(state_path)])
        assert_true("Completion confidence: high" not in result.stdout, result.stdout)
        assert_true("Completion confidence: blocked" in result.stdout, result.stdout)
        assert_true("digest does not match latest committed state" in result.stdout, result.stdout)
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
        assert_true("Completion confidence: blocked" in output, output)
        assert_true("Completion confidence: high" not in output, output)

        (artifact_dir / "acceptance_registry.json").unlink()
        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        output = result.stdout
        assert_true("Acceptance: missing" in output, output)
        assert_true("Completion confidence: blocked" in output, output)
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


def test_schema_version_has_one_runtime_source() -> None:
    temp, artifact_dir = full_artifact("schema source")
    try:
        generated_state = load_json(artifact_dir / "run_state.json")
        generated_registry = load_json(artifact_dir / "acceptance_registry.json")
        template_state = load_json(ROOT / "templates" / "run_state.json")
        template_registry = load_json(ROOT / "templates" / "acceptance_registry.json")
        assert_true(
            generated_state["version"]
            == generated_registry["version"]
            == template_state["version"]
            == template_registry["version"],
            "schema version drift between templates and initialized artifacts",
        )
        result = run(
            ["python3", "scripts/validate_report.py", str(artifact_dir / "run_state.json"), "--type", "run_state"]
        )
        assert_true(result.returncode == 0, result.stdout + result.stderr)
        result = run(
            ["python3", "scripts/validate_report.py", str(artifact_dir / "acceptance_registry.json"), "--type", "acceptance"]
        )
        assert_true(result.returncode == 0, result.stdout + result.stderr)
        for filename, artifact_type in (("run_state.json", "run_state"), ("acceptance_registry.json", "acceptance")):
            result = run(
                ["python3", "scripts/validate_report.py", str(ROOT / "templates" / filename), "--type", artifact_type],
                check=False,
            )
            assert_true(result.returncode == 0, result.stdout + result.stderr)
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        assert_true(f"Master Prompt v{version}" in (ROOT / "master-prompt.md").read_text(encoding="utf-8"), "master prompt version drift")
        assert_true(f"Sub-Agent Prompt v{version}" in (ROOT / "sub-prompt.md").read_text(encoding="utf-8"), "sub-agent prompt version drift")
    finally:
        shutil.rmtree(temp)


def test_public_identity_is_consistent() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    openai_manifest = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    package_script = (ROOT / "scripts" / "package_skill.py").read_text(encoding="utf-8")

    frontmatter = skill.split("---", 2)[1]
    assert_true("name: agent-reliability-harness" in frontmatter, frontmatter)
    assert_true("# Agent Reliability Harness" in skill, "SKILL.md title is stale")
    for document in (readme, readme_zh):
        assert_true("# Agent Reliability Harness" in document, "README title is stale")
        assert_true("agent-reliability-harness" in document, "README install/repository slug is stale")
    assert_true("Agent Reliability Harness" in openai_manifest, openai_manifest)
    assert_true("agent-reliability-harness" in package_script, package_script)


def test_codex_model_router_uses_luna_main_and_sol_planning() -> None:
    cases = (
        (["--simple", "--mechanically-verifiable"], "fast", "gpt-5.6-luna", "medium"),
        ([], "main", "gpt-5.6-luna", "xhigh"),
        (["--harness-synthesis"], "planner", "gpt-5.6-sol", "high"),
        (["--high-risk"], "critical_reviewer", "gpt-5.6-sol", "xhigh"),
        (["--validation-failures", "2"], "critical_reviewer", "gpt-5.6-sol", "xhigh"),
    )
    for arguments, profile, model, effort in cases:
        result = run(["python3", "scripts/model_router.py", *arguments], check=False)
        assert_true(result.returncode == 0, result.stdout + result.stderr)
        decision = json.loads(result.stdout)
        assert_true(decision["profile"] == profile, decision)
        assert_true(decision["model"] == model, decision)
        assert_true(decision["reasoning_effort"] == effort, decision)
        assert_true("terra" not in decision["model"], decision)


def test_harnessctl_persists_model_route_on_dispatch() -> None:
    temp, artifact_dir = full_artifact("model routed dispatch")
    try:
        result = run(
            [
                "python3", "scripts/harnessctl.py", "dispatch-create", str(artifact_dir),
                "--task-id", "1.1", "--worker-id", "/root/luna-worker",
                "--contract-path", "tasks/1.1-docs.md", "--report-path", "1.1-docs-report.md",
                "--runtime", "codex", "--profile", "fast",
                "--requested-model", "gpt-5.6-luna", "--reasoning-effort", "medium",
                "--route-reason", "simple mechanically verifiable batch",
            ],
            check=False,
        )
        assert_true(result.returncode == 0, result.stdout + result.stderr)
        record = load_json(artifact_dir / "run_state.json")["state_layers"]["session_state"]["delegation_state"][0]
        assert_true(record["runtime"] == "codex", record)
        assert_true(record["profile"] == "fast", record)
        assert_true(record["requested_model"] == "gpt-5.6-luna", record)
        assert_true(record["reasoning_effort"] == "medium", record)
        assert_true(record["route_reason"] == "simple mechanically verifiable batch", record)
        assert_true(record["escalation_count"] == 0, record)
        run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)])
    finally:
        shutil.rmtree(temp)


def test_harnessctl_rejects_codex_route_bypasses() -> None:
    temp, artifact_dir = full_artifact("reject codex route bypasses")
    try:
        base_command = [
            "python3", "scripts/harnessctl.py", "dispatch-create", str(artifact_dir),
            "--task-id", "1.1", "--worker-id", "/root/invalid-worker",
            "--contract-path", "tasks/1.1-docs.md", "--report-path", "1.1-docs-report.md",
        ]
        uppercase_runtime = run(
            [
                *base_command, "--runtime", "CODEX", "--profile", "main",
                "--requested-model", "gpt-5.6-terra", "--reasoning-effort", "xhigh",
            ],
            check=False,
        )
        assert_true(uppercase_runtime.returncode != 0, uppercase_runtime.stdout + uppercase_runtime.stderr)

        resolved_terra = run(
            [
                *base_command, "--runtime", "codex", "--profile", "main",
                "--resolved-model", "gpt-5.6-terra",
            ],
            check=False,
        )
        assert_true(resolved_terra.returncode != 0, resolved_terra.stdout + resolved_terra.stderr)

        dispatches = load_json(artifact_dir / "run_state.json")["state_layers"]["session_state"]["delegation_state"]
        assert_true(dispatches == [], dispatches)
    finally:
        shutil.rmtree(temp)


def localized_spec(*, goal: str = "让真实运行状态可以被可靠恢复。") -> str:
    return f"""# 任务规范

## 1. 目标

{goal}

## 2. 用户可见结果

用户可以看到确定的完成或阻塞结论。

## （三）非目标

不修改产品代码。

## 4. 约束

只使用标准库。

## 5. 验收标准

非法状态必须被拒绝。

## 6. 验证证据

自动化测试和命令输出。

## 7. 风险

过度放松校验。

## 8. 预算

一轮实现与一次修复。

## 9. 停止条件

连续失败且没有新诊断。

## 10. Artifact 位置

workspace/example/

```markdown
## Goal
TODO
```
"""


def test_localized_numbered_spec_sections_are_semantic() -> None:
    temp, artifact_dir = full_artifact("localized spec")
    try:
        path = artifact_dir / "localized-task-spec.md"
        path.write_text(localized_spec(), encoding="utf-8")
        result = run(["python3", "scripts/validate_report.py", str(path), "--type", "spec", "--require-filled"])
        assert_true(result.returncode == 0, result.stdout + result.stderr)

        path.write_text(localized_spec(goal="### TODO"), encoding="utf-8")
        result = run(
            ["python3", "scripts/validate_report.py", str(path), "--type", "spec", "--require-filled"],
            check=False,
        )
        assert_true(result.returncode != 0, "empty localized Goal must fail")
        assert_true("section must not be empty: Goal" in result.stdout, result.stdout)

        path.write_text(localized_spec().replace("## 2. 用户可见结果", "## 2. 用户可见结果\n\n重复内容\n\n## User-Facing Outcome"), encoding="utf-8")
        result = run(
            ["python3", "scripts/validate_report.py", str(path), "--type", "spec", "--require-filled"],
            check=False,
        )
        assert_true(result.returncode != 0, "duplicate localized section aliases must fail")
        assert_true("duplicate section: User-Facing Outcome" in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)


def test_localized_numbered_progress_snapshot_is_validated() -> None:
    temp, artifact_dir = full_artifact("localized progress")
    try:
        replacements = {
            "## Snapshot": "## 1. 快照",
            "## Completed": "## 2. 已完成",
            "## Changed Files": "## 3. 修改文件",
            "## Decisions": "## 4. 决策",
            "## Commands And Evidence": "## 5. 命令与证据",
            "## Verification": "## 6. 验证",
            "## Open Risks": "## 7. 未决风险",
            "## Next Step": "## 8. 下一步",
        }
        text = (ROOT / "templates" / "progress_ledger.md").read_text(encoding="utf-8")
        for source, target in replacements.items():
            text = text.replace(source, target)
        path = artifact_dir / "localized-progress.md"
        path.write_text(text, encoding="utf-8")
        result = run(["python3", "scripts/validate_report.py", str(path), "--type", "progress"], check=False)
        assert_true(result.returncode == 0, result.stdout + result.stderr)
    finally:
        shutil.rmtree(temp)


def test_harnessctl_rejects_invalid_or_evidence_free_transitions() -> None:
    temp, artifact_dir = full_artifact("controlled mutation")
    try:
        state_path = artifact_dir / "run_state.json"
        registry_path = artifact_dir / "acceptance_registry.json"

        invalid = run(
            ["python3", "scripts/harnessctl.py", "task-set", str(artifact_dir), "--task-id", "1.1", "--status", "passed"],
            check=False,
        )
        assert_true(invalid.returncode != 0, "planned -> passed without evidence must fail")
        assert_true(load_json(state_path)["tasks"][0]["status"] == "planned", "invalid transition changed state")

        for status in ("ready", "running"):
            run(["python3", "scripts/harnessctl.py", "task-set", str(artifact_dir), "--task-id", "1.1", "--status", status])
        no_evidence = run(
            ["python3", "scripts/harnessctl.py", "task-set", str(artifact_dir), "--task-id", "1.1", "--status", "passed"],
            check=False,
        )
        assert_true(no_evidence.returncode != 0, "passed without evidence must fail")
        assert_true(load_json(state_path)["tasks"][0]["status"] == "running", "evidence failure changed state")
        whitespace_evidence = run(
            [
                "python3", "scripts/harnessctl.py", "task-set", str(artifact_dir),
                "--task-id", "1.1", "--status", "passed", "--evidence", "   ",
            ],
            check=False,
        )
        assert_true(whitespace_evidence.returncode != 0, "whitespace task evidence must fail")

        evidence_path = artifact_dir / "tests.log"
        evidence_path.write_text("manager verified controller fixture\n", encoding="utf-8")
        run(
            [
                "python3", "scripts/harnessctl.py", "task-set", str(artifact_dir),
                "--task-id", "1.1", "--status", "passed", "--evidence-file", str(evidence_path),
                "--no-test-reason", "test covers controller behavior outside this fixture",
            ]
        )
        acceptance_without_evidence = run(
            [
                "python3", "scripts/harnessctl.py", "acceptance-set", str(artifact_dir),
                "--criterion-id", "AC-001", "--status", "pass",
            ],
            check=False,
        )
        assert_true(acceptance_without_evidence.returncode != 0, "acceptance pass without evidence must fail")
        assert_true(load_json(registry_path)["criteria"][0]["status"] == "pending", "invalid acceptance changed state")
        acceptance_whitespace = run(
            [
                "python3", "scripts/harnessctl.py", "acceptance-set", str(artifact_dir),
                "--criterion-id", "AC-001", "--status", "pass",
                "--evidence", "   ", "--pass-algorithm", "   ",
            ],
            check=False,
        )
        assert_true(acceptance_whitespace.returncode != 0, "whitespace acceptance evidence must fail")

        run(
            [
                "python3", "scripts/harnessctl.py", "acceptance-set", str(artifact_dir),
                "--criterion-id", "AC-001", "--status", "pass",
                "--evidence-file", str(evidence_path), "--pass-algorithm", "tests.log exists and passed",
                "--no-test-reason", "test covers controller behavior outside this fixture",
            ]
        )
        reopen = run(
            [
                "python3", "scripts/harnessctl.py", "acceptance-set", str(artifact_dir),
                "--criterion-id", "AC-001", "--status", "pending",
            ],
            check=False,
        )
        assert_true(reopen.returncode != 0, "passed acceptance must not silently return to pending")
        trace_events = [json.loads(line) for line in (artifact_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
        assert_true(any(event.get("event") == "task_transition" for event in trace_events), trace_events)
        assert_true(any(event.get("event") == "acceptance_transition" for event in trace_events), trace_events)
        run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)])
    finally:
        shutil.rmtree(temp)


def test_harnessctl_preserves_concurrent_runtime_state_update() -> None:
    temp, artifact_dir = full_artifact("concurrent official writer")
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import harnessctl
        from runtime_state import update_json

        original_validate = harnessctl.validate_candidate

        def racing_validate(*args: object, **kwargs: object) -> None:
            original_validate(*args, **kwargs)
            update_json(
                artifact_dir / "run_state.json",
                {"race_marker": "preserve-me"},
                writer_role="manager",
                scope="global",
            )

        harnessctl.validate_candidate = racing_validate
        args = __import__("argparse").Namespace(
            artifact_dir=artifact_dir,
            task_id="1.1",
            status="ready",
            evidence=[],
            stop_reason="",
            no_test_reason="",
        )
        failed = False
        try:
            harnessctl.task_set(args)
        except ValueError:
            failed = True
        finally:
            harnessctl.validate_candidate = original_validate
        assert_true(failed, "stale harnessctl snapshot must be rejected")
        assert_true(load_json(artifact_dir / "run_state.json").get("race_marker") == "preserve-me", "concurrent update was lost")
    finally:
        shutil.rmtree(temp)


def test_harnessctl_serializes_read_modify_write() -> None:
    temp, artifact_dir = full_artifact("serialized mutation")
    try:
        command = [
            "python3", "scripts/harnessctl.py", "task-set", str(artifact_dir),
            "--task-id", "1.1", "--status", "ready",
        ]
        processes = [
            subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for _ in range(20)
        ]
        results = [process.communicate() + (process.returncode,) for process in processes]
        successes = [result for result in results if result[2] == 0]
        assert_true(len(successes) == 1, f"exactly one concurrent transition should commit: {results}")
    finally:
        shutil.rmtree(temp)


def test_harnessctl_refuses_mutation_when_trace_is_dirty() -> None:
    temp, artifact_dir = full_artifact("dirty trace mutation")
    try:
        state_path = artifact_dir / "run_state.json"
        trace_path = artifact_dir / "trace.jsonl"
        before_state = state_path.read_text(encoding="utf-8")
        trace_path.write_text(trace_path.read_text(encoding="utf-8") + "not-json\n", encoding="utf-8")
        before_trace = trace_path.read_text(encoding="utf-8")
        result = run(
            [
                "python3", "scripts/harnessctl.py", "task-set", str(artifact_dir),
                "--task-id", "1.1", "--status", "ready",
            ],
            check=False,
        )
        assert_true(result.returncode != 0, "dirty trace must block mutation")
        assert_true(state_path.read_text(encoding="utf-8") == before_state, "dirty trace mutation changed state")
        assert_true(trace_path.read_text(encoding="utf-8") == before_trace, "dirty trace mutation appended trace")

        clean_temp, clean_artifact = full_artifact("unterminated trace mutation")
        try:
            clean_state = clean_artifact / "run_state.json"
            clean_trace = clean_artifact / "trace.jsonl"
            clean_trace.write_bytes(clean_trace.read_bytes().rstrip(b"\n"))
            before_state = clean_state.read_text(encoding="utf-8")
            before_trace = clean_trace.read_bytes()
            result = run(
                [
                    "python3", "scripts/harnessctl.py", "task-set", str(clean_artifact),
                    "--task-id", "1.1", "--status", "ready",
                ],
                check=False,
            )
            assert_true(result.returncode != 0, "unterminated JSONL must block mutation")
            assert_true(clean_state.read_text(encoding="utf-8") == before_state, "unterminated trace changed state")
            assert_true(clean_trace.read_bytes() == before_trace, "unterminated trace was appended")
        finally:
            shutil.rmtree(clean_temp)
    finally:
        shutil.rmtree(temp)


def test_harnessctl_validate_rejects_invalid_trace_and_empty_registry() -> None:
    temp, artifact_dir = full_artifact("protocol integrity")
    try:
        trace_path = artifact_dir / "trace.jsonl"
        trace_path.write_text(trace_path.read_text(encoding="utf-8") + "not-json\n", encoding="utf-8")
        result = run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)], check=False)
        assert_true(result.returncode != 0, "invalid trace must fail workspace validation")
        assert_true("trace.jsonl: line 2 invalid JSON" in result.stdout, result.stdout)

        trace_path.write_text(
            json.dumps({"event": "task_transition_started", "transaction_id": "incomplete"}) + "\n"
            + json.dumps({"event": "unrelated_event", "transaction_id": "incomplete"}) + "\n",
            encoding="utf-8",
        )
        result = run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)], check=False)
        assert_true(result.returncode != 0, "incomplete transaction must fail workspace validation")
        assert_true("incomplete transaction: incomplete" in result.stdout, result.stdout)

        trace_path.write_text(
            json.dumps({"event": "task_transition_started", "transaction_id": "mismatch", "task_id": "1.1", "to_status": "ready"}) + "\n"
            + json.dumps({"event": "task_transition", "transaction_id": "mismatch", "task_id": "1.1", "to_status": "passed"}) + "\n",
            encoding="utf-8",
        )
        result = run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)], check=False)
        assert_true(result.returncode != 0, "mismatched transaction payload must fail")
        assert_true("transaction payload mismatch: mismatch" in result.stdout, result.stdout)

        trace_path.write_text("", encoding="utf-8")
        registry_path = artifact_dir / "acceptance_registry.json"
        registry = load_json(registry_path)
        registry["criteria"] = []
        write_json(registry_path, registry)
        result = run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)], check=False)
        assert_true(result.returncode != 0, "empty acceptance registry must fail")
        assert_true("criteria must not be empty" in result.stdout, result.stdout)

        fresh = load_json(ROOT / "templates" / "acceptance_registry.json")
        fresh["criteria"][0]["status"] = "pass"
        fresh["criteria"][0]["pass_algorithm"] = "pass if the required evidence exists"
        fresh["criteria"][0]["evidence"] = []
        write_json(registry_path, fresh)
        result = run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)], check=False)
        assert_true(result.returncode != 0, "hand-written evidence-free acceptance PASS must fail")
        assert_true("requires qualifying verified evidence for acceptance:AC-001" in result.stdout, result.stdout)

        fresh["criteria"][0]["evidence"] = ["evidence.log"]
        fresh["criteria"][0]["verification_gate"]["mode"] = "test_first_evidence"
        write_json(registry_path, fresh)
        result = run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)], check=False)
        assert_true(result.returncode != 0, "empty test-first gate must not validate")
        assert_true("test_first_evidence requires" in result.stdout, result.stdout)

        state_path = artifact_dir / "run_state.json"
        state = load_json(state_path)
        state["tasks"][0]["status"] = "passed"
        state["tasks"][0]["evidence"] = []
        write_json(state_path, state)
        result = run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)], check=False)
        assert_true("requires qualifying verified evidence for task:1.1" in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)


def test_harnessctl_rejects_broken_graph_invariants() -> None:
    temp, artifact_dir = full_artifact("broken graph")
    try:
        state_path = artifact_dir / "run_state.json"
        state = load_json(state_path)
        state["current_stage"] = "missing-stage"
        state["tasks"][0]["stage"] = 999
        state["tasks"][0]["dependencies"] = ["missing-task"]
        state["tasks"].append(dict(state["tasks"][0]))
        write_json(state_path, state)

        registry_path = artifact_dir / "acceptance_registry.json"
        registry = load_json(registry_path)
        registry["criteria"].append(dict(registry["criteria"][0]))
        write_json(registry_path, registry)

        result = run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)], check=False)
        assert_true(result.returncode != 0, "broken task/stage/criterion graph must fail")
        for expected in (
            "current_stage references unknown stage",
            ".stage references unknown stage",
            ".dependencies references unknown task",
            ".id duplicates",
        ):
            assert_true(expected in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)


def test_harnessctl_rejects_dependency_cycles_and_stage_membership_mismatch() -> None:
    temp, artifact_dir = full_artifact("dependency and stage mismatch")
    try:
        state_path = artifact_dir / "run_state.json"
        state = load_json(state_path)
        state["tasks"][0]["dependencies"] = ["1.1"]
        state["tasks"][1]["dependencies"] = ["1.1"]
        state["tasks"][1]["status"] = "running"
        state["stages"][0]["tasks"].remove("1.1")
        state["stages"].append(
            {
                "id": "2", "name": "wrong membership", "status": "planned",
                "tasks": ["1.2"], "budget": "", "evidence": [], "stop_reason": "",
            }
        )
        write_json(state_path, state)
        result = run(
            ["python3", "scripts/harnessctl.py", "seal", str(artifact_dir), "--reason", "invalid graph"],
            check=False,
        )
        assert_true(result.returncode != 0, "seal must reject invalid dependency and stage graph")
        for expected in (
            "dependencies must not reference itself",
            "task dependency cycle",
            "is missing from declared stage",
            "lists task '1.2' declared in stage",
            "running task '1.2' has incomplete dependencies",
        ):
            assert_true(expected in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)


def test_harnessctl_cross_file_invariants_and_scoped_out() -> None:
    temp, artifact_dir = full_artifact("cross file integrity")
    try:
        state_path = artifact_dir / "run_state.json"
        state = load_json(state_path)
        state["status"] = "accepted"
        write_json(state_path, state)
        result = run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)], check=False)
        assert_true(result.returncode != 0, "accepted run with pending acceptance must fail")
        assert_true("accepted run has unresolved acceptance" in result.stdout, result.stdout)

        state["status"] = "intake"
        write_json(state_path, state)
        scoped = run(
            [
                "python3", "scripts/harnessctl.py", "acceptance-set", str(artifact_dir),
                "--criterion-id", "AC-001", "--status", "scoped_out", "--evidence", "user-approved scope",
            ],
            check=False,
        )
        assert_true(scoped.returncode == 0, scoped.stdout + scoped.stderr)

        state["status"] = "accepted"
        write_json(state_path, state)
        result = run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)], check=False)
        assert_true(result.returncode != 0, "accepted run with incomplete tasks/stages must fail")
        assert_true("accepted run has incomplete tasks" in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)


def test_harnessctl_clears_resolved_blocking_issues() -> None:
    temp, artifact_dir = full_artifact("resolved acceptance blocker")
    try:
        base = ["python3", "scripts/harnessctl.py", "acceptance-set", str(artifact_dir), "--criterion-id", "AC-001"]
        evidence_path = artifact_dir / "tests.log"
        evidence_path.write_text("manager verified resolved blocker\n", encoding="utf-8")
        run([*base, "--status", "fail", "--blocking-issue", "test failed"])
        run([*base, "--status", "pending"])
        run([*base, "--status", "pass", "--evidence-file", str(evidence_path), "--pass-algorithm", "pass if tests.log reports PASS", "--no-test-reason", "controller fixture"])
        criterion = load_json(artifact_dir / "acceptance_registry.json")["criteria"][0]
        assert_true(criterion["blocking_issues"] == [], criterion)
    finally:
        shutil.rmtree(temp)


def test_harnessctl_run_set_controls_final_acceptance() -> None:
    temp, artifact_dir = full_artifact("controlled final run")
    try:
        registry_path = artifact_dir / "acceptance_registry.json"
        registry = load_json(registry_path)
        gate = registry["criteria"][0]["verification_gate"]
        gate.update(
            {
                "mode": "test_first_evidence",
                "tdd_trace_path": "tdd_trace.jsonl",
                "red_command": "python3 failing_test.py",
                "red_result": "FAIL",
                "red_failure_reason": "expected behavior was missing",
                "green_command": "python3 passing_test.py",
                "green_result": "PASS",
            }
        )
        write_json(registry_path, registry)
        run(
            [
                "python3", "scripts/harnessctl.py", "seal", str(artifact_dir),
                "--reason", "bind test-first gate fixture before execution",
            ]
        )
        evidence_path = artifact_dir / "tests.log"
        evidence_path.write_text("manager verified controller acceptance fixture\n", encoding="utf-8")
        tasks = {str(item["id"]): item for item in load_json(artifact_dir / "run_state.json")["tasks"]}
        for task_id in ("1.1", "1.2"):
            task = tasks[task_id]
            created = run(
                [
                    "python3", "scripts/harnessctl.py", "dispatch-create", str(artifact_dir),
                    "--worker-id", f"fixture/{task_id}", "--task-id", task_id,
                    "--contract-path", str(task["task_path"]), "--report-path", str(task["report_path"]),
                ]
            )
            dispatch_id = created.stdout.split("dispatch_id=", 1)[1].split()[0]
            task_evidence = artifact_dir / f"{task_id}.log"
            task_evidence.write_text(f"manager verified {task_id}\n", encoding="utf-8")
            base = ["python3", "scripts/harnessctl.py", "task-set", str(artifact_dir), "--task-id", task_id]
            run([*base, "--status", "ready"])
            run([*base, "--status", "running"])
            run(
                [
                    "python3", "scripts/harnessctl.py", "dispatch-update", str(artifact_dir),
                    "--dispatch-id", dispatch_id, "--status", "running",
                ]
            )
            (artifact_dir / str(task["report_path"])).write_text(
                f"# Report {task_id}\n\nVerified controller fixture.\n",
                encoding="utf-8",
            )
            run(
                [
                    "python3", "scripts/harnessctl.py", "dispatch-update", str(artifact_dir),
                    "--dispatch-id", dispatch_id, "--status", "reported",
                ]
            )
            run([*base, "--status", "passed", "--evidence-file", str(task_evidence), "--no-test-reason", "controller fixture"])
        run(
            [
                "python3", "scripts/harnessctl.py", "acceptance-set", str(artifact_dir),
                "--criterion-id", "AC-001", "--status", "pass", "--evidence-file", str(evidence_path),
                "--pass-algorithm", "pass if tests.log reports PASS",
            ]
        )
        for status in ("gated", "specified", "dispatched", "reported", "evaluating"):
            run(["python3", "scripts/harnessctl.py", "run-set", str(artifact_dir), "--status", status])
        blocked = run(
            [
                "python3", "scripts/harnessctl.py", "run-set", str(artifact_dir),
                "--status", "accepted", "--evidence-file", str(evidence_path),
            ],
            check=False,
        )
        assert_true(blocked.returncode != 0, "invalid active TDD trace must block final acceptance")
        (artifact_dir / "tdd_trace.jsonl").write_text(
            '\n'.join(
                (
                    json.dumps({"event": "gate_decision", "gate_mode": "test_first_evidence", "reason": "controller fixture"}),
                    json.dumps({"event": "test_run", "phase": "RED", "result": "FAIL"}),
                    json.dumps({"event": "test_run", "phase": "GREEN", "result": "PASS"}),
                )
            ) + '\n',
            encoding="utf-8",
        )
        run(
            [
                "python3", "scripts/harnessctl.py", "run-set", str(artifact_dir),
                "--status", "accepted", "--evidence-file", str(evidence_path),
            ]
        )
        state = load_json(artifact_dir / "run_state.json")
        assert_true(state["status"] == "accepted", state)
        assert_true(all(stage["status"] == "passed" for stage in state["stages"]), state["stages"])
        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        assert_true("Completion confidence: high" in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)


def test_harnessctl_recover_reconciles_interrupted_transition() -> None:
    for state_is_after in (False, True):
        temp, artifact_dir = full_artifact(f"recover transaction {state_is_after}")
        try:
            state_path = artifact_dir / "run_state.json"
            before_bytes = state_path.read_bytes()
            after = load_json(state_path)
            after["status"] = "gated"
            after_bytes = (json.dumps(after, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            if state_is_after:
                state_path.write_bytes(after_bytes)
            event = {
                "event": "run_transition_started",
                "transaction_id": f"recover-{state_is_after}",
                "state_file": "run_state.json",
                "before_sha256": hashlib.sha256(before_bytes).hexdigest(),
                "after_sha256": hashlib.sha256(after_bytes).hexdigest(),
                "from_status": "intake",
                "to_status": "gated",
                "evidence": [],
                "stop_reason": "",
                "ts": "2026-07-14T00:00:00Z",
            }
            (artifact_dir / "trace.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
            result = run(["python3", "scripts/harnessctl.py", "recover", str(artifact_dir)], check=False)
            assert_true(result.returncode == 0, result.stdout + result.stderr)
            events = [json.loads(line) for line in (artifact_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
            expected_event = "run_transition" if state_is_after else "run_transition_aborted"
            assert_true(events[-1]["event"] == expected_event, events)
            run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)])
        finally:
            shutil.rmtree(temp)


def test_harnessctl_recover_checks_canonical_digest_without_pending_transaction() -> None:
    temp, artifact_dir = full_artifact("recover canonical tamper")
    try:
        run(
            [
                "python3", "scripts/harnessctl.py", "task-set", str(artifact_dir),
                "--task-id", "1.1", "--status", "ready",
            ]
        )
        state_path = artifact_dir / "run_state.json"
        state = load_json(state_path)
        state["title"] = "hand-edited before recover"
        write_json(state_path, state)
        trace_path = artifact_dir / "trace.jsonl"
        trace_before = trace_path.read_bytes()
        result = run(["python3", "scripts/harnessctl.py", "recover", str(artifact_dir)], check=False)
        assert_true(result.returncode != 0, "recover must reject canonical tamper even with no pending transaction")
        assert_true("digest does not match latest committed state" in result.stdout, result.stdout)
        assert_true(trace_path.read_bytes() == trace_before, "failed recovery must not append trace events")
    finally:
        shutil.rmtree(temp)


def test_harnessctl_validates_transaction_digest_chain() -> None:
    temp, artifact_dir = full_artifact("transaction digest chain")
    try:
        base = [
            "python3", "scripts/harnessctl.py", "task-set", str(artifact_dir),
            "--task-id", "1.1",
        ]
        run([*base, "--status", "ready"])
        run([*base, "--status", "running"])
        trace_path = artifact_dir / "trace.jsonl"
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        transaction_ids = []
        for event in events:
            if event.get("event") == "task_transition_started":
                transaction_ids.append(event["transaction_id"])
        tampered_id = transaction_ids[-1]
        for event in events:
            if event.get("transaction_id") == tampered_id:
                event["before_sha256"] = "0" * 64
        trace_path.write_text(
            "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
            encoding="utf-8",
        )
        result = run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)], check=False)
        assert_true(result.returncode != 0, "broken transaction digest chain must fail validation")
        assert_true("digest chain" in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)


def test_harnessctl_strict_gate_cannot_be_downgraded_by_latest_trace() -> None:
    temp, artifact_dir = full_artifact("strict gate downgrade")
    try:
        state_path = artifact_dir / "run_state.json"
        state = load_json(state_path)
        task = state["tasks"][0]
        task["verification_gate"].update(
            {
                "mode": "strict_tdd",
                "tdd_trace_path": "tdd_trace.jsonl",
                "red_command": "python3 strict_test.py",
                "red_result": "FAIL",
                "red_failure_reason": "expected missing behavior",
                "green_command": "python3 strict_test.py",
                "green_result": "PASS",
                "refactor_check": "PASS",
            }
        )
        write_json(state_path, state)
        run(
            [
                "python3", "scripts/harnessctl.py", "seal", str(artifact_dir),
                "--reason", "bind strict gate fixture before execution",
            ]
        )
        evidence_path = artifact_dir / "strict.log"
        evidence_path.write_text("manager verified strict gate fixture\n", encoding="utf-8")
        base = [
            "python3", "scripts/harnessctl.py", "task-set", str(artifact_dir),
            "--task-id", "1.1",
        ]
        run([*base, "--status", "ready"])
        run([*base, "--status", "running"])
        run([*base, "--status", "passed", "--evidence-file", str(evidence_path)])
        (artifact_dir / "tdd_trace.jsonl").write_text(
            '\n'.join(
                (
                    json.dumps({"event": "gate_decision", "gate_mode": "test_first_evidence", "reason": "weaker cycle"}),
                    json.dumps({"event": "test_run", "phase": "RED", "result": "FAIL"}),
                    json.dumps({"event": "test_run", "phase": "GREEN", "result": "PASS"}),
                )
            ) + '\n',
            encoding="utf-8",
        )
        result = run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)], check=False)
        assert_true(result.returncode != 0, "strict active gate must reject weaker latest trace")
        assert_true("latest gate mode must be strict_tdd" in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)


def test_status_empty_registry_cannot_be_high_confidence() -> None:
    temp, artifact_dir = full_artifact("empty registry")
    try:
        mark_full_passed(artifact_dir)
        registry_path = artifact_dir / "acceptance_registry.json"
        registry = load_json(registry_path)
        registry["criteria"] = []
        write_json(registry_path, registry)
        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        assert_true("Completion confidence: blocked" in result.stdout, result.stdout)
        assert_true("acceptance registry has no criteria" in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)


def test_status_invalid_run_state_cannot_be_high_confidence() -> None:
    temp, artifact_dir = full_artifact("invalid run state status")
    try:
        mark_full_passed(artifact_dir)
        state_path = artifact_dir / "run_state.json"
        state = load_json(state_path)
        state["version"] = 999
        state["status"] = "mystery"
        write_json(state_path, state)
        result = run(["python3", "scripts/status.py", str(state_path)])
        assert_true("Completion confidence: blocked" in result.stdout, result.stdout)
        assert_true("Integrity errors:" in result.stdout, result.stdout)
        assert_true("Completion confidence: high" not in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)


def test_status_invalid_registry_or_trace_cannot_be_high_confidence() -> None:
    temp, artifact_dir = full_artifact("invalid registry trace status")
    try:
        mark_full_passed(artifact_dir)
        registry_path = artifact_dir / "acceptance_registry.json"
        registry = load_json(registry_path)
        registry["version"] = 999
        write_json(registry_path, registry)
        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        assert_true("Completion confidence: blocked" in result.stdout, result.stdout)
        assert_true("acceptance_registry.json: version must be 1" in result.stdout, result.stdout)

        registry["version"] = 1
        write_json(registry_path, registry)
        trace_path = artifact_dir / "trace.jsonl"
        trace_path.write_text(trace_path.read_text(encoding="utf-8") + "not-json\n", encoding="utf-8")
        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        assert_true("Completion confidence: blocked" in result.stdout, result.stdout)
        assert_true("trace.jsonl" in result.stdout, result.stdout)

        trace_path.write_text(trace_path.read_text(encoding="utf-8").removesuffix("not-json\n"), encoding="utf-8")
        registry = load_json(registry_path)
        gate = registry["criteria"][0]["verification_gate"]
        gate.update(
            {
                "mode": "test_first_evidence",
                "tdd_trace_path": "tdd_trace.jsonl",
                "red_command": "python3 test.py",
                "red_result": "FAIL",
                "red_failure_reason": "missing behavior",
                "green_command": "python3 test.py",
                "green_result": "PASS",
            }
        )
        write_json(registry_path, registry)
        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        assert_true("Completion confidence: blocked" in result.stdout, result.stdout)
        assert_true("latest gate mode must be test_first_evidence; got missing" in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)


def test_harnessctl_requires_verifiable_terminal_evidence() -> None:
    temp, artifact_dir = full_artifact("typed terminal evidence")
    try:
        task_base = [
            "python3", "scripts/harnessctl.py", "task-set", str(artifact_dir),
            "--task-id", "1.1",
        ]
        run([*task_base, "--status", "ready"])
        run([*task_base, "--status", "running"])
        self_report = run(
            [
                *task_base, "--status", "passed", "--evidence", "worker self-report: done",
                "--no-test-reason", "read-only fixture",
            ],
            check=False,
        )
        assert_true(self_report.returncode != 0, "worker self-report must not satisfy terminal task evidence")

        evidence_path = artifact_dir / "evidence" / "task-1.1.txt"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text("manager verified report and command output\n", encoding="utf-8")
        typed = run(
            [
                *task_base, "--status", "passed", "--evidence-file", str(evidence_path),
                "--no-test-reason", "read-only fixture",
            ],
            check=False,
        )
        assert_true(typed.returncode == 0, typed.stdout + typed.stderr)
        evidence = load_json(artifact_dir / "run_state.json")["tasks"][0]["evidence"]
        assert_true(isinstance(evidence[-1], dict) and evidence[-1].get("type") == "artifact_digest", evidence)
        assert_true(evidence[-1]["verification"]["transaction_id"], evidence[-1])

        acceptance = run(
            [
                "python3", "scripts/harnessctl.py", "acceptance-set", str(artifact_dir),
                "--criterion-id", "AC-001", "--status", "pass",
                "--evidence", "worker says done", "--pass-algorithm", "worker says done",
                "--no-test-reason", "read-only fixture",
            ],
            check=False,
        )
        assert_true(acceptance.returncode != 0, "worker self-report must not satisfy acceptance PASS")
    finally:
        shutil.rmtree(temp)


def test_harnessctl_binds_canonical_state_to_trace_and_checks_stage_tasks() -> None:
    temp, artifact_dir = full_artifact("canonical digest binding")
    try:
        run(
            [
                "python3", "scripts/harnessctl.py", "task-set", str(artifact_dir),
                "--task-id", "1.1", "--status", "ready",
            ]
        )
        state_path = artifact_dir / "run_state.json"
        state = load_json(state_path)
        state["title"] = "hand-edited after commit"
        write_json(state_path, state)
        result = run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)], check=False)
        assert_true(result.returncode != 0, "unjournaled canonical state edit must fail validation")
        assert_true("digest does not match latest committed state" in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)

    temp, artifact_dir = full_artifact("nonterminal stage contradiction")
    try:
        state_path = artifact_dir / "run_state.json"
        state = load_json(state_path)
        state["stages"][0]["status"] = "passed"
        write_json(state_path, state)
        result = run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)], check=False)
        assert_true(result.returncode != 0, "passed stage with planned tasks must fail before terminal run state")
        assert_true("passed stage has incomplete tasks" in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)


def test_strict_spec_rejects_low_information_section_echoes() -> None:
    temp, artifact_dir = full_artifact("strict semantic spec")
    try:
        path = artifact_dir / "low-information-spec.md"
        for goal in ("Goal", "Goal Goal Goal", "Done"):
            path.write_text(localized_spec(goal=goal), encoding="utf-8")
            result = run(
                ["python3", "scripts/validate_report.py", str(path), "--type", "spec", "--require-filled"],
                check=False,
            )
            assert_true(result.returncode != 0, f"low-information Goal must fail: {goal!r}")
            assert_true("section lacks concrete content: Goal" in result.stdout, result.stdout)

        keyword_soup = "PASS must evidence baseline verify success risk stop artifact"
        path.write_text(
            "# Keyword soup\n\n" + "\n\n".join(
                f"## {heading}\n\n{keyword_soup}"
                for heading in (
                    "Goal", "User-Facing Outcome", "Non-Goals", "Constraints",
                    "Acceptance Criteria", "Verification Evidence", "Risks", "Budget",
                    "Stop Conditions", "Artifact Location",
                )
            ) + "\n",
            encoding="utf-8",
        )
        result = run(
            ["python3", "scripts/validate_report.py", str(path), "--type", "spec", "--require-filled"],
            check=False,
        )
        assert_true(result.returncode != 0, "repeated keyword soup across required sections must fail")
        assert_true("reused identical content across sections" in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)


def test_harnessctl_persists_and_validates_dispatch_lifecycle() -> None:
    temp, artifact_dir = full_artifact("durable dispatch lifecycle")
    try:
        base = ["python3", "scripts/harnessctl.py"]
        created = run(
            [
                *base, "dispatch-create", str(artifact_dir),
                "--task-id", "1.1", "--worker-id", "/root/worker-123",
                "--contract-path", "tasks/1.1-docs.md",
                "--report-path", "1.1-docs-report.md",
            ],
            check=False,
        )
        assert_true(created.returncode == 0, created.stdout + created.stderr)
        dispatch_id = created.stdout.split("dispatch_id=", 1)[1].split()[0]
        report_path = artifact_dir / "1.1-docs-report.md"
        report_path.write_text("# Worker report\n\nConcrete result.\n", encoding="utf-8")
        reported = run(
            [
                *base, "dispatch-update", str(artifact_dir),
                "--dispatch-id", dispatch_id, "--status", "reported",
            ],
            check=False,
        )
        assert_true(reported.returncode == 0, reported.stdout + reported.stderr)

        state = load_json(artifact_dir / "run_state.json")
        entries = state["state_layers"]["session_state"]["delegation_state"]
        assert_true(len(entries) == 1, entries)
        assert_true(entries[0]["worker_id"] == "/root/worker-123", entries[0])
        assert_true(entries[0]["task_id"] == "1.1", entries[0])
        assert_true(entries[0]["contract_path"] == "tasks/1.1-docs.md", entries[0])
        assert_true(entries[0]["report_path"] == "1.1-docs-report.md", entries[0])
        assert_true(entries[0]["status"] == "reported", entries[0])
        run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)])
    finally:
        shutil.rmtree(temp)


def test_harnessctl_seal_rejects_persisted_dispatch() -> None:
    temp, artifact_dir = full_artifact("seal after dispatch")
    try:
        run(
            [
                "python3", "scripts/harnessctl.py", "dispatch-create", str(artifact_dir),
                "--task-id", "1.1", "--worker-id", "/root/worker-seal-check",
                "--contract-path", "tasks/1.1-docs.md",
                "--report-path", "1.1-docs-report.md",
            ]
        )
        trace_path = artifact_dir / "trace.jsonl"
        trace_before = trace_path.read_bytes()
        result = run(
            ["python3", "scripts/harnessctl.py", "seal", str(artifact_dir), "--reason", "too late"],
            check=False,
        )
        assert_true(result.returncode != 0, "seal must fail after a durable dispatch is created")
        assert_true("seal is only allowed before dispatch" in result.stdout, result.stdout)
        assert_true(trace_path.read_bytes() == trace_before, "rejected seal must not append a trace event")
    finally:
        shutil.rmtree(temp)


def test_harnessctl_rejects_chat_only_running_worker_after_dispatch() -> None:
    temp, artifact_dir = full_artifact("chat only dispatch")
    try:
        base = [
            "python3", "scripts/harnessctl.py", "task-set", str(artifact_dir),
            "--task-id", "1.1",
        ]
        run([*base, "--status", "ready"])
        run([*base, "--status", "running"])
        for status in ("gated", "specified", "dispatched"):
            run(["python3", "scripts/harnessctl.py", "run-set", str(artifact_dir), "--status", status])
        result = run(["python3", "scripts/harnessctl.py", "validate", str(artifact_dir)], check=False)
        assert_true(result.returncode != 0, "running worker without durable dispatch must fail validation")
        assert_true("running task lacks active durable dispatch: 1.1" in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)


def test_status_blocks_when_typed_evidence_file_changes() -> None:
    temp, artifact_dir = full_artifact("tampered typed evidence status")
    try:
        mark_full_passed(artifact_dir)
        (artifact_dir / "evidence" / "task-1.1.txt").write_text("changed after PASS\n", encoding="utf-8")
        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        assert_true("Completion confidence: blocked" in result.stdout, result.stdout)
        assert_true("artifact digest mismatch" in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)


def test_run_acceptance_rejects_missing_durable_dispatch_before_commit() -> None:
    temp, artifact_dir = full_artifact("acceptance missing dispatch")
    try:
        evidence_path = artifact_dir / "manager-evidence.txt"
        evidence_path.write_text("manager verified fixture\n", encoding="utf-8")
        for task_id in ("1.1", "1.2"):
            base = [
                "python3", "scripts/harnessctl.py", "task-set", str(artifact_dir),
                "--task-id", task_id,
            ]
            run([*base, "--status", "ready"])
            run([*base, "--status", "running"])
            run(
                [
                    *base, "--status", "passed", "--evidence-file", str(evidence_path),
                    "--no-test-reason", "controller fixture",
                ]
            )
        run(
            [
                "python3", "scripts/harnessctl.py", "acceptance-set", str(artifact_dir),
                "--criterion-id", "AC-001", "--status", "pass",
                "--evidence-file", str(evidence_path),
                "--pass-algorithm", "pass if the manager evidence digest remains valid",
                "--no-test-reason", "controller fixture",
            ]
        )
        for status in ("gated", "specified", "dispatched", "reported", "evaluating"):
            run(["python3", "scripts/harnessctl.py", "run-set", str(artifact_dir), "--status", status])
        result = run(
            [
                "python3", "scripts/harnessctl.py", "run-set", str(artifact_dir),
                "--status", "accepted", "--evidence-file", str(evidence_path),
            ],
            check=False,
        )
        assert_true(result.returncode != 0, "accepted transition must fail before committing missing dispatch history")
        assert_true("completed task lacks reported durable dispatch" in result.stdout, result.stdout)
        assert_true(load_json(artifact_dir / "run_state.json")["status"] == "evaluating", "invalid acceptance changed state")
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
        test_tdd_trace_template_is_empty_and_not_evidence,
        test_progress_template_is_lightweight,
        test_lite_init_is_minimal,
        test_lite_plan_has_single_worker_table,
        test_status_output_from_run_state,
        test_status_high_confidence_when_tasks_and_acceptance_pass,
        test_status_acceptance_pending_prevents_high_confidence,
        test_status_completed_tasks_pending_run_state_is_not_high,
        test_status_reports_evidence_gap_for_passed_task_without_evidence,
        test_status_blocked_when_task_or_acceptance_blocked,
        test_status_malformed_or_missing_registry_cannot_be_high_confidence,
        test_status_passed_acceptance_without_evidence_cannot_be_high_confidence,
        test_status_schema_malformed_registry_is_blocked,
        test_status_reports_accepted_run_with_pending_acceptance_conflict,
        test_negative_validators_and_package_check,
        test_schema_version_has_one_runtime_source,
        test_public_identity_is_consistent,
        test_codex_model_router_uses_luna_main_and_sol_planning,
        test_harnessctl_persists_model_route_on_dispatch,
        test_harnessctl_rejects_codex_route_bypasses,
        test_localized_numbered_spec_sections_are_semantic,
        test_localized_numbered_progress_snapshot_is_validated,
        test_harnessctl_rejects_invalid_or_evidence_free_transitions,
        test_harnessctl_preserves_concurrent_runtime_state_update,
        test_harnessctl_serializes_read_modify_write,
        test_harnessctl_refuses_mutation_when_trace_is_dirty,
        test_harnessctl_validate_rejects_invalid_trace_and_empty_registry,
        test_harnessctl_rejects_broken_graph_invariants,
        test_harnessctl_rejects_dependency_cycles_and_stage_membership_mismatch,
        test_harnessctl_cross_file_invariants_and_scoped_out,
        test_harnessctl_clears_resolved_blocking_issues,
        test_harnessctl_run_set_controls_final_acceptance,
        test_harnessctl_recover_reconciles_interrupted_transition,
        test_harnessctl_recover_checks_canonical_digest_without_pending_transaction,
        test_harnessctl_validates_transaction_digest_chain,
        test_harnessctl_strict_gate_cannot_be_downgraded_by_latest_trace,
        test_status_empty_registry_cannot_be_high_confidence,
        test_status_invalid_run_state_cannot_be_high_confidence,
        test_status_invalid_registry_or_trace_cannot_be_high_confidence,
        test_harnessctl_requires_verifiable_terminal_evidence,
        test_harnessctl_binds_canonical_state_to_trace_and_checks_stage_tasks,
        test_strict_spec_rejects_low_information_section_echoes,
        test_harnessctl_persists_and_validates_dispatch_lifecycle,
        test_harnessctl_seal_rejects_persisted_dispatch,
        test_harnessctl_rejects_chat_only_running_worker_after_dispatch,
        test_status_blocks_when_typed_evidence_file_changes,
        test_run_acceptance_rejects_missing_durable_dispatch_before_commit,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
