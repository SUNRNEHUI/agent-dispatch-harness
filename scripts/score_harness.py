#!/usr/bin/env python3
"""Score a harness artifact directory for Spec Synthesis quality.

Deterministic, evidence-oriented scoring used to compare baseline vs upgraded
harness instances. Not a substitute for runtime task success.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


DIMENSION_WEIGHTS = {
    "goal_rewrite": 12,
    "fake_success": 14,
    "constraints_nongoals": 10,
    "pass_algorithm": 14,
    "risk_order": 12,
    "task_contracts": 14,
    "measurement_phase": 8,
    "evidence_layout": 6,
    "stop_resume": 6,
    "doc_priority": 4,
}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def clamp(score: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, score))


def normalize_match_text(text: str) -> str:
    """Lowercase and treat hyphen/underscore as spaces for matching."""
    t = text.lower()
    t = re.sub(r"[-_]+", " ", t)
    return t


def has_any(text: str, patterns: list[str]) -> bool:
    lower = normalize_match_text(text)
    for p in patterns:
        pn = normalize_match_text(p)
        if pn in lower:
            return True
        if re.search(p, text, flags=re.I | re.M):
            return True
    return False


def count_hits(text: str, patterns: list[str]) -> int:
    return sum(1 for p in patterns if has_any(text, [p]))


@dataclass
class DimResult:
    name: str
    score_0_10: float
    weight: int
    weighted: float
    notes: list[str]


def score_goal_rewrite(spec: str, notes: list[str]) -> float:
    s = 0.0
    if has_any(spec, [r"^##\s+Goal", "User-Facing Outcome", "用户可感知", "成功结果"]):
        s += 3
    else:
        notes.append("missing Goal / User-Facing Outcome")
    if has_any(spec, ["不是", "不是“", "rather than", "not merely", "不算", "不能把"]):
        s += 2
        notes.append("negation/contrast present in success definition")
    if has_any(spec, ["presented", "上屏", "user-facing", "用户", "可感知", "actual "]):
        s += 2
    if len(spec.strip()) >= 400:
        s += 2
    if has_any(spec, ["Target Call Chain", "目标调用链", "应然", "call chain"]):
        s += 1
    return clamp(s)


def score_fake_success(spec: str, tasks_blob: str, notes: list[str]) -> float:
    text = spec + "\n" + tasks_blob
    markers = [
        "假成功",
        "fake success",
        "fake-success",
        "fake_success",
        "anti-success",
        "anti success",
        "不算成功",
        "不能算",
        "不得.*成功",
        "proxy",
        "embedded preview",
        "state commit",
        "GPU complet",
        "self-assessment",
        "自评",
        "看起来像",
        "microbenchmark",
        "平均值",
    ]
    hits = count_hits(text, markers)
    if hits == 0:
        notes.append("no fake-success / anti-terminal language")
        return 0.0
    if hits <= 2:
        notes.append(f"weak fake-success coverage ({hits} hits)")
        return 4.0
    if hits <= 4:
        notes.append(f"moderate fake-success coverage ({hits} hits)")
        return 7.0
    notes.append(f"strong fake-success coverage ({hits} hits)")
    return 10.0


def score_constraints(spec: str, notes: list[str]) -> float:
    s = 0.0
    if has_any(spec, [r"##\s+Non-Goals", "非目标"]):
        s += 3
    else:
        notes.append("missing Non-Goals")
    if has_any(spec, [r"##\s+Constraints", "硬约束", "不可改变", "Constraints"]):
        s += 3
    else:
        notes.append("missing Constraints")
    if has_any(spec, [r"##\s+Stop", "停止条件", "Stop Conditions"]):
        s += 2
    if has_any(spec, ["不得", "禁止", "must not", "do not", "不允许"]):
        s += 2
    return clamp(s)


def is_quality_pass_algorithm(algo: str) -> bool:
    """Reject keyword-only / stuffed strings; require executable or TBD+measure shape."""
    a = algo.strip()
    if len(a) < 24:
        return False
    low = normalize_match_text(a)
    junk = [
        "keyword only",
        "stuffed",
        "without executable",
        "lorem ipsum",
        "no real algorithm",
        "placeholder algorithm",
        "todo pass",
    ]
    if any(j in low for j in junk):
        return False
    # Allow explicit measurement TBD plans
    if ("tbd" in low or "待" in a) and any(
        x in low for x in ["measure", "baseline", "phase 0", "测量", "基线"]
    ):
        return True
    quality = [
        "every",
        "must",
        "exactly",
        "==",
        ">=",
        "<=",
        "pass if",
        "fail if",
        "valid run",
        "compare",
        "baseline",
        "p50",
        "p95",
        "when ",
        "iff ",
        "全部",
        "必须",
        "等于",
        "不超过",
        "相对",
        "缺失率",
        "attempt",
        "presented",
        "ack",
    ]
    return any(q in low or q in a for q in quality)


def score_pass_algorithm(registry: Any, notes: list[str]) -> float:
    if not isinstance(registry, dict):
        notes.append("acceptance_registry.json missing/invalid")
        return 0.0
    criteria = registry.get("criteria") or []
    if not criteria:
        notes.append("no acceptance criteria")
        return 0.0
    with_algo = 0
    with_quality = 0
    with_evidence = 0
    with_desc = 0
    for c in criteria:
        if not isinstance(c, dict):
            continue
        desc = str(c.get("description") or "").strip()
        if desc:
            with_desc += 1
        algo = str(c.get("pass_algorithm") or c.get("passAlgorithm") or "").strip()
        if algo:
            with_algo += 1
            if is_quality_pass_algorithm(algo):
                with_quality += 1
        ev = c.get("required_evidence") or []
        if isinstance(ev, list) and len(ev) > 0:
            with_evidence += 1
        elif str(c.get("required_evidence") or "").strip():
            with_evidence += 1
    n = max(len(criteria), 1)
    ratio_desc = with_desc / n
    ratio_algo = with_algo / n
    ratio_quality = with_quality / n
    ratio_ev = with_evidence / n
    # Quality algorithms dominate; empty-or-junk algorithms barely help
    s = ratio_desc * 2 + ratio_algo * 1 + ratio_quality * 5 + ratio_ev * 2
    notes.append(
        f"criteria={n} pass_algorithm={with_algo} quality_algo={with_quality} required_evidence={with_evidence}"
    )
    if ratio_quality < 0.5:
        notes.append("quality pass_algorithm coverage < 50%")
    return clamp(s)


def score_risk_order(spec: str, run_state: Any, notes: list[str]) -> float:
    s = 0.0
    if has_any(spec, ["Phase 0", "阶段 0", "measurement", "基线", "baseline", "先.*量", "风险序"]):
        s += 3
        notes.append("measurement/baseline language present")
    phases = re.findall(r"Phase\s+(\d+)|阶段\s*(\d+)", spec, flags=re.I)
    if len(phases) >= 3:
        s += 3
        notes.append(f"multi-phase map detected ({len(phases)})")
    elif len(phases) >= 1:
        s += 1
    if isinstance(run_state, dict):
        stages = run_state.get("stages") or []
        if isinstance(stages, list) and len(stages) >= 2:
            s += 2
        tasks = run_state.get("tasks") or []
        deps = 0
        for t in tasks if isinstance(tasks, list) else []:
            if isinstance(t, dict) and t.get("dependencies"):
                deps += 1
        if deps:
            s += 2
            notes.append(f"tasks_with_dependencies={deps}")
    if has_any(spec, ["依赖", "Dependencies", "before", "不得跳", "先于"]):
        s += 1
    return clamp(s)


def score_task_contracts(task_files: list[Path], notes: list[str]) -> float:
    if not task_files:
        notes.append("no tasks/*.md contracts")
        return 1.0
    required = [
        (r"##\s+Goal|##\s+目标", "Goal"),
        (r"Allowed Scope|允许修改|allowed_scope|##\s+范围", "Scope"),
        (r"Testing Gate|Gate mode|验证|verification", "Gate"),
        (r"##\s+PASS|Phase PASS|成功标准", "PASS"),
        (r"##\s+Stop|停止", "Stop"),
    ]
    scores = []
    for path in task_files:
        text = read_text(path)
        hits = sum(1 for pat, _ in required if re.search(pat, text, flags=re.I))
        scores.append(hits / len(required) * 10)
    avg = sum(scores) / len(scores)
    notes.append(f"task_files={len(task_files)} avg_contract_fill={avg:.1f}/10")
    return clamp(avg)


def score_measurement(spec: str, registry: Any, notes: list[str]) -> float:
    improvement_shaped = has_any(
        spec,
        ["性能", "performance", "p50", "p95", "latency", "更快", "优化", "improve", "准确率", "cost", "基线"],
    )
    text = spec
    if isinstance(registry, dict):
        text += "\n" + json.dumps(registry, ensure_ascii=False)
    has_measure = has_any(
        text,
        [
            "Phase 0",
            "measurement",
            "基线",
            "baseline",
            "cold",
            "warm",
            "sample",
            "n=",
            "valid run",
            "DEVICE_MEASUREMENT",
            "测量协议",
        ],
    )
    if not improvement_shaped:
        notes.append("not improvement-shaped; measurement optional -> neutral 7")
        return 7.0 if has_measure or True else 7.0
    if has_measure:
        notes.append("improvement-shaped with measurement plan")
        return 10.0 if has_any(text, ["p50", "p95", "cold", "warm", "基线", "baseline"]) else 8.0
    notes.append("improvement-shaped but missing measurement/baseline plan")
    return 2.0


def score_evidence(spec: str, runbook: str, notes: list[str]) -> float:
    text = spec + "\n" + runbook
    s = 0.0
    if has_any(text, ["evidence/", "required_evidence", "证据", "console.log", "metrics.json"]):
        s += 4
    if has_any(text, ["原始", "raw log", "不得只", "禁止只输出一个平均", "recomputable", "可复算"]):
        s += 3
    if has_any(text, ["trace.jsonl", "tdd_trace", "report"]):
        s += 2
    if has_any(text, ["evaluator", "独立"]):
        s += 1
    if s == 0:
        notes.append("no evidence layout language")
    return clamp(s)


def score_stop_resume(spec: str, run_state: Any, notes: list[str]) -> float:
    s = 0.0
    if has_any(spec, ["Stop Conditions", "停止条件", "stop_reason"]):
        s += 4
    if isinstance(run_state, dict) and "status" in run_state:
        s += 2
    if has_any(spec, ["恢复", "resume", "run_state", "handoff", "交接"]):
        s += 2
    if has_any(spec, ["连续两次", "twice", "budget", "预算"]):
        s += 2
    return clamp(s)


def score_doc_priority(spec: str, readme: str, notes: list[str]) -> float:
    text = spec + "\n" + readme
    if has_any(text, ["文档优先级", "priority", "canonical", "优先于", "冲突时"]):
        notes.append("document priority / canonical order present")
        return 10.0
    if has_any(text, ["task_spec", "acceptance_registry", "run_state"]):
        return 4.0
    notes.append("no document priority rule")
    return 1.0


def assess_integrity(
    spec: str,
    registry: Any,
    tasks_blob: str,
    task_files: list[Path],
    notes: list[str],
) -> float:
    """Down-rank keyword stuffing and empty structural shells.

    Returns a multiplier in [0.15, 1.0] applied to the weighted total.
    Uses combined signals so legitimate long harnesses with repeated domain
    terms are not destroyed solely by keyword density.
    """
    blob = spec + "\n" + tasks_blob
    signals = 0.0

    # Explicit stuffing confession
    if has_any(blob, ["keyword stuffed", "keyword only", "stuffed pass_algorithm", "empty plan"]):
        signals += 3.0
        notes.append("explicit stuffing language detected")

    # Registry pass_algorithm quality
    quality = 0
    junk = 0
    n_crit = 0
    if isinstance(registry, dict):
        criteria = registry.get("criteria") or []
        for c in criteria:
            if not isinstance(c, dict):
                continue
            n_crit += 1
            algo = str(c.get("pass_algorithm") or "").strip()
            if not algo:
                junk += 1
            elif is_quality_pass_algorithm(algo):
                quality += 1
            else:
                junk += 1
    if n_crit:
        if quality == 0 and junk:
            signals += 3.0
            notes.append("all pass_algorithm entries fail quality check")
        elif junk > quality:
            signals += 1.5
            notes.append("majority pass_algorithm entries low quality")

    # Task contracts: require non-trivial PASS bodies
    thin_tasks = 0
    for p in task_files:
        t = read_text(p)
        m = re.search(r"(?is)##\s*PASS\b(.*?)(?:##\s|\Z)", t)
        body = (m.group(1) if m else "").strip()
        if len(body) < 30:
            thin_tasks += 1
    if task_files and thin_tasks == len(task_files):
        signals += 2.0
        notes.append("all task PASS sections thin/empty")
    elif task_files and thin_tasks >= max(1, len(task_files) // 2):
        signals += 1.0
        notes.append(f"thin_task_pass_sections={thin_tasks}/{len(task_files)}")

    # Empty or near-empty markdown sections under ## headers (very short only)
    empty_sections = 0
    sections = re.split(r"(?m)^##\s+", spec)
    for sec in sections[1:]:
        body = sec.split("\n", 1)[1] if "\n" in sec else ""
        # ignore HTML comments and pure placeholders
        body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
        body = re.sub(r"(?m)^\s*[-*]\s*$", "", body)
        body_stripped = re.sub(r"\s+", " ", body).strip()
        if 0 < len(body_stripped) < 25 or body_stripped == "":
            # count only truly empty-ish (not short but real sentences)
            if len(body_stripped) < 15:
                empty_sections += 1
    if empty_sections >= 4:
        signals += 1.5
        notes.append(f"empty_or_thin_sections={empty_sections}")

    # Keyword soup only stacks when quality is already weak
    words = re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]{2,}", blob)
    unique = len(set(w.lower() for w in words))
    n_words = max(len(words), 1)
    uniq_ratio = unique / n_words
    markers = [
        "fake success", "假成功", "proxy", "embedded preview", "gpu complet",
        "pass algorithm", "phase 0", "baseline", "p50", "p95", "microbenchmark",
        "evidence/", "run_state", "tdd_trace", "anti success",
    ]
    hits = count_hits(blob, markers)
    quality_ratio = (quality / n_crit) if n_crit else 0.0
    if hits >= 10 and uniq_ratio < 0.50 and quality_ratio < 0.5:
        signals += 2.5
        notes.append(f"keyword soup with weak algorithms: hits={hits} uniq={uniq_ratio:.2f}")
    elif hits >= 12 and uniq_ratio < 0.42 and quality_ratio < 0.75:
        signals += 1.0
        notes.append(f"dense markers mild: hits={hits} uniq={uniq_ratio:.2f}")

    # Map cumulative signals to multiplier
    if signals >= 5.0:
        factor = 0.20
    elif signals >= 3.5:
        factor = 0.35
    elif signals >= 2.0:
        factor = 0.55
    elif signals >= 1.0:
        factor = 0.80
    else:
        factor = 1.0

    factor = max(0.15, min(1.0, factor))
    if factor < 1.0:
        notes.append(f"integrity_signals={signals:.1f} factor={factor:.2f}")
    return factor


def score_directory(root: Path) -> dict[str, Any]:
    spec = read_text(root / "task_spec.md")
    readme = read_text(root / "README.md")
    runbook = read_text(root / "MODEL_RUNBOOK.md") + "\n" + read_text(root / "DEVICE_MEASUREMENT_PROTOCOL.md")
    progress = read_text(root / "progress.md")
    registry = load_json(root / "acceptance_registry.json")
    run_state = load_json(root / "run_state.json")
    task_dir = root / "tasks"
    task_files = sorted(task_dir.glob("*.md")) if task_dir.is_dir() else []
    tasks_blob = "\n".join(read_text(p) for p in task_files)
    # include progress in stop/resume signals
    spec_all = "\n".join([spec, progress, readme])

    total_weight = sum(DIMENSION_WEIGHTS.values())
    results: list[DimResult] = []
    n1: list[str] = []
    s1 = score_goal_rewrite(spec, n1)
    results.append(DimResult("goal_rewrite", s1, DIMENSION_WEIGHTS["goal_rewrite"], s1 * DIMENSION_WEIGHTS["goal_rewrite"] / 10, n1))

    n2: list[str] = []
    s2 = score_fake_success(spec_all, tasks_blob, n2)
    results.append(DimResult("fake_success", s2, DIMENSION_WEIGHTS["fake_success"], s2 * DIMENSION_WEIGHTS["fake_success"] / 10, n2))

    n3: list[str] = []
    s3 = score_constraints(spec, n3)
    results.append(DimResult("constraints_nongoals", s3, DIMENSION_WEIGHTS["constraints_nongoals"], s3 * DIMENSION_WEIGHTS["constraints_nongoals"] / 10, n3))

    n4: list[str] = []
    s4 = score_pass_algorithm(registry, n4)
    results.append(DimResult("pass_algorithm", s4, DIMENSION_WEIGHTS["pass_algorithm"], s4 * DIMENSION_WEIGHTS["pass_algorithm"] / 10, n4))

    n5: list[str] = []
    s5 = score_risk_order(spec, run_state, n5)
    results.append(DimResult("risk_order", s5, DIMENSION_WEIGHTS["risk_order"], s5 * DIMENSION_WEIGHTS["risk_order"] / 10, n5))

    n6: list[str] = []
    s6 = score_task_contracts(task_files, n6)
    results.append(DimResult("task_contracts", s6, DIMENSION_WEIGHTS["task_contracts"], s6 * DIMENSION_WEIGHTS["task_contracts"] / 10, n6))

    n7: list[str] = []
    s7 = score_measurement(spec, registry, n7)
    results.append(DimResult("measurement_phase", s7, DIMENSION_WEIGHTS["measurement_phase"], s7 * DIMENSION_WEIGHTS["measurement_phase"] / 10, n7))

    n8: list[str] = []
    s8 = score_evidence(spec_all, runbook, n8)
    results.append(DimResult("evidence_layout", s8, DIMENSION_WEIGHTS["evidence_layout"], s8 * DIMENSION_WEIGHTS["evidence_layout"] / 10, n8))

    n9: list[str] = []
    s9 = score_stop_resume(spec_all, run_state, n9)
    results.append(DimResult("stop_resume", s9, DIMENSION_WEIGHTS["stop_resume"], s9 * DIMENSION_WEIGHTS["stop_resume"] / 10, n9))

    n10: list[str] = []
    s10 = score_doc_priority(spec, readme, n10)
    results.append(DimResult("doc_priority", s10, DIMENSION_WEIGHTS["doc_priority"], s10 * DIMENSION_WEIGHTS["doc_priority"] / 10, n10))

    weighted_sum = sum(r.weighted for r in results)
    raw_total = 100.0 * weighted_sum / total_weight

    integrity_notes: list[str] = []
    integrity = assess_integrity(spec_all, registry, tasks_blob, task_files, integrity_notes)
    total = round(raw_total * integrity, 2)

    grade = "F"
    if total >= 85:
        grade = "A"
    elif total >= 75:
        grade = "B"
    elif total >= 60:
        grade = "C"
    elif total >= 45:
        grade = "D"

    return {
        "fixture": str(root),
        "total": total,
        "raw_total_before_integrity": round(raw_total, 2),
        "integrity_factor": integrity,
        "integrity_notes": integrity_notes,
        "grade": grade,
        "max": 100,
        "dimensions": [asdict(r) for r in results],
        "files_present": {
            "task_spec.md": (root / "task_spec.md").exists(),
            "acceptance_registry.json": (root / "acceptance_registry.json").exists(),
            "run_state.json": (root / "run_state.json").exists(),
            "progress.md": (root / "progress.md").exists(),
            "tasks": len(task_files),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score a harness artifact directory.")
    parser.add_argument("--fixture", required=True, help="Path to harness artifact directory")
    parser.add_argument("--label", default="", help="Optional label stored in output")
    parser.add_argument("--out", default="", help="Optional JSON output path")
    parser.add_argument("--pretty", action="store_true", help="Print human summary")
    args = parser.parse_args()

    root = Path(args.fixture).resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}")
        return 2

    result = score_directory(root)
    if args.label:
        result["label"] = args.label

    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")

    if args.pretty or not args.out:
        print(f"label={result.get('label', '')} total={result['total']} grade={result['grade']}")
        for d in result["dimensions"]:
            print(f"  - {d['name']}: {d['score_0_10']}/10 (w={d['weight']}) {'; '.join(d['notes'][:2])}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
