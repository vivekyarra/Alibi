"""Stage S10 — reference matching (SPEC 8.11).

Normalized cross-correlation of demeaned tracks over candidate start times at 1 s steps, refined
to sub-second by parabolic interpolation. Thresholds come from thresholds.yaml (R8).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from gridprint_engine.enf import reference_window_mean, remove_clock_bias
from gridprint_engine.schemas import MatchStats, Reason, SegmentMatch


@dataclass
class Window:
    start_utc: float
    end_utc: float
    source: str  # "claim" | "sidecar" | "max"


def search_window(claim_utc: float | None, claim_tol_s: float | None, sidecar_wall_utc: float | None,
                  ref_latest_utc: float | None, cfg: dict[str, Any]) -> Window | None:
    if claim_utc is not None:
        half = max(claim_tol_s or 0.0, cfg["min_search_window_s"])
        return Window(claim_utc - half, claim_utc + half, "claim")
    if sidecar_wall_utc is not None:
        return Window(sidecar_wall_utc - cfg["sidecar_window_s"], sidecar_wall_utc + cfg["sidecar_window_s"],
                      "sidecar")
    if ref_latest_utc is None:
        return None
    return Window(ref_latest_utc - cfg["max_search_window_s"], ref_latest_utc, "max")


@dataclass
class NccScan:
    offsets: np.ndarray  # candidate start times (UTC s), 1 s steps
    rho: np.ndarray  # NaN where the reference does not cover


def ncc_scan(tau: np.ndarray, track_hz: np.ndarray, ref_t: np.ndarray, ref_f: np.ndarray,
             window: Window, avg_window_s: float, chunk: int = 4096) -> NccScan:
    v = remove_clock_bias(track_hz)
    vn = v / max(np.linalg.norm(v), 1e-15)
    offs = np.arange(np.floor(window.start_utc), np.ceil(window.end_utc) + 1, 1.0)
    rho = np.full(len(offs), np.nan)
    for s in range(0, len(offs), chunk):
        o = offs[s:s + chunk]
        R = reference_window_mean(ref_t, ref_f, o[:, None] + tau[None, :], avg_window_s)
        good = ~np.isnan(R).any(axis=1)
        if not good.any():
            continue
        Rg = R[good]
        Rg = Rg - Rg.mean(axis=1, keepdims=True)  # S9 on the reference segment
        nr = np.linalg.norm(Rg, axis=1)
        rr = (Rg @ vn) / np.maximum(nr, 1e-15)
        tmp = np.full(len(o), np.nan)
        tmp[good] = rr
        rho[s:s + chunk] = tmp
    return NccScan(offs, rho)


def _peak(scan: NccScan, exclusion_s: float, n: int) -> dict[str, Any]:
    r = scan.rho
    if np.all(np.isnan(r)):
        return {"coverage": False}
    i = int(np.nanargmax(r))
    rho1 = float(r[i])
    d = 0.0
    if 0 < i < len(r) - 1 and not np.isnan(r[i - 1]) and not np.isnan(r[i + 1]):
        den = r[i - 1] - 2 * r[i] + r[i + 1]
        d = float(0.5 * (r[i - 1] - r[i + 1]) / den) if den < 0 else 0.0
        d = float(np.clip(d, -0.5, 0.5))
    best = float(scan.offsets[i] + d)
    far = np.abs(scan.offsets - scan.offsets[i]) > exclusion_s
    side = r[far & ~np.isnan(r)]
    rho2 = float(side.max()) if len(side) else float("nan")
    psr = float((rho1 - side.mean()) / side.std()) if len(side) > 2 and side.std() > 0 else float("nan")
    # uncertainty: where the parabola falls by the NCC standard error 1/sqrt(n - 3)
    unc = 0.5
    if 0 < i < len(r) - 1 and not np.isnan(r[i - 1]) and not np.isnan(r[i + 1]):
        curv = -(r[i - 1] - 2 * r[i] + r[i + 1])
        if curv > 0:
            unc = float(np.sqrt(2 * (1.0 / np.sqrt(max(n - 3, 1))) / curv))
    return {"coverage": True, "best": best, "rho1": rho1, "rho2": rho2, "psr": psr, "unc": unc, "index": i}


def match_track(tau: np.ndarray, track_hz: np.ndarray, ref_t: np.ndarray, ref_f: np.ndarray, zone: str,
                window: Window, cfg: dict[str, Any], thr: dict[str, Any],
                avg_window_s: float) -> tuple[MatchStats, list[Reason], NccScan | None]:
    reasons: list[Reason] = []
    length = float(tau[-1] - tau[0] + avg_window_s) if len(tau) else 0.0
    stats = MatchStats(zone=zone, window_start_utc=window.start_utc, window_end_utc=window.end_utc,
                       track_length_s=length)
    if len(tau) < 3:
        reasons.append(Reason.TRACK_TOO_SHORT)
        return stats, reasons, None
    scan = ncc_scan(tau, track_hz, ref_t, ref_f, window, avg_window_s)
    pk = _peak(scan, cfg["exclusion_s"], len(tau))
    if not pk["coverage"]:
        reasons.append(Reason.NO_REFERENCE_COVERAGE)
        return stats, reasons, scan
    margin = pk["rho1"] - pk["rho2"] if not np.isnan(pk["rho2"]) else pk["rho1"]
    stats.best_offset_utc = pk["best"]
    stats.rho1 = pk["rho1"]
    stats.rho2 = None if np.isnan(pk["rho2"]) else pk["rho2"]
    stats.margin = float(margin)
    stats.psr = None if np.isnan(pk["psr"]) else pk["psr"]
    stats.time_uncertainty_s = pk["unc"]
    m = thr["match"]
    if length < m["min_track_s"]:
        reasons.append(Reason.TRACK_TOO_SHORT)
    elif pk["rho1"] < m["rho1_min"] or margin < m["margin_min"]:
        reasons.append(Reason.NO_UNIQUE_MATCH)
    else:
        stats.passes = True
        reasons.append(Reason.MATCH_OK)
    # segment matching (SPEC 8.11.5)
    seg_len = cfg["segment_length_s"]
    if length >= 2 * seg_len:
        segs = []
        start = tau[0]
        while start + seg_len <= tau[-1] + 1e-9:
            sel = (tau >= start) & (tau < start + seg_len)
            if sel.sum() >= 5:
                ss = ncc_scan(tau[sel], track_hz[sel], ref_t, ref_f, window, avg_window_s)
                sp = _peak(ss, cfg["exclusion_s"], int(sel.sum()))
                if sp["coverage"]:
                    smargin = sp["rho1"] - (sp["rho2"] if not np.isnan(sp["rho2"]) else 0.0)
                    passes = sp["rho1"] >= m["rho1_min"] and smargin >= m["margin_min"]
                    segs.append(SegmentMatch(start_s=float(start), end_s=float(start + seg_len),
                                             offset_s=sp["best"], rho1=sp["rho1"], margin=float(smargin),
                                             passes=bool(passes)))
                else:
                    segs.append(SegmentMatch(start_s=float(start), end_s=float(start + seg_len),
                                             offset_s=None, rho1=None, passes=False))
            start += seg_len
        stats.segments = segs
        passing = [s.offset_s for s in segs if s.passes and s.offset_s is not None]
        if len(passing) >= 2:
            spread = max(passing) - min(passing)
            stats.segments_consistent = spread <= cfg["segment_offset_tolerance_s"]
            if not stats.segments_consistent:
                reasons.append(Reason.SEGMENT_OFFSET_INCONSISTENT)
    return stats, reasons, scan
