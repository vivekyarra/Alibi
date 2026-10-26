"""Stage S12 — face-region check, EXPERIMENTAL (SPEC 8.13).

Faces are detected with FaceDetectorYN (YuNet). No identity recognition; no embeddings or crops are
stored. In sensor rows covered by a face, the band amplitude of face pixels is compared with
background pixels of the same rows, both projected on the frame's measured flicker phase.
Never the sole basis for CONTRADICTED (R9) — verdict.py does not read this result for rule 2/3.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from gridprint_engine.config import REPO
from gridprint_engine.rowsignal import Modulation
from gridprint_engine.schemas import FaceStats


def detect_faces(gray8: np.ndarray, model_path: str, score_threshold: float,
                 every_n: int) -> dict[int, np.ndarray] | None:
    p = Path(model_path)
    if not p.is_absolute():
        p = REPO / p
    if not p.exists():
        return None
    k, h, w = gray8.shape
    det = cv2.FaceDetectorYN.create(str(p), "", (w, h), score_threshold)
    out: dict[int, np.ndarray] = {}
    for i in range(0, k, every_n):
        _, faces = det.detect(cv2.cvtColor(gray8[i], cv2.COLOR_GRAY2BGR))
        if faces is not None and len(faces):
            out[i] = faces[:, :4].astype(np.float32)  # x, y, w, h only
    return out


def face_region_check(mod: Modulation, static_sel: np.ndarray, faces: dict[int, np.ndarray] | None,
                      axis: str, t_rows: np.ndarray, phi: np.ndarray, frame_ok: np.ndarray, f0: float,
                      ratio_anomaly: float) -> FaceStats:
    if faces is None:
        return FaceStats(status="model_unavailable")
    if not faces:
        return FaceStats(status="no_faces")
    k, h, w = mod.m.shape
    amp_f, amp_b = [], []
    for i, boxes in faces.items():
        if not frame_ok[i]:
            continue
        fmask = np.zeros((h, w), bool)
        for x, y, bw, bh in boxes:
            fmask[max(int(y), 0):min(int(y + bh), h), max(int(x), 0):min(int(x + bw), w)] = True
        okp = mod.ok[i]
        if axis == "rows":
            rows = np.flatnonzero(fmask.any(axis=1))
            fsel = fmask[rows] & okp[rows]
            bsel = (~fmask[rows]) & okp[rows] & static_sel[i][rows]
            mm = mod.m[i][rows]
        else:
            rows = np.flatnonzero(fmask.any(axis=0))
            fsel = (fmask[:, rows] & okp[:, rows]).T
            bsel = ((~fmask[:, rows]) & okp[:, rows] & static_sel[i][:, rows]).T
            mm = mod.m[i][:, rows].T
        if len(rows) < 4:
            continue
        g = np.cos(2 * np.pi * f0 * t_rows[i, rows] + phi[i])
        fr = np.array([mm[j][fsel[j]].mean() if fsel[j].any() else np.nan for j in range(len(rows))])
        br = np.array([mm[j][bsel[j]].mean() if bsel[j].any() else np.nan for j in range(len(rows))])
        good = ~np.isnan(fr) & ~np.isnan(br)
        if good.sum() < 4:
            continue
        gg = g[good]
        den = float((gg * gg).sum())
        amp_f.append(float((fr[good] * gg).sum() / den))
        amp_b.append(float((br[good] * gg).sum() / den))
    if len(amp_f) < 3:
        return FaceStats(status="no_faces", frames_with_faces=len(amp_f))
    af, ab = np.array(amp_f), np.array(amp_b)
    ratio = float(af.mean() / ab.mean()) if ab.mean() != 0 else float("nan")
    d = ab - af
    sig = float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))) if d.std(ddof=1) > 0 else 0.0
    anomaly = bool(ratio < ratio_anomaly and sig > 3.0)
    return FaceStats(status="ok", ratio=ratio, significance=sig, frames_with_faces=len(af), anomaly=anomaly)
