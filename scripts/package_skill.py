#!/usr/bin/env python3
"""Create a clean runtime-only copy of the multi-agent-dispatcher skill."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


RUNTIME_FILES = [
    "SKILL.md",
    "master-prompt.md",
    "sub-prompt.md",
    "agents/openai.yaml",
    "adapters/claude-code.md",
    "adapters/codex.md",
    "references/closed-loop-pattern.md",
    "references/eval_cases.md",
    "references/harness-protocol.md",
    "references/roles.md",
    "references/stop-conditions.md",
    "references/superpowers-integration.md",
    "references/tdd-gates.md",
    "scripts/init_run.py",
    "scripts/validate_report.py",
    "templates/acceptance_registry.json",
    "templates/capability_snapshot.md",
    "templates/evaluator_report.md",
    "templates/progress_ledger.md",
    "templates/run_state.json",
    "templates/subagent_report.md",
    "templates/subagent_task.md",
    "templates/task_spec.md",
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
        required=True,
        help="Destination directory for the clean runtime copy.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace the output directory if it already exists.",
    )
    return parser.parse_args()


def validate_paths(source: Path, output: Path) -> tuple[Path, Path]:
    source = source.expanduser().resolve()
    output = output.expanduser().resolve()

    if not (source / "SKILL.md").is_file():
        raise SystemExit(f"source does not look like a skill repo: {source}")

    if source == output or source in output.parents:
        raise SystemExit("output must not be the source directory or inside it")

    missing = [path for path in RUNTIME_FILES if not (source / path).is_file()]
    if missing:
        raise SystemExit("missing runtime files:\n- " + "\n- ".join(missing))

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


def main() -> None:
    args = parse_args()
    source, output = validate_paths(args.source, args.output)
    prepare_output(output, args.force)
    copy_runtime_files(source, output)

    print(f"runtime_package={output}")
    print("created:")
    for relative in RUNTIME_FILES:
        print(f"- {relative}")


if __name__ == "__main__":
    main()
