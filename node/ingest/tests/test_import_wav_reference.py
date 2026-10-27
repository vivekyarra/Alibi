from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from gridprint_engine.adapters import LocalGridLog
from node.ingest import import_wav_reference as iw


def _wav(path: Path, freq: np.ndarray, fs: int = 8000) -> None:
    t = np.arange(len(freq) * fs) / fs
    f_inst = np.repeat(freq, fs)
    phase = 2 * np.pi * np.cumsum(f_inst) / fs
    x = 0.8 * np.sin(phase) + 0.1 * np.sin(3 * phase) + 0.01 * np.random.default_rng(0).normal(size=len(t))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes((x * 30000).astype(np.int16).tobytes())


def test_per_second_frequency_recovers_track(tmp_path):
    truth = 50 + 0.02 * np.sin(np.arange(30) / 5)
    _wav(tmp_path / "r.wav", truth)
    x, fs = iw.read_wav(tmp_path / "r.wav")
    s, f = iw.per_second_frequency(x, fs, 50.0)
    assert len(s) >= 28
    assert np.max(np.abs(f[2:-2] - truth[s[2:-2]])) < 0.002


def test_cli_writes_gridlog(tmp_path):
    _wav(tmp_path / "r.wav", np.full(10, 50.01))
    assert iw.main([str(tmp_path / "r.wav"), "--zone", "CN", "--t0-utc", "2023-01-01T00:00:00Z",
                    "--root", str(tmp_path / "gl")]) == 0
    t, f = LocalGridLog(tmp_path / "gl").read("CN", 1672531200, 1672531210)
    assert len(t) >= 8 and np.allclose(f, 50.01, atol=1e-3)
