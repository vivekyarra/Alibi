"""Reproducible generator for the GRIDPRINT submission video (SPEC 14.4, docs/VIDEO_SCRIPT.md, human task H8).

Run from the repository root:

    PYTHONPATH=".;engine" python video/make_video.py            # build (runs missing engine jobs first)
    PYTHONPATH=".;engine" python video/make_video.py --rerun-engine   # re-run all engine jobs

Inputs: video/scenes.yaml, video/assets/* (optional screenshots / team clip), files under results/, docs/diagrams/.
Outputs: results/video/gridprint_submission.mp4, results/video/manifest.json, results/video/build/ (cache).

Rules kept here:
- Every number on screen is read from a file under results/ and shown with its source path. No typed numbers.
- Verdicts on screen are the engine's own output (result JSON written by the engine run), shown verbatim.
- Clips from the simulator carry the on-screen label "SYNTHETIC test clip".
- Missing inputs render a neutral placeholder card and a warning; nothing is invented.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import textwrap
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
VIDEO_DIR = ROOT / "video"
OUT_DIR = ROOT / "results" / "video"
BUILD = OUT_DIR / "build"
RUNS = OUT_DIR / "engine_runs"
OUT_MP4 = OUT_DIR / "gridprint_submission.mp4"
PY = sys.executable

W, H, FPS = 1920, 1080, 30
LIMIT_S = 300.0
TARGET_MAX_S = 290.0  # keep a margin below the 300 s limit
LEAD_S, TAIL_S = 0.5, 0.8
SUB_TOP = 948  # subtitle band starts here; content stays above it

# colors (RGB)
BG = (16, 20, 28)
PANEL = (28, 34, 46)
FG = (236, 239, 244)
MUTED = (150, 160, 178)
ACCENT = (255, 196, 64)
VERDICT_STYLE = {  # text + icon, never color alone
    "VERIFIED": ((46, 160, 90), "\u2714"),
    "CONTRADICTED": ((200, 50, 50), "\u2716"),
    "INCONCLUSIVE": ((120, 128, 140), "?"),
}

FONT_DIR = Path("C:/Windows/Fonts")
WARNINGS: list[str] = []


def warn(msg: str) -> None:
    WARNINGS.append(msg)
    print(f"WARNING: {msg}", flush=True)


def font(size: int, kind: str = "reg") -> ImageFont.FreeTypeFont:
    name = {"reg": "segoeui.ttf", "bold": "segoeuib.ttf", "mono": "consola.ttf", "sym": "seguisym.ttf",
            "light": "segoeuil.ttf"}[kind]
    p = FONT_DIR / name
    if p.exists():
        return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size)


def rel(p: Path | str) -> str:
    p = Path(p)
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


# ----------------------------------------------------------------------------------------------- narration checks
FORBIDDEN_WORD_RE = re.compile(r"\bprov(e|es|ed|ing)\b", re.IGNORECASE)


def lint_narration(scene_id: str, text: str) -> None:
    sys.path.insert(0, str(ROOT))
    from scripts.claims_lint import scan_text  # noqa: PLC0415 - repo script, R5 forbidden claims

    hits = scan_text(text)
    if hits:
        raise SystemExit(f"narration of scene '{scene_id}' has forbidden claims: {hits}")
    if FORBIDDEN_WORD_RE.search(text):
        raise SystemExit(f"narration of scene '{scene_id}' uses 'prove'; say 'checks' instead")


# ----------------------------------------------------------------------------------------------- TTS
PS1 = r"""param([string]$InFile, [string]$OutFile)
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = 0
$text = Get-Content -Raw -Encoding UTF8 -Path $InFile
$s.SetOutputToWaveFile($OutFile)
$s.Speak($text)
$s.Dispose()
"""


def tts(text: str) -> Path:
    """Synthesize text with Windows System.Speech. Cached by text hash."""
    d = BUILD / "tts"
    d.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256(("v1|" + text).encode()).hexdigest()[:16]
    out = d / f"{h}.wav"
    if out.exists() and out.stat().st_size > 1000:
        return out
    ps1 = d / "speak.ps1"
    ps1.write_text(PS1, encoding="utf-8")
    txt = d / f"{h}.txt"
    txt.write_text(text, encoding="utf-8")
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1),
                    "-InFile", str(txt), "-OutFile", str(out)], check=True)
    return out


def read_wav(p: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(p), "rb") as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if sw != 2:
        raise SystemExit(f"unexpected sample width in {p}")
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def resample(a: np.ndarray, sr: int, to: int) -> np.ndarray:
    if sr == to or len(a) == 0:
        return a
    n = int(round(len(a) * to / sr))
    return np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)


# ----------------------------------------------------------------------------------------------- data access
def load_json(p: Path) -> Any | None:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


@dataclass
class Run:
    name: str
    cfg: dict[str, Any]
    meta: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    result_path: Path | None = None
    files: dict[str, Path] = field(default_factory=dict)
    synthetic: bool = False

    @property
    def verdict(self) -> str | None:
        return (self.result or {}).get("verdict")


def ensure_runs(cfg: dict[str, Any], rerun: bool, no_engine: bool = False) -> dict[str, Run]:
    runs: dict[str, Run] = {}
    for name, rc in cfg.items():
        wd = RUNS / name
        meta_p = wd / "run_meta.json"
        if not no_engine and (rerun or not meta_p.exists()):
            print(f"[engine] running {name} on {rc['video']} (this can take several minutes)", flush=True)
            cmd = [PY, str(VIDEO_DIR / "run_engine.py"), name, rc["video"], "--gridlog", rc.get("gridlog", "")]
            if rc.get("sidecar"):
                cmd += ["--sidecar", rc["sidecar"]]
            env = dict(**__import__("os").environ)
            env["PYTHONPATH"] = f"{ROOT};{ROOT / 'engine'}"
            subprocess.run(cmd, cwd=ROOT, env=env, check=False)
        r = Run(name, rc, meta=load_json(meta_p))
        # the engine's own result JSON (S15 write_json) wherever it put it; fall back to our dump of job.result
        cands = [p for p in wd.rglob("result.json")] + [wd / "video_result.json"]
        for p in cands:
            j = load_json(p)
            if j and "verdict" in j:
                r.result, r.result_path = j, p
                break
        for pat in ["overlay.mp4", "enf_track.png", "phase_residual.png", "ncc_scan.png", "band_amplitude.png",
                    "plots.json", "report.html"]:
            hits = sorted(wd.rglob(pat))
            if hits:
                r.files[pat] = hits[0]
        truth = load_json(Path(rc["truth"])) if rc.get("truth") else None
        r.synthetic = bool(truth and truth.get("label") == "SYNTHETIC")
        if r.result is None:
            err = (r.meta or {}).get("error", "no result file")
            warn(f"engine run '{name}' has no result ({err}); scene shows a pending card")
        runs[name] = r
    return runs


def find_agent_trace() -> tuple[dict[str, Any] | None, Path | None]:
    """Prefer results/agent_traces/*.json; else an agent trace written by the eval harness (planner field set)."""
    cands = sorted((ROOT / "results" / "agent_traces").glob("*.json")) if (ROOT / "results" / "agent_traces").exists() else []
    best: tuple[int, dict[str, Any] | None, Path | None] = (-1, None, None)
    pool = cands or sorted((ROOT / "results" / "eval").glob("**/trace.json"))
    for p in pool:
        t = load_json(p)
        if not t or not isinstance(t.get("steps"), list) or not t["steps"]:
            continue
        if not any(s.get("planner") for s in t["steps"]):
            continue  # not an agent trace (plain run_default trace)
        score = 1 + (10 if trace_kind(t) == "recovery" else 0) + (5 if p in cands else 0)
        if score > best[0]:
            best = (score, t, p)
    if best[1] is None:
        warn("no agent trace found under results/; trace scene shows 'Agent trace: see results'")
    return best[1], best[2]


def _snr(step: dict[str, Any]) -> float | None:
    try:
        return float(json.loads(step.get("output_summary") or "{}").get("band_snr_db"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def trace_kind(t: dict[str, Any] | None) -> str:
    if not t:
        return "none"
    ex = [s for s in t["steps"] if s.get("tool") == "extract_flicker" and _snr(s) is not None]
    if len(ex) >= 2 and _snr(ex[-1]) > _snr(ex[0]):  # type: ignore[operator]
        # recovery only if the later extraction was followed by matching (signal usable)
        tools = [s.get("tool") for s in t["steps"]]
        if "match_reference" in tools:
            return "recovery"
    return "plain"


def collect_results() -> dict[str, list[tuple[Path, Any]]]:
    out: dict[str, list[tuple[Path, Any]]] = {"eval": [], "bench_summary": [], "bench_cost": [], "bench_parity": []}
    for p in sorted((ROOT / "results" / "eval").glob("**/summary.json")):
        if "work" in p.parts:
            continue
        out["eval"].append((p, load_json(p)))
    for key, nm in [("bench_summary", "summary.json"), ("bench_cost", "cost.json"), ("bench_parity", "parity.json")]:
        for p in sorted((ROOT / "results" / "bench").glob(f"**/{nm}")):
            if "work" in p.parts:
                continue
            out[key].append((p, load_json(p)))
    if not out["eval"]:
        warn("results/eval/**/summary.json not found: evaluation results shown as 'Results pending'")
    if not out["bench_cost"]:
        warn("results/bench/**/cost.json not found: cost shown as 'Results pending'")
    if not out["bench_parity"]:
        warn("results/bench/**/parity.json not found: parity shown as 'Results pending'")
    return out


def svg_to_png(svg: Path, override: Path) -> Path | None:
    """Rasterize a diagram SVG. Order: supplied PNG override, cairosvg, headless Edge/Chrome screenshot."""
    if override.exists():
        return override
    out = BUILD / (svg.stem + ".png")
    if out.exists() and out.stat().st_mtime >= svg.stat().st_mtime:
        return out
    BUILD.mkdir(parents=True, exist_ok=True)
    m = re.search(r'viewBox="([\d.\s-]+)"', svg.read_text(encoding="utf-8", errors="ignore")[:4000])
    vw, vh = (float(v) for v in m.group(1).split()[2:4]) if m else (1600.0, 1000.0)
    try:
        import cairosvg  # type: ignore[import-not-found]  # noqa: PLC0415

        cairosvg.svg2png(url=str(svg), write_to=str(out), output_width=int(min(3200, vw)))
        return out
    except Exception:  # noqa: BLE001 - optional dependency; fall through to the browser
        pass
    width = 2600
    height = int(math.ceil(width * vh / vw))
    html = BUILD / (svg.stem + "_wrap.html")
    html.write_text(f"<!doctype html><html><body style='margin:0;background:#fff'>"
                    f"<img src='{svg.resolve().as_uri()}' style='width:{width}px;height:{height}px;display:block'>"
                    f"</body></html>", encoding="utf-8")
    for exe in [Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
                Path("C:/Program Files/Google/Chrome/Application/chrome.exe")]:
        if not exe.exists():
            continue
        subprocess.run([str(exe), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
                        "--force-device-scale-factor=1", f"--window-size={width},{height}",
                        f"--screenshot={out}", html.resolve().as_uri()],
                       capture_output=True, timeout=120, check=False)
        if out.exists() and out.stat().st_size > 10000:
            return out
    needs = VIDEO_DIR / "NEEDS.md"
    needs.write_text(f"# Needed for the video\n\n- PNG export of `{rel(svg)}` at `{rel(override)}` "
                     "(SVG conversion failed: no cairosvg and no headless browser).\n", encoding="utf-8")
    warn(f"could not convert {rel(svg)}; see video/NEEDS.md")
    return None


# ----------------------------------------------------------------------------------------------- drawing helpers
def canvas() -> Image.Image:
    return Image.new("RGB", (W, H), BG)


def wrap_px(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if draw.textlength(t, font=f) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def heading(img: Image.Image, text: str, sub: str | None = None) -> None:
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 6], fill=ACCENT)
    d.text((60, 34), text, font=font(50, "bold"), fill=FG)
    if sub:
        d.text((62, 98), sub, font=font(26), fill=MUTED)
    d.text((W - 60, 44), "GRIDPRINT", font=font(30, "bold"), fill=MUTED, anchor="ra")


def tag(img: Image.Image, xy: tuple[int, int], text: str, fill: tuple[int, int, int] = ACCENT,
        fg: tuple[int, int, int] = (20, 20, 20), size: int = 26) -> int:
    d = ImageDraw.Draw(img)
    f = font(size, "bold")
    tw = int(d.textlength(text, font=f))
    x, y = xy
    d.rounded_rectangle([x, y, x + tw + 28, y + size + 18], radius=8, fill=fill)
    d.text((x + 14, y + 6), text, font=f, fill=fg)
    return x + tw + 28


def source_line(img: Image.Image, text: str, y: int = SUB_TOP - 40) -> None:
    ImageDraw.Draw(img).text((60, y), text, font=font(22, "mono"), fill=MUTED)


def paste_fit(img: Image.Image, src: Image.Image, box: tuple[int, int, int, int], bg: tuple[int, int, int] | None = None) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    s = min(bw / src.width, bh / src.height)
    nw, nh = max(1, int(src.width * s)), max(1, int(src.height * s))
    r = src.resize((nw, nh), Image.LANCZOS)
    if bg is not None:
        ImageDraw.Draw(img).rectangle(box, fill=bg)
    px, py = x0 + (bw - nw) // 2, y0 + (bh - nh) // 2
    img.paste(r, (px, py))
    return px, py, px + nw, py + nh


def placeholder(img: Image.Image, box: tuple[int, int, int, int], title: str, sub: str = "") -> None:
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box, radius=18, fill=PANEL, outline=(70, 80, 98), width=3)
    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    d.text((cx, cy - 20), title, font=font(48, "bold"), fill=MUTED, anchor="mm")
    if sub:
        for i, ln in enumerate(wrap_px(d, sub, font(26), box[2] - box[0] - 80)):
            d.text((cx, cy + 36 + i * 34), ln, font=font(26), fill=MUTED, anchor="mm")


def fmt(v: Any, nd: int = 3) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.{nd}g}" if abs(v) < 1e-3 or abs(v) >= 1e5 else f"{v:.{nd}f}".rstrip("0").rstrip(".")
    return str(v)


def verdict_card(img: Image.Image, box: tuple[int, int, int, int], run: Run, label: str) -> None:
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    d.rounded_rectangle(box, radius=18, fill=PANEL)
    res = run.result
    if res is None:
        placeholder(img, box, "Engine run pending", f"No result file under {rel(RUNS / run.name)} yet.")
        return
    v = res["verdict"]
    col, icon = VERDICT_STYLE.get(v, ((120, 120, 120), "?"))
    d.rounded_rectangle([x0, y0, x1, y0 + 120], radius=18, fill=col)
    d.rectangle([x0, y0 + 100, x1, y0 + 120], fill=col)
    d.text((x0 + 34, y0 + 60), icon, font=font(70, "sym"), fill=(255, 255, 255), anchor="lm")
    d.text((x0 + 120, y0 + 60), v, font=font(58, "bold"), fill=(255, 255, 255), anchor="lm")
    y = y0 + 140
    rows = [("State", res.get("lifecycle_state"))]
    if v == "CONTRADICTED":
        rows.append(("Review", "a person must approve before FINAL"))
    if res.get("time_estimate_iso"):
        rows.append(("Time (UTC)", str(res["time_estimate_iso"]).replace("T", " ").replace("+00:00", "")))
    if res.get("time_uncertainty_s") is not None:
        rows.append(("Uncertainty", f"± {fmt(res['time_uncertainty_s'])} s"))
    if res.get("zone"):
        rows.append(("Grid zone", res["zone"]))
    q = res.get("quality") or {}
    if q.get("band_snr_db") is not None:
        rows.append(("Band SNR", f"{fmt(q['band_snr_db'])} dB"))
    ev = [e for e in res.get("continuity_events") or [] if e.get("kind") == "EDIT_CANDIDATE"]
    if ev:
        rows.append(("Edit marks", ", ".join(f"t = {fmt(e['t_s'])} s" for e in ev[:3])))
    fk, fv = font(26), font(26, "bold")
    for k, val in rows:
        d.text((x0 + 30, y), k, font=fk, fill=MUTED)
        for i, ln in enumerate(wrap_px(d, str(val), fv, x1 - x0 - 260)):
            d.text((x0 + 230, y + i * 32), ln, font=fv, fill=FG)
            y += 32 if i else 0
        y += 42
    reasons = res.get("reasons") or []
    if reasons:
        d.text((x0 + 30, y), "Reasons", font=fk, fill=MUTED)
        y += 38
        for r in reasons[:6]:
            d.text((x0 + 46, y), str(r), font=font(24, "mono"), fill=FG)
            y += 32
    tx = x0 + 30
    tag(img, (tx, y1 - 64), label, fill=ACCENT if "SYNTHETIC" in label else (90, 140, 220),
        fg=(20, 20, 20) if "SYNTHETIC" in label else (255, 255, 255), size=24)


# ----------------------------------------------------------------------------------------------- video readers
class Clip:
    def __init__(self, path: Path):
        self.cap = cv2.VideoCapture(str(path))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.n = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.pos = -1
        self.last: np.ndarray | None = None

    def frame_at(self, t: float) -> Image.Image | None:
        if self.n <= 0:
            return None
        idx = int(t * self.fps) % self.n
        if idx != self.pos + 1:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        if idx != self.pos or self.last is None:
            ok, f = self.cap.read()
            if not ok:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, f = self.cap.read()
                if not ok:
                    return None if self.last is None else Image.fromarray(self.last)
            self.last = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
            self.pos = idx
        return Image.fromarray(self.last)


# ----------------------------------------------------------------------------------------------- scene renderers
class Scene:
    def __init__(self, spec: dict[str, Any], ctx: dict[str, Any]):
        self.spec, self.ctx, self.v = spec, ctx, spec["visual"]
        self.sources: list[str] = []
        self.pending: list[str] = []
        self._static: Image.Image | None = None
        self.duration = 0.0
        self.audio_override: Path | None = None
        self.prepare()

    def prepare(self) -> None:  # noqa: B027 - optional hook
        pass

    def static(self) -> Image.Image:
        raise NotImplementedError

    def frame(self, t: float) -> Image.Image:
        if self._static is None:
            self._static = self.static()
        return self._static.copy()


class TitleScene(Scene):
    def static(self) -> Image.Image:
        img = canvas()
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 6], fill=ACCENT)
        d.text((W // 2, 300), self.v["title"], font=font(150, "bold"), fill=FG, anchor="mm")
        y = 470
        for ln in self.v.get("lines", []):
            for sub in wrap_px(d, ln, font(54), 1500):
                d.text((W // 2, y), sub, font=font(54), fill=FG, anchor="mm")
                y += 74
            y += 10
        if self.v.get("footer"):
            d.text((W // 2, SUB_TOP - 60), self.v["footer"], font=font(30), fill=MUTED, anchor="mm")
        return img


class PublicClipScene(Scene):
    def prepare(self) -> None:
        self.path = Path(self.ctx["cfg"]["engine_runs"]["public_fluorescent"]["video"])
        self.clip = Clip(self.path) if self.path.exists() else None
        self.sources.append(self.path.as_posix())
        if self.clip is None:
            self.pending.append(f"public clip missing: {self.path}")

    def static(self) -> Image.Image:
        img = canvas()
        heading(img, self.v["heading"])
        d = ImageDraw.Draw(img)
        y = 200
        for b in self.v.get("bullets", []):
            lines = wrap_px(d, b, font(34), 640)
            d.text((1220, y), "\u2022", font=font(34), fill=ACCENT)
            for i, ln in enumerate(lines):
                d.text((1250, y + i * 46), ln, font=font(34), fill=FG)
            y += 46 * len(lines) + 28
        d.text((60, SUB_TOP - 46), self.ctx["cfg"]["credit_public"], font=font(26), fill=FG)
        return img

    def frame(self, t: float) -> Image.Image:
        img = super().frame(t)
        box = (60, 150, 1180, 150 + 840)
        if self.clip is None:
            placeholder(img, box, "Public clip missing")
            return img
        f = self.clip.frame_at(t)
        if f is not None:
            paste_fit(img, f, (60, 150, 1180, SUB_TOP - 60))
        return img


class EngineRunScene(Scene):
    def prepare(self) -> None:
        self.run: Run = self.ctx["runs"][self.v["run"]]
        self.ov = self.run.files.get("overlay.mp4")
        self.clip = Clip(self.ov) if self.ov else None
        if self.run.result_path:
            self.sources.append(rel(self.run.result_path))
        if self.ov:
            self.sources.append(rel(self.ov))
        else:
            self.pending.append(f"overlay.mp4 for run {self.run.name}")
        if self.run.result is None:
            self.pending.append(f"engine result for run {self.run.name}")
        self.t0 = 0.0
        if self.v.get("seek") == "continuity" and self.run.result:
            ev = [e for e in self.run.result.get("continuity_events") or [] if e.get("kind") == "EDIT_CANDIDATE"]
            if ev:
                self.t0 = max(0.0, float(ev[0]["t_s"]) - 6.0)
        self.side = self.run.files.get(self.v.get("side_plot", "")) if self.v.get("side_plot") else None
        if self.side:
            self.sources.append(rel(self.side))
        if self.run.name == "public_fluorescent":
            self.label = "Public clip: Wikimedia Commons, CC BY-SA 3.0"
        elif self.run.synthetic:
            self.label = "SYNTHETIC test clip"
        else:
            self.label = "Clip source: " + Path(self.run.cfg["video"]).name

    def static(self) -> Image.Image:
        img = canvas()
        heading(img, self.v["heading"], f"Input: {Path(self.run.cfg['video']).name}"
                + ("  ·  sidecar" if self.run.cfg.get("sidecar") else "  ·  no sidecar"))
        verdict_card(img, (1240, 150, 1860, SUB_TOP - 60), self.run, self.label)
        if self.run.result_path:
            source_line(img, "source: " + rel(self.run.result_path), y=SUB_TOP - 46)
        if self.side:
            p = Image.open(self.side).convert("RGB")
            paste_fit(img, p, (60, 716, 1200, SUB_TOP - 56), bg=(255, 255, 255))
        return img

    def frame(self, t: float) -> Image.Image:
        img = super().frame(t)
        vbox_bottom = 680 if self.side else SUB_TOP - 120
        box = (60, 150, 1200, vbox_bottom)
        f = self.clip.frame_at(self.t0 + t) if self.clip else None
        if f is None:
            placeholder(img, box, "Overlay pending", "The engine has not produced overlay.mp4 for this run.")
            return img
        x0, y0, x1, y1 = paste_fit(img, f, box)
        d = ImageDraw.Draw(img)
        d.rectangle([x0, y1 - 40, x1, y1], fill=(0, 0, 0))
        d.text(((x0 + x1) // 2, y1 - 20), "Visualization of measured flicker. Not itself evidence.",
               font=font(24), fill=(255, 255, 255), anchor="mm")
        if self.run.synthetic:
            tag(img, (x0 + 14, y0 + 14), "SYNTHETIC test clip", size=24)
        if self.clip and self.clip.n:
            vt = ((self.t0 + t) * self.clip.fps % self.clip.n) / self.clip.fps
            d.text((x0, y1 + 8), f"overlay.mp4  t = {vt:5.1f} s", font=font(20, "mono"), fill=MUTED)
        return img


class PlotsScene(Scene):
    def prepare(self) -> None:
        self.run: Run = self.ctx["runs"][self.v["run"]]
        self.paths = [self.run.files.get(f) for f in self.v["files"]]
        pj = load_json(self.run.files["plots.json"]) if "plots.json" in self.run.files else None
        self.caps: dict[str, str] = {}
        if isinstance(pj, list):
            self.caps = {p.get("file"): p.get("caption", "") for p in pj if isinstance(p, dict)}
        elif isinstance(pj, dict):
            for p in pj.get("plots", []):
                self.caps[p.get("file")] = p.get("caption", "")
        for f, p in zip(self.v["files"], self.paths, strict=True):
            if p:
                self.sources.append(rel(p))
            else:
                self.pending.append(f"{f} for run {self.run.name}")

    def static(self) -> Image.Image:
        img = canvas()
        heading(img, self.v["heading"], ("SYNTHETIC test clip  ·  " if self.run.synthetic else "")
                + Path(self.run.cfg["video"]).name)
        n = len(self.paths)
        top, bottom = 150, SUB_TOP - 60
        hh = (bottom - top) // n
        d = ImageDraw.Draw(img)
        for i, (f, p) in enumerate(zip(self.v["files"], self.paths, strict=True)):
            box = (60, top + i * hh + 4, 1440, top + (i + 1) * hh - 8)
            if p is None:
                placeholder(img, box, f"{f}: pending")
                continue
            paste_fit(img, Image.open(p).convert("RGB"), box, bg=(255, 255, 255))
            cap = self.caps.get(f, "")
            yy = box[1] + 10
            for ln in wrap_px(d, cap, font(28), 400):
                d.text((1470, yy), ln, font=font(28), fill=FG)
                yy += 38
            d.text((1470, yy + 10), rel(p), font=font(18, "mono"), fill=MUTED)
        if self.run.synthetic:
            tag(img, (1470, bottom - 50), "SYNTHETIC test clip", size=24)
        return img


class UIScene(Scene):
    def prepare(self) -> None:
        self.shots = []
        for s in self.v["shots"]:
            p = ROOT / s["file"]
            if p.exists():
                self.shots.append((s["caption"], Image.open(p).convert("RGB"), p))
                self.sources.append(rel(p))
            else:
                self.shots.append((s["caption"], None, p))
                self.pending.append(f"UI screenshot {s['file']}")
                warn(f"UI screenshot missing: {s['file']} (neutral card shown)")
        self._cache: dict[int, Image.Image] = {}

    def frame(self, t: float) -> Image.Image:
        i = min(len(self.shots) - 1, int(t / max(self.duration, 1e-6) * len(self.shots)))
        if i not in self._cache:
            cap, im, p = self.shots[i]
            img = canvas()
            heading(img, "Verify web app", f"{cap}  ({i + 1}/{len(self.shots)})")
            box = (60, 150, W - 60, SUB_TOP - 60)
            if im is None:
                placeholder(img, box, "UI screenshot", f"{cap}: screenshot to be supplied at {rel(p)}")
            else:
                paste_fit(img, im, box)
            self._cache[i] = img
        return self._cache[i].copy()


class ImageScene(Scene):
    def prepare(self) -> None:
        svg = ROOT / self.v["svg"]
        self.png = svg_to_png(svg, ROOT / self.v["override_png"])
        self.im = Image.open(self.png).convert("RGB") if self.png else None
        if self.png:
            self.sources.append(rel(svg))
        else:
            self.pending.append(f"PNG of {self.v['svg']}")
        self.box = (60, 140, W - 60, SUB_TOP - 20)
        self.base = canvas()
        heading(self.base, self.v["heading"], rel(svg))
        if self.im is not None and self.v.get("pan") == "vertical":
            bw = self.box[2] - self.box[0]
            s = bw / self.im.width
            self.scaled = self.im.resize((bw, int(self.im.height * s)), Image.LANCZOS)
        else:
            self.scaled = None

    def frame(self, t: float) -> Image.Image:
        img = self.base.copy()
        if self.im is None:
            placeholder(img, self.box, "Diagram pending", "See video/NEEDS.md")
            return img
        bh = self.box[3] - self.box[1]
        if self.scaled is not None and self.scaled.height > bh:
            # hold, pan top -> bottom, hold
            u = min(1.0, max(0.0, (t - 1.5) / max(self.duration - 3.0, 1.0)))
            u = 0.5 - 0.5 * math.cos(math.pi * u)
            y = int(u * (self.scaled.height - bh))
            ImageDraw.Draw(img).rectangle(self.box, fill=(255, 255, 255))
            img.paste(self.scaled.crop((0, y, self.scaled.width, y + bh)), (self.box[0], self.box[1]))
            return img
        if self._static is None:
            paste_fit(img, self.im, self.box, bg=(255, 255, 255))
            self._static = img
        return self._static.copy()


class TraceScene(Scene):
    ROW_H = 46

    def prepare(self) -> None:
        self.trace, self.path = self.ctx["trace"], self.ctx["trace_path"]
        if self.path:
            self.sources.append(rel(self.path))
        else:
            self.pending.append("agent trace JSON under results/agent_traces/")
        self.base = canvas()
        planner = ""
        if self.trace:
            pl = sorted({s.get("planner") for s in self.trace["steps"] if s.get("planner")})
            planner = "planner: " + ", ".join(pl)
        synth = self.path is not None and "synthetic" in rel(self.path)
        heading(self.base, self.v["heading"], (f"job {self.trace.get('job_id')}  ·  {planner}" if self.trace else ""))
        if synth:
            tag(self.base, (W - 380, 100), "SYNTHETIC test clip", size=22)
        if self.path:
            source_line(self.base, "source: " + rel(self.path), y=SUB_TOP - 40)
        self.table: Image.Image | None = None
        if self.trace:
            rows = []
            for s in self.trace["steps"]:
                out = s.get("output_summary") or ""
                snr = _snr(s)
                extra = f"band SNR {fmt(snr)} dB" if snr is not None else ""
                if s.get("tool") == "compute_verdict":
                    try:
                        extra = "verdict " + str(json.loads(out).get("verdict"))
                    except json.JSONDecodeError:
                        pass
                rows.append((str(s.get("index")), str(s.get("tool")), str(s.get("decision_reason") or ""),
                             extra, s.get("policy_note") or ""))
            th = self.ROW_H * (len(rows) + 1) + 20
            tab = Image.new("RGB", (W - 120, th), PANEL)
            d = ImageDraw.Draw(tab)
            cols = [20, 110, 470, 1420]
            for c, hname in zip(cols, ["step", "tool", "decision reason", "measured output"], strict=True):
                d.text((c, 10), hname, font=font(26, "bold"), fill=ACCENT)
            for i, (idx, tool, reason, extra, pol) in enumerate(rows):
                y = 10 + self.ROW_H * (i + 1)
                hl = reason.startswith("B") and ":" in reason[:4]
                if hl:
                    d.rectangle([0, y - 4, tab.width, y + self.ROW_H - 6], fill=(60, 52, 24))
                ym = y + (self.ROW_H - 10) // 2
                d.text((cols[0], ym), idx, font=font(24, "mono"), fill=FG, anchor="lm")
                d.text((cols[1], ym), tool, font=font(24, "mono"), fill=FG, anchor="lm")
                r = reason if not pol else f"{reason} [policy: {pol}]"
                r = r if d.textlength(r, font=font(24)) < 920 else r[:78] + "…"
                d.text((cols[2], ym), r, font=font(24), fill=FG, anchor="lm")
                d.text((cols[3], ym), extra, font=font(24, "mono"), fill=FG, anchor="lm")
            self.table = tab

    def frame(self, t: float) -> Image.Image:
        img = self.base.copy()
        box = (60, 150, W - 60, SUB_TOP - 60)
        if self.table is None:
            placeholder(img, box, "Agent trace: see results", "No agent trace file under results/ yet.")
            return img
        bh = box[3] - box[1]
        if self.table.height <= bh:
            img.paste(self.table, (box[0], box[1]))
        else:
            u = min(1.0, max(0.0, (t - 2.0) / max(self.duration - 4.0, 1.0)))
            y = int(u * (self.table.height - bh))
            img.paste(self.table.crop((0, y, self.table.width, y + bh)), (box[0], box[1]))
        return img


class ResultsScene(Scene):
    def prepare(self) -> None:
        self.res = self.ctx["results"]

    def static(self) -> Image.Image:
        img = canvas()
        heading(img, self.v["heading"], "Values read from files under results/  ·  each line shows its source")
        d = ImageDraw.Draw(img)
        x, y = 60, 160
        f_h, f_r, f_s = font(32, "bold"), font(28), font(20, "mono")

        def section(title: str) -> None:
            nonlocal y
            d.text((x, y), title, font=f_h, fill=ACCENT)
            y += 50

        def line(k: str, v: str, src: str) -> None:
            nonlocal y
            d.text((x + 20, y), k, font=f_r, fill=MUTED)
            d.text((x + 640, y), v, font=font(28, "bold"), fill=FG)
            d.text((x + 1100, y + 6), src, font=f_s, fill=MUTED)
            y += 42

        section("Evaluation (results/eval/**/summary.json)")
        if not self.res["eval"]:
            line("Evaluation summary", "Results pending", "no summary.json yet")
            self.pending.append("results/eval/<date>/summary.json")
        for p, j in self.res["eval"][:1]:
            self.sources.append(rel(p))
            keys = ["false_contradicted_rate", "verified_coverage_capture", "inconclusive_rate_stock"]
            shown = 0
            for k in keys:
                if isinstance(j, dict) and k in j:
                    line(k, fmt(j[k]), f"{rel(p)}#{k}")
                    shown += 1
            if not shown and isinstance(j, dict):
                for k, val in list(j.items())[:6]:
                    if isinstance(val, (int, float, str)):
                        line(k, fmt(val), f"{rel(p)}#{k}")
            if isinstance(j, dict) and j.get("label"):
                line("label", str(j["label"]), f"{rel(p)}#label")
        y += 20
        section("Benchmark (results/bench/**/summary.json, cost.json, parity.json)")
        if not self.res["bench_summary"]:
            line("Benchmark summary", "Results pending", "no summary.json yet")
            self.pending.append("results/bench/<date>/summary.json")
        for p, j in self.res["bench_summary"][:3]:
            if not isinstance(j, dict):
                continue
            self.sources.append(rel(p))
            cfg = j.get("config", p.parent.name)
            line(f"config '{cfg}': machine", f"{j.get('machine')} · OpenCV {j.get('opencv_version')}", f"{rel(p)}#machine")
            tp = (j.get("throughput_video_s_per_wall_s") or {}).get("mean")
            if tp is not None:
                line(f"config '{cfg}': throughput", f"{fmt(tp)} video s / wall s",
                     f"{rel(p)}#throughput_video_s_per_wall_s.mean")
            if j.get("runs") is not None:
                line(f"config '{cfg}': runs", fmt(j.get("runs")), f"{rel(p)}#runs")
            if "test" in str(cfg).lower() or "local" in str(p).lower():
                d.text((x + 20, y), "This is a local test run, not the A/B/C COOL comparison.",
                       font=font(24), fill=ACCENT)
                y += 40
        for key, nm in [("bench_cost", "Cost per video hour (cost.json)"), ("bench_parity", "Parity report (parity.json)")]:
            if not self.res[key]:
                line(nm, "Results pending", f"no {nm.split('(')[1][:-1]} yet")
                self.pending.append(f"results/bench/<date>/{nm.split('(')[1][:-1]}")
            for p, j in self.res[key][:1]:
                self.sources.append(rel(p))
                if isinstance(j, dict):
                    for k, val in list(j.items())[:4]:
                        if isinstance(val, (int, float, str, bool)):
                            line(f"{nm.split(' (')[0]}: {k}", fmt(val), f"{rel(p)}#{k}")
        return img


class BulletsScene(Scene):
    def static(self) -> Image.Image:
        img = canvas()
        heading(img, self.v["heading"], "from " + self.v.get("source", ""))
        self.sources.append(self.v.get("source", ""))
        d = ImageDraw.Draw(img)
        y = 180
        for b in self.v["bullets"]:
            lines = wrap_px(d, b, font(38), 1650)
            d.text((80, y), "\u2022", font=font(38), fill=ACCENT)
            for i, ln in enumerate(lines):
                d.text((120, y + i * 50), ln, font=font(38), fill=FG)
            y += 50 * len(lines) + 22
        return img


class TeamScene(Scene):
    def prepare(self) -> None:
        self.path = ROOT / self.v["file"]
        self.clip = None
        if self.path.exists():
            self.clip = Clip(self.path)
            self.sources.append(rel(self.path))
            wav = BUILD / "team_audio.wav"
            r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(self.path), "-vn", "-ac", "1", "-ar", "22050",
                                "-c:a", "pcm_s16le", str(wav)], check=False)
            if r.returncode == 0 and wav.exists():
                self.audio_override = wav
            self.clip_dur = self.clip.n / self.clip.fps if self.clip.n else 0.0
        else:
            self.pending.append(f"team clip {self.v['file']}")
            warn(f"team clip missing: {self.v['file']} (card shown)")

    def frame(self, t: float) -> Image.Image:
        if self.clip is None:
            if self._static is None:
                img = canvas()
                placeholder(img, (60, 120, W - 60, SUB_TOP - 40), "Team", "Team clip to be supplied at video/assets/team.mp4")
                self._static = img
            return self._static.copy()
        img = canvas()
        f = self.clip.frame_at(min(t, max(self.clip_dur - 0.05, 0)))
        if f is not None:
            paste_fit(img, f, (0, 0, W, H))
        return img


RENDERERS = {"title": TitleScene, "public_clip": PublicClipScene, "engine_run": EngineRunScene, "plots": PlotsScene,
             "ui": UIScene, "image": ImageScene, "trace": TraceScene, "results": ResultsScene,
             "bullets": BulletsScene, "team": TeamScene}


# ----------------------------------------------------------------------------------------------- subtitles
def sub_chunks(text: str, max_chars: int = 95) -> list[str]:
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    out: list[str] = []
    for s in sents:
        if len(s) <= max_chars:
            out.append(s)
            continue
        parts = re.split(r"(?<=,)\s+", s)
        cur = ""
        for p in parts:
            if cur and len(cur) + len(p) + 1 > max_chars:
                out.append(cur)
                cur = p
            else:
                cur = (cur + " " + p).strip()
        if cur:
            out.append(cur)
    return [c for c in out if c]


def draw_sub(img: Image.Image, text: str) -> None:
    d = ImageDraw.Draw(img)
    f = font(36)
    lines = wrap_px(d, text, f, 1720)[:2]
    y0 = SUB_TOP + (2 - len(lines)) * 22
    d.rectangle([0, SUB_TOP - 6, W, H], fill=(0, 0, 0))
    for i, ln in enumerate(lines):
        d.text((W // 2, y0 + 30 + i * 48), ln, font=f, fill=(255, 255, 255), anchor="mm")


# ----------------------------------------------------------------------------------------------- main
def pick_narration(spec: dict[str, Any], ctx: dict[str, Any]) -> str:
    nb = spec.get("narration_by")
    if nb:
        src = nb["source"]
        if src.startswith("verdict:"):
            key = ctx["runs"][src.split(":", 1)[1]].verdict or "default"
        elif src == "trace":
            key = trace_kind(ctx["trace"])
        else:
            raise SystemExit(f"unknown narration_by source {src}")
        text = nb["options"].get(key) or nb["options"]["default"]
    else:
        text = spec["narration"]
    return " ".join(text.split()).format(**ctx["placeholders"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rerun-engine", action="store_true", help="re-run all engine jobs")
    ap.add_argument("--scenes", default=str(VIDEO_DIR / "scenes.yaml"))
    ap.add_argument("--out", default=str(OUT_MP4))
    ap.add_argument("--no-engine", action="store_true", help="do not start missing engine runs")
    ap.add_argument("--preview", default=None, help="write one PNG per scene to this folder and stop")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.scenes).read_text(encoding="utf-8"))
    BUILD.mkdir(parents=True, exist_ok=True)

    runs = ensure_runs(cfg["engine_runs"], args.rerun_engine, args.no_engine)
    trace, trace_path = find_agent_trace()
    planners = sorted({s.get("planner") for s in (trace or {}).get("steps", []) if s.get("planner")})
    if planners == ["bedrock"]:
        planner_phrase = "Its planner is Claude on Amazon Bedrock, as in the trace you just saw."
    elif planners:
        planner_phrase = ("Its planner can be Claude on Amazon Bedrock. The trace you saw used the fixed "
                          "fallback planner.")
    else:
        planner_phrase = "Its planner can be Claude on Amazon Bedrock, with a fixed fallback planner."
    ctx = {"cfg": cfg, "runs": runs, "trace": trace, "trace_path": trace_path, "results": collect_results(),
           "placeholders": {"planner_phrase": planner_phrase}}

    # narration + audio per scene
    plan = []
    for spec in cfg["scenes"]:
        text = pick_narration(spec, ctx)
        lint_narration(spec["id"], text)
        plan.append({"spec": spec, "text": text})
    for p in plan:
        p["wav"] = tts(p["text"])
        a, sr = read_wav(p["wav"])
        p["audio"], p["sr"] = a, sr
        p["speech_s"] = len(a) / sr

    scenes: list[Scene] = []
    for p in plan:
        cls = RENDERERS[p["spec"]["visual"]["type"]]
        scenes.append(cls(p["spec"], ctx))

    # durations: max(narration + padding, min_s); shrink minimums if the total is too long
    need = []
    for p, sc in zip(plan, scenes, strict=True):
        if sc.audio_override is not None:
            a, sr = read_wav(sc.audio_override)
            p["audio"], p["sr"] = a, sr
            p["speech_s"] = len(a) / sr
            p["lead"] = 0.0
            need.append(max(p["speech_s"], getattr(sc, "clip_dur", 0.0)))
        else:
            p["lead"] = LEAD_S
            need.append(LEAD_S + p["speech_s"] + TAIL_S)
    mins = [float(p["spec"].get("min_s", 0)) for p in plan]
    scale = 1.0
    for _ in range(50):
        durs = [max(n, m * scale) for n, m in zip(need, mins, strict=True)]
        if sum(durs) <= TARGET_MAX_S or scale <= 0:
            break
        scale -= 0.02
    if sum(durs) > LIMIT_S:
        raise SystemExit(f"narration alone is {sum(need):.1f} s; shorten scenes.yaml narration (limit {LIMIT_S} s)")
    durs = [math.ceil(d * FPS) / FPS for d in durs]
    for sc, d in zip(scenes, durs, strict=True):
        sc.duration = d
    total = sum(durs)
    print(f"[plan] {len(scenes)} scenes, total {total:.1f} s (minimum scale {scale:.2f})", flush=True)
    if args.preview:
        pv = Path(args.preview)
        pv.mkdir(parents=True, exist_ok=True)
        for k, (p, sc, d) in enumerate(zip(plan, scenes, durs, strict=True)):
            for frac in (0.1, 0.6):
                img = sc.frame(d * frac)
                draw_sub(img, sub_chunks(p["text"])[0])
                img.save(pv / f"{k:02d}_{p['spec']['id']}_{int(frac * 100)}.png")
            print(f"  {p['spec']['id']:<16} {d:6.1f} s  {p['text'][:70]}")
        return 0

    # audio track
    sr_out = 48000
    track = np.zeros(int(round(total * sr_out)) + sr_out, dtype=np.float32)
    t = 0.0
    for p, d in zip(plan, durs, strict=True):
        a = resample(p["audio"], p["sr"], sr_out)
        i0 = int(round((t + p["lead"]) * sr_out))
        a = a[: max(0, int(d * sr_out) - int(p["lead"] * sr_out))]
        track[i0:i0 + len(a)] += a
        t += d
    track = track[: int(round(total * sr_out))]
    wav_out = BUILD / "narration.wav"
    with wave.open(str(wav_out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr_out)
        w.writeframes((np.clip(track, -1, 1) * 32767).astype(np.int16).tobytes())

    # video frames -> ffmpeg (H.264), then mux audio
    silent = BUILD / "video_noaudio.mp4"
    ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                           "-pix_fmt", "yuv420p", str(silent)], stdin=subprocess.PIPE)
    assert ff.stdin is not None
    srt_lines = []
    t_global = 0.0
    for k, (p, sc, d) in enumerate(zip(plan, scenes, durs, strict=True)):
        print(f"[render] {k + 1:2d}/{len(scenes)} {p['spec']['id']:<16} {d:6.1f} s", flush=True)
        chunks = sub_chunks(p["text"])
        weights = np.array([max(len(c), 1) for c in chunks], dtype=np.float64)
        speech = p["speech_s"] if sc.audio_override is None else 0.0
        bounds = p["lead"] + np.concatenate([[0], np.cumsum(weights) / weights.sum() * speech])
        for ci, c in enumerate(chunks):
            if speech > 0:
                srt_lines.append((t_global + bounds[ci], t_global + bounds[ci + 1], c))
        nfr = int(round(d * FPS))
        for fi in range(nfr):
            ts = fi / FPS
            img = sc.frame(ts)
            if speech > 0:
                ci = int(np.searchsorted(bounds, ts, side="right")) - 1
                ci = min(max(ci, 0), len(chunks) - 1)
                if ts <= bounds[-1] + TAIL_S:
                    draw_sub(img, chunks[ci])
            ff.stdin.write(img.tobytes())
        t_global += d
    ff.stdin.close()
    if ff.wait() != 0:
        raise SystemExit("ffmpeg video encode failed")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(silent), "-i", str(wav_out), "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out)], check=True)

    # sidecar subtitles file (same text as the burned-in subtitles)
    def ts_(x: float) -> str:
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    (out.with_suffix(".srt")).write_text("\n".join(f"{i + 1}\n{ts_(a)} --> {ts_(b)}\n{c}\n"
                                                   for i, (a, b, c) in enumerate(srt_lines)), encoding="utf-8")

    manifest = {
        "output": rel(out), "duration_planned_s": round(total, 3),
        "scenes": [{"id": p["spec"]["id"], "start_s": round(sum(durs[:i]), 2), "duration_s": round(durs[i], 2),
                    "narration": p["text"], "visual": p["spec"]["visual"]["type"], "sources": sc.sources,
                    "pending": sc.pending}
                   for i, (p, sc) in enumerate(zip(plan, scenes, strict=True))],
        "engine_runs": {n: {"verdict": r.verdict, "lifecycle_state": (r.result or {}).get("lifecycle_state"),
                            "reasons": (r.result or {}).get("reasons"),
                            "result_file": rel(r.result_path) if r.result_path else None,
                            "synthetic": r.synthetic} for n, r in runs.items()},
        "agent_trace": rel(trace_path) if trace_path else None,
        "warnings": WARNINGS,
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    r = subprocess.run([PY, str(ROOT / "scripts" / "check_video_duration.py"), str(out)], cwd=ROOT, check=False)
    print(f"[done] {rel(out)}  planned {total:.1f} s; {len(WARNINGS)} warning(s)")
    for w_ in WARNINGS:
        print("  - " + w_)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
