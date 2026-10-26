"""Record the submission video duration (H8) in results/video/duration.json using ffprobe."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_video_duration.py <video file>")
        return 2
    f = Path(sys.argv[1])
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(f)],
                         capture_output=True, text=True, check=True).stdout
    dur = float(json.loads(out)["format"]["duration"])
    rec = {"file": f.name, "sha256": hashlib.sha256(f.read_bytes()).hexdigest(), "duration_s": dur,
           "limit_s": 300, "ok": dur <= 300, "checked": datetime.now(tz=UTC).isoformat()}
    dst = ROOT / "results" / "video" / "duration.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec))
    return 0 if rec["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
