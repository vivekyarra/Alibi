"""R5: fail if forbidden claims appear in user-facing text."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = [
    "cryptographic",
    "impossible to fake",
    "detects all deepfakes",
    "100% accurate",
    "proves the video is fake",
    "guaranteed",
]
# SPEC 1.8 requires the plain statement that GRIDPRINT is "Not cryptographic proof".
ALLOWED_PHRASES = ["not cryptographic proof", "not a cryptographic proof", "is not cryptographic"]
TEXT_SUFFIXES = {".md", ".html", ".tsx", ".ts", ".css", ".json", ".txt", ".j2", ".jinja"}


def targets(root: Path) -> list[Path]:
    files: list[Path] = []
    for d in ["web/src", "web/public", "docs", "engine/gridprint_engine/templates"]:
        p = root / d
        if p.exists():
            files += [f for f in p.rglob("*") if f.is_file() and f.suffix in TEXT_SUFFIXES]
    for f in ["README.md", "web/index.html"]:
        if (root / f).exists():
            files.append(root / f)
    return [f for f in files if f.name != "SPEC.md" and "node_modules" not in f.parts]


def scan_text(text: str) -> list[tuple[int, str]]:
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        for a in ALLOWED_PHRASES:
            low = low.replace(a, "")
        for phrase in FORBIDDEN:
            if re.search(re.escape(phrase), low):
                hits.append((i, phrase))
    return hits


def main(root: Path = ROOT) -> int:
    bad = 0
    files = targets(root)
    for f in files:
        for line, phrase in scan_text(f.read_text(encoding="utf-8", errors="ignore")):
            print(f"{f.relative_to(root)}:{line}: forbidden claim '{phrase}'")
            bad += 1
    print(f"claims_lint: {len(files)} files scanned, {bad} violations")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
