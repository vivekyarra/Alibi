"""Stage S14 — band overlay (visualization only; SPEC 8.15).

The fractional modulation is band-passed in time at the flicker alias rate, colorized, and blended
over the video. A timeline strip shows the phase residual, edit candidates (red), dropped-frame
gaps (grey) and matched segments (green). The overlay is labeled as not itself evidence.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING

import av
import cv2
import numpy as np

if TYPE_CHECKING:
    from gridprint_engine.pipeline import Job

LABEL = "Visualization of measured flicker. Not itself evidence."
STRIP_H = 44


def alias_rate(flicker_hz: float, fps: float) -> float:
    return abs(flicker_hz - fps * round(flicker_hz / fps))


def bandpass_frame(m: np.ndarray, i: int, center_hz: float, fps: float, taps: int = 9) -> np.ndarray:
    """Temporal band-pass of frame i at center_hz by complex demodulation over `taps` frames.

    y_i = 2·Re( Σ_j h_j · m_j · e^{−iω(j−i)} ), Hann weights h. float32 [h, w]. Streaming: only
    `taps` frames are touched per output frame.
    """
    if center_hz < 0.5:
        return m[i]
    lo, hi = max(0, i - taps // 2), min(m.shape[0], i + taps // 2 + 1)
    j = np.arange(lo, hi)
    h = np.hanning(taps + 2)[1:-1][(j - i) + taps // 2]
    h = h / h.sum()
    w = 2 * np.pi * center_hz / fps
    c = (h * np.cos(w * (j - i))).astype(np.float32)
    # 2·Re(Σ h m e^{-iω(j−i)}) = 2·Σ h cos(ω(j−i)) m
    return (2 * np.tensordot(c, m[lo:hi], axes=(0, 0))).astype(np.float32)


def _strip(job: Job, width: int, t_now: float) -> np.ndarray:
    assert job.timing is not None
    strip = np.full((STRIP_H, width, 3), 32, np.uint8)
    dur = max(float(job.timing.t_s[-1]), 1e-6)

    def x(t: float) -> int:
        return int(np.clip(t / dur * (width - 1), 0, width - 1))

    tr = job.primary_track()
    if tr is not None and tr.id in job.matches:
        ms = job.matches[tr.id][0]
        for sg in ms.segments:
            col = (60, 160, 60) if sg.passes else (60, 60, 60)
            cv2.rectangle(strip, (x(sg.start_s), 2), (x(sg.end_s), 6), col, -1)
    for g in job.timing.gaps:
        cv2.line(strip, (x(g.t_s), 0), (x(g.t_s), STRIP_H - 1), (150, 150, 150), 2)
    if tr is not None and tr.id in job.continuity:
        c = job.continuity[tr.id]
        if len(c.residual_t):
            ys = np.clip(STRIP_H / 2 - c.residual_rad / np.pi * (STRIP_H / 2 - 8), 8, STRIP_H - 2)
            pts = np.stack([[x(float(t)) for t in c.residual_t], ys], 1).astype(np.int32)
            cv2.polylines(strip, [pts], False, (220, 220, 220), 1)
        for e in c.events:
            if e.kind == "EDIT_CANDIDATE":
                cv2.line(strip, (x(e.t_s), 0), (x(e.t_s), STRIP_H - 1), (40, 40, 230), 2)
    cv2.line(strip, (x(t_now), 0), (x(t_now), STRIP_H - 1), (255, 255, 255), 1)
    return strip


def render_overlay(job: Job, out_path: Path, scale: int = 2) -> Path | None:
    stack, mod, tm = job.stack, job.mod, job.timing
    if stack is None or mod is None or tm is None:
        return None
    tr = job.primary_track()
    fps = 1.0 / tm.median_dt_s if tm.median_dt_s > 0 else 30.0
    flick = tr.f0 if tr is not None else 100.0
    alias = alias_rate(flick, fps)
    mm = np.where(mod.ok, mod.m, 0).astype(np.float32)
    k, h, w = mm.shape
    sample = [bandpass_frame(mm, i, alias, fps) for i in np.linspace(0, k - 1, min(k, 20)).astype(int)]
    vals = np.abs(np.stack(sample))
    lim = float(np.percentile(vals[vals > 0], 99)) if (vals > 0).any() else 1.0
    W, H = w * scale, h * scale
    tmp = out_path.with_suffix(".mp4v.mp4")
    vw = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H + STRIP_H))
    for i in range(k):
        g = cv2.cvtColor(stack.gray8[i], cv2.COLOR_GRAY2BGR)
        v = np.clip((bandpass_frame(mm, i, alias, fps) / max(lim, 1e-9)) * 127 + 128, 0, 255).astype(np.uint8)
        col = cv2.applyColorMap(v, cv2.COLORMAP_TWILIGHT_SHIFTED)
        a = (mod.ok[i] * 0.6).astype(np.float32)[..., None]
        fr = (g * (1 - a) + col * a).astype(np.uint8)
        fr = cv2.resize(fr, (W, H), interpolation=cv2.INTER_NEAREST)
        cv2.rectangle(fr, (0, 0), (W, 16), (0, 0, 0), -1)
        cv2.putText(fr, LABEL, (4, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1, cv2.LINE_AA)
        vw.write(np.vstack([fr, _strip(job, W, float(tm.t_s[i]))]))
    vw.release()
    # re-encode to H.264 for browser playback
    with av.open(str(tmp)) as src, av.open(str(out_path), "w") as dst:
        st = dst.add_stream("libx264", rate=Fraction(round(fps * 1000), 1000))
        st.width, st.height, st.pix_fmt = W, H + STRIP_H, "yuv420p"
        st.options = {"crf": "20", "preset": "veryfast"}
        for fr in src.decode(video=0):
            img = fr.to_ndarray(format="bgr24")
            nf = av.VideoFrame.from_ndarray(img, format="bgr24")
            for pkt in st.encode(nf):
                dst.mux(pkt)
        for pkt in st.encode():
            dst.mux(pkt)
    tmp.unlink(missing_ok=True)
    return out_path
