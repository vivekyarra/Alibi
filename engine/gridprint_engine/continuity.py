"""Stage S11 — continuity (SPEC 8.12). Works with or without reference data.

The flicker phase φ_k is measured against absolute frame time, so it follows a smooth curve (slope 2π·δf).
A cut that was re-timed to look continuous shifts the phase after the cut by 2π·f·(removed time) mod 2π;
dropped frames with true timestamps do not. At every frame boundary the phase is fitted with a straight line
on each side (frames within `jump_window_s`), both lines are evaluated at the boundary, and the difference is
the phase jump. Its standard error comes from the two fits. Change points are local maxima of |jump|/σ
(DECISIONS D-014, D-023).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from gridprint_engine.schemas import ContinuityEvent, GapEvent, Reason


def _wrap(x: np.ndarray) -> np.ndarray:
    return (x + np.pi) % (2 * np.pi) - np.pi


@dataclass
class ContinuityResult:
    events: list[ContinuityEvent]
    residual_t: np.ndarray
    residual_rad: np.ndarray
    reasons: list[Reason]
    boundaries: list[dict[str, float]] = field(default_factory=list)  # raw candidates for calibration


def _side_fits(t: np.ndarray, y: np.ndarray, lo: np.ndarray, hi: np.ndarray, tb: np.ndarray
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Least-squares line through samples [lo, hi) of (t, y) evaluated at tb: (value, variance, n). float64."""
    c = lambda a: np.concatenate([[0.0], np.cumsum(a)])  # noqa: E731
    St, Sy, Stt, Sty, Syy = c(t), c(y), c(t * t), c(t * y), c(y * y)
    n = (hi - lo).astype(np.float64)
    st, sy = St[hi] - St[lo], Sy[hi] - Sy[lo]
    stt, sty, syy = Stt[hi] - Stt[lo], Sty[hi] - Sty[lo], Syy[hi] - Syy[lo]
    with np.errstate(invalid="ignore", divide="ignore"):
        tm, ym = st / n, sy / n
        sxx = stt - n * tm * tm
        sxy = sty - n * tm * ym
        b = sxy / sxx
        a = ym - b * tm
        rss = np.maximum(syy - n * ym * ym - b * sxy, 0.0)
        s2 = rss / np.maximum(n - 2, 1)
        val = a + b * tb
        var = s2 * (1.0 / n + (tb - tm) ** 2 / sxx)
    return val, var, n


def check_continuity(t_frame: np.ndarray, phi_unwrapped: np.ndarray, gaps: list[GapEvent],
                     jump_window_s: float, thr: dict[str, float], min_side_frames: int = 8,
                     t_clip: np.ndarray | None = None) -> ContinuityResult:
    """`t_frame` (sensor or pts time) drives the fits. Reported times (events, raw boundaries, residual series) are
    in-clip times `t_clip[frame]` when given, so a splice whose sensor timestamps come from another recording is
    still located inside the clip."""
    ok = ~np.isnan(phi_unwrapped)
    idx = np.flatnonzero(ok)
    if len(idx) < 2 * min_side_frames:
        return ContinuityResult([], np.zeros(0), np.zeros(0), [])
    t = t_frame[idx].astype(np.float64)
    phi = phi_unwrapped[idx].astype(np.float64)
    tc = (t_frame if t_clip is None else t_clip)[idx].astype(np.float64)
    # boundary j lies between samples j and j+1
    tb = 0.5 * (t[1:] + t[:-1])
    j = np.arange(len(t) - 1)
    left_lo = np.searchsorted(t, tb - jump_window_s, "left")
    left_hi = j + 1
    right_lo = j + 1
    right_hi = np.searchsorted(t, tb + jump_window_s, "right")
    vl, varl, nl = _side_fits(t, phi, left_lo, left_hi, tb)
    vr, varr, nr = _side_fits(t, phi, right_lo, right_hi, tb)
    jump = _wrap(vr - vl)
    sigma = np.sqrt(np.maximum(varl + varr, 1e-12))
    z = np.where((nl >= min_side_frames) & (nr >= min_side_frames), np.abs(jump) / sigma, 0.0)
    # local maxima of z within ±jump_window_s (a single jump raises z at its neighbours too)
    peak = np.zeros(len(z), bool)
    for cand in np.flatnonzero(z > 3.0):
        near = np.abs(tb - tb[cand]) <= jump_window_s
        peak[cand] = z[cand] >= z[near].max()
    sig_thr = float(thr["edit_significance_sigma"])
    min_rad = float(thr["edit_min_rad"])
    gap_at = {g.frame_index: g for g in gaps}
    events: list[ContinuityEvent] = []
    raw: list[dict[str, float]] = []
    for i in range(len(z)):
        k = int(idx[i + 1])
        gap = gap_at.get(k)
        if not peak[i] and gap is None:
            continue
        significant = bool(peak[i] and z[i] > sig_thr and abs(jump[i]) >= min_rad)
        raw.append({"t_s": float(tc[i + 1]), "z": float(z[i]), "rad": float(abs(jump[i])), "gap": gap is not None})
        if gap is not None and not significant:
            events.append(ContinuityEvent(kind="DROPPED_FRAMES_EXPLAINED", frame_index=k, t_s=float(tc[i + 1]),
                                          magnitude_rad=float(jump[i]), significance=float(z[i]), significant=False,
                                          gap_s=gap.size_s))
        elif significant:
            events.append(ContinuityEvent(kind="EDIT_CANDIDATE", frame_index=k, t_s=float(tc[i + 1]),
                                          magnitude_rad=float(jump[i]), significance=float(z[i]), significant=True,
                                          gap_s=gap.size_s if gap else None))
    reasons: list[Reason] = []
    if any(e.kind == "EDIT_CANDIDATE" for e in events):
        reasons.append(Reason.EDIT_CANDIDATE)
    if any(e.kind == "DROPPED_FRAMES_EXPLAINED" for e in events):
        reasons.append(Reason.DROPPED_FRAMES_EXPLAINED)
    # series for plots: the estimated phase jump at every boundary with enough frames on both sides
    valid = (nl >= min_side_frames) & (nr >= min_side_frames)
    tbc = 0.5 * (tc[1:] + tc[:-1])
    return ContinuityResult(events, tbc[valid], jump[valid], reasons, raw)
