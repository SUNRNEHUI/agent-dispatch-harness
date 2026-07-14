#!/usr/bin/env python3
"""Shared schema constants and transition rules for harness runtime files."""

from __future__ import annotations


SCHEMA_VERSION = 1
MODEL_ROUTING_POLICY = "cost-aware-v1"
AGENT_PROFILES = {"fast", "main", "planner", "critical_reviewer"}
CODEX_MODEL_PROFILES = {
    "fast": {"model": "gpt-5.6-luna", "reasoning_effort": "medium"},
    "main": {"model": "gpt-5.6-luna", "reasoning_effort": "xhigh"},
    "planner": {"model": "gpt-5.6-sol", "reasoning_effort": "high"},
    "critical_reviewer": {"model": "gpt-5.6-sol", "reasoning_effort": "xhigh"},
}

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
