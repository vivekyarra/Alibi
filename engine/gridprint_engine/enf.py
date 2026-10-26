"""Stage S9 — clock-bias removal (SPEC 8.10) and reference-track helpers.

A camera clock error of ε ppm scales all measured frequencies by (1 + ε); for a track that varies
by only tens of mHz this is a near-constant offset. Matching uses variations only.
"""

from __future__ import annotations

import numpy as np


def remove_clock_bias(track_hz: np.ndarray) -> np.ndarray:
    x = np.asarray(track_hz, dtype=np.float64)
    return x - x.mean()


def reference_window_mean(ref_t: np.ndarray, ref_f: np.ndarray, centers_utc: np.ndarray,
                          window_s: float) -> np.ndarray:
    """Mean reference frequency over [c − W/2, c + W/2] for each center c (float64).

    A reference sample at UTC second s is the mean frequency over [s, s + 1). The integral of this
    step function is piecewise linear, so window means are exact. NaN where the window is not
    fully covered by consecutive reference seconds.
    """
    t = np.asarray(ref_t, dtype=np.int64)
    f = np.asarray(ref_f, dtype=np.float64)
    if len(t) == 0:
        return np.full(np.shape(centers_utc), np.nan)
    # split at gaps: positions where consecutive seconds are missing
    knots = np.concatenate([t, [t[-1] + 1]]).astype(np.float64)
    cum = np.concatenate([[0.0], np.cumsum(f)])
    contiguous = np.concatenate([[0], np.cumsum(np.diff(t) != 1)])  # segment id per sample
    c = np.asarray(centers_utc, dtype=np.float64)
    lo, hi = c - window_s / 2, c + window_s / 2
    inside = (lo >= knots[0]) & (hi <= knots[-1])
    out = np.full(c.shape, np.nan)
    if not inside.any():
        return out
    # integral via knot interpolation is valid only within one contiguous segment
    seg_lo = contiguous[np.clip(np.searchsorted(t, np.floor(lo[inside]), "right") - 1, 0, len(t) - 1)]
    seg_hi = contiguous[np.clip(np.searchsorted(t, np.ceil(hi[inside]) - 1, "right") - 1, 0, len(t) - 1)]
    same = seg_lo == seg_hi
    vals = (np.interp(hi[inside], knots, cum) - np.interp(lo[inside], knots, cum)) / window_s
    vals[~same] = np.nan
    out[inside] = vals
    return out
