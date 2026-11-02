"""Synthetic positive/negative cases for the aging rules (needs semgrep on PATH or $SEMGREP).

Each case: (language, source, expected rule ids). Run: python -I static/test_aging_rules.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aging_rules  # noqa: E402

CASES = [
    ("javascript", "const db = require('x');\nfunction h(){ const c = new sqlite3.Database(':memory:'); }\n",
     {"aging-js-db-connection-per-call"}),
    ("javascript", "const m = new Map();\nfunction h(k){ m.set(k, 1); }\n", {"aging-js-global-collection-growth"}),
    ("javascript", "const m = new Map();\nfunction h(k){ m.set(k, 1); }\nfunction g(k){ m.delete(k); }\n", set()),
    ("python", "def f():\n    h = open('x')\n    return h.read()\n", {"aging-py-open-without-close"}),
    ("python", "def f():\n    h = open('x')\n    h.read()\n    h.close()\n", set()),
]


def main() -> int:
    bad = 0
    for lang, src, want in CASES:
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / ("t.js" if lang == "javascript" else "t.py")
            f.write_text(src)
            kept, _, _ = aging_rules.scan(f, lang)
        got = {k["rule"] for k in kept}
        ok = got == want
        bad += not ok
        print(("PASS" if ok else "FAIL"), lang, sorted(want), "got", sorted(got))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
