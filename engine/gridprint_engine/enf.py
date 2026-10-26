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
    c = np.asarray(centers_utc, dtype=np.float64)
    out = np.full(c.shape, np.nan)
    if len(t) == 0:
        return out
    t0 = int(t.min())
    n = int(t.max()) - t0 + 1
    dense = np.zeros(n, np.float64)
    missing = np.ones(n, np.int64)
    dense[t - t0] = f
    missing[t - t0] = 0
    knots = t0 + np.arange(n + 1, dtype=np.float64)
    cum = np.concatenate([[0.0], np.cumsum(dense)])  # piecewise-linear integral of the step function
    miss = np.concatenate([[0], np.cumsum(missing)])
    lo, hi = c - window_s / 2, c + window_s / 2
    inside = (lo >= knots[0]) & (hi <= knots[-1])
    if not inside.any():
        return out
    li, hj = lo[inside], hi[inside]
    a = np.floor(li - t0).astype(np.int64)
    b = np.ceil(hj - t0).astype(np.int64)
    gap = (miss[b] - miss[a]) > 0  # any missing second inside the window
    vals = (np.interp(hj, knots, cum) - np.interp(li, knots, cum)) / window_s
    vals[gap] = np.nan
    out[inside] = vals
    return out
