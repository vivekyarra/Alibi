"""Stage S5 — foreground masking with an OpenCV `dnn` person segmentation model (SPEC 8.6).

Model: PP-HumanSeg (opencv_zoo `human_segmentation_pphumanseg_2023mar.onnx`, Apache-2.0;
DECISIONS D-009). Pre-processing follows the opencv_zoo reference demo: RGB, resize to 192×192,
scale to [0, 1], subtract 0.5, divide by 0.5; output channel 1 is "person".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from gridprint_engine.config import REPO


@dataclass
class SegmentationResult:
    foreground: np.ndarray | None  # bool [K, h, w] or None
    status: str  # "ok" | "model_unavailable"
    foreground_fraction: float


def segment_people(gray8: np.ndarray, model_path: str, input_size: tuple[int, int],
                   every_n: int) -> SegmentationResult:
    p = Path(model_path)
    if not p.is_absolute():
        p = REPO / p
    if not p.exists():
        return SegmentationResult(None, "model_unavailable", 0.0)
    net = cv2.dnn.readNet(str(p))
    k, h, w = gray8.shape
    fg = np.zeros((k, h, w), bool)
    last = np.zeros((h, w), bool)
    for i in range(k):
        if i % every_n == 0:
            rgb = cv2.cvtColor(gray8[i], cv2.COLOR_GRAY2RGB)
            img = cv2.resize(rgb, input_size).astype(np.float32) / 255.0
            img = (img - 0.5) / 0.5
            net.setInput(cv2.dnn.blobFromImage(img))
            out = net.forward()  # [1, 2, H, W]
            mask = (np.argmax(out[0], axis=0) == 1).astype(np.uint8)
            mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
            last = cv2.dilate(mask, np.ones((5, 5), np.uint8)) > 0
        fg[i] = last
    return SegmentationResult(fg, "ok", float(fg.mean()))
