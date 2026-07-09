#!/usr/bin/env python3
"""Check or update current-version references from VERSION."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


VERSION_PATTERNS = {
    "README.md": (
        (
            re.compile(r"^Current version: \*\*v[^*]+\*\* · .*$", re.MULTILINE),
            "Current version: **v{version}** · {date}",
        ),
    ),
    "README.zh-CN.md": (
        (
            re.compile(r"^当前版本：\*\*v[^*]+\*\* · .*$", re.MULTILINE),
            "当前版本：**v{version}** · {date}",
        ),
    ),
    "SKILL.md": (
        (
            re.compile(r"^\*Agent Dispatch Harness v[^|]+ \| [^*]+\*$", re.MULTILINE),
            "*Agent Dispatch Harness v{version} | {date}*",
        ),
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync current version references from VERSION.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to the parent of scripts/.",
    )
    parser.add_argument("--date", default="2026-07-09", help="Release date to write with --fix.")
    parser.add_argument("--fix", action="store_true", help="Rewrite current-version references.")
    return parser.parse_args()


def read_version(root: Path) -> str:
    path = root / "VERSION"
    if not path.is_file():
        raise SystemExit(f"missing VERSION file: {path}")
    version = path.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit(f"VERSION must be MAJOR.MINOR.PATCH, got {version!r}")
    return version


def sync_file(path: Path, version: str, date: str, fix: bool) -> list[str]:
    content = path.read_text(encoding="utf-8")
    updated = content
    errors: list[str] = []

    for pattern, replacement in VERSION_PATTERNS[path.name]:
        expected = replacement.format(version=version, date=date)
        matches = pattern.findall(updated)
        if not matches:
            errors.append(f"{path.name}: missing current-version pattern {pattern.pattern!r}")
            continue
        updated = pattern.sub(expected, updated, count=1)

    if updated != content:
        if fix:
            path.write_text(updated, encoding="utf-8")
        else:
            errors.append(f"{path.name}: current version is not v{version}; run with --fix")
    return errors


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve()
    version = read_version(root)

    errors: list[str] = []
    for filename in VERSION_PATTERNS:
        path = root / filename
        if not path.is_file():
            errors.append(f"missing file: {path}")
            continue
        errors.extend(sync_file(path, version, args.date, args.fix))

    if errors:
        print("FAIL version sync")
        for error in errors:
            print(f"- {error}")
        return 1

    action = "updated" if args.fix else "verified"
    print(f"version_sync={action} v{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
