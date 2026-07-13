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


def test_gpt56_routing_policy_is_explicit_and_bounded() -> None:
    routing = (ROOT / "references" / "model-routing.md").read_text(encoding="utf-8")
    adapter = (ROOT / "adapters" / "codex.md").read_text(encoding="utf-8")
    for term in ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol", "low", "depth one", "one follow-up"):
        assert_true(term in routing, f"routing reference missing {term!r}")
    assert_true("Luna/low" in adapter, "Codex adapter must expose the Luna default")
    assert_true("cannot select a model" in adapter, "Codex adapter must document model fallback")


def test_superpowers_methods_are_risk_gated() -> None:
    text = (ROOT / "references" / "superpowers-integration.md").read_text(encoding="utf-8")
    for term in ("optional", "one at a time", "No TDD ceremony", "reviewer only after", "Do not chain"):
        assert_true(term in text, f"Superpowers policy missing {term!r}")


def test_runtime_package_contains_model_routing_reference() -> None:
    temp = Path(tempfile.mkdtemp(prefix="adh-test-model-routing-package-"))
    try:
        package_dir = temp / "pkg"
        run(["python3", "scripts/package_skill.py", "--output", str(package_dir), "--force"])
        assert_true(
            (package_dir / "references" / "model-routing.md").is_file(),
            "runtime package must include model-routing reference",
        )
    finally:
        shutil.rmtree(temp)


def test_token_budget_contract_is_present_and_safe() -> None:
    required = {
        "token_budget",
        "tokens_used",
        "tokens_remaining",
        "usage_kind",
        "accounting_note",
        "exhaustion_action",
    }
    template_state = load_json(ROOT / "templates" / "run_state.json")
    template_budget = template_state["task_shape"]["resource_budget"]
    assert_true(required <= set(template_budget), f"template budget missing {required - set(template_budget)}")
    assert_true(template_budget["usage_kind"] == "unknown", "template must not invent token measurements")
    assert_true(
        template_budget["exhaustion_action"] == "stop_and_record_decision",
        "budget exhaustion must stop and record a decision",
    )
    temp = Path(tempfile.mkdtemp(prefix="adh-test-token-budget-"))
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
                "token budget behavior",
                "--agents",
                "worker",
                "--force",
            ]
        )
        state = load_json(temp / "workspace" / "token-budget-behavior" / "run_state.json")
        for budget in (state["tasks"][0]["resource_budget"], state["stages"][0]["resource_budget"]):
            assert_true(required <= set(budget), f"generated budget missing {required - set(budget)}")
            assert_true(budget["usage_kind"] == "unknown", "generated state must expose unavailable accounting")
            assert_true(
                budget["exhaustion_action"] == "stop_and_record_decision",
                "generated state must preserve the exhaustion breaker",
            )
    finally:
        shutil.rmtree(temp)


def test_status_blocks_exhausted_token_budget() -> None:
    temp, artifact_dir = full_artifact("exhausted token budget")
    try:
        mark_full_passed(artifact_dir)
        state = load_json(artifact_dir / "run_state.json")
        state["tasks"][0]["resource_budget"].update(
            {
                "token_budget": 100,
                "tokens_used": 120,
                "tokens_remaining": 0,
                "usage_kind": "actual",
            }
        )
        write_json(artifact_dir / "run_state.json", state)

        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        output = result.stdout
        assert_true("token budget exhausted" in output, output)
        assert_true("Completion confidence: blocked" in output, output)
        assert_true("Completion confidence: high" not in output, output)
    finally:
        shutil.rmtree(temp)


def test_status_blocks_exhausted_stage_token_budget() -> None:
    temp, artifact_dir = full_artifact("exhausted stage token budget")
    try:
        mark_full_passed(artifact_dir)
        state = load_json(artifact_dir / "run_state.json")
        state["stages"][0]["resource_budget"].update(
            {
                "token_budget": 100,
                "tokens_used": 120,
                "tokens_remaining": 0,
                "usage_kind": "actual",
            }
        )
        write_json(artifact_dir / "run_state.json", state)

        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        output = result.stdout
        assert_true("token budget exhausted" in output, output)
        assert_true("Completion confidence: blocked" in output, output)
        assert_true("Completion confidence: high" not in output, output)
    finally:
        shutil.rmtree(temp)


def test_token_budget_policy_documents_exhaustion_and_unknown_fallback() -> None:
    text = "\n".join(
        (
            (ROOT / "references" / "model-routing.md").read_text(encoding="utf-8"),
            (ROOT / "references" / "harness-protocol.md").read_text(encoding="utf-8"),
            (ROOT / "scripts" / "status.py").read_text(encoding="utf-8"),
            (ROOT / "scripts" / "validate_report.py").read_text(encoding="utf-8"),
        )
    )
    for term in (
        "tokens_used",
        "tokens_remaining",
        "usage_kind",
        "unknown",
        "stop_and_record_decision",
        "accepted state is not allowed",
    ):
        assert_true(term in text, f"token budget contract missing {term!r}")


def test_status_blocks_unknown_configured_task_and_stage_budget() -> None:
    temp, artifact_dir = full_artifact("unknown configured budget")
    try:
        mark_full_passed(artifact_dir)
        state = load_json(artifact_dir / "run_state.json")
        for budget in (state["tasks"][0]["resource_budget"], state["stages"][0]["resource_budget"]):
            budget["token_budget"] = 100
            budget["usage_kind"] = "unknown"
        write_json(artifact_dir / "run_state.json", state)

        result = run(["python3", "scripts/status.py", str(artifact_dir / "run_state.json")])
        output = result.stdout
        assert_true(output.count("token budget accounting unavailable") == 2, output)
        assert_true("Completion confidence: blocked" in output, output)
    finally:
        shutil.rmtree(temp)


def test_validator_rejects_accepted_exhausted_budget() -> None:
    temp, artifact_dir = full_artifact("accepted exhausted budget")
    try:
        mark_full_passed(artifact_dir)
        state = load_json(artifact_dir / "run_state.json")
        state["tasks"][0]["resource_budget"].update(
            {
                "token_budget": 100,
                "tokens_used": 120,
                "tokens_remaining": 0,
                "usage_kind": "actual",
            }
        )
        write_json(artifact_dir / "run_state.json", state)

        result = run(
            [
                "python3",
                "scripts/validate_report.py",
                str(artifact_dir / "progress.md"),
                "--type",
                "progress",
            ],
            check=False,
        )
        assert_true(result.returncode != 0, "accepted run with exhausted budget must fail validation")
        assert_true("resource budget exhausted" in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)


def test_validator_rejects_accepted_unknown_budget() -> None:
    temp, artifact_dir = full_artifact("accepted unknown budget")
    try:
        mark_full_passed(artifact_dir)
        state = load_json(artifact_dir / "run_state.json")
        state["tasks"][0]["resource_budget"].update(
            {
                "token_budget": 100,
                "usage_kind": "unknown",
            }
        )
        write_json(artifact_dir / "run_state.json", state)

        result = run(
            [
                "python3",
                "scripts/validate_report.py",
                str(artifact_dir / "progress.md"),
                "--type",
                "progress",
            ],
            check=False,
        )
        assert_true(result.returncode != 0, "accepted run with unknown budget must fail validation")
        assert_true("resource budget accounting unavailable" in result.stdout, result.stdout)
    finally:
        shutil.rmtree(temp)


def test_status_require_high_confidence_gate() -> None:
    temp, artifact_dir = full_artifact("strict status gate")
    try:
        mark_full_passed(artifact_dir)
        passed = run(
            [
                "python3",
                "scripts/status.py",
                str(artifact_dir / "run_state.json"),
                "--require-high-confidence",
            ],
            check=False,
        )
        assert_true(passed.returncode == 0, passed.stdout)
        assert_true("Completion confidence: high" in passed.stdout, passed.stdout)

        registry = load_json(artifact_dir / "acceptance_registry.json")
        registry["criteria"][0]["status"] = "pending"
        registry["criteria"][0]["evidence"] = []
        write_json(artifact_dir / "acceptance_registry.json", registry)
        blocked = run(
            [
                "python3",
                "scripts/status.py",
                str(artifact_dir / "run_state.json"),
                "--require-high-confidence",
            ],
            check=False,
        )
        assert_true(blocked.returncode == 1, blocked.stdout)
        assert_true("Completion confidence: blocked" in blocked.stdout, blocked.stdout)
        assert_true("requires high completion confidence" in blocked.stdout, blocked.stdout)
    finally:
        shutil.rmtree(temp)


def test_codex_orchestration_review_records_adopted_and_removed_patterns() -> None:
    review = (ROOT / "docs" / "codex-orchestration-review.md").read_text(encoding="utf-8")
    for term in (
        "单一 root",
        "no subagents",
        "真实路由状态",
        "取消",
        "第二个 orchestrator",
        "跨 provider bridge",
        "Full artifact",
    ):
        assert_true(term in review, f"comparison review missing {term!r}")


def test_alignment_is_not_a_default_user_question_loop() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert_true("Do not ask a question for ordinary planning ambiguity" in skill, skill)
    assert_true("only when the unresolved choice changes" in skill, skill)


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
        test_gpt56_routing_policy_is_explicit_and_bounded,
        test_superpowers_methods_are_risk_gated,
        test_runtime_package_contains_model_routing_reference,
        test_token_budget_contract_is_present_and_safe,
        test_status_blocks_exhausted_token_budget,
        test_status_blocks_exhausted_stage_token_budget,
        test_token_budget_policy_documents_exhaustion_and_unknown_fallback,
        test_validator_rejects_accepted_exhausted_budget,
        test_status_blocks_unknown_configured_task_and_stage_budget,
        test_validator_rejects_accepted_unknown_budget,
        test_status_require_high_confidence_gate,
        test_codex_orchestration_review_records_adopted_and_removed_patterns,
        test_alignment_is_not_a_default_user_question_loop,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
