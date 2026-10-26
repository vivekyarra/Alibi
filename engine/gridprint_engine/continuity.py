"""Stage S11 — continuity (SPEC 8.12). Works with or without reference data.

The flicker phase φ_k is measured against absolute frame time, so across a true time interval Δt it
advances by 2π·δf·Δt. Residual r_k = wrap(Δφ_k − 2π·δf_local·Δt_k). A cut that was re-timed to
look continuous leaves a residual of 2π·f·(removed time) mod 2π; dropped frames with true
timestamps leave none. Change points: robust z-score of r_k (DECISIONS D-014).
"""

from __future__ import annotations

from dataclasses import dataclass

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


def check_continuity(t_frame: np.ndarray, phi_unwrapped: np.ndarray, gaps: list[GapEvent],
                     smooth_window_s: float, thr: dict[str, float]) -> ContinuityResult:
    ok = ~np.isnan(phi_unwrapped)
    idx = np.flatnonzero(ok)
    if len(idx) < 10:
        return ContinuityResult([], np.zeros(0), np.zeros(0), [])
    t = t_frame[idx]
    phi = phi_unwrapped[idx]
    dphi = _wrap(np.diff(phi))
    dt = np.diff(t)
    rate = dphi / np.maximum(dt, 1e-9)  # rad/s per interval
    # smooth frequency model: running median of the phase rate over the smoothing window
    mid = 0.5 * (t[1:] + t[:-1])
    loc = np.empty_like(rate)
    for i in range(len(rate)):
        sel = np.abs(mid - mid[i]) <= smooth_window_s / 2
        sel[i] = False
        loc[i] = np.median(rate[sel]) if sel.any() else rate[i]
    res = _wrap(dphi - loc * dt)
    mad = float(np.median(np.abs(res - np.median(res)))) * 1.4826 + 1e-9
    z = np.abs(res - np.median(res)) / mad
    sig_thr = float(thr["edit_significance_sigma"])
    min_rad = float(thr["edit_min_rad"])
    gap_at = {g.frame_index: g for g in gaps}
    events: list[ContinuityEvent] = []
    reasons: list[Reason] = []
    for j in range(len(res)):
        k = int(idx[j + 1])  # boundary between idx[j] and idx[j+1]
        gap = gap_at.get(k)  # S1 timestamp gap at this boundary
        significant = bool(z[j] > sig_thr and abs(res[j]) >= min_rad)
        if gap is not None and not significant:
            events.append(ContinuityEvent(kind="DROPPED_FRAMES_EXPLAINED", frame_index=k, t_s=float(t[j + 1]),
                                          magnitude_rad=float(res[j]), significance=float(z[j]),
                                          significant=False, gap_s=gap.size_s))
        elif significant:
            events.append(ContinuityEvent(kind="EDIT_CANDIDATE", frame_index=k, t_s=float(t[j + 1]),
                                          magnitude_rad=float(res[j]), significance=float(z[j]),
                                          significant=True, gap_s=gap.size_s if gap else None))
    if any(e.kind == "EDIT_CANDIDATE" for e in events):
        reasons.append(Reason.EDIT_CANDIDATE)
    if any(e.kind == "DROPPED_FRAMES_EXPLAINED" for e in events):
        reasons.append(Reason.DROPPED_FRAMES_EXPLAINED)
    return ContinuityResult(events, mid, res, reasons)
