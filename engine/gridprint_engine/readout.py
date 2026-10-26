"""Stage S3 — readout time (SPEC 8.4). Priority: sidecar → camera profile → blind estimate → unknown."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from gridprint_engine.phase import explained_fraction, frame_fits, row_times
from gridprint_engine.schemas import CaptureSidecar, Reason


@dataclass
class Readout:
    readout_s: float | None
    reason: Reason
    confidence: float
    uncertainty_s: float | None = None
    search_curve: list[tuple[float, float]] | None = None


def from_sidecar(sc: CaptureSidecar | None) -> Readout | None:
    if sc is None or sc.rolling_shutter_skew_ns <= 0:
        return None
    return Readout(sc.rolling_shutter_skew_ns * 1e-9, Reason.READOUT_FROM_SIDECAR, 1.0)


def profile_key(device: str, width: int, height: int, fps: float) -> str:
    return f"{device}|{width}x{height}|{int(round(fps))}"


def from_profile(profiles: dict[str, Any], device: str | None, width: int, height: int,
                 fps: float) -> Readout | None:
    if not device:
        return None
    p = profiles.get(profile_key(device, width, height, fps))
    if not p:
        return None
    return Readout(float(p["readout_s"]), Reason.READOUT_FROM_PROFILE, 0.9,
                   uncertainty_s=float(p.get("uncertainty_s", 0.0)))


def blind_estimate(rs: np.ndarray, mask: np.ndarray, t_frame: np.ndarray, exposure: np.ndarray,
                   row_pos: np.ndarray, n_rows: int, f0: float, t_min: float, t_max: float,
                   steps: int, max_frames: int = 150) -> Readout:
    """Search T_ro in [t_min, t_max] maximizing explained flicker variance × cross-frame phase
    coherence (SPEC 8.4.3). Coarse grid of `steps` values, then a fine grid around the best."""
    k = rs.shape[0]
    sub = np.linspace(0, k - 1, min(k, max_frames)).astype(int)
    rs_s, mk_s = rs[sub], mask[sub]

    def score(T: float) -> float:
        tr = row_times(t_frame[sub], exposure[sub], row_pos, n_rows, float(T))
        ff = frame_fits(rs_s, mk_s, tr, f0, use_opencv=False)
        ef = explained_fraction(ff, rs_s, mk_s)
        if ff.ok.sum() <= 3:
            return 0.0
        coh = float(np.abs(np.mean(np.exp(1j * np.diff(ff.phi[ff.ok])))))
        return ef * coh

    coarse = np.linspace(t_min, t_max, steps)
    curve = [(float(T), score(T)) for T in coarse]
    i = int(np.argmax([c[1] for c in curve]))
    step = (t_max - t_min) / max(steps - 1, 1)
    fine = np.linspace(max(t_min, coarse[i] - step), min(t_max, coarse[i] + step), 21)
    curve += [(float(T), score(T)) for T in fine]
    T_best, s_best = max(curve, key=lambda c: c[1])
    if s_best <= 0:
        return Readout(None, Reason.READOUT_UNKNOWN, 0.0, search_curve=curve)
    return Readout(T_best, Reason.READOUT_ESTIMATED, s_best, uncertainty_s=step / 10,
                   search_curve=sorted(curve))
