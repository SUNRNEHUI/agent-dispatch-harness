#!/usr/bin/env python3
"""Deterministic tests for cost-aware model routing (Codex + Grok)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from harness_schema import (  # noqa: E402
    CODEX_MODEL_PROFILES,
    GROK_MODEL_PROFILES,
    model_profiles_for,
)
from model_router import resolve_configuration, select_profile  # noqa: E402
from validate_report import validate_run_state  # noqa: E402


class _Args:
    def __init__(self, **kwargs):
        self.simple = kwargs.get("simple", False)
        self.mechanically_verifiable = kwargs.get("mechanically_verifiable", False)
        self.fuzzy = kwargs.get("fuzzy", False)
        self.harness_synthesis = kwargs.get("harness_synthesis", False)
        self.high_risk = kwargs.get("high_risk", False)
        self.worker_conflict = kwargs.get("worker_conflict", False)
        self.validation_failures = kwargs.get("validation_failures", 0)


class ProfileSelectionTests(unittest.TestCase):
    def test_fast_requires_both_flags(self):
        profile, reasons = select_profile(_Args(simple=True, mechanically_verifiable=True))
        self.assertEqual(profile, "fast")
        self.assertEqual(reasons, ["simple", "mechanically_verifiable"])

    def test_simple_alone_is_main(self):
        profile, _ = select_profile(_Args(simple=True))
        self.assertEqual(profile, "main")

    def test_planner_and_critical(self):
        self.assertEqual(select_profile(_Args(fuzzy=True))[0], "planner")
        self.assertEqual(select_profile(_Args(harness_synthesis=True))[0], "planner")
        self.assertEqual(select_profile(_Args(high_risk=True))[0], "critical_reviewer")
        self.assertEqual(select_profile(_Args(validation_failures=2))[0], "critical_reviewer")


class RuntimeMapTests(unittest.TestCase):
    def test_grok_map_sealed(self):
        # Default install has only 4.5 → every profile (including sub-agents) uses grok-api.
        for profile in ("fast", "main", "planner", "critical_reviewer"):
            self.assertEqual(GROK_MODEL_PROFILES[profile]["model"], "grok-api")
        self.assertEqual(GROK_MODEL_PROFILES["fast"]["reasoning_effort"], "low")
        self.assertEqual(GROK_MODEL_PROFILES["critical_reviewer"]["reasoning_effort"], "xhigh")

    def test_codex_map_unchanged(self):
        self.assertEqual(CODEX_MODEL_PROFILES["fast"]["model"], "gpt-5.6-luna")
        self.assertEqual(CODEX_MODEL_PROFILES["planner"]["model"], "gpt-5.6-sol")

    def test_model_profiles_for(self):
        self.assertIsNone(model_profiles_for("claude"))
        grok = model_profiles_for("GROK")
        assert grok is not None
        grok["fast"]["model"] = "mutated"
        self.assertEqual(GROK_MODEL_PROFILES["fast"]["model"], "grok-api")

    def test_resolve_configuration_runtime(self):
        cfg, overrides = resolve_configuration("grok", "fast")
        self.assertEqual(cfg["model"], "grok-api")
        self.assertEqual(cfg["reasoning_effort"], "low")
        self.assertEqual(overrides, [])
        with self.assertRaises(ValueError):
            resolve_configuration("claude", "fast")


class CliRouterTests(unittest.TestCase):
    def _run(self, *args: str) -> dict:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "model_router.py"), *args],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        return json.loads(proc.stdout)

    def test_cli_grok_fast(self):
        payload = self._run("--runtime", "grok", "--simple", "--mechanically-verifiable")
        self.assertEqual(payload["runtime"], "grok")
        self.assertEqual(payload["profile"], "fast")
        self.assertEqual(payload["model"], "grok-api")
        self.assertEqual(payload["reasoning_effort"], "low")

    def test_cli_codex_default(self):
        payload = self._run("--runtime", "codex")
        self.assertEqual(payload["profile"], "main")
        self.assertEqual(payload["model"], "gpt-5.6-luna")

    def test_cli_env_override(self):
        env = os.environ.copy()
        env["HARNESS_GROK_FAST_MODEL"] = "experimental-cheap"
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "model_router.py"),
                "--runtime",
                "grok",
                "--simple",
                "--mechanically-verifiable",
                "--allow-env-override",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["model"], "experimental-cheap")
        self.assertIn("HARNESS_GROK_FAST_MODEL", payload["env_overrides_applied"])


class DispatchValidationTests(unittest.TestCase):
    def _base_state(self) -> dict:
        return {
            "version": 1,
            "evidence_policy": "typed-v1",
            "routing_policy": "cost-aware-v1",
            "created_at": "2026-07-17T00:00:00Z",
            "updated_at": "2026-07-17T00:00:00Z",
            "title": "routing-test",
            "mode": "full",
            "artifact_dir": "/tmp/routing-test",
            "trace_path": "trace.jsonl",
            "tdd_trace_path": "tdd_trace.jsonl",
            "state_layers": {
                "working_state": {
                    "current_stage": "1",
                    "current_task": "1.1",
                    "active_blockers": [],
                    "volatile_notes": [],
                    "updated_at": "2026-07-17T00:00:00Z",
                },
                "session_state": {
                    "shared_decisions": [],
                    "shared_assumptions": [],
                    "artifact_paths": {
                        "task_spec": "task_spec.md",
                        "progress": "progress.md",
                        "acceptance_registry": "acceptance_registry.json",
                        "trace": "trace.jsonl",
                        "tdd_trace": "tdd_trace.jsonl",
                    },
                    "delegation_state": [],
                    "document_priority": ["task_spec.md"],
                },
                "execution_log": {
                    "trace_path": "trace.jsonl",
                    "tdd_trace_path": "tdd_trace.jsonl",
                    "append_only": True,
                },
                "memory_boundary": {
                    "policy": "none",
                    "memory_candidates": [],
                    "promotion_required": "user_approval_or_project_doc_update",
                },
            },
            "state_witness": {
                "required": False,
                "path": "",
                "required_tier": "policy",
                "observed_tier": "",
                "review_status": "not_required",
                "reviewer_id": "",
                "review_evidence": [],
                "sealed_digest": "",
                "reviewed_at": "",
            },
            "tdd_current_cycle_context": {
                "task_id": "",
                "gate_mode": "",
                "phase": "",
                "command": "",
                "result": "",
                "exit_code": None,
                "trace_path": "tdd_trace.jsonl",
                "stdout_tail": "",
                "stderr_tail": "",
                "retry_count": 0,
                "max_retries": 3,
                "updated_at": "",
            },
            "status": "specified",
            "current_stage": "1",
            "synthesis": {
                "status": "complete",
                "fuzzy_goal": False,
                "alignment_packet_path": "",
                "checklist": {
                    "rewritten_goal": True,
                    "fake_success_list": True,
                    "constraints_nongoals": True,
                    "pass_algorithms": True,
                    "risk_ordered_phases": True,
                    "first_ready_task": True,
                    "stop_conditions": True,
                },
                "recommended_defaults": [],
                "open_questions": [],
            },
            "stages": [
                {
                    "id": "1",
                    "name": "execution",
                    "status": "ready",
                    "tasks": ["1.1"],
                    "budget": "",
                    "evidence": [],
                    "stop_reason": "",
                }
            ],
            "tasks": [
                {
                    "id": "1.1",
                    "name": "worker",
                    "stage": 1,
                    "status": "ready",
                    "owner": "worker",
                    "allowed_scope": ["scripts/*"],
                    "task_path": "tasks/1.1-worker.md",
                    "report_path": "1.1-worker-report.md",
                    "dependencies": [],
                    "expected_outputs": ["report"],
                    "verification": ["unit tests"],
                    "verification_gate": {
                        "mode": "not_applicable",
                        "tdd_trace_path": "",
                        "red_command": "",
                        "red_result": "",
                        "red_failure_reason": "",
                        "green_command": "",
                        "green_result": "",
                        "refactor_check": "",
                        "substitute_check": "",
                        "no_test_reason": "routing unit test fixture",
                    },
                    "retry_count": 0,
                    "budget": "",
                    "runtime_budget_seconds": 1800,
                    "required_cwd": "",
                    "repository_root": "",
                    "required_branch": "",
                    "evidence": [],
                    "stop_reason": "",
                }
            ],
            "acceptance_path": "acceptance_registry.json",
            "stop_reason": "",
            "handoff": {"summary": "", "next_actions": [], "open_risks": []},
        }

    def _dispatch(self, **kwargs) -> dict:
        return {
            "dispatch_id": "11111111-1111-1111-1111-111111111111",
            "worker_id": "w1",
            "task_id": "1.1",
            "contract_path": "tasks/1.1-worker.md",
            "report_path": "1.1-worker-report.md",
            "status": "dispatched",
            "runtime": kwargs.get("runtime", "grok"),
            "profile": kwargs.get("profile", "fast"),
            "requested_model": kwargs.get("requested_model", "grok-api"),
            "resolved_model": kwargs.get("resolved_model", ""),
            "reasoning_effort": kwargs.get("reasoning_effort", "low"),
            "route_reason": kwargs.get("route_reason", "simple mechanically verifiable batch on 4.5"),
            "escalation_count": 0,
            "created_at": "2026-07-17T00:00:00Z",
            "updated_at": "2026-07-17T00:00:00Z",
            "stop_reason": "",
        }

    def _validate(self, state: dict) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run_state.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            return validate_run_state(path)

    def test_grok_fast_dispatch_valid(self):
        state = self._base_state()
        state["state_layers"]["session_state"]["delegation_state"] = [self._dispatch()]
        errors = self._validate(state)
        self.assertEqual(errors, [], errors)

    def test_grok_fast_wrong_model_rejected(self):
        state = self._base_state()
        state["state_layers"]["session_state"]["delegation_state"] = [
            self._dispatch(requested_model="grok-fast")
        ]
        errors = self._validate(state)
        self.assertTrue(any("requested_model must match grok profile" in e for e in errors), errors)

    def test_codex_regression(self):
        state = self._base_state()
        state["state_layers"]["session_state"]["delegation_state"] = [
            self._dispatch(
                runtime="codex",
                profile="fast",
                requested_model="gpt-5.6-luna",
                reasoning_effort="medium",
            )
        ]
        errors = self._validate(state)
        self.assertEqual(errors, [], errors)


class DocsTests(unittest.TestCase):
    def test_adapter_and_example_exist(self):
        grok_adapter = (SKILL_ROOT / "adapters" / "grok.md").read_text(encoding="utf-8")
        self.assertIn("grok-api", grok_adapter)
        self.assertIn("4.5", grok_adapter)
        self.assertIn("density", grok_adapter.casefold())
        self.assertIn("`grok-api`", grok_adapter)

        routing = (SKILL_ROOT / "references" / "model-routing.md").read_text(encoding="utf-8")
        self.assertIn("## Grok Policy", routing)
        self.assertIn("every profile", routing.casefold())
        self.assertIn("`grok-api`", routing)

        example = (SKILL_ROOT / "references" / "examples" / "grok-fast-model-config.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn("OPTIONAL", example)
        self.assertIn("[model.grok-fast]", example)


def write_matrix(path: Path) -> None:
    cases = [
        ["--runtime", "grok", "--simple", "--mechanically-verifiable"],
        ["--runtime", "grok"],
        ["--runtime", "grok", "--fuzzy"],
        ["--runtime", "grok", "--harness-synthesis"],
        ["--runtime", "grok", "--high-risk"],
        ["--runtime", "grok", "--validation-failures", "2"],
        ["--runtime", "codex", "--simple", "--mechanically-verifiable"],
        ["--runtime", "codex"],
    ]
    rows = []
    for args in cases:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "model_router.py"), *args],
            check=True,
            capture_output=True,
            text=True,
        )
        rows.append({"args": args, "result": json.loads(proc.stdout)})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    if "--write-matrix" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--write-matrix") + 1])
        write_matrix(out)
        print(f"wrote {out}")
        return 0
    if "--expect-missing-grok" in sys.argv:
        # Historical RED helper: fail if Grok map missing (used only before implementation).
        if "GROK_MODEL_PROFILES" in (SCRIPTS / "harness_schema.py").read_text(encoding="utf-8"):
            print("GROK map present; RED expectation not met (implementation already landed)")
            return 1
        print("GROK map missing as expected for RED")
        return 0
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
