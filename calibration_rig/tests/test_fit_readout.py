"""Synthetic rolling-shutter LED video -> fit_readout recovers the readout time within 1 %."""

from __future__ import annotations

import json
from pathlib import Path

import av
import cv2
import numpy as np
import pytest
import yaml

from calibration_rig import fit_readout as fr

F_LED = 1000.0
FPS = 30


def synth_frames(h: int, w: int, readout_s: float, n: int, seed: int = 0) -> list[np.ndarray]:
    """LED square-ish wave (fundamental + 3rd harmonic) seen by a rolling shutter on a lit card with
    uneven illumination and sensor noise."""
    rng = np.random.default_rng(seed)
    row_time = readout_s / (h - 1)
    r = np.arange(h, dtype=np.float64)[:, None]
    c = np.arange(w, dtype=np.float64)[None, :]
    base = 0.45 + 0.2 * (r / h) - 0.1 * ((c - w / 2) / w) ** 2
    out = []
    for k in range(n):
        t = k / FPS + 0.0007 * k + r * row_time
        ph = 2 * np.pi * F_LED * t
        led = 1.0 + 0.25 * (np.sin(ph) + np.sin(3 * ph) / 3)
        img = base * led + rng.normal(0, 0.01, (h, w))
        out.append(np.clip(img * 255, 0, 255).astype(np.uint8))
    return out


def write_video(path: Path, frames: list[np.ndarray]) -> Path:
    h, w = frames[0].shape
    try:
        with av.open(str(path), "w") as c:
            s = c.add_stream("libx264", rate=FPS)
            s.width, s.height, s.pix_fmt = w, h, "yuv420p"
            s.options = {"crf": "12", "preset": "veryfast"}
            for f in frames:
                vf = av.VideoFrame.from_ndarray(cv2.cvtColor(f, cv2.COLOR_GRAY2RGB), format="rgb24")
                for p in s.encode(vf):
                    c.mux(p)
            for p in s.encode():
                c.mux(p)
        return path
    except (av.error.FFmpegError, ValueError):
        vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (w, h))
        assert vw.isOpened()
        for f in frames:
            vw.write(cv2.cvtColor(f, cv2.COLOR_GRAY2BGR))
        vw.release()
        return path


@pytest.mark.parametrize("h,readout", [(480, 0.025), (360, 0.012)])
def test_band_period_on_raw_frames(h, readout):
    frames = synth_frames(h, 64, readout, 5)
    p_true = (h - 1) / (F_LED * readout)
    for f in frames:
        p, snr = fr.band_period_rows(f.astype(np.float32) / 255)
        assert abs(p - p_true) / p_true < 0.005 and snr > fr.MIN_SNR


def test_recover_readout_from_video_and_write_profile(tmp_path):
    readout = 0.025
    clip = write_video(tmp_path / "640x480_30.mp4", synth_frames(480, 640, readout, 40))
    profiles = tmp_path / "camera_profiles.yaml"
    profiles.write_text("# header kept\nprofiles: {}\n")
    sidecar = tmp_path / "sc.json"
    sidecar.write_text(json.dumps({"rolling_shutter_skew_ns": 24_800_000}))
    rc = fr.main([str(clip), "--device", "SynthPhone", "--f-led", str(F_LED), "--sidecar", str(sidecar),
                  "--profiles", str(profiles), "--results", str(tmp_path / "results")])
    assert rc == 0
    text = profiles.read_text()
    assert text.startswith("# header kept")
    e = yaml.safe_load(text)["profiles"]["SynthPhone|640x480|30"]
    assert abs(e["readout_s"] - readout) / readout < 0.01
    assert e["n_frames"] >= 30 and e["f_led_hz"] == F_LED and len(e["source_clip_sha256"]) == 64
    assert e["uncertainty_s"] >= 0 and "date" in e
    assert abs(e["sidecar_diff_s"] - (e["readout_s"] - 0.0248)) < 1e-12
    assert (tmp_path / "results" / "SynthPhone" / "640x480_30.json").exists()


def test_all_mode_merges_entries(tmp_path):
    root = tmp_path / "calibration"
    write_video((root / "PhoneA").mkdir(parents=True) or root / "PhoneA" / "320x240_30.mp4",
                synth_frames(240, 320, 0.02, 30, seed=1))
    write_video((root / "PhoneB").mkdir(parents=True) or root / "PhoneB" / "320x360_30.mp4",
                synth_frames(360, 320, 0.03, 30, seed=2))
    profiles = tmp_path / "p.yaml"
    profiles.write_text("profiles:\n  Old|1x1|30: {readout_s: 0.01}\n")
    rc = fr.main(["--all", str(root), "--f-led", str(F_LED), "--profiles", str(profiles), "--results",
                  str(tmp_path / "r")])
    assert rc == 0
    p = yaml.safe_load(profiles.read_text())["profiles"]
    assert set(p) == {"Old|1x1|30", "PhoneA|320x240|30", "PhoneB|320x360|30"}
    assert abs(p["PhoneA|320x240|30"]["readout_s"] - 0.02) / 0.02 < 0.01
    assert abs(p["PhoneB|320x360|30"]["readout_s"] - 0.03) / 0.03 < 0.01


def test_flat_video_is_rejected(tmp_path):
    clip = write_video(tmp_path / "flat.mp4", [np.full((240, 320), 128, np.uint8)] * 15)
    with pytest.raises(fr.CalibrationError):
        fr.fit_clip(clip, "X", F_LED)


def test_empty_all_dir_fails(tmp_path):
    assert fr.main(["--all", str(tmp_path / "missing"), "--f-led", "1000"]) == 1
