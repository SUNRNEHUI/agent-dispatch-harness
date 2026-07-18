#!/usr/bin/env python3
"""Select a cost-aware model profile from observable task signals."""

from __future__ import annotations

import argparse
import json
import os

from harness_schema import (
    MODEL_ROUTING_POLICY,
    SUPPORTED_MODEL_RUNTIMES,
    model_profiles_for,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select a cost-aware model profile.")
    parser.add_argument(
        "--runtime",
        default="codex",
        help="Runtime mapping to resolve (codex|grok). Default: codex.",
    )
    parser.add_argument("--simple", action="store_true")
    parser.add_argument("--mechanically-verifiable", action="store_true")
    parser.add_argument("--fuzzy", action="store_true")
    parser.add_argument("--harness-synthesis", action="store_true")
    parser.add_argument("--high-risk", action="store_true")
    parser.add_argument("--worker-conflict", action="store_true")
    parser.add_argument("--validation-failures", type=int, default=0)
    parser.add_argument(
        "--allow-env-override",
        action="store_true",
        help="Apply HARNESS_<RUNTIME>_<PROFILE>_MODEL env overrides to the sealed map.",
    )
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


def env_override_key(runtime: str, profile: str) -> str:
    return f"HARNESS_{runtime.upper()}_{profile.upper()}_MODEL"


def apply_env_overrides(
    runtime: str, profiles: dict[str, dict[str, str]]
) -> tuple[dict[str, dict[str, str]], list[str]]:
    applied: list[str] = []
    updated = {name: dict(config) for name, config in profiles.items()}
    for profile, config in updated.items():
        key = env_override_key(runtime, profile)
        value = os.environ.get(key, "").strip()
        if value:
            config["model"] = value
            applied.append(key)
    return updated, applied


def resolve_configuration(
    runtime: str, profile: str, *, allow_env_override: bool = False
) -> tuple[dict[str, str], list[str]]:
    runtime_key = (runtime or "").strip().casefold()
    if runtime_key not in SUPPORTED_MODEL_RUNTIMES:
        supported = ", ".join(sorted(SUPPORTED_MODEL_RUNTIMES))
        raise ValueError(f"unsupported runtime {runtime!r}; expected one of: {supported}")
    profiles = model_profiles_for(runtime_key)
    if profiles is None or profile not in profiles:
        raise ValueError(f"no sealed profile {profile!r} for runtime {runtime_key!r}")
    overrides: list[str] = []
    if allow_env_override:
        profiles, overrides = apply_env_overrides(runtime_key, profiles)
    return dict(profiles[profile]), overrides


def main() -> int:
    args = parse_args()
    try:
        profile, reasons = select_profile(args)
        configuration, overrides = resolve_configuration(
            args.runtime, profile, allow_env_override=args.allow_env_override
        )
    except ValueError as exc:
        print(f"ERROR {exc}")
        return 2
    payload = {
        "policy": MODEL_ROUTING_POLICY,
        "runtime": args.runtime.strip().casefold(),
        "profile": profile,
        "model": configuration["model"],
        "reasoning_effort": configuration["reasoning_effort"],
        "reason_codes": reasons,
        "env_overrides_applied": overrides,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
