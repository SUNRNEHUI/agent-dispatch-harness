#!/usr/bin/env python3
"""Shared schema constants and transition rules for harness runtime files."""

from __future__ import annotations


SCHEMA_VERSION = 1
MODEL_ROUTING_POLICY = "cost-aware-v1"
AGENT_PROFILES = {"fast", "main", "planner", "critical_reviewer"}
SUPPORTED_MODEL_RUNTIMES = {"codex", "grok"}
CODEX_MODEL_PROFILES = {
    "fast": {"model": "gpt-5.6-luna", "reasoning_effort": "medium"},
    "main": {"model": "gpt-5.6-luna", "reasoning_effort": "xhigh"},
    "planner": {"model": "gpt-5.6-sol", "reasoning_effort": "high"},
    "critical_reviewer": {"model": "gpt-5.6-sol", "reasoning_effort": "xhigh"},
}
GROK_MODEL_PROFILES = {
    "fast": {"model": "grok-api", "reasoning_effort": "low"},
    "main": {"model": "grok-api", "reasoning_effort": "high"},
    "planner": {"model": "grok-api", "reasoning_effort": "high"},
    "critical_reviewer": {"model": "grok-api", "reasoning_effort": "xhigh"},
}
RUNTIME_MODEL_PROFILES = {
    "codex": CODEX_MODEL_PROFILES,
    "grok": GROK_MODEL_PROFILES,
}


def model_profiles_for(runtime: str) -> dict[str, dict[str, str]] | None:
    """Return the sealed profile map for a runtime, if one exists."""
    profiles = RUNTIME_MODEL_PROFILES.get((runtime or "").strip().casefold())
    if profiles is None:
        return None
    return {name: dict(config) for name, config in profiles.items()}


CONTINUATION_PROTOCOL = "handoff-v1"
CONTINUATION_STATUSES = {"unclaimed", "active", "ready"}
TERMINAL_RUN_STATUSES = {"accepted", "handed_off", "failed"}

RUN_STATUSES = {
    "intake",
    "gated",
    "specified",
    "dispatched",
    "reported",
    "evaluating",
    "accepted",
    "handed_off",
    "blocked",
    "needs_decision",
    "failed",
    "unplanned",
}

RUN_TRANSITIONS = {
    "intake": {"gated", "blocked", "needs_decision", "failed"},
    "gated": {"specified", "blocked", "needs_decision", "failed"},
    "specified": {"dispatched", "blocked", "needs_decision", "failed"},
    "dispatched": {"reported", "blocked", "needs_decision", "failed"},
    "reported": {"evaluating", "blocked", "needs_decision", "failed"},
    "evaluating": {"accepted", "blocked", "needs_decision", "failed"},
    "accepted": {"handed_off"},
    "blocked": {"needs_decision", "specified", "failed"},
    "needs_decision": {"specified", "failed"},
    "failed": set(),
    "handed_off": set(),
    "unplanned": {"intake", "failed"},
}

TASK_STATUSES = {
    "planned",
    "ready",
    "running",
    "blocked",
    "verify_failed",
    "passed",
    "merged",
    "cancelled",
    "unplanned",
}

ACCEPTANCE_STATUSES = {"pending", "pass", "fail", "blocked", "scoped_out"}
MODES = {"direct", "lite", "full"}
VERIFICATION_GATE_MODES = {
    "strict_tdd",
    "test_first_evidence",
    "substitute",
    "not_applicable",
}

DISPATCH_STATUSES = {"dispatched", "running", "reported", "failed", "cancelled"}
DISPATCH_TRANSITIONS = {
    "dispatched": {"running", "reported", "failed", "cancelled"},
    "running": {"reported", "failed", "cancelled"},
    "reported": set(),
    "failed": set(),
    "cancelled": set(),
}

EVIDENCE_POLICY = "typed-v1"
QUALIFYING_EVIDENCE_TYPES = {"artifact_digest"}
VERIFICATION_TIERS = ("policy", "flow", "user_visible")
VERIFICATION_TIER_RANK = {tier: index for index, tier in enumerate(VERIFICATION_TIERS)}
STATE_WITNESS_REVIEW_STATUSES = {"not_required", "pending", "pass", "fail", "blocked"}

TASK_TRANSITIONS = {
    "planned": {"ready", "blocked", "cancelled"},
    "ready": {"running", "blocked", "cancelled"},
    "running": {"passed", "verify_failed", "blocked", "cancelled"},
    "verify_failed": {"ready", "running", "blocked", "cancelled"},
    "blocked": {"ready", "cancelled"},
    "passed": {"merged", "verify_failed"},
    "merged": set(),
    "cancelled": set(),
    "unplanned": {"planned", "cancelled"},
}

ACCEPTANCE_TRANSITIONS = {
    "pending": {"pass", "fail", "blocked", "scoped_out"},
    "fail": {"pending", "blocked"},
    "blocked": {"pending", "fail"},
    "pass": set(),
    "scoped_out": set(),
}
