"""Stage S8 — per-frame phase fit, phase tracking, and DFT cross-check (SPEC 8.9).

Row time model (SPEC 8.4): t(k, r) = t_k + e_k/2 + r × T_ro / (N − 1), r = sensor row.
All signal arithmetic is float64 (R6).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


def row_times(t_frame: np.ndarray, exposure: np.ndarray, row_pos: np.ndarray, n_rows: int,
              readout_s: float) -> np.ndarray:
    """float64 [K, R]. row_pos = sensor row index of each analysis row (0 = first row read)."""
    dt_row = readout_s / max(n_rows - 1, 1)
    return (t_frame[:, None] + exposure[:, None] / 2.0 + row_pos[None, :] * dt_row).astype(np.float64)


@dataclass
class FrameFits:
    a: np.ndarray
    b: np.ndarray
    c: np.ndarray
    amp: np.ndarray
    phi: np.ndarray
    resvar: np.ndarray
    snr: np.ndarray
    nrows: np.ndarray
    ok: np.ndarray


def _design(t: np.ndarray, f0: float) -> tuple[np.ndarray, np.ndarray]:
    w = 2 * np.pi * f0 * t
    return np.cos(w), np.sin(w)


def frame_fits(rs: np.ndarray, mask: np.ndarray, t_rows: np.ndarray, f0: float,
               use_opencv: bool = True) -> FrameFits:
    """Least squares m(k,r) ≈ a cos(2π f0 t) + b sin(2π f0 t) + c per frame (cv2.solve, float64)."""
    k = rs.shape[0]
    a = np.zeros(k)
    b = np.zeros(k)
    c = np.zeros(k)
    rv = np.full(k, np.inf)
    n = mask.sum(1)
    ok = n >= 8
    t_ref = float(t_rows[0, 0])
    if use_opencv:
        for i in np.flatnonzero(ok):
            mk = mask[i]
            cs, sn = _design(t_rows[i, mk] - t_ref, f0)
            A = np.stack([cs, sn, np.ones_like(cs)], 1).astype(np.float64)
            y = rs[i, mk].astype(np.float64).reshape(-1, 1)
            ret, sol = cv2.solve(A, y, flags=cv2.DECOMP_SVD)
            a[i], b[i], c[i] = sol[:, 0]
            res = y[:, 0] - A @ sol[:, 0]
            rv[i] = float(res @ res) / max(len(res) - 3, 1)
    else:
        a, b, c, rv = _batched_fit(rs, mask, t_rows - t_ref, f0, ok)
    amp = np.hypot(a, b)
    # fit used (t - t_ref); express the phase against absolute t: cos(ω(t - t_ref) + φ') = cos(ωt + φ)
    phi = np.angle(np.exp(1j * (np.arctan2(-b, a) - 2 * np.pi * f0 * t_ref)))
    snr = np.where(ok & (rv > 0), (amp ** 2 / 2) / np.maximum(rv, 1e-30), 0.0)
    return FrameFits(a=a, b=b, c=c, amp=amp, phi=phi, resvar=rv, snr=snr, nrows=n, ok=ok)


def flicker_model(fits: FrameFits, t_rows: np.ndarray, f0: float) -> np.ndarray:
    """Fitted flicker term A_k cos(2π f0 t + φ_k) per frame and row (no constant). float64."""
    w = 2 * np.pi * f0 * t_rows
    return np.where(fits.ok[:, None], fits.amp[:, None] * np.cos(w + fits.phi[:, None]), 0.0)


def _batched_fit(rs: np.ndarray, mask: np.ndarray, t: np.ndarray, f0: float,
                 ok: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized normal-equation solve (used inside the blind readout search for speed)."""
    cs, sn = _design(t, f0)
    wm = mask.astype(np.float64)
    y = rs.astype(np.float64) * wm
    X = np.stack([cs * wm, sn * wm, wm], -1)  # [K, R, 3]
    G = np.einsum("kri,krj->kij", X, X)
    h = np.einsum("kri,kr->ki", X, y)
    G[~ok] = np.eye(3)
    sol = np.linalg.solve(G + 1e-12 * np.eye(3), h[..., None])[..., 0]
    res = y - np.einsum("kri,ki->kr", X, sol)
    rv = (res ** 2).sum(1) / np.maximum(mask.sum(1) - 3, 1)
    rv[~ok] = np.inf
    return sol[:, 0], sol[:, 1], sol[:, 2], rv


def band_snr_db(fits: FrameFits) -> float:
    if not fits.ok.any():
        return -99.0
    med = float(np.median(fits.snr[fits.ok]))
    return 10 * np.log10(med) if med > 0 else -99.0


def explained_fraction(fits: FrameFits, rs: np.ndarray, mask: np.ndarray) -> float:
    """Mean over frames of the fraction of row variance explained by the flicker fit."""
    tot = np.array([rs[i, mask[i]].var() if mask[i].sum() > 3 else 0.0 for i in range(rs.shape[0])])
    good = fits.ok & (tot > 0)
    if not good.any():
        return 0.0
    return float(np.mean(np.clip((fits.amp[good] ** 2 / 2) / tot[good], 0, 1)))


@dataclass
class Track:
    tau_s: np.ndarray  # window centers, video time from first frame (s)
    flicker_hz: np.ndarray
    enf_hz: np.ndarray
    sigma_hz: np.ndarray
    phase_unwrapped: np.ndarray  # per frame (nan where not ok)
    frame_weight: np.ndarray
    f0: float
    mean_flicker_hz: float


def phase_track(fits: FrameFits, t_frame: np.ndarray, f0: float, window_s: float, hop_s: float,
                jitter_s: float, n_rows_used: np.ndarray) -> Track:
    ok = fits.ok & (fits.amp > 0)
    phi_u = np.full(len(t_frame), np.nan)
    idx = np.flatnonzero(ok)
    if len(idx) < 3:
        empty = np.zeros(0)
        return Track(empty, empty, empty, empty, phi_u, np.zeros(len(t_frame)), f0, float("nan"))
    phi_u[idx] = np.unwrap(fits.phi[idx])
    # phase variance from the fit, plus timestamp jitter (SPEC 8.9.6)
    var_fit = 2 * fits.resvar / np.maximum(fits.amp ** 2 * np.maximum(n_rows_used, 1), 1e-30)
    var = var_fit + (2 * np.pi * f0 * jitter_s) ** 2
    wgt = np.where(ok, 1.0 / np.maximum(var, 1e-12), 0.0)
    t = t_frame
    taus, fl, sg = [], [], []
    c = t[0] + window_s / 2
    med_dt = float(np.median(np.diff(t))) if len(t) > 1 else 1.0
    need = 0.5 * window_s / med_dt
    while c + window_s / 2 <= t[-1] + med_dt / 2 + 1e-9:
        sel = ok & (t >= c - window_s / 2) & (t < c + window_s / 2)
        if sel.sum() >= max(need, 3):
            s, s_sig = _wls_slope(t[sel] - c, phi_u[sel], wgt[sel])
            taus.append(c)
            fl.append(f0 + s / (2 * np.pi))
            sg.append(s_sig / (2 * np.pi))
        c += hop_s
    s_all, _ = _wls_slope(t[ok] - t[ok].mean(), phi_u[ok], wgt[ok])
    tau = np.array(taus, np.float64)
    flk = np.array(fl, np.float64)
    return Track(tau_s=tau, flicker_hz=flk, enf_hz=flk / 2.0, sigma_hz=np.array(sg, np.float64) / 2.0,
                 phase_unwrapped=phi_u, frame_weight=wgt, f0=f0, mean_flicker_hz=f0 + s_all / (2 * np.pi))


def _wls_slope(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> tuple[float, float]:
    sw = w.sum()
    if sw <= 0 or len(x) < 2:
        return 0.0, float("inf")
    xm = (w * x).sum() / sw
    ym = (w * y).sum() / sw
    sxx = (w * (x - xm) ** 2).sum()
    if sxx <= 0:
        return 0.0, float("inf")
    slope = (w * (x - xm) * (y - ym)).sum() / sxx
    res = y - (ym + slope * (x - xm))
    dof = max(len(x) - 2, 1)
    s2 = (w * res ** 2).sum() / dof / (sw / len(x))
    return float(slope), float(np.sqrt(s2 / (sxx / (sw / len(x)))))


@dataclass
class DftEstimate:
    peak_hz: float
    peak_snr_db: float
    n_samples: int
    fill_fraction: float


def dft_estimate(rs: np.ndarray, mask: np.ndarray, t_rows: np.ndarray, f0: float, rate_factor: float,
                 search_hz: float = 1.5) -> DftEstimate:
    """Cross-check estimator (SPEC 8.9.4): uniform virtual time grid, idle gaps zero-filled with a
    known mask (never interpolated), Hann window, cv2.dft, parabolic peak interpolation."""
    fs = rate_factor * f0
    t0 = float(t_rows[mask].min()) if mask.any() else 0.0
    bins = np.floor((t_rows - t0) * fs).astype(np.int64)
    bsel = bins[mask]
    n = int(bsel.max()) + 1 if len(bsel) else 1
    sums = np.bincount(bsel, weights=rs[mask].astype(np.float64), minlength=n)
    cnts = np.bincount(bsel, minlength=n).astype(np.float64)
    filled = cnts > 0
    x = np.zeros(n, np.float64)
    x[filled] = sums[filled] / cnts[filled]  # empty bins (idle gaps, dropped frames) stay exactly 0
    x[filled] -= x[filled].mean()
    x *= np.hanning(n)
    nfft = cv2.getOptimalDFTSize(4 * n)
    buf = np.zeros((1, nfft), np.float64)
    buf[0, :n] = x
    spec = cv2.dft(buf, flags=cv2.DFT_COMPLEX_OUTPUT)
    mag = np.hypot(spec[0, :, 0], spec[0, :, 1])[: nfft // 2]
    freqs = np.arange(len(mag)) * fs / nfft
    band = (freqs >= f0 - search_hz) & (freqs <= f0 + search_hz)
    if not band.any():
        return DftEstimate(float("nan"), -99.0, n, float(filled.mean()))
    bi = np.flatnonzero(band)
    p = int(bi[np.argmax(mag[bi])])
    if 0 < p < len(mag) - 1:
        y0, y1, y2 = np.log(mag[p - 1:p + 2] + 1e-30)
        den = y0 - 2 * y1 + y2
        d = 0.5 * (y0 - y2) / den if den != 0 else 0.0
    else:
        d = 0.0
    peak = (p + d) * fs / nfft
    noise_band = (freqs >= f0 - 5) & (freqs <= f0 + 5) & (np.abs(freqs - peak) > 0.5)
    noise = float(np.median(mag[noise_band] ** 2)) if noise_band.any() else 1e-30
    snr = 10 * np.log10(mag[p] ** 2 / max(noise, 1e-30))
    return DftEstimate(peak_hz=float(peak), peak_snr_db=float(snr), n_samples=n,
                       fill_fraction=float(filled.mean()))
