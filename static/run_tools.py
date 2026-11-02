"""Canal A: runs the aging rules on a source tree and writes static_findings.json.

Usage: python static/run_tools.py <target-dir> <out.json>
Languages are chosen from file extensions present in the target. Matches are CANDIDATES for the
triage agent (.claude/agents/aging-finding-triage.md), never confirmed aging.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aging_rules  # noqa: E402

EXTS = {"python": {".py"}, "javascript": {".js", ".mjs", ".cjs", ".ts"}}
SKIP = {"node_modules", ".git", "__pycache__", "results", ".cache"}


def languages(target: Path) -> list[str]:
    found = set()
    for p in target.rglob("*"):
        if SKIP & set(p.parts):
            continue
        for lang, exts in EXTS.items():
            if p.suffix in exts:
                found.add(lang)
    return sorted(found)


def main() -> None:
    target, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    findings = []
    for lang in languages(target):
        kept, dropped, _ = aging_rules.scan(target, lang)
        for k in kept:
            findings.append(k | {"language": lang, "category": "aging"})
    out.write_text(json.dumps({"rules_version": aging_rules.rules_version(),
                               "target": str(target), "findings": findings}, indent=2))
    print(f"{len(findings)} candidate findings -> {out}")


if __name__ == "__main__":
    main()
