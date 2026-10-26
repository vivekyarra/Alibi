"""R12 / SPEC 14.3: every measured number in user-facing docs needs a source tag.

A line "needs a tag" when it contains a measured-looking number: a decimal, a percentage,
a multiplier (1.5x), or a value with a measurement unit. Allowed without tag: versions,
dates, nominal grid frequencies (50/60/100/120 Hz), and values on lines tagged
`<!-- cfg: config/... -->` (configuration values documented in DECISIONS.md).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ["README.md", "docs/TECHNICAL_REPORT.md", "docs/VIDEO_SCRIPT.md", "docs/JUDGE_GUIDE.md"]
WEB_DIR = "web/src"
SRC_TAG = re.compile(r"<!--\s*src:\s*results/[^\s#]+#[^\s]+\s*-->|data-src=\"results/[^\"]+\"")
CFG_TAG = re.compile(r"<!--\s*cfg:\s*config/[^\s]+\s*-->")
ALLOWED = [
    re.compile(r"\b(?:50|60|100|120)\s?Hz\b"),
    re.compile(r"\bv?\d+\.\d+\.\d+(?:\.\d+)?\b"),           # versions
    re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ][\d:.Z+-]+)?\b"),  # dates
    re.compile(r"\b(?:OpenCV|Python|WCAG|ES|Graviton|python|opencv)\s?\d+(?:\.\d+)*\b"),
    re.compile(r"\b(?:c8g|c7g|c7i|m7g|m7i|c8i)\.\w+\b"),
    re.compile(r"\b[MHVRDSB]\d+(?:\.\d+)*\b"),              # milestone/rule/stage ids
    re.compile(r"\b(?:Part|Section|§)\s?\d+(?:\.\d+)*\b"),
    re.compile(r"\b\d:\d{2}(?:[–-]\d:\d{2})?\b"),             # video timecodes
    re.compile(r"`[^`]*`"),                                   # code spans
    re.compile(r"\]\([^)]*\)"),                               # link targets
    re.compile(r"https?://\S+"),
]
MEASURED = re.compile(
    r"\d+\.\d+|\d+\s?%|\d+(?:\.\d+)?\s?[x×]\b|\b\d+(?:\.\d+)?\s?(?:ms|s|mHz|Hz|fps|MB|GB|USD|\$)\b|\$\s?\d"
)


def check_line(line: str) -> bool:
    if SRC_TAG.search(line) or CFG_TAG.search(line):
        return True
    stripped = line
    for pat in ALLOWED:
        stripped = pat.sub(" ", stripped)
    return not MEASURED.search(stripped)


def check_text(text: str) -> list[int]:
    bad, in_code = [], False
    for i, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if not check_line(line):
            bad.append(i)
    return bad


def main(root: Path = ROOT) -> int:
    paths = [root / f for f in FILES if (root / f).exists()]
    web = root / WEB_DIR
    if web.exists():
        paths += [p for p in web.rglob("*.tsx")]
    n = 0
    for p in paths:
        for line in check_text(p.read_text(encoding="utf-8", errors="ignore")):
            print(f"{p.relative_to(root)}:{line}: measured number without source tag")
            n += 1
    print(f"check_numbers_sourced: {len(paths)} files scanned, {n} untagged numbers")
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
