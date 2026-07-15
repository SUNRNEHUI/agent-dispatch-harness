#!/usr/bin/env python3
"""Create a clean runtime-only copy of the agent-dispatch-harness skill."""

from __future__ import annotations

import argparse
import filecmp
import shutil
from pathlib import Path


RUNTIME_FILES = [
    "VERSION",
    "SKILL.md",
    "master-prompt.md",
    "sub-prompt.md",
    "agents/openai.yaml",
    "adapters/claude-code.md",
    "adapters/codex.md",
    "adapters/universal.md",
    "references/closed-loop-pattern.md",
    "references/bugfix-lane.md",
    "references/eval_cases.md",
    "references/examples/fuzzy-goal-full-harness.md",
    "references/examples/state-witness-example.md",
    "references/feature-spec-lane.md",
    "references/harness-protocol.md",
    "references/model-routing.md",
    "references/proportionality.md",
    "references/roles.md",
    "references/spec-synthesis.md",
    "references/state-memory-boundary.md",
    "references/stop-conditions.md",
    "references/state-witness.md",
    "references/superpowers-integration.md",
    "references/tdd-gates.md",
    "scripts/harness_schema.py",
    "scripts/init_run.py",
    "scripts/harness_test_run.py",
    "scripts/harnessctl.py",
    "scripts/model_router.py",
    "scripts/runtime_state.py",
    "scripts/score_harness.py",
    "scripts/score_skill_protocol.py",
    "scripts/state_witness_check.py",
    "scripts/status.py",
    "scripts/tdd_gate_check.py",
    "scripts/validate_report.py",
    "scripts/validate_workspace.py",
    "templates/acceptance_registry.json",
    "templates/capability_snapshot.md",
    "templates/evaluator_report.md",
    "templates/lite_plan.md",
    "templates/lite_review.md",
    "templates/progress_ledger.md",
    "templates/run_state.json",
    "templates/state_witness.md",
    "templates/subagent_report.md",
    "templates/subagent_task.md",
    "templates/task_spec.md",
    "templates/tdd_trace.jsonl",
    "templates/trace.jsonl",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package only the files needed by the runtime skill."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to the parent of scripts/.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=False,
        help="Destination directory for the clean runtime copy.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace the output directory if it already exists.",
    )
    parser.add_argument(
        "--check",
        type=Path,
        help="Compare a freshly generated runtime package with an installed skill directory.",
    )
    parser.add_argument(
        "--verify-source",
        action="store_true",
        help="Only verify that runtime source files exist.",
    )
    return parser.parse_args()


def validate_source(source: Path) -> Path:
    source = source.expanduser().resolve()

    if not (source / "SKILL.md").is_file():
        raise SystemExit(f"source does not look like a skill repo: {source}")

    missing = [path for path in RUNTIME_FILES if not (source / path).is_file()]
    if missing:
        raise SystemExit("missing runtime files:\n- " + "\n- ".join(missing))

    return source


def validate_paths(source: Path, output: Path) -> tuple[Path, Path]:
    source = validate_source(source)
    output = output.expanduser().resolve()

    if source == output or source in output.parents:
        raise SystemExit("output must not be the source directory or inside it")

    return source, output


def prepare_output(output: Path, force: bool) -> None:
    if output.exists():
        if not force:
            raise SystemExit(f"output exists; pass --force to replace it: {output}")
        if output.parent == output or str(output) in {"/", str(Path.home())}:
            raise SystemExit(f"refusing to remove unsafe output path: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True)


def copy_runtime_files(source: Path, output: Path) -> None:
    for relative in RUNTIME_FILES:
        src = source / relative
        dst = output / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def compare_dirs(expected: Path, actual: Path) -> list[str]:
    differences: list[str] = []

    def walk(left: Path, right: Path, relative: Path = Path("")) -> None:
        comparison = filecmp.dircmp(left, right)
        for name in comparison.left_only:
            differences.append(f"missing in install: {relative / name}")
        for name in comparison.right_only:
            differences.append(f"extra in install: {relative / name}")
        for name in comparison.diff_files:
            differences.append(f"modified in install: {relative / name}")
        for name in comparison.funny_files:
            differences.append(f"unreadable or incompatible: {relative / name}")
        for name in comparison.common_dirs:
            walk(left / name, right / name, relative / name)

    walk(expected, actual)
    return sorted(str(item) for item in differences)


def check_install(source: Path, install_dir: Path) -> int:
    source = validate_source(source)
    install_dir = install_dir.expanduser().resolve()
    if not install_dir.is_dir():
        raise SystemExit(f"install directory does not exist: {install_dir}")

    temp_output = Path("/tmp/agent-dispatch-harness-package-check")
    prepare_output(temp_output, force=True)
    copy_runtime_files(source, temp_output)
    differences = compare_dirs(temp_output, install_dir)
    if differences:
        print(f"FAIL runtime install differs from source package: {install_dir}")
        for difference in differences:
            print(f"- {difference}")
        return 1
    print(f"runtime_install=verified {install_dir}")
    return 0


def main() -> None:
    args = parse_args()
    if args.verify_source:
        source = validate_source(args.source)
        print(f"runtime_source=verified {source}")
        return
    if args.check:
        raise SystemExit(check_install(args.source, args.check))
    if args.output is None:
        raise SystemExit("--output is required unless --check or --verify-source is used")
    source, output = validate_paths(args.source, args.output)
    prepare_output(output, args.force)
    copy_runtime_files(source, output)

    print(f"runtime_package={output}")
    print("created:")
    for relative in RUNTIME_FILES:
        print(f"- {relative}")


if __name__ == "__main__":
    main()
