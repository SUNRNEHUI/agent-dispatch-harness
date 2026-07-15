#!/usr/bin/env python3
"""Select the configured Codex model profile from observable task signals."""

from __future__ import annotations

import argparse
import json

from harness_schema import CODEX_MODEL_PROFILES, MODEL_ROUTING_POLICY


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select a cost-aware Codex model profile.")
    parser.add_argument("--simple", action="store_true")
    parser.add_argument("--mechanically-verifiable", action="store_true")
    parser.add_argument("--fuzzy", action="store_true")
    parser.add_argument("--harness-synthesis", action="store_true")
    parser.add_argument("--high-risk", action="store_true")
    parser.add_argument("--worker-conflict", action="store_true")
    parser.add_argument("--validation-failures", type=int, default=0)
    return parser.parse_args()


def select_profile(args: argparse.Namespace) -> tuple[str, list[str]]:
    if args.validation_failures < 0:
        raise ValueError("validation failures must be non-negative")
    if args.high_risk or args.worker_conflict or args.validation_failures >= 2:
        reasons = []
        if args.high_risk:
            reasons.append("high_risk")
        if args.worker_conflict:
            reasons.append("worker_conflict")
        if args.validation_failures >= 2:
            reasons.append("repeated_validation_failure")
        return "critical_reviewer", reasons
    if args.fuzzy or args.harness_synthesis:
        return "planner", ["fuzzy_goal" if args.fuzzy else "harness_synthesis"]
    if args.simple and args.mechanically_verifiable:
        return "fast", ["simple", "mechanically_verifiable"]
    return "main", ["default_high_frequency_main"]


def main() -> int:
    args = parse_args()
    try:
        profile, reasons = select_profile(args)
    except ValueError as exc:
        print(f"ERROR {exc}")
        return 2
    configuration = CODEX_MODEL_PROFILES[profile]
    print(
        json.dumps(
            {
                "policy": MODEL_ROUTING_POLICY,
                "runtime": "codex",
                "profile": profile,
                "model": configuration["model"],
                "reasoning_effort": configuration["reasoning_effort"],
                "reason_codes": reasons,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
