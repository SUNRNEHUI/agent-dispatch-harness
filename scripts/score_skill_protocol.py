#!/usr/bin/env python3
"""Score whether agent-dispatch-harness skill docs encode Spec Synthesis protocol."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


CHECKS = [
    {
        "id": "spec_synthesis_ref",
        "weight": 12,
        "paths": ["references/spec-synthesis.md"],
        "patterns": [r"Spec Synthesis", r"假成功|fake[- ]success", r"pass_algorithm", r"Fuzzy|fuzzy|含糊|笼统"],
        "desc": "spec-synthesis reference exists with core concepts",
    },
    {
        "id": "skill_links_synthesis",
        "weight": 10,
        "paths": ["SKILL.md"],
        "patterns": [r"spec-synthesis|Spec Synthesis|Synthesize", r"fake-success|Fake-success|Not success"],
        "desc": "SKILL.md routes to Spec Synthesis",
    },
    {
        "id": "master_prompt_synthesis",
        "weight": 8,
        "paths": ["master-prompt.md"],
        "patterns": [r"Spec Synthesis|Synthesize|fake-success|Not success|TBD"],
        "desc": "master prompt requires synthesis for fuzzy goals",
    },
    {
        "id": "mode_proportionality",
        "weight": 12,
        "paths": ["SKILL.md"],
        "patterns": [r"Direct", r"Lite", r"Full", r"Proportionality|Density|lightest"],
        "desc": "mode selection prevents ceremony on tiny tasks",
    },
    {
        "id": "token_discipline",
        "weight": 10,
        "paths": ["SKILL.md"],
        "patterns": [r"Token|token", r"Progressive|Load only|ceremony|Density"],
        "desc": "token discipline / progressive load present",
    },
    {
        "id": "proportionality_ref",
        "weight": 8,
        "paths": ["references/proportionality.md"],
        "patterns": [r"Density|Direct", r"Full", r"Compact synthesis"],
        "desc": "proportionality guide exists",
    },
    {
        "id": "universal_adapter",
        "weight": 6,
        "paths": ["adapters/universal.md"],
        "patterns": [r"Codex|Claude|Grok|agnostic|Universal"],
        "desc": "universal runtime adapter exists",
    },
    {
        "id": "fake_success_protocol",
        "weight": 8,
        "paths": ["SKILL.md", "references/spec-synthesis.md", "templates/task_spec.md"],
        "patterns": [r"假成功|fake[- ]success|Anti-Success|Not success|fake success"],
        "desc": "fake-success checklist is first-class",
    },
    {
        "id": "pass_algorithm_template",
        "weight": 8,
        "paths": ["templates/acceptance_registry.json"],
        "patterns": [r"pass_algorithm"],
        "desc": "acceptance template includes pass_algorithm",
    },
    {
        "id": "task_contract_slots",
        "weight": 6,
        "paths": ["templates/subagent_task.md"],
        "patterns": [r"PASS", r"Stop", r"Allowed|允许", r"Gate mode|Testing Gate"],
        "desc": "task template has Goal/Scope/Gate/PASS/Stop shape",
    },
    {
        "id": "measurement_phase",
        "weight": 6,
        "paths": ["references/spec-synthesis.md", "SKILL.md", "templates/task_spec.md"],
        "patterns": [r"Phase 0|measurement|baseline|改善|improvement"],
        "desc": "improvement tasks require measurement guidance",
    },
    {
        "id": "doc_priority",
        "weight": 4,
        "paths": ["references/spec-synthesis.md", "SKILL.md"],
        "patterns": [r"Document priority|task_spec.*>|acceptance_registry"],
        "desc": "document priority rule present",
    },
    {
        "id": "eval_fuzzy_cases",
        "weight": 6,
        "paths": ["references/eval_cases.md"],
        "patterns": [r"Fuzzy Goal|模糊目标|Spec Synthesis|Fake Success|Measurement Phase"],
        "desc": "eval cases cover synthesis path",
    },
    {
        "id": "scoring_scripts",
        "weight": 4,
        "paths": ["scripts/score_harness.py", "scripts/score_skill_protocol.py"],
        "patterns": [r"."],
        "desc": "scoring scripts present",
    },
]


def read(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Score skill protocol coverage for Spec Synthesis.")
    parser.add_argument("--skill-root", required=True)
    parser.add_argument("--out", default="")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    root = Path(args.skill_root).resolve()
    results = []
    earned = 0
    total_w = 0
    for check in CHECKS:
        total_w += check["weight"]
        blob = "\n".join(read(root / rel) for rel in check["paths"])
        missing_files = [rel for rel in check["paths"] if not (root / rel).exists()]
        hits = []
        for pat in check["patterns"]:
            if pat == r".":
                if blob.strip() and not missing_files:
                    hits.append(pat)
                continue
            if re.search(pat, blob, flags=re.I | re.M):
                hits.append(pat)
        # pass if all patterns hit and no missing required files for multi-file existence checks
        need = len(check["patterns"])
        ratio = len(hits) / need if need else 0.0
        if missing_files and check["id"] in {"spec_synthesis_ref", "scoring_scripts"}:
            ratio = 0.0
        score = round(check["weight"] * ratio, 2)
        earned += score
        results.append(
            {
                "id": check["id"],
                "desc": check["desc"],
                "weight": check["weight"],
                "score": score,
                "ratio": ratio,
                "missing_files": missing_files,
                "hits": len(hits),
                "need": need,
                "pass": ratio >= 0.75,
            }
        )

    total = round(100.0 * earned / total_w, 2) if total_w else 0.0
    grade = "F"
    if total >= 85:
        grade = "A"
    elif total >= 75:
        grade = "B"
    elif total >= 60:
        grade = "C"
    elif total >= 45:
        grade = "D"

    out_obj = {
        "skill_root": str(root),
        "total": total,
        "grade": grade,
        "earned": earned,
        "max": total_w,
        "checks": results,
        "mode_proportionality": "pass" if any(c["id"] == "mode_proportionality" and c["pass"] for c in results) else "fail",
    }

    text = json.dumps(out_obj, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")

    if args.pretty or not args.out:
        print(f"skill_protocol total={total} grade={grade}")
        for c in results:
            mark = "PASS" if c["pass"] else "FAIL"
            print(f"  [{mark}] {c['id']}: {c['score']}/{c['weight']} — {c['desc']}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
