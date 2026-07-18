#!/usr/bin/env python3
"""Behavioral tests for durable cross-runtime checkpoint, handoff, and resume."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)


def require_success(result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HandoffResumeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project = Path(tempfile.mkdtemp(prefix="harness-handoff-"))
        require_success(run("git", "init", "-q", str(self.project)))
        require_success(run("git", "config", "user.email", "harness@example.invalid", cwd=self.project))
        require_success(run("git", "config", "user.name", "Harness Test", cwd=self.project))
        (self.project / "README.md").write_text("initial\n", encoding="utf-8")
        require_success(run("git", "add", "README.md", cwd=self.project))
        require_success(run("git", "commit", "-qm", "initial", cwd=self.project))

    def tearDown(self) -> None:
        shutil.rmtree(self.project)

    def init_artifact(self, title: str, *, witness: bool = False) -> Path:
        command = [
            "python3",
            "scripts/init_run.py",
            "--project-root",
            str(self.project),
            "--mode",
            "full",
            "--title",
            title,
            "--agents",
            "implementation",
        ]
        if witness:
            command.extend(["--with-state-witness", "--required-verification-tier", "flow"])
        result = run(*command)
        require_success(result)
        return self.project / "workspace" / title.replace(" ", "-")

    def harness(self, command: str, path: Path | None = None, *args: str) -> subprocess.CompletedProcess[str]:
        return run(
            "python3",
            "scripts/harnessctl.py",
            command,
            str(path or self.project),
            *args,
        )

    def checkpoint(self, *, actor: str = "codex-main", next_action: str = "run focused tests") -> dict[str, object]:
        result = self.harness(
            "checkpoint",
            self.project,
            "--runtime",
            "codex",
            "--actor-id",
            actor,
            "--current-task",
            "1.1",
            "--next-action",
            next_action,
            "--pending-verification",
            "focused regression suite",
            "--reason",
            "safe point before quota boundary",
        )
        require_success(result)
        return json.loads(result.stdout)

    def test_unique_active_run_is_discovered_from_project_root(self) -> None:
        artifact = self.init_artifact("unique active")
        result = self.harness("discover", self.project)
        require_success(result)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["active_count"], 1)
        self.assertEqual(payload["runs"][0]["artifact_dir"], str(artifact.resolve()))

    def test_resume_rejects_ambiguous_active_runs_without_mutation(self) -> None:
        first = self.init_artifact("first active")
        second = self.init_artifact("second active")
        before = {path: sha256(path / "run_state.json") for path in (first, second)}
        result = self.harness(
            "resume",
            self.project,
            "--runtime",
            "grok",
            "--actor-id",
            "grok-main",
            "--takeover-reason",
            "codex quota exhausted",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("multiple active", result.stderr.casefold())
        self.assertEqual(before, {path: sha256(path / "run_state.json") for path in (first, second)})

    def test_resume_rejects_corrupt_artifact_before_claim(self) -> None:
        artifact = self.project / "workspace" / "corrupt"
        artifact.mkdir(parents=True)
        (artifact / "run_state.json").write_text("{broken\n", encoding="utf-8")
        result = self.harness(
            "resume",
            self.project,
            "--runtime",
            "grok",
            "--actor-id",
            "grok-main",
            "--takeover-reason",
            "codex quota exhausted",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("corrupt", result.stderr.casefold())
        self.assertEqual((artifact / "run_state.json").read_text(encoding="utf-8"), "{broken\n")

    def test_explicit_handoff_then_resume(self) -> None:
        artifact = self.init_artifact("explicit handoff")
        self.checkpoint(next_action="implement resume packet")
        handed_off = self.harness(
            "handoff",
            self.project,
            "--actor-id",
            "codex-main",
            "--owner-epoch",
            "1",
            "--reason",
            "Codex quota is low",
            "--next-action",
            "implement resume packet",
        )
        require_success(handed_off)

        resumed = self.harness(
            "resume",
            self.project,
            "--runtime",
            "grok",
            "--actor-id",
            "grok-main",
        )
        require_success(resumed)
        packet = json.loads(resumed.stdout)
        state = load_json(artifact / "run_state.json")
        self.assertEqual(packet["artifact_dir"], str(artifact.resolve()))
        self.assertEqual(packet["previous_owner"]["actor_id"], "codex-main")
        self.assertEqual(packet["owner"]["actor_id"], "grok-main")
        self.assertEqual(packet["recorded_next_action"], "implement resume packet")
        self.assertEqual(packet["pending_verification"], ["focused regression suite"])
        self.assertIn("task_spec.md", packet["required_reads"])
        self.assertTrue(
            all((artifact / value).is_file() for value in packet["required_reads"]),
            packet["required_reads"],
        )
        self.assertIn("1.1-implementation-report.md", packet["missing_required_reads"])
        self.assertEqual(state["status"], "intake")
        self.assertEqual(state["continuation"]["status"], "active")

    def test_abrupt_codex_to_grok_takeover_requires_reason(self) -> None:
        artifact = self.init_artifact("abrupt takeover")
        self.checkpoint(next_action="inspect interrupted implementation")
        refused = self.harness(
            "resume",
            self.project,
            "--runtime",
            "grok",
            "--actor-id",
            "grok-main",
        )
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("takeover reason", refused.stderr.casefold())

        resumed = self.harness(
            "resume",
            self.project,
            "--runtime",
            "grok",
            "--actor-id",
            "grok-main",
            "--takeover-reason",
            "Codex quota exhausted unexpectedly",
        )
        require_success(resumed)
        packet = json.loads(resumed.stdout)
        state = load_json(artifact / "run_state.json")
        self.assertTrue(packet["forced_takeover"])
        self.assertEqual(packet["owner"]["runtime"], "grok")
        self.assertEqual(packet["owner"]["epoch"], 2)
        self.assertEqual(state["status"], "intake")

    def test_stale_owner_is_fenced_after_takeover(self) -> None:
        artifact = self.init_artifact("owner fence")
        self.checkpoint()
        resumed = self.harness(
            "resume",
            self.project,
            "--runtime",
            "grok",
            "--actor-id",
            "grok-main",
            "--takeover-reason",
            "Codex quota exhausted",
        )
        require_success(resumed)
        before = sha256(artifact / "run_state.json")

        stale = self.harness(
            "task-set",
            artifact,
            "--task-id",
            "1.1",
            "--status",
            "ready",
            "--actor-id",
            "codex-main",
            "--owner-epoch",
            "1",
        )
        self.assertNotEqual(stale.returncode, 0)
        self.assertIn("current owner", stale.stderr.casefold())
        self.assertEqual(before, sha256(artifact / "run_state.json"))

        current = self.harness(
            "task-set",
            artifact,
            "--task-id",
            "1.1",
            "--status",
            "ready",
            "--actor-id",
            "grok-main",
            "--owner-epoch",
            "2",
        )
        require_success(current)

    def test_reused_actor_id_is_still_fenced_by_owner_epoch(self) -> None:
        artifact = self.init_artifact("epoch fence")
        self.checkpoint()
        require_success(
            self.harness(
                "resume",
                self.project,
                "--runtime",
                "grok",
                "--actor-id",
                "grok-main",
                "--takeover-reason",
                "Codex quota exhausted",
            )
        )
        returned = self.harness(
            "resume",
            self.project,
            "--runtime",
            "codex",
            "--actor-id",
            "codex-main",
            "--takeover-reason",
            "Grok quota exhausted",
        )
        require_success(returned)
        self.assertEqual(json.loads(returned.stdout)["owner"]["epoch"], 3)

        stale = self.harness(
            "task-set",
            artifact,
            "--task-id",
            "1.1",
            "--status",
            "ready",
            "--actor-id",
            "codex-main",
            "--owner-epoch",
            "1",
        )
        self.assertNotEqual(stale.returncode, 0)
        self.assertIn("owner epoch", stale.stderr.casefold())

        current = self.harness(
            "task-set",
            artifact,
            "--task-id",
            "1.1",
            "--status",
            "ready",
            "--actor-id",
            "codex-main",
            "--owner-epoch",
            "3",
        )
        require_success(current)

    def test_resume_surfaces_post_checkpoint_workspace_drift(self) -> None:
        self.init_artifact("workspace drift")
        self.checkpoint(next_action="continue implementation")
        (self.project / "README.md").write_text("changed after checkpoint\n", encoding="utf-8")

        resumed = self.harness(
            "resume",
            self.project,
            "--runtime",
            "grok",
            "--actor-id",
            "grok-main",
            "--takeover-reason",
            "Codex quota exhausted",
        )
        require_success(resumed)
        packet = json.loads(resumed.stdout)
        self.assertTrue(packet["workspace_drift"])
        self.assertIn("README.md", packet["changed_paths"])
        self.assertIn("inspect", packet["next_verification"].casefold())
        self.assertEqual(packet["recorded_next_action"], "continue implementation")

    def test_preexisting_dirty_workspace_without_new_changes_is_not_drift(self) -> None:
        self.init_artifact("stable dirty workspace")
        (self.project / "README.md").write_text("dirty before checkpoint\n", encoding="utf-8")
        self.checkpoint(next_action="continue known dirty implementation")

        resumed = self.harness(
            "resume",
            self.project,
            "--runtime",
            "grok",
            "--actor-id",
            "grok-main",
            "--takeover-reason",
            "Codex quota exhausted",
        )
        require_success(resumed)
        packet = json.loads(resumed.stdout)
        self.assertFalse(packet["workspace_drift"])
        self.assertEqual(packet["changed_paths"], [])

    def test_drift_paths_exclude_unchanged_preexisting_dirty_files(self) -> None:
        self.init_artifact("precise dirty attribution")
        (self.project / "README.md").write_text("dirty before checkpoint\n", encoding="utf-8")
        self.checkpoint(next_action="continue known dirty implementation")
        (self.project / "later.txt").write_text("created after checkpoint\n", encoding="utf-8")

        resumed = self.harness(
            "resume",
            self.project,
            "--runtime",
            "grok",
            "--actor-id",
            "grok-main",
            "--takeover-reason",
            "Codex quota exhausted",
        )
        require_success(resumed)
        packet = json.loads(resumed.stdout)
        self.assertTrue(packet["workspace_drift"])
        self.assertEqual(packet["changed_paths"], ["later.txt"])

    def test_status_exposes_continuation_owner_epoch_and_next_action(self) -> None:
        artifact = self.init_artifact("continuation status")
        self.checkpoint(next_action="run the handoff regression suite")
        result = run("python3", "scripts/status.py", str(artifact / "run_state.json"))
        require_success(result)
        self.assertIn("Continuation: active", result.stdout)
        self.assertIn("codex-main", result.stdout)
        self.assertIn("epoch=1", result.stdout)
        self.assertIn("run the handoff regression suite", result.stdout)

    def test_terminal_runs_are_not_auto_resumed(self) -> None:
        artifact = self.init_artifact("terminal run")
        state = load_json(artifact / "run_state.json")
        state["status"] = "failed"
        write_json(artifact / "run_state.json", state)
        result = self.harness("discover", self.project)
        require_success(result)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["active_count"], 0)

    def test_valid_legacy_artifact_is_upgraded_on_resume(self) -> None:
        artifact = self.init_artifact("legacy run")
        state_path = artifact / "run_state.json"
        state = load_json(state_path)
        state.pop("continuation", None)
        write_json(state_path, state)
        trace_path = artifact / "trace.jsonl"
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        events[0]["state_digests"]["run_state.json"] = sha256(state_path)
        trace_path.write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in events), encoding="utf-8")

        resumed = self.harness(
            "resume",
            self.project,
            "--runtime",
            "grok",
            "--actor-id",
            "grok-main",
        )
        require_success(resumed)
        packet = json.loads(resumed.stdout)
        self.assertTrue(packet["legacy_upgrade"])
        self.assertTrue(packet["recorded_next_action"])

    def test_resume_recovers_incomplete_state_transaction(self) -> None:
        artifact = self.init_artifact("recover on resume")
        self.checkpoint()
        state_path = artifact / "run_state.json"
        digest = sha256(state_path)
        transaction_id = str(uuid.uuid4())
        started = {
            "event": "checkpoint_started",
            "transaction_id": transaction_id,
            "state_file": "run_state.json",
            "before_sha256": digest,
            "after_sha256": digest,
            "reason": "simulated process death",
        }
        with (artifact / "trace.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(started, sort_keys=True) + "\n")

        resumed = self.harness(
            "resume",
            self.project,
            "--runtime",
            "grok",
            "--actor-id",
            "grok-main",
            "--takeover-reason",
            "Codex quota exhausted",
        )
        require_success(resumed)
        trace = (artifact / "trace.jsonl").read_text(encoding="utf-8")
        self.assertIn(transaction_id, trace)
        self.assertIn('"event": "checkpoint"', trace)

    def test_rejected_resume_does_not_commit_planned_recovery(self) -> None:
        artifact = self.init_artifact("rejected recovery")
        self.checkpoint()
        state_path = artifact / "run_state.json"
        digest = sha256(state_path)
        transaction_id = str(uuid.uuid4())
        started = {
            "event": "checkpoint_started",
            "transaction_id": transaction_id,
            "state_file": "run_state.json",
            "before_sha256": digest,
            "after_sha256": digest,
            "reason": "simulated process death",
        }
        trace_path = artifact / "trace.jsonl"
        with trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(started, sort_keys=True) + "\n")
        (artifact / "acceptance_registry.json").write_text("{invalid\n", encoding="utf-8")
        trace_before = sha256(trace_path)
        state_before = sha256(state_path)

        resumed = self.harness(
            "resume",
            self.project,
            "--runtime",
            "grok",
            "--actor-id",
            "grok-main",
            "--takeover-reason",
            "Codex quota exhausted",
        )
        self.assertNotEqual(resumed.returncode, 0)
        self.assertEqual(trace_before, sha256(trace_path))
        self.assertEqual(state_before, sha256(state_path))

    def test_rejected_forced_resume_does_not_commit_planned_recovery(self) -> None:
        artifact = self.init_artifact("rejected forced recovery")
        self.checkpoint()
        state_path = artifact / "run_state.json"
        digest = sha256(state_path)
        transaction_id = str(uuid.uuid4())
        started = {
            "event": "checkpoint_started",
            "transaction_id": transaction_id,
            "state_file": "run_state.json",
            "before_sha256": digest,
            "after_sha256": digest,
            "reason": "simulated process death",
        }
        trace_path = artifact / "trace.jsonl"
        with trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(started, sort_keys=True) + "\n")
        trace_before = sha256(trace_path)
        state_before = sha256(state_path)

        resumed = self.harness(
            "resume",
            self.project,
            "--runtime",
            "grok",
            "--actor-id",
            "grok-main",
        )
        self.assertNotEqual(resumed.returncode, 0)
        self.assertIn("takeover reason", resumed.stderr.casefold())
        self.assertEqual(trace_before, sha256(trace_path))
        self.assertEqual(state_before, sha256(state_path))

    def test_reopened_task_can_refresh_rewritten_report_before_reacceptance(self) -> None:
        artifact = self.init_artifact("reopened report refresh")
        state = load_json(artifact / "run_state.json")
        task = next(item for item in state["tasks"] if item["id"] == "1.1")
        report_path = artifact / task["report_path"]
        report_path.write_text("# Initial report\n\nPASS\n", encoding="utf-8")

        for status in ("ready", "running"):
            require_success(self.harness("task-set", artifact, "--task-id", "1.1", "--status", status))
        require_success(
            self.harness(
                "task-set",
                artifact,
                "--task-id",
                "1.1",
                "--status",
                "passed",
                "--evidence-file",
                task["report_path"],
                "--no-test-reason",
                "fixture report verification",
            )
        )
        require_success(
            self.harness(
                "task-set",
                artifact,
                "--task-id",
                "1.1",
                "--status",
                "verify_failed",
                "--stop-reason",
                "independent review requested a rerun",
            )
        )
        for status in ("ready", "running"):
            require_success(self.harness("task-set", artifact, "--task-id", "1.1", "--status", status))
        report_path.write_text("# Rechecked report\n\nPASS after rerun\n", encoding="utf-8")

        refreshed = self.harness(
            "task-refresh",
            artifact,
            "--task-id",
            "1.1",
            "--evidence-file",
            task["report_path"],
        )
        require_success(refreshed)
        require_success(self.harness("validate", artifact))

    def test_seal_rebinds_human_edited_witness_baseline(self) -> None:
        artifact = self.init_artifact("seal edited baseline", witness=True)
        state_path = artifact / "run_state.json"
        state = load_json(state_path)
        state["state_layers"]["working_state"]["volatile_notes"] = ["filled before seal"]
        write_json(state_path, state)
        (artifact / "state_witness.md").write_text(
            """# Production State Witness

## Symptom and terminal condition
- Symptom: source owner stops.
- Success observable: destination resumes.

## Actual call chain
`scripts/harnessctl.py::resume` -> `scripts/harnessctl.py::validate_artifact` -> packet

## State inputs
| Input | Producer | Lifecycle/event | Source locator | Reported value |
|---|---|---|---|---|
| owner | checkpoint | resume | `run_state.json::continuation.owner` | codex |

## Truth table
| Case | Production state | Observed before | Expected after | Executable evidence |
|---|---|---|---|---|
| failing before | active owner | no resume | RED | `python3 scripts/test_handoff_resume.py` |
| fixed after | active owner | RED | resume | `python3 scripts/test_handoff_resume.py` |
| preserved block | corrupt state | blocked | blocked | `python3 scripts/test_handoff_resume.py` |

## Unknowns and instrumentation
- Unknown: provider callback; Log/fixture: subprocess.

## Verification tier
- Required tier: flow
- Observed tier: pending
- Review status: pending
- Independent reviewer: critical-reviewer
- Review evidence path: `evidence/adversarial_review.md`
""",
            encoding="utf-8",
        )
        sealed = self.harness("seal", artifact, "--reason", "reviewed human baseline")
        require_success(sealed)
        validated = self.harness("validate", artifact)
        require_success(validated)

    def test_tdd_wrapper_preserves_sealed_run_digest_chain(self) -> None:
        artifact = self.init_artifact("sealed tdd context")
        sealed = self.harness("seal", artifact, "--reason", "bind baseline before TDD")
        require_success(sealed)
        checked = run(
            "python3",
            "scripts/harness_test_run.py",
            "--trace",
            str(artifact / "tdd_trace.jsonl"),
            "--task-id",
            "1.1",
            "--phase",
            "REFACTOR",
            "--run-state",
            str(artifact / "run_state.json"),
            "--",
            "python3",
            "-c",
            "print('verified')",
        )
        require_success(checked)
        validated = self.harness("validate", artifact)
        require_success(validated)

    def test_reseal_rebinds_pre_dispatch_run_state_without_breaking_chain(self) -> None:
        artifact = self.init_artifact("rebind sealed state", witness=True)
        witness = artifact / "state_witness.md"
        witness.write_text(
            (ROOT / "references" / "examples" / "state-witness-example.md").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
        require_success(self.harness("seal", artifact, "--reason", "bind first baseline"))
        state_path = artifact / "run_state.json"
        state = load_json(state_path)
        state["state_layers"]["working_state"]["volatile_notes"] = ["updated before dispatch"]
        write_json(state_path, state)

        resealed = self.harness("seal", artifact, "--reason", "authorize updated pre-dispatch state")
        require_success(resealed)
        require_success(self.harness("validate", artifact))

    def test_tdd_wrapper_rejects_stale_owner_before_running_command(self) -> None:
        artifact = self.init_artifact("stale tdd wrapper")
        self.checkpoint()
        require_success(
            self.harness(
                "resume",
                self.project,
                "--runtime",
                "grok",
                "--actor-id",
                "grok-main",
                "--takeover-reason",
                "Codex quota exhausted",
            )
        )
        marker = self.project / "stale-command-ran"
        stale = run(
            "python3",
            "scripts/harness_test_run.py",
            "--trace",
            str(artifact / "tdd_trace.jsonl"),
            "--task-id",
            "1.1",
            "--phase",
            "REFACTOR",
            "--run-state",
            str(artifact / "run_state.json"),
            "--actor-id",
            "codex-main",
            "--owner-epoch",
            "1",
            "--",
            "python3",
            "-c",
            f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
        )
        self.assertNotEqual(stale.returncode, 0)
        self.assertIn("current owner", stale.stderr.casefold())
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
