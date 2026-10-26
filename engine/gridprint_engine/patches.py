"""Stage S6 — light patches (SPEC 8.7).

Patches are rectangles of the reference frame (analysis grid, coded orientation). A patch mask is
mapped into each frame with the S4 homography.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from gridprint_engine.rowsignal import Modulation


@dataclass
class Patch:
    id: int
    y0: int
    y1: int
    x0: int
    x1: int
    eligible: bool
    static_fraction: float
    mean_linear: float
    saturation_fraction: float
    score_db: float | None = None


@dataclass
class PatchSet:
    patches: list[Patch]
    shape: tuple[int, int]
    ranked: list[int] = field(default_factory=list)


def make_patches(lin: np.ndarray, ok: np.ndarray, sat: np.ndarray, grid: tuple[int, int],
                 min_static_fraction: float, min_mean_linear: float,
                 max_saturation_fraction: float) -> PatchSet:
    k, h, w = lin.shape
    gy, gx = grid
    ys = np.linspace(0, h, gy + 1).astype(int)
    xs = np.linspace(0, w, gx + 1).astype(int)
    mean_lin = lin.mean(axis=0, dtype=np.float64)
    pats = []
    for i in range(gy):
        for j in range(gx):
            sl = (slice(ys[i], ys[i + 1]), slice(xs[j], xs[j + 1]))
            frac_ok = ok[:, sl[0], sl[1]].mean(axis=(1, 2))
            sf = float((frac_ok >= 0.8).mean())
            ml = float(mean_lin[sl].mean())
            satf = float(sat[sl].mean())
            pats.append(Patch(id=i * gx + j, y0=int(ys[i]), y1=int(ys[i + 1]), x0=int(xs[j]), x1=int(xs[j + 1]),
                              eligible=sf >= min_static_fraction and ml >= min_mean_linear
                              and satf < max_saturation_fraction,
                              static_fraction=sf, mean_linear=ml, saturation_fraction=satf))
    return PatchSet(patches=pats, shape=(h, w))


def selection_mask(ps: PatchSet, ids: list[int], homs: np.ndarray | None, k: int) -> np.ndarray:
    """bool [K, h, w]: selected patch pixels mapped into each frame."""
    h, w = ps.shape
    ref = np.zeros((h, w), np.uint8)
    for p in ps.patches:
        if p.id in ids:
            ref[p.y0:p.y1, p.x0:p.x1] = 1
    if homs is None:
        return np.broadcast_to(ref.astype(bool), (k, h, w)).copy()
    out = np.empty((k, h, w), bool)
    for i in range(k):
        out[i] = cv2.warpPerspective(ref, homs[i], (w, h), flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP) > 0
    return out


def score_patches(ps: PatchSet, mod: Modulation, sel_all: np.ndarray, axis: str, t_rows: np.ndarray,
                  phi: np.ndarray, frame_ok: np.ndarray, f0: float) -> None:
    """Coherent band SNR per patch, using the first-pass frame phases (SPEC 8.7.3)."""
    use = mod.ok & sel_all
    wgt = np.where(use, mod.lbar, 0).astype(np.float32)
    mw = mod.m * wgt
    g = np.cos(2 * np.pi * f0 * t_rows + phi[:, None])  # [K, R] unit flicker model per sensor row
    if axis == "rows":  # reduce each patch's columns → [K, h, n_col_bands]
        cuts = sorted({p.x0 for p in ps.patches})
        num = np.add.reduceat(mw, cuts, axis=2, dtype=np.float64)
        den = np.add.reduceat(wgt, cuts, axis=2, dtype=np.float64)
    else:  # sensor rows are coded columns: reduce each patch's rows → [K, w, n_row_bands]
        cuts = sorted({p.y0 for p in ps.patches})
        num = np.add.reduceat(mw, cuts, axis=1, dtype=np.float64).transpose(0, 2, 1)
        den = np.add.reduceat(wgt, cuts, axis=1, dtype=np.float64).transpose(0, 2, 1)
    for p in ps.patches:
        p.score_db = None
        if not p.eligible:
            continue
        band = cuts.index(p.x0 if axis == "rows" else p.y0)
        r0, r1 = (p.y0, p.y1) if axis == "rows" else (p.x0, p.x1)
        nn, dd = num[:, r0:r1, band], den[:, r0:r1, band]
        rmask = (dd > 0) & frame_ok[:, None]
        if rmask.sum() < 10:
            continue
        y = nn[rmask] / dd[rmask]
        gg = g[:, r0:r1][rmask]
        amp = float((y * gg).sum() / max((gg * gg).sum(), 1e-12))
        rv = float((y - amp * gg).var())
        p.score_db = float(10 * np.log10(amp ** 2 / 2 / rv)) if rv > 0 and amp > 0 else -99.0
    ranked = sorted([p for p in ps.patches if p.score_db is not None], key=lambda q: -(q.score_db or -99))
    ps.ranked = [p.id for p in ranked]


def choose(ps: PatchSet, strategy: str) -> list[int]:
    elig = [p for p in ps.patches if p.eligible]
    if strategy == "all":
        return [p.id for p in elig]
    if strategy == "top":
        good = [i for i in ps.ranked if (_score(ps, i) or -99) > 0]
        n = max(4, len(ps.ranked) // 4)
        return good[:n] or ps.ranked[:n]
    if strategy == "coherent":
        sc = [s for i in ps.ranked if (s := _score(ps, i)) is not None]
        if not sc:
            return [p.id for p in elig]
        med = float(np.median(sc))
        return [i for i in ps.ranked if (_score(ps, i) or -99) >= med]
    if strategy == "bright":
        srt = sorted(elig, key=lambda p: -p.mean_linear)
        return [p.id for p in srt[: max(4, len(srt) // 2)]]
    raise ValueError(f"unknown strategy {strategy}")


def _score(ps: PatchSet, pid: int) -> float | None:
    return next(p.score_db for p in ps.patches if p.id == pid)
