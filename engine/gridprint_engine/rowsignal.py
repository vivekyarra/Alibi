"""Stage S7 — row signal from fractional modulation (SPEC 8.8).

Temporal means are taken in scene coordinates (warped by the S4 homographies); every sample keeps
its original sensor row index for timing (SPEC 8.5.4).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Modulation:
    m: np.ndarray  # float32 [K, h, w] fractional modulation (L - Lbar) / Lbar
    lbar: np.ndarray  # float32 [K, h, w] temporal mean linear luminance (frame coordinates)
    ok: np.ndarray  # bool [K, h, w] usable samples (valid, static, Lbar > 0)


def _window_mean(x: np.ndarray, okf: np.ndarray, window: int) -> np.ndarray:
    """Centered moving average over axis 0, counting only ok samples. float32 out."""
    k = x.shape[0]
    half = window // 2
    out = np.zeros(x.shape, np.float32)
    s = np.zeros(x.shape[1:], np.float64)
    n = np.zeros(x.shape[1:], np.float64)
    hi = 0
    lo = 0
    for i in range(k):  # sliding accumulator: memory O(h·w) instead of O(K·h·w)
        while hi < min(k, i + half + 1):
            s += x[hi] * okf[hi]
            n += okf[hi]
            hi += 1
        while lo < i - half:
            s -= x[lo] * okf[lo]
            n -= okf[lo]
            lo += 1
        np.divide(s, n, out=out[i], where=n > 0.5, casting="unsafe")
    return out


def fractional_modulation(lin: np.ndarray, valid: np.ndarray, static: np.ndarray | None,
                          homs: np.ndarray | None, window: int) -> Modulation:
    assert lin.dtype == np.float32
    k, h, w = lin.shape
    ok = valid.copy()
    if static is not None:
        ok &= static
    if homs is None:
        lbar = _window_mean(lin, ok.astype(np.float32), window)
    else:
        # temporal mean in scene (reference) coordinates, then mapped back to each frame
        lw = np.empty_like(lin)
        ow = np.empty(lin.shape, np.float32)
        for i in range(k):
            lw[i] = cv2.warpPerspective(lin[i], homs[i], (w, h), flags=cv2.INTER_LINEAR)
            ow[i] = cv2.warpPerspective(ok[i].astype(np.float32), homs[i], (w, h), flags=cv2.INTER_NEAREST)
        mean_ref = _window_mean(lw, ow, window)
        lbar = np.empty_like(lin)
        for i in range(k):
            lbar[i] = cv2.warpPerspective(mean_ref[i], homs[i], (w, h),
                                          flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
    good = ok & (lbar > 1e-4)
    m = np.zeros_like(lin)
    np.divide(lin - lbar, lbar, out=m, where=good)
    assert m.dtype == np.float32
    return Modulation(m=m, lbar=lbar, ok=good)


def row_signal(mod: Modulation, sel: np.ndarray, axis: str, min_pixels: int,
               detrend_order: int) -> tuple[np.ndarray, np.ndarray]:
    """Weighted (by Lbar) mean of m per sensor row. Returns (rs float32 [K, R], mask bool [K, R]).

    axis = "rows": sensor rows are coded rows; axis = "cols": sensor rows are coded columns.
    """
    use = mod.ok & sel
    wgt = np.where(use, mod.lbar, 0).astype(np.float32)
    red = 2 if axis == "rows" else 1
    num = (mod.m * wgt).sum(axis=red, dtype=np.float64)
    den = wgt.sum(axis=red, dtype=np.float64)
    cnt = use.sum(axis=red)
    mask = (cnt >= min_pixels) & (den > 0)
    rs = np.where(mask, num / np.maximum(den, 1e-12), 0.0)
    rs = detrend_rows(rs, mask, detrend_order)
    return rs.astype(np.float32), mask


def detrend_rows(rs: np.ndarray, mask: np.ndarray, order: int) -> np.ndarray:
    """Remove a low-order polynomial across rows per frame (SPEC 8.8.4). float64."""
    k, r = rs.shape
    x = np.linspace(-1, 1, r)
    V = np.vander(x, order + 1)
    out = rs.astype(np.float64).copy()
    for i in range(k):
        mk = mask[i]
        if mk.sum() <= order + 3:
            out[i] = 0.0
            mask[i] = False
            continue
        coef, *_ = np.linalg.lstsq(V[mk], out[i, mk], rcond=None)
        out[i] = np.where(mk, out[i] - V @ coef, 0.0)
    return out


def compensate_window_mean(rs: np.ndarray, mask: np.ndarray, model: np.ndarray, window: int) -> np.ndarray:
    """Correct the row signal for flicker left in the temporal mean.

    With flicker gain g(k, r) = 1 + model(k, r), the measured m = g / ḡ_W − 1, where ḡ_W is the
    W-frame mean of g. ḡ_W ≠ 1 when the window phases do not cancel (gaps, dropped frames, short
    windows), which adds a fixed sinusoid across rows. Using the fitted model for ḡ_W gives
    m' = (1 + m) · ḡ_W − 1 ≈ g − 1. float64 (R6).
    """
    g = 1.0 + np.where(mask, model, 0.0)
    gbar = _window_mean(g.astype(np.float32)[:, :, None], mask.astype(np.float32)[:, :, None], window)[:, :, 0]
    gbar = np.where(mask & (gbar > 0), gbar, 1.0).astype(np.float64)
    out = np.where(mask, (1.0 + rs.astype(np.float64)) * gbar - 1.0, 0.0)
    return out.astype(np.float32)
