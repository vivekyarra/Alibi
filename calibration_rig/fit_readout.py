"""Measure rolling-shutter readout time from a video of an LED-lit white card (SPEC 10.5, 8.4).

The rig LED blinks at a known frequency f_led. A rolling shutter samples each row at a later time, so the
card shows horizontal bands. For each frame:
  1. row means with cv2.reduce (coded orientation, the same row order the engine uses);
  2. fractional modulation: divide by a quadratic fit of the row profile, subtract 1, Hann window;
  3. zero-padded cv2.dft; strongest peak between 1/(rows/2) and 1/3 cycles per row; Gaussian
     (log-parabolic) peak interpolation -> band period P in rows;
  4. row time = 1 / (f_led * P); readout T_ro = row time * (N - 1), N = rows in the coded frame.
Per-frame values -> median. Uncertainty = standard error of the median, 1.2533 * 1.4826 * MAD / sqrt(n).

Writes or merges an entry in config/camera_profiles.yaml under "<device>|<W>x<H>|<fps>" (the key used by
gridprint_engine.readout.profile_key) and a per-clip JSON file under results/calibration/.

Usage:
  python calibration_rig/fit_readout.py CLIP.mp4 --device "Pixel 7" [--sidecar CLIP.json]
  python calibration_rig/fit_readout.py --all data/calibration      # <dir>/<device>/<W>x<H>_<fps>.mp4
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make the repo and engine importable
    _ROOT = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(_ROOT), str(_ROOT / "engine")]

import argparse  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
from dataclasses import asdict, dataclass, field  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from typing import Any  # noqa: E402

import av  # noqa: E402
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402

from gridprint_engine.readout import profile_key  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILES = ROOT / "config" / "camera_profiles.yaml"
DEFAULT_RESULTS = ROOT / "results" / "calibration"
MIN_PERIOD_ROWS = 3.0     # below this the bands are too fine to measure (and may alias)
MIN_MODULATION = 1e-4    # band amplitude as a fraction of the mean level; below this the frame is flat
MIN_SNR = 8.0             # peak / median spectrum magnitude in the search band
MIN_FRAMES = 10           # accepted frames needed for a profile entry
PAD_FACTOR = 8            # zero padding of the row profile before the DFT
MODE_RE = re.compile(r"^(\d+)x(\d+)_(\d+(?:\.\d+)?)$")


class CalibrationError(RuntimeError):
    pass


@dataclass
class ClipFit:
    device: str
    width: int
    height: int
    fps: float
    key: str
    f_led_hz: float
    readout_s: float
    uncertainty_s: float
    spread_s: float
    period_rows: float
    n_frames: int
    frames_total: int
    source_clip: str
    source_clip_sha256: str
    date: str
    sidecar_skew_s: float | None = None
    sidecar_diff_s: float | None = None
    warnings: list[str] = field(default_factory=list)

    def profile_entry(self) -> dict[str, Any]:
        e: dict[str, Any] = {
            "readout_s": float(self.readout_s), "uncertainty_s": float(self.uncertainty_s),
            "n_frames": int(self.n_frames), "f_led_hz": float(self.f_led_hz),
            "source_clip_sha256": self.source_clip_sha256, "date": self.date,
            "period_rows": float(self.period_rows), "rows": int(self.height),
            "spread_s": float(self.spread_s), "tool": "calibration_rig/fit_readout.py",
        }
        if self.sidecar_skew_s is not None:
            e["sidecar_rolling_shutter_skew_s"] = float(self.sidecar_skew_s)
            e["sidecar_diff_s"] = float(self.sidecar_diff_s)  # readout_s - sidecar skew
        return e


def load_f_led(config_path: Path = ROOT / "config" / "default.yaml") -> float:
    return float(yaml.safe_load(Path(config_path).read_text())["calibration"]["led_frequency_hz"])


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def band_period_rows(gray: np.ndarray, min_period: float = MIN_PERIOD_ROWS,
                     max_period: float | None = None) -> tuple[float, float] | None:
    """Return (P rows, snr) for one frame, or None when no usable peak exists."""
    g = np.asarray(gray, dtype=np.float32)
    n = g.shape[0]
    if n < 16:
        return None
    prof = cv2.reduce(g, 1, cv2.REDUCE_AVG, dtype=cv2.CV_32F).reshape(-1).astype(np.float64)
    x = np.linspace(-1.0, 1.0, n)
    trend = np.polyval(np.polyfit(x, prof, 2), x)
    if np.any(trend <= 1e-6):
        return None
    mod = (prof / trend - 1.0) * np.hanning(n)
    m = cv2.getOptimalDFTSize(PAD_FACTOR * n)
    buf = np.zeros((1, m), np.float32)
    buf[0, :n] = mod
    spec = cv2.dft(buf, flags=cv2.DFT_COMPLEX_OUTPUT)
    mag = cv2.magnitude(spec[0, :, 0], spec[0, :, 1]).reshape(-1).astype(np.float64)
    max_p = max_period if max_period is not None else n / 2.0
    k_lo = max(int(np.ceil(m / max_p)), 1)
    k_hi = min(int(np.floor(m / min_period)), m // 2 - 1)
    if k_hi - k_lo < 3:
        return None
    band = mag[k_lo:k_hi + 1]
    i = int(np.argmax(band))
    k = k_lo + i
    floor = float(np.median(band))
    # a flat (band-free) frame has no modulation at all: reject it instead of dividing 0 by 0
    if band[i] * 2.0 / max(float(np.hanning(n).sum()), 1e-12) < MIN_MODULATION:
        return None
    snr = float(band[i] / floor) if floor > 0 else float("inf")
    if k <= k_lo or k >= k_hi:
        return None
    a, b, c = np.log(mag[k - 1] + 1e-30), np.log(mag[k] + 1e-30), np.log(mag[k + 1] + 1e-30)
    den = a - 2 * b + c
    delta = 0.5 * (a - c) / den if den != 0 else 0.0
    f = (k + float(np.clip(delta, -0.5, 0.5))) / m
    return 1.0 / f, snr


def decode_gray(path: Path) -> tuple[list[np.ndarray], int, int, float]:
    """Frames as float32 in [0, 1], coded orientation (rotation metadata is not applied, like the engine)."""
    frames = []
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        w, h = s.codec_context.width, s.codec_context.height
        fps = float(s.average_rate) if s.average_rate else 0.0
        for fr in c.decode(video=0):
            frames.append(_luma(fr))
    return frames, w, h, fps


_YUV8 = {"yuv420p", "yuvj420p", "yuv422p", "yuvj422p", "yuv444p", "yuvj444p", "nv12", "nv21", "gray"}


def _luma(fr: av.VideoFrame) -> np.ndarray:
    """Luma plane as float32 in [0, 1], read directly from plane 0 (no colour conversion)."""
    name = fr.format.name
    pl = fr.planes[0]
    if name in _YUV8:
        y = np.frombuffer(pl, np.uint8).reshape(-1, pl.line_size)[: fr.height, : fr.width]
        return y.astype(np.float32) / 255.0
    if name.endswith("p10le") and name.startswith("yuv"):
        y = np.frombuffer(pl, np.uint16).reshape(-1, pl.line_size // 2)[: fr.height, : fr.width]
        return y.astype(np.float32) / 1023.0
    return fr.to_ndarray(format="gray").astype(np.float32) / 255.0


def fit_clip(path: Path, device: str, f_led: float, sidecar: Path | None = None,
             fps_override: float | None = None, min_snr: float = MIN_SNR) -> ClipFit:
    frames, w, h, fps = decode_gray(path)
    if fps_override:
        fps = fps_override
    readouts, periods = [], []
    for g in frames:
        r = band_period_rows(g)
        if r is None or r[1] < min_snr:
            continue
        p = r[0]
        periods.append(p)
        readouts.append((h - 1) / (f_led * p))
    n = len(readouts)
    if n < MIN_FRAMES:
        raise CalibrationError(
            f"{path}: only {n} of {len(frames)} frames have clear bands (need {MIN_FRAMES})")
    ro = np.array(readouts, np.float64)
    med = float(np.median(ro))
    mad = float(np.median(np.abs(ro - med)))
    spread = 1.4826 * mad
    fit = ClipFit(device=device, width=w, height=h, fps=fps, key=profile_key(device, w, h, fps),
                  f_led_hz=f_led,
                  readout_s=med, uncertainty_s=1.2533 * spread / np.sqrt(n), spread_s=spread,
                  period_rows=float(np.median(periods)), n_frames=n, frames_total=len(frames),
                  source_clip=str(path), source_clip_sha256=sha256_file(path),
                  date=datetime.now(UTC).date().isoformat())
    if fps > 0 and med > 1.0 / fps:
        raise CalibrationError(f"{path}: readout {med:.6f} s is longer than the frame period "
                               f"{1 / fps:.6f} s; check f_led and the band count (possible aliasing)")
    if sidecar is not None:
        skew_ns = json.loads(Path(sidecar).read_text()).get("rolling_shutter_skew_ns")
        if skew_ns and skew_ns > 0:
            fit.sidecar_skew_s = skew_ns * 1e-9
            fit.sidecar_diff_s = med - fit.sidecar_skew_s
    return fit


def merge_profile(profiles_path: Path, key: str, entry: dict[str, Any]) -> None:
    p = Path(profiles_path)
    text = p.read_text() if p.exists() else ""
    header = [ln for ln in text.splitlines() if ln.startswith("#")]
    if not header:
        header = ["# Readout times per device/mode. Written by calibration_rig/fit_readout.py (needs H3).",
                  '# Key: "<device_model>|<width>x<height>|<fps>"']
    data = (yaml.safe_load(text) if text.strip() else None) or {}
    profiles = data.get("profiles") or {}
    profiles[key] = entry
    data["profiles"] = dict(sorted(profiles.items()))
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text("\n".join(header) + "\n" + yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    os.replace(tmp, p)


def write_result(results_dir: Path, fit: ClipFit) -> Path:
    safe_dev = re.sub(r"[^A-Za-z0-9._-]+", "_", fit.device)
    out = Path(results_dir) / safe_dev / f"{fit.width}x{fit.height}_{round(fit.fps)}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(fit), indent=1))
    return out


def find_clips(root: Path) -> list[tuple[str, Path, re.Match[str] | None]]:
    out = []
    for dev in sorted(p for p in Path(root).iterdir() if p.is_dir()):
        for clip in sorted(dev.iterdir()):
            if clip.suffix.lower() in (".mp4", ".mov"):
                out.append((dev.name, clip, MODE_RE.match(clip.stem)))
    return out


def run_one(clip: Path, device: str, f_led: float, profiles: Path, results: Path | None,
            sidecar: Path | None, mode: re.Match[str] | None, dry_run: bool) -> ClipFit:
    fps_override = None
    fit = fit_clip(clip, device, f_led, sidecar=sidecar)
    if mode is not None:
        mw, mh, mfps = int(mode.group(1)), int(mode.group(2)), float(mode.group(3))
        if {mw, mh} != {fit.width, fit.height}:
            fit.warnings.append(f"mode name {mw}x{mh} does not match coded size {fit.width}x{fit.height}")
        if fit.fps <= 0:
            fps_override = mfps
        elif round(fit.fps) != round(mfps):
            fit.warnings.append(f"mode fps {mfps} does not match stream fps {fit.fps:.3f}")
        if fps_override:
            fit.fps = fps_override
            fit.key = profile_key(device, fit.width, fit.height, fps_override)
    if not dry_run:
        merge_profile(profiles, fit.key, fit.profile_entry())
        if results is not None:
            write_result(results, fit)
    return fit


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip", nargs="?", type=Path)
    ap.add_argument("--device", help="device model string, as the Capture sidecar reports it")
    ap.add_argument("--all", type=Path, help="directory laid out as <dir>/<device>/<W>x<H>_<fps>.mp4")
    ap.add_argument("--sidecar", type=Path, help="JSON with rolling_shutter_skew_ns (single clip)")
    ap.add_argument("--f-led", type=float, default=None, help="default: calibration.led_frequency_hz")
    ap.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    ap.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    ap.add_argument("--dry-run", action="store_true", help="print results, write nothing")
    a = ap.parse_args(argv)
    f_led = a.f_led if a.f_led is not None else load_f_led()
    jobs: list[tuple[str, Path, Path | None, re.Match[str] | None]] = []
    if a.all is not None:
        if not a.all.is_dir():
            print(f"no calibration directory {a.all} (human task H3)", file=sys.stderr)
            return 1
        for dev, clip, mode in find_clips(a.all):
            cands = (clip.with_suffix(".json"), clip.with_suffix(".sidecar.json"))
            sc = next((p for p in cands if p.exists()), None)
            jobs.append((dev, clip, sc, mode))
        if not jobs:
            print(f"no clips found under {a.all} (human task H3)", file=sys.stderr)
            return 1
    else:
        if a.clip is None or not a.device:
            ap.error("give CLIP and --device, or --all DIR")
        jobs.append((a.device, a.clip, a.sidecar, MODE_RE.match(a.clip.stem)))
    failed = 0
    for dev, clip, sc, mode in jobs:
        try:
            fit = run_one(clip, dev, f_led, a.profiles, a.results, sc, mode, a.dry_run)
        except (CalibrationError, av.error.FFmpegError, OSError, ValueError) as e:
            failed += 1
            print(json.dumps({"clip": str(clip), "error": str(e)}))
            continue
        print(json.dumps({"key": fit.key, **fit.profile_entry(), "warnings": fit.warnings}))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
