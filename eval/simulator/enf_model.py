"""Synthetic ENF tracks (DECISIONS D-010) and the flicker phase integral.

The grid frequency is modeled per UTC second; within a second it is linear between samples.
The lamp flickers at twice the grid frequency.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np


def ou_track(n_s: int, nominal_hz: float, rng: np.random.Generator, theta: float = 0.02,
             sigma: float = 0.004) -> np.ndarray:
    """Ornstein–Uhlenbeck random walk around nominal, 1 s steps (float64)."""
    x = np.zeros(n_s, dtype=np.float64)
    x[0] = rng.normal(0.0, sigma / np.sqrt(2 * theta))
    noise = rng.normal(0.0, sigma, n_s)
    for i in range(1, n_s):
        x[i] = x[i - 1] - theta * x[i - 1] + noise[i]
    return nominal_hz + x


def load_track_csv(path: Path, t0_utc: int, n_s: int) -> np.ndarray:
    """Read a real 1 s log (t_utc_s,freq_hz) and return n_s values from t0_utc. Gaps are not filled."""
    vals = {}
    with Path(path).open() as fh:
        for row in csv.DictReader(fh):
            vals[int(row["t_utc_s"])] = float(row["freq_hz"])
    out = np.array([vals.get(t0_utc + i, np.nan) for i in range(n_s)], dtype=np.float64)
    if np.isnan(out).any():
        raise ValueError("reference CSV does not cover the requested span")
    return out


@dataclass
class GridSignal:
    """Grid frequency f(t) on knots t0_utc + i (i = 0..n-1), linear between knots."""

    t0_utc: int
    knots_hz: np.ndarray

    def __post_init__(self) -> None:
        f = self.knots_hz
        # cumulative integral of f over each whole second (trapezoid is exact for linear segments)
        seg = 0.5 * (f[:-1] + f[1:])
        self._cum = np.concatenate([[0.0], np.cumsum(seg)])

    def freq(self, t_utc: np.ndarray) -> np.ndarray:
        x = np.asarray(t_utc, dtype=np.float64) - self.t0_utc
        return np.interp(x, np.arange(len(self.knots_hz)), self.knots_hz)

    def grid_cycles(self, t_utc: np.ndarray) -> np.ndarray:
        """∫ f dt from t0_utc to t (cycles of the grid), float64."""
        x = np.asarray(t_utc, dtype=np.float64) - self.t0_utc
        if np.any(x < 0) or np.any(x >= len(self.knots_hz) - 1):
            raise ValueError("time outside the simulated grid span")
        i = np.floor(x).astype(np.int64)
        u = x - i
        f0 = self.knots_hz[i]
        f1 = self.knots_hz[i + 1]
        return self._cum[i] + f0 * u + 0.5 * (f1 - f0) * u * u

    def reference_log(self) -> tuple[np.ndarray, np.ndarray]:
        """What a Node logs: mean frequency over each UTC second [s, s+1)."""
        t = self.t0_utc + np.arange(len(self.knots_hz) - 1, dtype=np.int64)
        return t, np.diff(self._cum)
