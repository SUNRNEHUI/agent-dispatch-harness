#!/usr/bin/env python3
"""Regression tests for the Production State Witness control loop."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL = Path("/Users/sunrenhui/.codex/skills/agent-reliability-harness")


def run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def write_witness(path: Path, *, hollow: bool) -> None:
    if hollow:
        content = """# Production State Witness

## Symptom and terminal condition
- Symptom: x
- Success observable: y

## Actual call chain
a -> b

## State inputs
| Input | Producer | Lifecycle/event | Reported value |
|---|---|---|---|
| x | y | z | q |

## Truth table
| Case | Production state | Expected decision | Executable evidence |
|---|---|---|---|
| failing | x | allow | test |
| fixed | x | allow | test |
| preserved | x | block | test |

## Unknowns and instrumentation
- Unknown: none
- Log/fixture needed: none

## Verification tier
- policy / flow / user-visible
"""
    else:
        content = """# Production State Witness

## Symptom and terminal condition
- Symptom: imported thumbnails remain blank while the spinner stays visible
- Success observable: current token thumbnail cache is populated and spinner is false

## Actual call chain
user action -> Sources/ImportController.swift::handleImport -> Sources/ThumbnailGate.swift::shouldDecode -> Sources/ThumbnailStore.swift::commit -> Sources/ThumbnailCell.swift::render

## State inputs
| Input | Producer | Lifecycle/event | Source locator | Reported value |
|---|---|---|---|---|
| rawDisplayMode | render state | full render commit | Sources/EditorState.swift::rawDisplayMode | renderedRaw |
| presentationPending | first-frame receipt | receipt consumption | Sources/EditorState.swift::rawPresentationPending | true |
| baseReady | image service | base decode | Sources/ThumbnailService.swift::hasRawStyleThumbnailBase | true |
| importWindow | import lease | import tail release | Sources/ImportCoordinator.swift::importCriticalWindow | false |

## Truth table
| Case | Production state | Observed before | Expected after | Executable evidence |
|---|---|---|---|---|
| failing before | renderedRaw + presentationPending=true + baseReady=true + importWindow=false | blocked | allow | Tests/ThumbnailGateTests.swift::renderedRawPresentationPending |
| fixed after | renderedRaw + presentationPending=true + baseReady=true + importWindow=false | blocked | allow | Tests/ThumbnailGateTests.swift::renderedRawPresentationPending |
| preserved block | renderedRaw + presentationPending=true + baseReady=true + importWindow=true | blocked | blocked | Tests/ThumbnailGateTests.swift::importCriticalWindow |

## Unknowns and instrumentation
- Unknown: whether receipt consumption triggers a store refresh
- Log/fixture needed: Sources/ThumbnailPipeline.swift::logGateState

## Verification tier
- Required tier: user_visible
- Observed tier: flow
- Review status: pending
- Independent reviewer: reviewer-1
- Review evidence path: reports/state-witness-review.md
"""
    path.write_text(content, encoding="utf-8")


def hollow_witness(path: Path) -> None:
    write_witness(path, hollow=True)


class StateWitnessGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp(prefix="adh-state-witness-red-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp)

    def artifact(self, title: str = "state witness gate", *, state_witness: bool = False) -> Path:
        command = [
            "python3",
            "scripts/init_run.py",
            "--mode",
            "full",
            "--project-root",
            str(self.temp),
            "--title",
            title,
            "--force",
        ]
        if state_witness:
            command.extend(["--with-state-witness", "--required-verification-tier", "user_visible"])
        result = run(*command)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return self.temp / "workspace" / title.replace(" ", "-")

    def test_checker_rejects_hollow_witness(self) -> None:
        path = self.temp / "state_witness.md"
        hollow_witness(path)
        result = run("python3", "scripts/state_witness_check.py", str(path), "--require-filled")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_checker_rejects_mismatched_failing_and_fixed_state(self) -> None:
        path = self.temp / "state_witness.md"
        write_witness(path, hollow=False)
        text = path.read_text(encoding="utf-8").replace(
            "| fixed after | renderedRaw + presentationPending=true + baseReady=true + importWindow=false |",
            "| fixed after | impossible production combination |",
        )
        path.write_text(text, encoding="utf-8")
        result = run("python3", "scripts/state_witness_check.py", str(path), "--require-filled")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("same production state", result.stderr)

    def test_run_dispatch_requires_sealed_baseline(self) -> None:
        artifact = self.artifact("sealed dispatch")
        gated = run("python3", "scripts/harnessctl.py", "run-set", str(artifact), "--status", "gated")
        self.assertEqual(gated.returncode, 0, gated.stdout + gated.stderr)
        specified = run("python3", "scripts/harnessctl.py", "run-set", str(artifact), "--status", "specified")
        self.assertEqual(specified.returncode, 0, specified.stdout + specified.stderr)
        dispatched = run("python3", "scripts/harnessctl.py", "run-set", str(artifact), "--status", "dispatched")
        self.assertNotEqual(dispatched.returncode, 0, dispatched.stdout + dispatched.stderr)
        self.assertIn("sealed baseline", dispatched.stdout)

    def test_stateful_validate_rejects_unfilled_witness(self) -> None:
        artifact = self.artifact("stateful validation", state_witness=True)
        result = run("python3", "scripts/harnessctl.py", "validate", str(artifact))
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("state_witness", result.stdout)

    def test_stateful_run_can_seal_review_and_accept(self) -> None:
        artifact = self.artifact("stateful happy path", state_witness=True)
        write_witness(artifact / "state_witness.md", hollow=False)
        sealed = run(
            "python3",
            "scripts/harnessctl.py",
            "seal",
            str(artifact),
            "--reason",
            "witness reviewed before dispatch",
        )
        self.assertEqual(sealed.returncode, 0, sealed.stdout + sealed.stderr)
        reviewed = run(
            "python3",
            "scripts/harnessctl.py",
            "witness-set",
            str(artifact),
            "--status",
            "pass",
            "--reviewer-id",
            "reviewer-1",
            "--verification-tier",
            "user_visible",
            "--evidence-file",
            "state_witness.md",
        )
        self.assertEqual(reviewed.returncode, 0, reviewed.stdout + reviewed.stderr)
        accepted = run(
            "python3",
            "scripts/harnessctl.py",
            "acceptance-set",
            str(artifact),
            "--criterion-id",
            "AC-001",
            "--status",
            "pass",
            "--verification-tier",
            "user_visible",
            "--evidence-file",
            "state_witness.md",
            "--pass-algorithm",
            "thumbnail cache and spinner reach the terminal UI state",
            "--no-test-reason",
            "UI evidence is supplied by the witness flow fixture",
        )
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
        validated = run("python3", "scripts/harnessctl.py", "validate", str(artifact))
        self.assertEqual(validated.returncode, 0, validated.stdout + validated.stderr)

    def test_witness_review_rejects_below_required_tier(self) -> None:
        artifact = self.artifact("tier gate", state_witness=True)
        write_witness(artifact / "state_witness.md", hollow=False)
        sealed = run(
            "python3",
            "scripts/harnessctl.py",
            "seal",
            str(artifact),
            "--reason",
            "bind witness before tier review",
        )
        self.assertEqual(sealed.returncode, 0, sealed.stdout + sealed.stderr)
        reviewed = run(
            "python3",
            "scripts/harnessctl.py",
            "witness-set",
            str(artifact),
            "--status",
            "pass",
            "--reviewer-id",
            "reviewer-1",
            "--verification-tier",
            "flow",
            "--evidence-file",
            "state_witness.md",
        )
        self.assertNotEqual(reviewed.returncode, 0, reviewed.stdout + reviewed.stderr)
        self.assertIn("below required user_visible", reviewed.stdout)

    def test_sealed_witness_digest_rejects_post_seal_mutation(self) -> None:
        artifact = self.artifact("sealed mutation", state_witness=True)
        write_witness(artifact / "state_witness.md", hollow=False)
        sealed = run(
            "python3",
            "scripts/harnessctl.py",
            "seal",
            str(artifact),
            "--reason",
            "bind witness before mutation check",
        )
        self.assertEqual(sealed.returncode, 0, sealed.stdout + sealed.stderr)
        witness = artifact / "state_witness.md"
        witness.write_text(witness.read_text(encoding="utf-8") + "\npost-seal mutation\n", encoding="utf-8")
        reviewed = run(
            "python3",
            "scripts/harnessctl.py",
            "witness-set",
            str(artifact),
            "--status",
            "pass",
            "--reviewer-id",
            "reviewer-1",
            "--verification-tier",
            "user_visible",
            "--evidence-file",
            "state_witness.md",
        )
        self.assertNotEqual(reviewed.returncode, 0, reviewed.stdout + reviewed.stderr)
        self.assertIn("state_witness.md", reviewed.stdout)

    def test_seal_rejects_required_but_unverified_witness(self) -> None:
        artifact = self.artifact(state_witness=True)
        result = run(
            "python3",
            "scripts/harnessctl.py",
            "seal",
            str(artifact),
            "--reason",
            "state witness must be filled before dispatch",
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_acceptance_rejects_policy_only_evidence_for_user_visible_state(self) -> None:
        artifact = self.artifact("stateful acceptance", state_witness=True)
        hollow_witness(artifact / "state_witness.md")
        result = run(
            "python3",
            "scripts/harnessctl.py",
            "acceptance-set",
            str(artifact),
            "--criterion-id",
            "AC-001",
            "--status",
            "pass",
            "--evidence-file",
            "state_witness.md",
            "--pass-algorithm",
            "user-visible state reaches the terminal render",
            "--no-test-reason",
            "not a policy-only criterion",
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_evaluator_requires_state_witness_sections(self) -> None:
        report = self.temp / "evaluator.md"
        report.write_text(
            """# Evaluator Report

Result: PASS

## Scope Checked
x
## Testing Gate Evidence Checked
- TDD trace path: x
- Trace chronology checked: x
- RED before GREEN: x
- First production edit after RED: x
- Gate records reviewed: x
- Missing or invalid gate records: none
- Strict TDD evidence accepted: x
- Substitute verification accepted: n/a
- Substitute reason checked: n/a
- Review gate evidence checked: x
## Evidence
x
## Blocking Issues
none
## Non-Blocking Issues
none
## Stub Or Placeholder Check
x
## Required Fixes
none
## Residual Risk
none
""",
            encoding="utf-8",
        )
        result = run(
            "python3",
            "scripts/validate_report.py",
            str(report),
            "--type",
            "evaluator",
            "--require-filled",
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_runtime_package_matches_install(self) -> None:
        result = run("python3", "scripts/package_skill.py", "--check", str(INSTALL))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
