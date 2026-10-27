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
                   strict_residual_limit_px: float = 0.5, camera_static_px: float = 0.05,
                   downscale_width: int = 160) -> MotionResult:
    full = band_suppressed(lin)
    k, H, W = full.shape
    f = max(1, int(np.ceil(W / downscale_width)))
    gray8 = full if f == 1 else np.stack([cv2.resize(g, (W // f, H // f), interpolation=cv2.INTER_AREA)
                                          for g in full])
    k, h, w = gray8.shape
    scale = np.diag([float(f), float(f), 1.0])  # analysis-grid coords = scale @ motion-grid coords
    limit = strict_residual_limit_px if strictness == "strict" else residual_limit_px
    step = [np.eye(3)]
    for i in range(1, k):
        step.append(_pair_homography(gray8[i - 1], gray8[i], max_features))  # (i-1) → i
    # Register every frame directly to the reference (middle) frame: features found once in the reference and
    # tracked with pyramidal LK. Chaining per-frame homographies accumulates error into fake drift over
    # hundreds of frames, so chaining is used only for a frame whose direct registration fails.
    ref = k // 2
    homs_l: list[np.ndarray | None] = [None] * k
    ref_pts = cv2.goodFeaturesToTrack(gray8[ref], maxCorners=max_features, qualityLevel=0.01, minDistance=5)
    for i in range(k):
        if i == ref:
            homs_l[i] = np.eye(3)
            continue
        if ref_pts is None or len(ref_pts) < 8:
            break
        nxt, st, _ = cv2.calcOpticalFlowPyrLK(gray8[ref], gray8[i], ref_pts, None, winSize=(21, 21), maxLevel=3)
        good = st.ravel() == 1
        if good.sum() >= 8:
            Hm, inl = cv2.findHomography(nxt[good], ref_pts[good], cv2.USAC_MAGSAC, 1.0)  # frame i → reference
            if Hm is not None and inl is not None and inl.sum() >= 8:
                homs_l[i] = Hm
    for i in list(range(ref + 1, k)) + list(range(ref - 1, -1, -1)):  # fallback: chain from a neighbour
        if homs_l[i] is None:
            if i > ref:
                homs_l[i] = homs_l[i - 1] @ np.linalg.inv(step[i])  # type: ignore[operator]
            else:
                homs_l[i] = homs_l[i + 1] @ step[i + 1]  # type: ignore[operator]
    homs = np.stack(homs_l).astype(np.float64)  # type: ignore[arg-type]
    homs /= homs[:, 2:3, 2:3]

    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_ULTRAFAST)  # type: ignore[attr-defined]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    grid = np.stack([xx, yy, np.ones_like(xx)], -1).reshape(-1, 3)
    static = np.ones((k, h, w), bool)
    resid_med = []
    cam_med = []
    for i in range(1, k):
        flow = dis.calc(gray8[i - 1], gray8[i], None)
        Hs = step[i]
        p = grid @ Hs.T
        p = p[:, :2] / p[:, 2:3]
        hflow = (p - grid[:, :2]).reshape(h, w, 2)
        r = np.linalg.norm(flow - hflow, axis=2)
        dyn = (r > limit).astype(np.uint8)
        dyn = cv2.dilate(dyn, np.ones((3, 3), np.uint8))
        static[i] &= dyn == 0
        static[i - 1] &= dyn == 0
        resid_med.append(float(np.median(r)))
        cam_med.append(float(np.median(np.linalg.norm(hflow, axis=2))))
    level = float(np.median(resid_med)) * f if resid_med else 0.0
    cam = float(np.median(cam_med)) * f if cam_med else 0.0
    if f > 1:  # back to the analysis grid
        static = np.stack([cv2.resize(s_.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST) > 0
                           for s_ in static])
        homs = np.stack([scale @ Hm @ np.linalg.inv(scale) for Hm in homs])
        h, w = H, W
    corners = np.array([[0, 0, 1], [w - 1, 0, 1], [0, h - 1, 1], [w - 1, h - 1, 1]], np.float64)
    disp = []
    for Hm in homs:
        q = corners @ Hm.T
        q = q[:, :2] / q[:, 2:3]
        disp.append(float(np.abs(q - corners[:, :2]).max()))
    max_disp = float(np.percentile(disp, 90)) if disp else 0.0
    moving = max_disp > max(1.0, 20 * camera_static_px)  # 90th-percentile corner displacement (analysis px)
    subset = None
    if strictness == "strict" and resid_med:
        rm = np.array([resid_med[0]] + resid_med)
        subset = np.flatnonzero(rm <= np.percentile(rm, 50))
    return MotionResult(
        homs=homs if moving else None,
        static=static,
        motion_level_px=level,
        camera_motion_px=cam,
        static_fraction=float(static.mean()),
        high_motion=level > high_motion_px,
        strictness=strictness,
        frame_subset=subset,
    )
