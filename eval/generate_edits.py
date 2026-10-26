"""Derived edit sets from real clips (SPEC 11.3): cuts (re-timed), dropped frames (original timestamps kept),
insertions from another recording of the same room, reorders. Re-encodes with libx264 (crf 12) and writes a
ground-truth JSON next to each output. Face composites (H7) and generator videos are added by humans."""

from __future__ import annotations

import argparse
import json
from fractions import Fraction
from pathlib import Path
from typing import Any

import av
import numpy as np


def read_frames(path: Path) -> tuple[list[np.ndarray], list[float], float]:
    with av.open(str(path)) as c:
        tb = float(c.streams.video[0].time_base)
        fr = [(f.pts * tb, f.to_ndarray(format="yuv420p")) for f in c.decode(video=0)]
    fr.sort(key=lambda x: x[0])
    ts = [t for t, _ in fr]
    return [a for _, a in fr], ts, float(np.median(np.diff(ts)))


def write(path: Path, frames: list[np.ndarray], pts: list[float], w: int, h: int) -> None:
    with av.open(str(path), "w") as c:
        st = c.add_stream("libx264", rate=30)
        st.width, st.height, st.pix_fmt = w, h, "yuv420p"
        st.time_base = Fraction(1, 90000)
        st.options = {"crf": "12", "preset": "medium"}
        for a, t in zip(frames, pts, strict=True):
            vf = av.VideoFrame.from_ndarray(a, format="yuv420p")
            vf.pts = int(round(t * 90000))
            vf.time_base = st.time_base
            for p in st.encode(vf):
                c.mux(p)
        for p in st.encode():
            c.mux(p)


def make(src: Path, out: Path, kind: str, at_s: float, dur_s: float, other: Path | None = None,
         b_s: float | None = None) -> dict[str, Any]:
    frames, ts, dt = read_frames(src)
    h, w = frames[0].shape[0] * 2 // 3, frames[0].shape[1]
    rel = [t - ts[0] for t in ts]
    truth: dict[str, Any] = {"source": src.name, "kind": kind, "at_s": at_s, "dur_s": dur_s}
    if kind in ("cut", "dropped"):
        keep = [i for i, t in enumerate(rel) if not (at_s <= t < at_s + dur_s)]
        frames = [frames[i] for i in keep]
        if kind == "cut":  # re-timed so timestamps look continuous (a true edit)
            pts = [i * dt for i in range(len(frames))]
            truth["output_t_s"] = next(pts[j] for j, i in enumerate(keep) if rel[i] >= at_s)
        else:  # original timestamps kept: must NOT be flagged as an edit
            pts = [rel[i] for i in keep]
    elif kind == "insert":
        if other is None:
            raise ValueError("insert needs --other")
        of, _, _ = read_frames(other)
        n = int(round(dur_s / dt))
        pos = next(i for i, t in enumerate(rel) if t >= at_s)
        frames = frames[:pos] + of[:n] + frames[pos:]
        pts = [i * dt for i in range(len(frames))]
        truth.update({"other": other.name, "output_t_s": pos * dt, "output_end_t_s": (pos + n) * dt})
    elif kind == "reorder":
        if b_s is None:
            raise ValueError("reorder needs --b")
        ia = [i for i, t in enumerate(rel) if at_s <= t < at_s + dur_s]
        ib = [i for i, t in enumerate(rel) if b_s <= t < b_s + dur_s]
        (lo0, lo1), (hi0, hi1) = sorted([(ia[0], ia[-1] + 1), (ib[0], ib[-1] + 1)])
        order = [*range(lo0), *range(hi0, hi1), *range(lo1, hi0), *range(lo0, lo1), *range(hi1, len(frames))]
        frames = [frames[i] for i in order]
        pts = [i * dt for i in range(len(frames))]
        truth.update({"b_s": b_s, "output_t_s": lo0 * dt})
    else:
        raise ValueError(kind)
    write(out, frames, pts, w, h)
    out.with_suffix(".truth.json").write_text(json.dumps(truth, indent=1))
    return truth


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--kind", required=True, choices=["cut", "dropped", "insert", "reorder"])
    ap.add_argument("--at", type=float, required=True)
    ap.add_argument("--dur", type=float, required=True)
    ap.add_argument("--other")
    ap.add_argument("--b", type=float)
    a = ap.parse_args()
    print(make(Path(a.src), Path(a.out), a.kind, a.at, a.dur, Path(a.other) if a.other else None, a.b))


if __name__ == "__main__":
    main()
