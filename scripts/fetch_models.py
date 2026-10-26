"""Download DNN models used by S5 (segmentation) and S12 (face detection) from opencv_zoo.

Records SHA-256 and the upstream LICENSE text next to each model (docs/LICENSES.md lists them).
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
ZOO = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"
ZOO_RAW = "https://raw.githubusercontent.com/opencv/opencv_zoo/main/models"
ITEMS = [
    ("face_detection_yunet", "face_detection_yunet_2023mar.onnx"),
    ("human_segmentation_pphumanseg", "human_segmentation_pphumanseg_2023mar.onnx"),
]


def fetch(url: str, dst: Path) -> None:
    with urllib.request.urlopen(url, timeout=600) as r:
        dst.write_bytes(r.read())


def main() -> int:
    MODELS.mkdir(exist_ok=True)
    failed = 0
    for folder, name in ITEMS:
        dst = MODELS / name
        try:
            if not dst.exists() or dst.stat().st_size < 10_000:
                fetch(f"{ZOO}/{folder}/{name}", dst)
            lic = MODELS / f"{folder}.LICENSE"
            if not lic.exists():
                fetch(f"{ZOO_RAW}/{folder}/LICENSE", lic)
            digest = hashlib.sha256(dst.read_bytes()).hexdigest()
            (MODELS / f"{name}.sha256").write_text(digest + "\n")
            print(f"{name}: {dst.stat().st_size} bytes sha256={digest}")
        except Exception as e:  # network failures leave the stage in 'model_unavailable' mode
            print(f"{name}: download failed: {e}", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
