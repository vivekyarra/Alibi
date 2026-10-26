"""Synthetic rolling-shutter ENF video generator (SPEC 11.1). All output is labeled SYNTHETIC.

Factors: ENF track (real log or random walk), flicker depth, readout time, exposure, frame-timing
jitter, dropped frames, camera motion, moving objects, noise, compression presets, cuts,
insertions, reorders, sensor axis / readout direction, rotation metadata, transfer function.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

import av
import cv2
import numpy as np

from eval.simulator.enf_model import GridSignal, load_track_csv, ou_track

COMPRESSION_PRESETS: dict[str, dict[str, Any]] = {
    "original": {"crf": 10, "preset": "veryfast"},
    "high": {"crf": 18, "preset": "veryfast"},
    "web": {"crf": 26, "preset": "medium"},
    "messaging": {"crf": 32, "preset": "medium"},
}


@dataclass
class SimConfig:
    seed: int = 0
    duration_s: float = 30.0
    fps: float = 30.0
    width: int = 320
    height: int = 240
    readout_s: float = 0.025
    exposure_s: float = 0.001
    zone: str = "SIM50"
    nominal_hz: float = 50.0
    start_utc: float = 1768471200.0  # 2026-01-15T10:00:00Z
    ref_margin_s: int = 3600
    flicker_depth: float = 0.15
    lamp_level: float = 0.55
    daylight_level: float = 0.0
    daylight_region: bool = False  # left part of the scene lit by daylight only (no flicker)
    daylight_region_noise: float = 0.0
    jitter_ms: float = 0.0
    drop_frames: list[tuple[int, int]] = field(default_factory=list)  # (first capture index, count)
    camera_motion_px: float = 0.0
    moving_objects: int = 0
    noise_sigma: float = 0.8  # code values (0..255)
    compression: str = "high"
    sensor_axis: str = "rows"  # "rows" | "cols" (coded frame is the transposed sensor frame)
    readout_reverse: bool = False
    rotation_deg: int = 0
    transfer: str = "bt709"  # "bt709" | "hlg"
    edits: list[dict[str, Any]] = field(default_factory=list)
    enf_csv: str | None = None
    sidecar: bool = False
    clock_ppm: float = 0.0  # camera clock error: PTS = true_time * (1 + ppm*1e-6)


def bt709_oetf(lin: np.ndarray) -> np.ndarray:
    lin = np.clip(lin, 0.0, 1.0)
    return np.where(lin < 0.018, 4.5 * lin, 1.099 * np.power(lin, 0.45) - 0.099)


def hlg_oetf(lin: np.ndarray) -> np.ndarray:
    a, b, c = 0.17883277, 0.28466892, 0.55991073
    lin = np.clip(lin, 0.0, 1.0)
    return np.where(lin <= 1 / 12, np.sqrt(3 * lin), a * np.log(np.maximum(12 * lin - b, 1e-12)) + c)


def _world(rng: np.random.Generator, h: int, w: int) -> np.ndarray:
    """Matte scene albedo in linear light, float32, values ~0.25..0.85."""
    base = np.linspace(0.45, 0.65, w, dtype=np.float32)[None, :].repeat(h, 0)
    noise = rng.normal(0, 1, (h // 8 + 1, w // 8 + 1)).astype(np.float32)
    noise = cv2.resize(noise, (w, h), interpolation=cv2.INTER_CUBIC)
    tex = base + 0.08 * noise
    for _ in range(12):
        cx, cy = rng.uniform(0, w), rng.uniform(0, h)
        r = rng.uniform(0.05, 0.2) * min(h, w)
        val = rng.uniform(-0.15, 0.15)
        yy, xx = np.mgrid[0:h, 0:w]
        tex += val * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * r * r)).astype(np.float32)
    return np.clip(tex, 0.25, 0.85).astype(np.float32)


def _schedule(cfg: SimConfig) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """Return (true capture times rel. to start, written PTS, applied edit events with output indices)."""
    n = int(round(cfg.duration_s * cfg.fps))
    period = 1.0 / cfg.fps
    true_t = np.arange(n, dtype=np.float64) * period
    keep = np.ones(n, bool)
    for first, count in cfg.drop_frames:
        keep[first:first + count] = False
    cap = list(true_t[keep])  # capture times of frames that survive (dropped frames keep their PTS gaps)
    pts = list(true_t[keep])
    events: list[dict[str, Any]] = []
    for e in cfg.edits:
        typ = e["type"]
        if typ == "cut":
            a, d = e["at_s"], e["dur_s"]
            idx = [i for i, t in enumerate(cap) if not (a <= t < a + d)]
            removed = len(cap) - len(idx)
            cap = [cap[i] for i in idx]
            out_idx = next(i for i, t in enumerate(cap) if t >= a)
            pts = [i * period for i in range(len(cap))]  # re-timed: timestamps look continuous
            events.append({"type": "cut", "at_s": a, "dur_s": d, "frames_removed": removed,
                           "output_frame": out_idx, "output_t_s": pts[out_idx]})
        elif typ == "insert":
            a, d, src = e["at_s"], e["dur_s"], e["from_offset_s"]
            pos = next(i for i, t in enumerate(cap) if t >= a)
            ins = [src + a + j * period for j in range(int(round(d * cfg.fps)))]
            cap = cap[:pos] + ins + cap[pos:]
            pts = [i * period for i in range(len(cap))]
            events.append({"type": "insert", "at_s": a, "dur_s": d, "from_offset_s": src,
                           "output_frame": pos, "output_end_frame": pos + len(ins), "output_t_s": pts[pos]})
        elif typ == "reorder":
            a, b, d = e["a_s"], e["b_s"], e["dur_s"]
            ia = [i for i, t in enumerate(cap) if a <= t < a + d]
            ib = [i for i, t in enumerate(cap) if b <= t < b + d]
            seq = list(range(len(cap)))
            lo, hi = sorted([(ia[0], ia[-1] + 1), (ib[0], ib[-1] + 1)])
            seq = seq[:lo[0]] + seq[hi[0]:hi[1]] + seq[lo[1]:hi[0]] + seq[lo[0]:lo[1]] + seq[hi[1]:]
            cap = [cap[i] for i in seq]
            pts = [i * period for i in range(len(cap))]
            events.append({"type": "reorder", "a_s": a, "b_s": b, "dur_s": d,
                           "output_frames": [lo[0], hi[0], lo[0] + hi[1] - hi[0], hi[1]]})
        else:
            raise ValueError(f"unknown edit {typ}")
    cap_a = np.array(cap, dtype=np.float64)
    pts_a = np.array(pts, dtype=np.float64) * (1.0 + cfg.clock_ppm * 1e-6)
    if cfg.jitter_ms > 0:
        rng = np.random.default_rng(cfg.seed + 7)
        pts_a = pts_a + rng.normal(0, cfg.jitter_ms * 1e-3, len(pts_a))
        pts_a = np.maximum.accumulate(pts_a + np.arange(len(pts_a)) * 1e-6)
    return cap_a, pts_a, events


def simulate(cfg: SimConfig, out_dir: Path, name: str) -> dict[str, Any]:
    """Render one clip. Writes <name>.mp4, <name>.truth.json, optional <name>.sidecar.json and the
    reference log under out_dir/gridlog. Returns the ground-truth dict."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(cfg.seed)
    cap_t, pts, events = _schedule(cfg)

    # ---- grid signal covering the clip, insert sources and the reference margin
    span0 = int(np.floor(cfg.start_utc)) - cfg.ref_margin_s
    span_n = int(cfg.duration_s) + 2 * cfg.ref_margin_s + 4
    if cfg.enf_csv:
        knots = load_track_csv(Path(cfg.enf_csv), span0, span_n)
    else:
        knots = ou_track(span_n, cfg.nominal_hz, np.random.default_rng(cfg.seed + 1000))
    grid = GridSignal(span0, knots)

    # ---- scene in sensor coordinates
    hs, ws = (cfg.height, cfg.width) if cfg.sensor_axis == "rows" else (cfg.width, cfg.height)
    margin = int(np.ceil(cfg.camera_motion_px)) + 4
    world = _world(rng, hs + 2 * margin, ws + 2 * margin)
    lamp_w = np.ones((hs, ws), np.float32)
    day_w = np.full((hs, ws), cfg.daylight_level, np.float32)
    if cfg.daylight_region:
        cut = int(0.45 * ws)
        lamp_w[:, :cut] = 0.0
        day_w[:, :cut] = cfg.lamp_level * 1.1
    objs = [
        {"x": rng.uniform(0, ws), "y": rng.uniform(0, hs), "vx": rng.uniform(-3, 3), "vy": rng.uniform(-1, 1),
         "w": rng.uniform(0.1, 0.2) * ws, "h": rng.uniform(0.2, 0.4) * hs, "a": rng.uniform(0.2, 0.8)}
        for _ in range(cfg.moving_objects)
    ]

    n_rows = hs
    row_off = np.arange(n_rows, dtype=np.float64) * cfg.readout_s / (n_rows - 1)
    if cfg.readout_reverse:
        row_off = row_off[::-1]
    f_fl = 2.0 * cfg.nominal_hz
    expo_gain = float(np.sinc(f_fl * cfg.exposure_s))  # np.sinc(x) = sin(pi x)/(pi x)
    oetf = hlg_oetf if cfg.transfer == "hlg" else bt709_oetf

    path = out_dir / f"{name}.mp4"
    tmp = out_dir / f"{name}.tmp.mp4"
    preset = COMPRESSION_PRESETS[cfg.compression]
    cont = av.open(str(tmp), "w")
    st = cont.add_stream("libx264", rate=int(round(cfg.fps)))
    ch, cw = (hs, ws) if cfg.sensor_axis == "rows" else (ws, hs)
    st.width, st.height = cw, ch
    st.pix_fmt = "yuv420p"
    st.time_base = Fraction(1, 90000)
    st.codec_context.time_base = st.time_base
    trc = "arib-std-b67" if cfg.transfer == "hlg" else "bt709"
    st.options = {"crf": str(preset["crf"]), "preset": preset["preset"],
                  "x264-params": f"transfer={trc}:colorprim=bt709:colormatrix=bt709"}
    noise_rng = np.random.default_rng(cfg.seed + 99)
    t_abs0 = cfg.start_utc
    for tc, tp in zip(cap_t, pts, strict=True):
        # camera pose
        dx = cfg.camera_motion_px * np.sin(2 * np.pi * tc / 4.0)
        dy = 0.5 * cfg.camera_motion_px * np.sin(2 * np.pi * tc / 5.3)
        m = np.array([[1, 0, margin + dx], [0, 1, margin + dy]], dtype=np.float32)
        alb = cv2.warpAffine(world, m, (ws, hs), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
        for o in objs:
            x = (o["x"] + o["vx"] * tc * cfg.fps) % (ws + o["w"]) - o["w"]
            y = (o["y"] + o["vy"] * tc * cfg.fps) % (hs + o["h"]) - o["h"]
            x0, y0 = int(max(x, 0)), int(max(y, 0))
            x1, y1 = int(min(x + o["w"], ws)), int(min(y + o["h"], hs))
            if x1 > x0 and y1 > y0:
                alb[y0:y1, x0:x1] = o["a"]
        # rolling-shutter illumination per sensor row (exposure-mean of the flicker)
        t_mid = t_abs0 + tc + row_off + cfg.exposure_s / 2
        phase = 2 * np.pi * 2.0 * grid.grid_cycles(t_mid)
        flick = (1.0 + cfg.flicker_depth * expo_gain * np.cos(phase)).astype(np.float32)[:, None]
        lin = alb * (cfg.lamp_level * lamp_w * flick + day_w)
        code = oetf(lin).astype(np.float32) * 255.0
        code += noise_rng.normal(0, cfg.noise_sigma, code.shape).astype(np.float32)
        if cfg.daylight_region and cfg.daylight_region_noise > 0:
            cut = int(0.45 * ws)
            code[:, :cut] += noise_rng.normal(0, cfg.daylight_region_noise, (hs, cut)).astype(np.float32)
        y8 = np.clip(code, 0, 255) / 255.0
        if cfg.sensor_axis == "cols":
            y8 = y8.T
        y = (16 + 219 * y8).round().astype(np.uint8)
        yuv = np.full((ch * 3 // 2, cw), 128, np.uint8)
        yuv[:ch] = y
        fr = av.VideoFrame.from_ndarray(yuv, format="yuv420p")
        fr.pts = int(round(tp * 90000))
        fr.time_base = st.time_base
        for pkt in st.encode(fr):
            cont.mux(pkt)
    for pkt in st.encode():
        cont.mux(pkt)
    cont.close()
    if cfg.rotation_deg:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-display_rotation", str(cfg.rotation_deg),
                        "-i", str(tmp), "-c", "copy", str(path)], check=True)
        tmp.unlink()
    else:
        tmp.replace(path)

    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    # reference log for the whole simulated span
    ref_t, ref_f = grid.reference_log()
    from gridprint_engine.adapters import LocalGridLog

    gl_root = out_dir / "gridlog"
    marker = gl_root / cfg.zone / f".written_{cfg.seed}_{int(cfg.start_utc)}"
    if not marker.exists():
        LocalGridLog(gl_root).write(cfg.zone, ref_t, ref_f, source="simulator", node=f"sim-{cfg.seed}")
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1")
    clip_sec = np.arange(int(cfg.duration_s), dtype=np.int64)
    truth: dict[str, Any] = {
        "label": "SYNTHETIC",
        "name": name,
        "config": asdict(cfg),
        "video": path.name,
        "video_sha256": sha,
        "start_utc": cfg.start_utc,
        "start_iso": datetime.fromtimestamp(cfg.start_utc, tz=UTC).isoformat(),
        "zone": cfg.zone,
        "flicker_hz": 2 * cfg.nominal_hz,
        "readout_s": cfg.readout_s,
        "frame_capture_t_s": cap_t.tolist(),
        "frame_pts_s": pts.tolist(),
        "edits": events,
        "dropped": [list(d) for d in cfg.drop_frames],
        "enf_clip_hz": grid.freq(cfg.start_utc + clip_sec + 0.5).tolist(),
        "gridlog_root": "gridlog",
        "expected_class": _expected_class(cfg, events),
    }
    if cfg.sidecar:
        boot = 123_456_789_000
        side = {
            "app_version": "simulator",
            "device_model": "SIMULATED",
            "sensor_orientation": 0 if cfg.sensor_axis == "rows" else 90,
            "frame_sensor_timestamps_ns": [int(boot + t * 1e9) for t in cap_t],
            "frame_exposure_ns": [int(cfg.exposure_s * 1e9)] * len(cap_t),
            "frame_duration_ns": [int(1e9 / cfg.fps)] * len(cap_t),
            "rolling_shutter_skew_ns": int(cfg.readout_s * 1e9),
            "iso": 800,
            "wall_clock_start_utc": datetime.fromtimestamp(cfg.start_utc, tz=UTC).isoformat(),
            "wall_clock_source": "simulator",
            "sensor_timestamp_wall_offset_ns": int(cfg.start_utc * 1e9) - boot,
            "zone": cfg.zone,
            "video_sha256": sha,
        }
        (out_dir / f"{name}.sidecar.json").write_text(json.dumps(side))
        truth["sidecar"] = f"{name}.sidecar.json"
    (out_dir / f"{name}.truth.json").write_text(json.dumps(truth, indent=1))
    return truth


def _expected_class(cfg: SimConfig, events: list[dict[str, Any]]) -> str:
    if cfg.flicker_depth <= 0 or cfg.lamp_level <= 0:
        return "authentic-without-mains-light"
    if events:
        return "edited"
    return "authentic-with-mains-light"
