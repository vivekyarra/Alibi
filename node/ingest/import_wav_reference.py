"""Import a recorded mains waveform (.wav) as a 1 s grid-frequency reference (SPEC 10.4 importers).

Public ENF datasets ship the mains reference as audio-rate voltage recordings (e.g. EV-ENFD `ENF_Reference`,
one hour per file). Frequency per second: rising zero crossings of the band-limited waveform, timed with
linear interpolation between samples; the mean period inside each second gives that second's frequency.

    python node/ingest/import_wav_reference.py REF.wav --zone CN --t0-utc 2023-01-01T00:00:00Z --source ev-enfd
The file has no absolute time, so the start time is given by the caller (documented with the dataset).
"""

from __future__ import annotations

import argparse
import sys
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "engine")]


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        n, ch, width, fs = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    dt = {1: np.uint8, 2: np.int16, 4: np.int32}[width]
    x = np.frombuffer(raw, dtype=dt).astype(np.float64).reshape(-1, ch)[:, 0]
    if width == 1:
        x -= 128.0
    return x, fs


def bandpass(x: np.ndarray, fs: int, nominal: float, half_width: float = 5.0) -> np.ndarray:
    """FFT band-pass around the nominal frequency (float64). Removes DC and harmonics before crossings."""
    spec = np.fft.rfft(x - x.mean())
    f = np.fft.rfftfreq(len(x), 1.0 / fs)
    spec[(f < nominal - half_width) | (f > nominal + half_width)] = 0
    return np.fft.irfft(spec, len(x))


def per_second_frequency(x: np.ndarray, fs: int, nominal: float) -> tuple[np.ndarray, np.ndarray]:
    """Return (second index from file start, frequency Hz) for every whole second with crossings."""
    y = bandpass(x, fs, nominal)
    s0, s1 = y[:-1], y[1:]
    idx = np.flatnonzero((s0 < 0) & (s1 >= 0))
    tc = (idx + (-s0[idx]) / (s1[idx] - s0[idx])) / fs  # crossing times, linear interpolation
    periods = np.diff(tc)
    mids = 0.5 * (tc[1:] + tc[:-1])
    ok = np.abs(periods - 1.0 / nominal) < 0.1 / nominal  # reject glitches (±10 % of a period)
    secs = np.floor(mids[ok]).astype(np.int64)
    out_s, out_f = [], []
    last = int(len(x) / fs) - 1
    for s in np.unique(secs):
        if s <= 0 or s >= last:  # the FFT band-pass biases the first and last second (edge effects)
            continue
        p = periods[ok][secs == s]
        if len(p) >= 0.8 * nominal:
            out_s.append(int(s))
            out_f.append(1.0 / float(p.mean()))
    return np.array(out_s, np.int64), np.array(out_f, np.float64)


def main(argv: list[str] | None = None) -> int:
    from gridprint_engine.adapters import LocalGridLog

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("wav", nargs="+")
    ap.add_argument("--zone", required=True)
    ap.add_argument("--nominal", type=float, default=50.0)
    ap.add_argument("--t0-utc", required=True, help="UTC start time of the first file (ISO 8601)")
    ap.add_argument("--source", default="wav-import")
    ap.add_argument("--root", default=str(REPO / "data" / "gridlog"))
    a = ap.parse_args(argv)
    t0 = int(datetime.fromisoformat(a.t0_utc.replace("Z", "+00:00")).timestamp())
    gl = LocalGridLog(Path(a.root))
    for p in a.wav:
        x, fs = read_wav(Path(p))
        s, f = per_second_frequency(x, fs, a.nominal)
        gl.write(a.zone, t0 + s, f, source=a.source, node=Path(p).stem, quality="reference-wav")
        print(f"{p}: {len(s)} seconds, {fs} Hz sample rate, frequency {f.min():.4f}–{f.max():.4f} Hz")
        t0 += int(len(x) / fs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
