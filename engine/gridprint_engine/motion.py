"""Stage S4 — motion and static background (SPEC 8.5).

Homographies map each frame to the reference (middle) frame. They are used only to know which
scene surface a pixel shows; timing always uses the original sensor row (SPEC 8.5.4).
Distances are in analysis-grid pixels.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class MotionResult:
    homs: np.ndarray | None  # float64 [K, 3, 3] frame → reference; None when the camera is static
    static: np.ndarray  # bool [K, h, w]
    motion_level_px: float  # median residual flow (px/frame)
    camera_motion_px: float  # median homography displacement (px/frame)
    static_fraction: float
    high_motion: bool
    strictness: str
    frame_subset: np.ndarray | None = None  # low-motion frames when restricted


def _pair_homography(a: np.ndarray, b: np.ndarray, max_features: int) -> np.ndarray:
    """Homography mapping frame a coordinates → frame b coordinates (LK tracks + USAC_MAGSAC)."""
    pts = cv2.goodFeaturesToTrack(a, maxCorners=max_features, qualityLevel=0.01, minDistance=5)
    if pts is None or len(pts) < 8:
        return np.eye(3)
    nxt, st, _ = cv2.calcOpticalFlowPyrLK(a, b, pts, None, winSize=(15, 15), maxLevel=2)
    good = st.ravel() == 1
    if good.sum() < 8:
        return np.eye(3)
    H, _ = cv2.findHomography(pts[good], nxt[good], cv2.USAC_MAGSAC, 1.0)
    return H if H is not None else np.eye(3)


def band_suppressed(lin: np.ndarray) -> np.ndarray:
    """uint8 frames for tracking with rolling-shutter bands removed.

    Flicker bands are a multiplicative gain per sensor row; dividing each row (and each column, for
    the transposed case) by its mean in linear light removes them, so moving bands are not read as
    motion. Scene texture remains.
    """
    x = lin.astype(np.float32) + 1e-4
    x = x / x.mean(axis=2, keepdims=True)
    x = x / x.mean(axis=1, keepdims=True)
    return np.clip(np.sqrt(x) * 128.0, 0, 255).astype(np.uint8)


def analyze_motion(lin: np.ndarray, residual_limit_px: float, high_motion_px: float,
                   max_features: int, strictness: str = "normal",
                   strict_residual_limit_px: float = 0.5) -> MotionResult:
    gray8 = band_suppressed(lin)
    k, h, w = gray8.shape
    limit = strict_residual_limit_px if strictness == "strict" else residual_limit_px
    step = [np.eye(3)]
    for i in range(1, k):
        step.append(_pair_homography(gray8[i - 1], gray8[i], max_features))  # (i-1) → i
    # accumulate frame → frame-0, then re-reference to the middle frame
    to0 = [np.eye(3)]
    for i in range(1, k):
        to0.append(to0[-1] @ np.linalg.inv(step[i]))
    ref = k // 2
    inv_ref = np.linalg.inv(to0[ref])
    homs = np.stack([inv_ref @ H for H in to0]).astype(np.float64)
    homs /= homs[:, 2:3, 2:3]

    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_FAST)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    grid = np.stack([xx, yy, np.ones_like(xx)], -1).reshape(-1, 3)
    static = np.ones((k, h, w), bool)
    resid_med = []
    cam_med = []
    for i in range(1, k):
        flow = dis.calc(gray8[i - 1], gray8[i], None)
        H = step[i]
        p = grid @ H.T
        p = p[:, :2] / p[:, 2:3]
        hflow = (p - grid[:, :2]).reshape(h, w, 2)
        r = np.linalg.norm(flow - hflow, axis=2)
        dyn = (r > limit).astype(np.uint8)
        dyn = cv2.dilate(dyn, np.ones((3, 3), np.uint8))
        static[i] &= dyn == 0
        static[i - 1] &= dyn == 0
        resid_med.append(float(np.median(r)))
        cam_med.append(float(np.median(np.linalg.norm(hflow, axis=2))))
    level = float(np.median(resid_med)) if resid_med else 0.0
    cam = float(np.median(cam_med)) if cam_med else 0.0
    max_disp = 0.0
    corners = np.array([[0, 0, 1], [w - 1, 0, 1], [0, h - 1, 1], [w - 1, h - 1, 1]], np.float64)
    for H in homs:
        q = corners @ H.T
        q = q[:, :2] / q[:, 2:3]
        max_disp = max(max_disp, float(np.abs(q - corners[:, :2]).max()))
    subset = None
    if strictness == "strict" and resid_med:
        rm = np.array([resid_med[0]] + resid_med)
        subset = np.flatnonzero(rm <= np.percentile(rm, 50))
    return MotionResult(
        homs=homs if max_disp > 0.5 else None,
        static=static,
        motion_level_px=level,
        camera_motion_px=cam,
        static_fraction=float(static.mean()),
        high_motion=level > high_motion_px,
        strictness=strictness,
        frame_subset=subset,
    )
