"""Stage S1 — ingest and timing (SPEC 8.2).

Frames are decoded in coded orientation (rotation metadata is recorded, never applied), because
timing depends on sensor rows, not display rows.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import av
import cv2
import numpy as np

from gridprint_engine.color import classify_transfer, inverse_lut, to_linear, valid_mask
from gridprint_engine.schemas import CaptureSidecar, GapEvent


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Probe:
    container: str
    codec: str
    width: int
    height: int
    frame_count: int
    bitrate: int
    avg_fps: float
    duration_s: float
    time_base: str
    transfer_code: int | None
    transfer: str
    transfer_assumed: bool
    hdr: bool
    rotation: int
    pix_fmt: str
    cv_frame_count: int | None = None
    cv_size: tuple[int, int] | None = None

    def bits_per_pixel(self) -> float:
        px = self.width * self.height * max(self.avg_fps, 1e-6)
        return float(self.bitrate) / px if px else 0.0


def probe_video(path: Path) -> Probe:
    path = Path(path)
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        cc = s.codec_context
        first = next(c.decode(video=0))
        trc = first.color_trc if first.color_trc not in (None, 2) else cc.color_trc
        rot = int(getattr(first, "rotation", 0) or 0)
        n = s.frames or 0
        dur = float(s.duration * s.time_base) if s.duration else float(c.duration or 0) / 1e6
        rate = float(s.average_rate) if s.average_rate else 0.0
        bitrate = int(s.bit_rate or c.bit_rate or 0)
        name, assumed = classify_transfer(int(trc) if trc is not None else None)
        pr = Probe(
            container=Path(path).suffix.lower().lstrip("."),
            codec=cc.name,
            width=cc.width,
            height=cc.height,
            frame_count=n,
            bitrate=bitrate,
            avg_fps=rate,
            duration_s=dur,
            time_base=str(s.time_base),
            transfer_code=int(trc) if trc is not None else None,
            transfer=name,
            transfer_assumed=assumed,
            hdr=name in ("pq", "hlg"),
            rotation=rot,
            pix_fmt=str(cc.format.name if cc.format else ""),
        )
    cap = cv2.VideoCapture(str(path))  # SPEC 8.17 S1: OpenCV cross-check of frame count and size
    if cap.isOpened():
        pr.cv_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        pr.cv_size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    cap.release()
    return pr


def read_pts(path: Path) -> np.ndarray:
    """Per-frame presentation timestamps in seconds (float64), decode order sorted by PTS."""
    try:
        with av.open(str(path)) as c:
            s = c.streams.video[0]
            tb = float(s.time_base)
            pts = [f.pts for f in c.decode(video=0)]
        if any(p is None for p in pts):
            raise ValueError("missing pts")
        return np.sort(np.array(pts, dtype=np.float64) * tb)
    except Exception:
        return read_pts_ffprobe(path)


def read_pts_ffprobe(path: Path) -> np.ndarray:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=pts_time",
         "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    frames = json.loads(out).get("frames", [])
    return np.sort(np.array([float(f["pts_time"]) for f in frames if "pts_time" in f], dtype=np.float64))


@dataclass
class Timing:
    t_s: np.ndarray  # first-row exposure start per frame, seconds, float64, relative to t_s[0]
    exposure_s: np.ndarray
    source: str  # "pts" | "sensor"
    jitter_p50_ms: float
    jitter_p95_ms: float
    median_dt_s: float
    gaps: list[GapEvent] = field(default_factory=list)
    wall_start_utc: float | None = None
    assumption: str = ""


def _robust_linear_fit(x: np.ndarray, y: np.ndarray, iters: int = 5) -> tuple[float, float, np.ndarray]:
    keep = np.ones(len(x), bool)
    a = b = 0.0
    for _ in range(iters):
        A = np.stack([np.ones(keep.sum()), x[keep]], 1)
        (a, b), *_ = np.linalg.lstsq(A, y[keep], rcond=None)
        res = y - (a + b * x)
        mad = np.median(np.abs(res[keep] - np.median(res[keep]))) * 1.4826 + 1e-12
        keep = np.abs(res) < 4 * mad
        if keep.sum() < 3:
            keep[:] = True
            break
    return float(a), float(b), y - (a + b * x)


def compute_timing(pts_s: np.ndarray, sidecar: CaptureSidecar | None, gap_factor: float) -> Timing:
    if sidecar is not None and len(sidecar.frame_sensor_timestamps_ns) == len(pts_s):
        ts = np.array(sidecar.frame_sensor_timestamps_ns, dtype=np.float64) * 1e-9
        expo = np.array(sidecar.frame_exposure_ns, dtype=np.float64) * 1e-9
        source = "sensor"
        wall = None
        if sidecar.sensor_timestamp_wall_offset_ns is not None:
            wall = (sidecar.frame_sensor_timestamps_ns[0] + sidecar.sensor_timestamp_wall_offset_ns) * 1e-9
        assumption = "sensor_timestamp_is_first_row_exposure_start"
    else:
        ts = np.asarray(pts_s, dtype=np.float64)
        expo = np.zeros(len(ts), dtype=np.float64)
        source = "pts"
        wall = None
        assumption = "pts_is_first_row_exposure_start"
    t = ts - ts[0]
    dt = np.diff(t)
    med = float(np.median(dt)) if len(dt) else 0.0
    gaps = [GapEvent(frame_index=i + 1, t_s=float(t[i + 1]), size_s=float(d - med))
            for i, d in enumerate(dt) if med > 0 and d > gap_factor * med]
    n_idx = np.round(t / med).astype(np.float64) if med > 0 else np.arange(len(t), dtype=np.float64)
    _, _, res = _robust_linear_fit(n_idx, t)
    ares = np.abs(res) * 1e3
    return Timing(t_s=t, exposure_s=expo, source=source, jitter_p50_ms=float(np.percentile(ares, 50)),
                  jitter_p95_ms=float(np.percentile(ares, 95)), median_dt_s=med, gaps=gaps,
                  wall_start_utc=wall, assumption=assumption)


@dataclass
class FrameStack:
    """Analysis grid of a video in coded orientation.

    lin: float32 [K, h, w] linear luminance (block mean over valid pixels)
    valid: bool [K, h, w] block has ≥ 50 % valid pixels
    sat: float32 [h, w] fraction of saturated pixels over the clip
    gray8: uint8 [K, h, w] block-mean code value (for motion, segmentation, faces, overlay)
    row_index: float64 [h] mean coded row index of each block row (sensor row when axis="rows")
    col_index: float64 [w] mean coded column index of each block column
    """

    lin: np.ndarray
    valid: np.ndarray
    sat: np.ndarray
    gray8: np.ndarray
    row_index: np.ndarray
    col_index: np.ndarray
    n_rows: int
    n_cols: int
    bin_rows: int
    bin_cols: int


_LIMITED_TO_FULL = np.clip(np.round((np.arange(256) - 16) * 255.0 / 219.0), 0, 255).astype(np.uint8)
_PLANAR_8BIT = {"yuv420p", "yuvj420p", "yuv422p", "yuvj422p", "yuv444p", "yuvj444p", "nv12", "nv21"}


def luma_full_range(fr: av.VideoFrame) -> np.ndarray:
    """8-bit full-range luma code values of a decoded frame (uint8 [H, W]).

    Reads the Y plane directly; limited-range (MPEG) luma is mapped to full range with a table.
    Other pixel formats fall back to swscale conversion.
    """
    fmt = fr.format.name
    if fmt in _PLANAR_8BIT:
        pl = fr.planes[0]
        y = np.frombuffer(pl, np.uint8).reshape(-1, pl.line_size)[: fr.height, : fr.width]
        full = fmt.startswith("yuvj") or int(fr.color_range or 0) == 2
        return np.ascontiguousarray(y) if full else _LIMITED_TO_FULL[y]
    return fr.to_ndarray(format="gray")


def decode_frames(path: Path, transfer: str, max_h: int, max_w: int, saturation_cutoff: float,
                  noise_floor: float) -> FrameStack:
    lut = inverse_lut(transfer)
    lin_l: list[np.ndarray] = []
    val_l: list[np.ndarray] = []
    g_l: list[np.ndarray] = []
    sat_acc: np.ndarray | None = None
    order: list[float] = []
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        H, W = s.codec_context.height, s.codec_context.width
        by, bx = int(np.ceil(H / max_h)), int(np.ceil(W / max_w))
        h, w = H // by, W // bx
        hi = int(np.ceil(saturation_cutoff * 255))
        for fr in c.decode(video=0):
            order.append(float(fr.pts or 0))
            g = luma_full_range(fr)[: h * by, : w * bx]
            v = valid_mask(g, saturation_cutoff, noise_floor)
            lin = to_linear(g, lut) * v
            bs = (h, by, w, bx)
            cnt = v.reshape(bs).sum(axis=(1, 3), dtype=np.float32)
            lsum = lin.reshape(bs).sum(axis=(1, 3), dtype=np.float32)
            lin_l.append(np.where(cnt > 0, lsum / np.maximum(cnt, 1), 0).astype(np.float32))
            val_l.append(cnt >= 0.5 * by * bx)
            g_l.append(g.reshape(bs).mean(axis=(1, 3)).astype(np.uint8))
            satb = (g >= hi).reshape(bs).mean(axis=(1, 3), dtype=np.float32)
            sat_acc = satb if sat_acc is None else sat_acc + satb
    idx = np.argsort(np.array(order), kind="stable")  # presentation order
    lin_a = np.stack(lin_l)[idx]
    assert lin_a.dtype == np.float32
    k = len(lin_l)
    if sat_acc is None:
        raise ValueError("video has no decodable frames")
    return FrameStack(
        lin=lin_a, valid=np.stack(val_l)[idx], sat=(sat_acc / max(k, 1)).astype(np.float32),
        gray8=np.stack(g_l)[idx],
        row_index=np.arange(h, dtype=np.float64) * by + (by - 1) / 2.0,
        col_index=np.arange(w, dtype=np.float64) * bx + (bx - 1) / 2.0,
        n_rows=H, n_cols=W, bin_rows=by, bin_cols=bx,
    )


def load_sidecar(path: Path | None, video_sha256: str) -> tuple[CaptureSidecar | None, list[str]]:
    """Load and check a Capture sidecar. Hash mismatch → sidecar rejected with a note (SPEC 8.2.1)."""
    if path is None:
        return None, []
    data: dict[str, Any] = json.loads(Path(path).read_text())
    sc = CaptureSidecar.model_validate(data)
    if sc.video_sha256.lower() != video_sha256.lower():
        return None, ["sidecar rejected: video_sha256 does not match the file"]
    return sc, []
