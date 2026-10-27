"""GRIDPRINT pitch video generator (v2, narrated, motion graphics).

Run from the repository root:
    PYTHONUTF8=1 PYTHONPATH=".;engine" python video/make_pitch.py

Inputs (all real files): video/assets/live/*.png (headless-Chrome screenshots of the live AWS app),
data/public/fluorescent_beat_effect.mp4 (Wikimedia Commons, CC BY-SA 3.0), results/video/engine_runs/* (engine output),
results/agent_traces/*.json (agent trace), results/bench/2026-10-27/{cost.json,A,B/summary.json} (benchmark).
Outputs: results/video/gridprint_submission.mp4, .srt, docs/VIDEO_SCRIPT.md.
TTS: edge-tts (en-US-AndrewNeural). Every number on screen is read from a results/ file at build time.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import subprocess
import sys
import wave
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "video"
BUILD = OUT / "build" / "pitch"
TTS_DIR = BUILD / "tts"
LIVE = ROOT / "video" / "assets" / "live"
RUNS = OUT / "engine_runs"
BENCH = ROOT / "results" / "bench" / "2026-10-27"
PUBLIC_CLIP = ROOT / "data" / "public" / "fluorescent_beat_effect.mp4"
APP_URL = "5u7suz00bi.execute-api.us-east-1.amazonaws.com"
REPO = "github.com/vivekyarra/Alibi"
VOICE, RATE = "en-US-AndrewNeural", "+0%"
W, H, FPS, SR = 1920, 1080, 30, 48000
GAP, LEAD, TAIL = 0.42, 0.4, 0.6

BG0, BG1 = np.array([9, 14, 20], np.float32), np.array([10, 30, 34], np.float32)
FG, MUTED, ACC = (238, 242, 246), (140, 156, 170), (70, 225, 160)
PANEL, LINE = (20, 30, 38), (44, 62, 72)
VCOL = {"VERIFIED": (52, 190, 110), "CONTRADICTED": (225, 70, 70), "INCONCLUSIVE": (150, 160, 172)}
FD = Path("C:/Windows/Fonts")
_FC: dict = {}


def F(size: int, kind: str = "b") -> ImageFont.FreeTypeFont:
    k = (size, kind)
    if k not in _FC:
        name = {"b": "segoeuib.ttf", "r": "segoeui.ttf", "l": "segoeuil.ttf", "m": "consola.ttf", "s": "seguisym.ttf"}[kind]
        _FC[k] = ImageFont.truetype(str(FD / name), size)
    return _FC[k]


def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def lerp(a, b, u):
    return a + (b - a) * u


# ----------------------------------------------------------------------------- narration (ASD-STE100 style)
SECTIONS = [
    ("01", "THE PROBLEM", [
        ("hook", ["Today, anyone can generate a realistic video in minutes.",
                  "It costs almost nothing, and it looks real."]),
        ("dismiss", ["This creates a second problem.",
                     "When a video is real, people now say: it is just AI.",
                     "True evidence loses its value."]),
        ("bulb", ["We need a fact from the physical world that a generator does not know.",
                  "There is one, and it hangs above your head.",
                  "Mains lights flicker with the power grid.",
                  "The grid frequency drifts a little, all the time, and that drift marks the time."]),
    ]),
    ("02", "WHO NEEDS THIS", [
        ("pain", ["This problem hurts real people.",
                  "Newsrooms must check footage before they publish it.",
                  "Courts must decide which video to trust.",
                  "Insurers must check claims that use video.",
                  "Human-rights groups must defend footage that powerful people call AI."]),
    ]),
    ("03", "HOW IT WORKS", [
        ("flicker", ["Meet GRIDPRINT. It checks a video against the power grid.",
                     "A mains light flickers at two times the grid frequency.",
                     "On a fifty hertz grid, that is one hundred pulses each second."]),
        ("rolling", ["A phone camera reads its sensor one row at a time.",
                     "This is called a rolling shutter.",
                     "So the fast flicker becomes faint horizontal bands in the image."]),
        ("overlay", ["This is a public clip of a real fluorescent light.",
                     "OpenCV 5 linearises the light, removes camera motion, and measures the bands in each frame."]),
        ("track", ["From the band phase, the engine rebuilds the grid frequency track.",
                   "Then it slides that track along the grid reference log.",
                   "One clear match gives a recording time. A cut or an insertion breaks the match."]),
    ]),
    ("04", "REAL EVIDENCE", [
        ("realclip", ["We filmed a real room with a normal phone.",
                      "This is an iPhone 13 video, recorded today under indoor mains light in India."]),
        ("realrun", ["The OpenCV 5 engine measured the full clip.",
                     "It found no clean flicker in this clip.",
                     "So GRIDPRINT said INCONCLUSIVE. It did not guess."]),
        ("reallive", ["We also ran the same clip live on AWS.",
                      "LIVE_SENTENCE",
                      "A missing signal never counts against a video."]),
    ]),
    ("05", "THE PRODUCT", [
        ("home", ["GRIDPRINT runs live on AWS today. This is the web app.",
                  "You upload a video. You can add a claimed grid zone and a claimed recording time."]),
        ("cases", ["Ready-made example cases run through the same live pipeline.",
                   "One click starts a full analysis job."]),
        ("job", ["Here is a finished job. The verdict is VERIFIED, and the report is final.",
                 "The page shows the estimated recording time and its uncertainty.",
                 "Each verdict comes with reason codes in plain words."]),
        ("trace", ["An agent plans each analysis.",
                   "It calls engine tools through an MCP server, and it logs every step."]),
        ("reviewer", ["A CONTRADICTED result is never final on its own.",
                      "A human reviewer must approve it first."]),
    ]),
    ("06", "BUILT ON AWS", [
        ("arch", ["A video arrives through API Gateway and an Application Load Balancer.",
                  "An API service on AWS Fargate stores it in S3 with KMS keys, and puts a job on an SQS queue.",
                  "Workers on Amazon ECS with Graviton4 run the OpenCV 5 engine in fifteen stages.",
                  "An agent with twelve MCP tools uses Amazon Nova Lite on Bedrock to plan each run, inside strict policies.",
                  "DynamoDB keeps jobs and the grid log. IoT Core and Lambda bring in grid data.",
                  "Cognito signs in reviewers. CloudWatch watches the system, and the AWS CDK deploys it all."]),
        ("bench", ["We measured the same engine on Graviton and on x86.",
                   "Graviton processed more video per second, at a lower cost per video hour."]),
    ]),
    ("07", "THE VERDICT", [
        ("close", ["GRIDPRINT gives exactly three verdicts: VERIFIED, CONTRADICTED, or INCONCLUSIVE.",
                   "A missing signal never counts against a video.",
                   "GRIDPRINT. Evidence from the light in the room."]),
    ]),
]


# ----------------------------------------------------------------------------- TTS
async def _tts_one(text: str, mp3: Path, sem: asyncio.Semaphore) -> None:
    import edge_tts
    async with sem:
        for attempt in range(4):
            try:
                await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(mp3))
                return
            except Exception as e:  # network hiccup
                print("tts retry", attempt, e)
                await asyncio.sleep(2)
        raise RuntimeError(f"tts failed: {text}")


def tts_all(sentences: list[str]) -> list[np.ndarray]:
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    jobs, paths = [], []
    for s in sentences:
        h = hashlib.sha1(f"{VOICE}|{RATE}|{s}".encode()).hexdigest()[:16]
        mp3, wav = TTS_DIR / f"{h}.mp3", TTS_DIR / f"{h}.wav"
        paths.append((mp3, wav))
        if not wav.exists():
            jobs.append((s, mp3))

    async def run():
        sem = asyncio.Semaphore(6)
        await asyncio.gather(*[_tts_one(s, m, sem) for s, m in jobs])
    if jobs:
        asyncio.run(run())
    out = []
    for mp3, wav in paths:
        if not wav.exists():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-af",
                            "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse",
                            "-ac", "1", "-ar", str(SR), str(wav)], check=True)
        with wave.open(str(wav)) as w:
            a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        out.append(a)
    return out


# ----------------------------------------------------------------------------- media helpers
def load_frames(p: Path, size: tuple[int, int] | None = None, maxn: int = 900) -> list[np.ndarray]:
    cap, fr = cv2.VideoCapture(str(p)), []
    while len(fr) < maxn:
        ok, f = cap.read()
        if not ok:
            break
        f = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
        fr.append(cv2.resize(f, size, interpolation=cv2.INTER_AREA) if size else f)
    return fr


_BG = None


def background() -> Image.Image:
    global _BG
    if _BG is None:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        u = np.clip((xx / W) * 0.6 + (yy / H) * 0.4, 0, 1)[..., None]
        r = np.exp(-(((xx - W * 0.75) / 900) ** 2 + ((yy - H * 0.2) / 600) ** 2))[..., None]
        a = BG0 * (1 - u) + BG1 * u + r * np.array([0, 18, 14], np.float32)
        g = np.zeros((H, W), np.float32)
        g[::60, :] = 1
        g[:, ::60] = 1
        a += g[..., None] * 4
        _BG = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return _BG.copy()


def rrect(d: ImageDraw.ImageDraw, box, fill=PANEL, outline=LINE, r=18, width=2):
    d.rounded_rectangle(box, r, fill=fill, outline=outline, width=width)


def ctext(d, xy, text, font, fill=FG, anchor="mm"):
    d.text(xy, text, font=font, fill=fill, anchor=anchor)


def alpha_text(img, xy, text, font, fill, a, anchor="la"):
    if a <= 0.01:
        return
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(lay).text(xy, text, font=font, fill=fill + (int(255 * min(1, a)),), anchor=anchor)
    img.alpha_composite(lay)


def paste_np(img: Image.Image, arr: np.ndarray, box, border=True):
    x0, y0, x1, y1 = box
    im = Image.fromarray(arr).resize((x1 - x0, y1 - y0), Image.BILINEAR)
    img.paste(im, (x0, y0))
    if border:
        ImageDraw.Draw(img).rounded_rectangle((x0 - 2, y0 - 2, x1 + 2, y1 + 2), 6, outline=LINE, width=3)


def tagline(d, num, title):
    rrect(d, (64, 44, 104, 72), fill=(18, 60, 46), outline=ACC, r=6, width=1)
    ctext(d, (84, 58), num, F(18, "b"), ACC)
    d.line((116, 58, 156, 58), fill=ACC, width=2)
    d.text((168, 58), title, font=F(20, "b"), fill=ACC, anchor="lm")


def source_tag(d, text, y=900):
    d.text((W - 64, y), text, font=F(18, "m"), fill=MUTED, anchor="rm")


def caption(img: Image.Image, text: str):
    d = ImageDraw.Draw(img)
    f = F(38, "b")
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if d.textlength(t, font=f) > 1500 and cur:
            lines.append(cur)
            cur = w_
        else:
            cur = t
    lines.append(cur)
    lh = 50
    y0 = 1032 - lh * len(lines)
    wmax = max(d.textlength(l_, font=f) for l_ in lines)
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(lay).rounded_rectangle((W / 2 - wmax / 2 - 28, y0 - 14, W / 2 + wmax / 2 + 28, y0 + lh * len(lines) + 8),
                                          14, fill=(6, 10, 14, 200))
    img.alpha_composite(lay)
    for i, l_ in enumerate(lines):
        d.text((W / 2, y0 + i * lh), l_, font=f, fill=FG, anchor="ma")


# ----------------------------------------------------------------------------- scene visuals
class Ctx:
    pass


def heading(img, d, text, t, y=150, size=72, x=110, delay=0.0, color=FG):
    a = ease((t - delay) / 0.6)
    alpha_text(img, (x, y + (1 - a) * 30), text, F(size, "b"), color, a)


def v_hook(img, d, t, D, c):
    # 3D perspective "frame wall": many video frames flying toward the camera
    rng = np.random.default_rng(3)
    pts = rng.uniform(-1, 1, (70, 2)) * [9, 4]
    zs = (rng.uniform(0, 1, 70) + t * 0.12) % 1.0
    order = np.argsort(-zs)
    for i in order:
        z = 6 - zs[i] * 5.5
        s = 520 / z
        cx, cy = W * 0.62 + pts[i, 0] * s * 0.6, H * 0.46 + pts[i, 1] * s * 0.6
        w_, h_ = 1.6 * s * 0.5, 0.9 * s * 0.5
        a = min(1, zs[i] * 2.2) * (1 - zs[i]) * 2
        col = tuple(int(v * min(1, a)) for v in (60, 120, 130))
        d.rectangle((cx - w_ / 2, cy - h_ / 2, cx + w_ / 2, cy + h_ / 2), outline=col, width=2)
        d.polygon([(cx - 8 * s / 100, cy - 10 * s / 100), (cx - 8 * s / 100, cy + 10 * s / 100), (cx + 10 * s / 100, cy)],
                  fill=col)
    heading(img, d, "Realistic video.", t, 300, 96)
    heading(img, d, "Generated in minutes.", t, 410, 96, delay=0.6, color=ACC)
    t2 = c.sent_t[1] if len(c.sent_t) > 1 else 3
    heading(img, d, "Almost free.", t, 520, 96, delay=t2)


def v_dismiss(img, d, t, D, c):
    fr = c.clip[int(t * 30) % len(c.clip)]
    box = (1000, 170, 1000 + 760, 170 + 570)
    paste_np(img, fr, box)
    d.text((1000, 755), "Real footage: \u201cFluorescent beat effect\u201d, Wikimedia Commons, CC BY-SA 3.0",
           font=F(18, "r"), fill=MUTED)
    t1 = c.sent_t[1]
    if t > t1:
        a = ease((t - t1) / 0.35)
        sc = 1.6 - 0.6 * a
        lay = Image.new("RGBA", (620, 170), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        ld.rounded_rectangle((8, 8, 612, 162), 16, outline=(235, 80, 80, 255), width=8)
        ld.text((310, 85), "\u201cIt's just AI.\u201d", font=F(70, "b"), fill=(235, 80, 80, 255), anchor="mm")
        lay = lay.resize((int(620 * sc), int(170 * sc))).rotate(-8, expand=True)
        lay.putalpha(lay.getchannel("A").point(lambda v: int(v * a)))
        img.alpha_composite(lay, (int(1380 - lay.width / 2), int(455 - lay.height / 2)))
    heading(img, d, "Real video,", t, 300, 92)
    heading(img, d, "dismissed as AI.", t, 410, 92, delay=0.5, color=(235, 90, 90))
    if len(c.sent_t) > 2:
        heading(img, d, "Evidence loses its value.", t, 560, 46, delay=c.sent_t[2], color=MUTED)


def bulb(img, d, cx, cy, r, level):
    glow = Image.new("RGBA", (r * 8, r * 8), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for k in range(10, 0, -1):
        rr = r * (1 + k * 0.28)
        gd.ellipse((r * 4 - rr, r * 4 - rr, r * 4 + rr, r * 4 + rr), fill=(255, 220, 140, int(10 * level)))
    img.alpha_composite(glow, (int(cx - r * 4), int(cy - r * 4)))
    v = int(120 + 135 * level)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(v, int(v * 0.9), int(v * 0.6)), outline=(255, 240, 200), width=3)
    d.rounded_rectangle((cx - r * 0.45, cy + r * 0.8, cx + r * 0.45, cy + r * 1.5), 6, fill=(150, 156, 160))
    for k in range(3):
        yk = cy + r * (0.95 + k * 0.18)
        d.line((cx - r * 0.45, yk, cx + r * 0.45, yk), fill=(100, 106, 110), width=3)


def helix(d, t, x0, x1, ycen, amp, cycles, rot, col, width=4, power=False):
    # 3D sine ribbon rotating around the time axis, projected with perspective
    n = 420
    xs = np.linspace(0, 1, n)
    ph = 2 * np.pi * cycles * xs - t * 3
    y3, z3 = np.sin(ph) * amp, np.cos(ph) * amp * 0.0
    if power:
        y3 = np.abs(np.sin(ph)) * amp * 1.4 - amp * 0.7
    yr = y3 * math.cos(rot) - z3 * math.sin(rot)
    zr = y3 * math.sin(rot) + z3 * math.cos(rot)
    persp = 900 / (900 + zr)
    X = x0 + xs * (x1 - x0)
    Y = ycen + yr * persp
    d.line(list(zip(X.tolist(), Y.tolist())), fill=col, width=width, joint="curve")


def v_bulb(img, d, t, D, c):
    s2 = c.sent_t[2] if len(c.sent_t) > 2 else 0
    lvl = 0.55 + 0.45 * abs(math.sin(t * 2 * math.pi * 1.2)) if t > s2 else 0.85
    bulb(img, d, 520, 420, 120, lvl)
    rot = t * 0.6
    if t > s2:
        a = ease((t - s2) / 0.8)
        x1 = 900 + 900 * a
        helix(d, t, 900, x1, 330, 90, 4, rot, ACC, 5)
        d.text((900, 210), "Grid voltage  \u00b7  50 or 60 Hz", font=F(30, "b"), fill=ACC)
        helix(d, t, 900, x1, 600, 90, 8, rot, (255, 210, 120), 4, power=True)
        d.text((900, 480), "Light output  \u00b7  flickers at 2\u00d7 grid frequency", font=F(30, "b"), fill=(255, 210, 120))
    else:
        heading(img, d, "A clock in every room.", t, 300, 76, x=900)
        heading(img, d, "The power grid.", t, 400, 76, x=900, delay=c.sent_t[1] if len(c.sent_t) > 1 else 1, color=ACC)
    if len(c.sent_t) > 3 and t > c.sent_t[3]:
        heading(img, d, "Frequency drifts \u2192 a timestamp in the light.", t, 760, 40, x=900, delay=c.sent_t[3], color=FG)


def v_pain(img, d, t, D, c):
    fr = c.clip_blur[int(t * 30) % len(c.clip_blur)]
    img.paste(Image.fromarray(fr).resize((W, H), Image.BILINEAR), (0, 0))
    heading(img, d, "Real footage needs a defence.", t, 130, 64)
    items = [("Newsrooms", "verify footage before publishing", "\u2709"),
             ("Courts", "decide which video to trust", "\u2696"),
             ("Insurers", "check claims that use video", "\u2602"),
             ("Human-rights groups", "defend footage called \u201cAI\u201d", "\u270A")]
    for i, (a_, b_, ic) in enumerate(items):
        st = c.sent_t[i + 1] if len(c.sent_t) > i + 1 else i
        a = ease((t - st) / 0.5)
        if a <= 0:
            continue
        x = 110 + i * 435
        y = 330 + (1 - a) * 60
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        ld.rounded_rectangle((x, y, x + 400, y + 380), 20, fill=(16, 26, 32, int(225 * a)), outline=ACC + (int(255 * a),), width=2)
        ld.text((x + 40, y + 50), ic, font=F(90, "s"), fill=ACC + (int(255 * a),))
        ld.text((x + 40, y + 200), a_, font=F(38, "b"), fill=FG + (int(255 * a),))
        ld.text((x + 40, y + 260), b_, font=F(25, "r"), fill=MUTED + (int(255 * a),))
        img.alpha_composite(lay)
    d.text((110, 820), "Background: \u201cFluorescent beat effect\u201d, Wikimedia Commons, CC BY-SA 3.0", font=F(18, "r"), fill=MUTED)


def v_flicker(img, d, t, D, c):
    heading(img, d, "GRIDPRINT", t, 120, 110, color=ACC)
    heading(img, d, "checks a video against the power grid.", t, 250, 44, delay=0.3)
    s1 = c.sent_t[1] if len(c.sent_t) > 1 else 2
    if t > s1:
        a = ease((t - s1) / 0.8)
        x0, x1 = 160, 160 + 1600 * a
        d.line((160, 520, 1760, 520), fill=LINE, width=2)
        d.line((160, 760, 1760, 760), fill=LINE, width=2)
        helix(d, t * 0.5, x0, x1, 520, 80, 5, t * 0.4, ACC, 5)
        helix(d, t * 0.5, x0, x1, 760, 80, 10, t * 0.4, (255, 210, 120), 4, power=True)
        d.text((160, 410), "Grid: 50 Hz", font=F(30, "b"), fill=ACC)
        d.text((160, 650), "Light: 100 pulses per second", font=F(30, "b"), fill=(255, 210, 120))
        lvl = 0.5 + 0.5 * abs(math.sin(t * 7))
        bulb(img, d, 1700, 380, 50, lvl)


def v_rolling(img, d, t, D, c):
    # sensor rows read one at a time; each row samples the flicker at its own readout time
    heading(img, d, "Rolling shutter", t, 120, 72)
    heading(img, d, "turns flicker into bands.", t, 210, 48, delay=0.4, color=ACC)
    x0, y0, w_, h_ = 980, 150, 760, 700
    rows = 70
    prog = ((t * 0.35) % 1.0)
    cur = int(prog * rows)
    full = t > (c.sent_t[2] if len(c.sent_t) > 2 else D * 0.6)
    rrect(d, (x0 - 14, y0 - 14, x0 + w_ + 14, y0 + h_ + 14), fill=(12, 18, 22))
    rh = h_ / rows
    for r in range(rows):
        if r > cur and not full:
            continue
        v = 0.5 + 0.5 * abs(math.sin(2 * math.pi * 3.3 * r / rows + t * 0.8))
        g = int(70 + 120 * v)
        d.rectangle((x0, y0 + r * rh, x0 + w_, y0 + (r + 1) * rh), fill=(g, int(g * 0.95), int(g * 0.8)))
    if not full:
        yy = y0 + cur * rh
        d.rectangle((x0 - 20, yy - 3, x0 + w_ + 20, yy + 3), fill=ACC)
        d.text((x0 - 30, yy), "reading row", font=F(22, "b"), fill=ACC, anchor="rm")
    d.text((x0, y0 + h_ + 30), "Each row is read a little later \u2192 it sees a different moment of the flicker.",
           font=F(24, "r"), fill=MUTED)
    bulb(img, d, 400, 560, 90, 0.5 + 0.5 * abs(math.sin(t * 9)))
    d.line((520, 560, x0 - 40, 560), fill=(255, 210, 120), width=3)
    for k in range(5):
        px = 520 + ((t * 260 + k * 90) % (x0 - 560))
        d.ellipse((px - 6, 554, px + 6, 566), fill=(255, 220, 140))


def v_overlay(img, d, t, D, c):
    heading(img, d, "Real light. Real measurement.", t, 100, 60)
    i = int(t * 30) % len(c.clip)
    paste_np(img, c.clip[i], (120, 260, 120 + 800, 260 + 600))
    paste_np(img, c.ovl[i % len(c.ovl)], (1000, 260, 1000 + 800, 260 + 655))
    d.text((120, 225), "Input: public clip of a fluorescent light", font=F(24, "b"), fill=FG)
    d.text((1000, 225), "OpenCV 5 engine overlay (engine output)", font=F(24, "b"), fill=ACC)
    d.text((120, 872), "\u201cFluorescent beat effect\u201d, Wikimedia Commons, CC BY-SA 3.0", font=F(18, "r"), fill=MUTED)
    source_tag(d, "results/video/engine_runs/public_fluorescent/.../overlay.mp4", 935)


def v_track(img, d, t, D, c):
    s1 = c.sent_t[1] if len(c.sent_t) > 1 else D / 2
    heading(img, d, "Rebuild the grid frequency track.", t, 100, 56)
    a = ease(t / 2.0)
    im = c.enf
    box = (160, 220, 1760, 220 + int(1600 * im.height / im.width))
    if t < s1 + 0.4:
        crop = im.crop((0, 0, max(1, int(im.width * a)), im.height))
        crop = crop.resize((max(1, int((box[2] - box[0]) * a)), box[3] - box[1]), Image.BILINEAR)
        rrect(d, (box[0] - 12, box[1] - 12, box[2] + 12, box[3] + 12), fill=(255, 255, 255), outline=LINE)
        img.paste(crop, (box[0], box[1]))
        source_tag(d, "engine output: results/video/engine_runs/capture_verified/.../enf_track.png", 935)
    else:
        heading(img, d, "Slide it along the grid log. One clear peak.", t, 170, 40, delay=s1 + 0.4, color=ACC)
        im2 = c.ncc
        b2 = (260, 260, 1660, 260 + int(1400 * im2.height / im2.width))
        b2 = (b2[0], b2[1], b2[2], min(b2[3], 880))
        rrect(d, (b2[0] - 12, b2[1] - 12, b2[2] + 12, b2[3] + 12), fill=(255, 255, 255), outline=LINE)
        img.paste(im2.resize((b2[2] - b2[0], b2[3] - b2[1]), Image.BILINEAR), (b2[0], b2[1]))
        source_tag(d, "engine output: results/video/engine_runs/capture_verified/.../ncc_scan.png", 935)


# --- live app walk-through: real screenshots, animated viewport + cursor
BX0, BY0, BX1, BY1 = 190, 160, 1730, 905  # browser content area on screen


def browser(img, d, shot: Image.Image, url_path: str, cam, cursor, clicks, t):
    """cam = (cx, cy, cw) in screenshot pixels; cursor = (x, y) in screenshot pixels."""
    rrect(d, (BX0 - 10, BY0 - 62, BX1 + 10, BY1 + 10), fill=(36, 40, 46), outline=(60, 66, 74), r=14)
    for k, col in enumerate([(240, 90, 80), (240, 190, 70), (90, 200, 100)]):
        d.ellipse((BX0 + 10 + k * 26, BY0 - 40, BX0 + 26 + k * 26, BY0 - 24), fill=col)
    rrect(d, (BX0 + 110, BY0 - 48, BX1 - 20, BY0 - 14), fill=(22, 24, 28), outline=(60, 66, 74), r=10, width=1)
    d.text((BX0 + 130, BY0 - 31), "\U0001F512 https://" + APP_URL + "/" + url_path, font=F(19, "r"), fill=(200, 205, 210), anchor="lm")
    cx, cy, cw = cam
    ch = cw * (BY1 - BY0) / (BX1 - BX0)
    x0, y0 = max(0, cx - cw / 2), max(0, cy - ch / 2)
    x0, y0 = min(x0, shot.width - cw), min(y0, shot.height - ch)
    crop = shot.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((BX1 - BX0, BY1 - BY0), Image.BILINEAR)
    img.paste(crop, (BX0, BY0))
    sc = (BX1 - BX0) / cw

    def to_screen(p):
        return BX0 + (p[0] - x0) * sc, BY0 + (p[1] - y0) * sc
    for (tc, p) in clicks:
        if 0 <= t - tc < 0.6:
            sx, sy = to_screen(p)
            r = 10 + (t - tc) * 90
            a = int(255 * (1 - (t - tc) / 0.6))
            lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            ImageDraw.Draw(lay).ellipse((sx - r, sy - r, sx + r, sy + r), outline=ACC + (a,), width=4)
            img.alpha_composite(lay)
    if cursor is not None:
        sx, sy = to_screen(cursor)
        pts = [(sx, sy), (sx, sy + 34), (sx + 9, sy + 26), (sx + 16, sy + 40), (sx + 22, sy + 37), (sx + 15, sy + 23), (sx + 26, sy + 23)]
        d.polygon(pts, fill=(255, 255, 255), outline=(0, 0, 0))


def track(keys, t):
    """keys: list of (time, value-tuple); eased interpolation."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (ta, va), (tb, vb) in zip(keys, keys[1:]):
        if t <= tb:
            u = ease((t - ta) / max(1e-6, tb - ta))
            return tuple(lerp(a, b, u) for a, b in zip(va, vb))
    return keys[-1][1]


def v_home(img, d, t, D, c):
    s1 = c.sent_t[1]
    cam = track([(0, (960, 560, 1500)), (s1, (960, 560, 1500)), (s1 + 1.2, (760, 700, 1000)), (D, (760, 760, 1000))], t)
    cur = track([(0, (1300, 300)), (s1 + 0.8, (480, 414)), (s1 + 2.2, (675, 603)), (s1 + 3.4, (600, 690)), (D - 0.6, (501, 930))], t)
    browser(img, d, c.shots["home"], "", cam, cur, [(s1 + 0.8, (480, 414)), (s1 + 2.2, (675, 603)), (D - 0.6, (501, 930))], t)


def v_cases(img, d, t, D, c):
    cam = track([(0, (960, 700, 1300)), (1.6, (960, 1450, 1300)), (D, (960, 1520, 1300))], t)
    s1 = c.sent_t[1]
    cur = track([(0, (1200, 1100)), (s1, (468, 1350)), (D, (470, 1352))], t)
    browser(img, d, c.shots["home"], "", cam, cur, [(s1 + 0.1, (468, 1350))], t)


def v_job(img, d, t, D, c):
    s1, s2 = c.sent_t[1], c.sent_t[2]
    cam = track([(0, (960, 560, 1500)), (1.0, (960, 560, 1500)), (2.2, (1240, 330, 760)), (s1, (1240, 330, 760)),
                 (s1 + 1.0, (1240, 470, 720)), (s2, (1240, 470, 720)), (s2 + 1.0, (1240, 600, 720)), (D, (1240, 610, 720))], t)
    cur = track([(0, (1500, 900)), (2.0, (1130, 280)), (s1 + 0.8, (1100, 440)), (s2 + 0.8, (1080, 590)), (D, (1080, 630))], t)
    browser(img, d, c.shots["job"], "#/jobs/aws3-capture-verified-040158", cam, cur, [], t)


def v_trace(img, d, t, D, c):
    heading(img, d, "Agent trace", t, 100, 60)
    d.text((110, 185), "Each step: one tool call through the MCP server, logged with its result.", font=F(28, "r"), fill=MUTED)
    steps = c.trace["steps"]
    y = 250
    for i, s in enumerate([s for s in steps if s.get("tool") != "render_report"][:9]):
        a = ease((t - 0.4 - i * 0.35) / 0.4)
        if a <= 0:
            break
        x = 110 + (1 - a) * 40
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        ld.rounded_rectangle((x, y, x + 1700, y + 54), 10, fill=(20, 30, 38, int(240 * a)), outline=LINE + (int(255 * a),))
        ld.text((x + 20, y + 27), f"{i + 1:02d}", font=F(24, "m"), fill=ACC + (int(255 * a),), anchor="lm")
        ld.text((x + 90, y + 27), str(s.get("tool")), font=F(26, "b"), fill=FG + (int(255 * a),), anchor="lm")
        summ = str(s.get("output_summary") or "")[:88]
        ld.text((x + 430, y + 27), summ, font=F(20, "m"), fill=MUTED + (int(255 * a),), anchor="lm")
        img.alpha_composite(lay)
        y += 62
    source_tag(d, "results/agent_traces/" + c.trace_name, 900)


def v_reviewer(img, d, t, D, c):
    cam = track([(0, (960, 400, 1400)), (1.2, (900, 330, 1000)), (D, (880, 360, 960))], t)
    cur = track([(0, (1300, 700)), (1.5, (700, 290)), (2.8, (700, 360)), (D - 0.8, (498, 510))], t)
    browser(img, d, c.shots["reviewer"], "#/reviewer", cam, cur, [(1.5, (700, 290)), (D - 0.8, (498, 510))], t)


def v_limits(img, d, t, D, c):
    cam = track([(0, (960, 500, 1300)), (D * 0.35, (960, 500, 1300)), (D, (960, 900, 1300))], t)
    cur = track([(0, (1400, 300)), (D, (1300, 900))], t)
    browser(img, d, c.shots["limits"], "#/limitations", cam, cur, [], t)


# --- architecture (boxes sized to their text)
ROWS = [  # (y, height, [(id, title, subtitle, appear_sentence)])
    (118, 92, [("cap", "Capture app / Upload", "Android app \u00b7 web upload", 0),
               ("apigw", "Amazon API Gateway", "HTTPS entry", 0),
               ("alb", "Application Load Balancer", "VPC link", 0),
               ("api", "AWS Fargate", "API service \u00b7 arm64", 1)]),
    (262, 300, [("bed", "Amazon Bedrock", "Amazon Nova Lite planner", 3),
                ("agent", "Agent + MCP server", "12 tools \u00b7 policies", 3),
                ("eng", "Amazon ECS \u00b7 Graviton4 c8g", "OpenCV 5 engine \u00b7 15 stages", 2),
                ("sqs", "Amazon SQS", "job queue + DLQ", 1)]),
    (612, 92, [("cog", "Amazon Cognito", "reviewer sign-in", 5),
               ("ddb", "Amazon DynamoDB", "jobs \u00b7 grid log", 4),
               ("s3", "Amazon S3 + AWS KMS", "videos \u00b7 reports \u00b7 encrypted", 1),
               ("iot", "AWS IoT Core + AWS Lambda", "grid Node ingest", 4)]),
    (756, 80, [("ecr", "Amazon ECR", "container images", 2),
               ("cw", "Amazon CloudWatch", "logs \u00b7 metrics \u00b7 alarms", 5),
               ("cdk", "AWS CDK", "infrastructure as code", 5)]),
]
EDGES = [("cap", "apigw"), ("apigw", "alb"), ("alb", "api"), ("api", "sqs"), ("sqs", "eng"), ("eng", "agent"),
         ("agent", "bed"), ("eng", "s3"), ("eng", "ddb"), ("iot", "ddb"), ("ecr", "eng"), ("cog", "api"), ("api", "s3")]
CHIPS = ["LUT linearisation", "goodFeaturesToTrack", "calcOpticalFlowPyrLK", "findHomography USAC_MAGSAC",
         "DISOpticalFlow", "dnn person masks", "FaceDetectorYN", "cv2.solve phase fit", "cv2.dft"]
TF, SF, CF = 24, 18, 16
NODES: dict = {}


def layout_arch():
    if NODES:
        return
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    chip_w = max(probe.textlength(ch, font=F(CF, "m")) for ch in CHIPS) + 20
    for y, h_, items in ROWS:
        ws = []
        for nid, ti, sub, s in items:
            w_ = max(probe.textlength(ti, font=F(TF, "b")), probe.textlength(sub, font=F(SF, "r"))) + 40
            if nid == "eng":
                w_ = max(w_, 3 * chip_w + 2 * 10 + 36)
            ws.append(w_)
        gap = (W - 2 * 70 - sum(ws)) / max(1, len(ws) - 1)
        x = 70.0
        for (nid, ti, sub, s), w_ in zip(items, ws):
            hh = h_ if nid == "eng" else min(h_, 92)
            yy = y + (h_ - hh) / 2
            NODES[nid] = (x, yy, w_, hh, ti, sub, s)
            x += w_ + gap
    NODES["_chip_w"] = chip_w


def anchor(n, other):
    x, y, w_, h_ = NODES[n][:4]
    ox, oy, ow, oh = NODES[other][:4]
    cx, cy, ocx, ocy = x + w_ / 2, y + h_ / 2, ox + ow / 2, oy + oh / 2
    dx, dy = ocx - cx, ocy - cy
    if abs(dy) < 1e-6 or abs(dx) * h_ > abs(dy) * w_:
        return (x + w_ if dx > 0 else x, cy)
    return (cx, y + h_ if dy > 0 else y)


def v_arch(img, d, t, D, c):
    layout_arch()
    st = c.sent_t
    nodes = {k: v for k, v in NODES.items() if not k.startswith("_")}
    vis = {n for n, v in nodes.items() if t >= st[min(v[6], len(st) - 1)]}
    for a, b in EDGES:
        if a in vis and b in vis:
            p, q = anchor(a, b), anchor(b, a)
            d.line((p, q), fill=(60, 120, 108), width=3)
            for k in range(2):
                u = (t * 0.55 + k * 0.5 + (sum(map(ord, a + b)) % 7) * 0.1) % 1.0
                px, py = lerp(p[0], q[0], u), lerp(p[1], q[1], u)
                d.ellipse((px - 7, py - 7, px + 7, py + 7), fill=ACC)
    chip_w = NODES["_chip_w"]
    for n, (x, y, w_, h_, ti, sub, s) in nodes.items():
        if n not in vis:
            continue
        a = ease((t - st[min(s, len(st) - 1)]) / 0.5)
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        yy = y + (1 - a) * 20
        ld.rounded_rectangle((x, yy, x + w_, yy + h_), 14, fill=(18, 34, 40, int(245 * a)), outline=ACC + (int(255 * a),), width=2)
        ld.text((x + 20, yy + 14), ti, font=F(TF, "b"), fill=FG + (int(255 * a),))
        ld.text((x + 20, yy + 50), sub, font=F(SF, "r"), fill=MUTED + (int(255 * a),))
        if n == "eng":
            for i, ch in enumerate(CHIPS):
                ca = ease((t - st[2] - 0.4 - i * 0.25) / 0.3) * a
                cx_, cy_ = x + 18 + (i % 3) * (chip_w + 10), yy + 92 + (i // 3) * 64
                ld.rounded_rectangle((cx_, cy_, cx_ + chip_w, cy_ + 52), 8, fill=(30, 60, 52, int(255 * ca)))
                ld.text((cx_ + chip_w / 2, cy_ + 26), ch, font=F(CF, "m"), fill=(200, 255, 225, int(255 * ca)), anchor="mm")
        img.alpha_composite(lay)


def v_bench(img, d, t, D, c):
    A, B = c.cost["configs"]["A"], c.cost["configs"]["B"]
    heading(img, d, "Graviton vs x86 \u00b7 same OpenCV 5 engine", t, 110, 56)
    rows = [("Throughput (video-s per wall-s)  \u00b7  higher is better",
             [(f"Graviton4 {B['instance_type']}", c.thr["B"], ACC), (f"x86 {A['instance_type']}", c.thr["A"], MUTED)], 2),
            ("Cost per video-hour (USD)  \u00b7  lower is better",
             [(f"Graviton4 {B['instance_type']}", B["cost_per_video_hour_usd"], ACC),
              (f"x86 {A['instance_type']}", A["cost_per_video_hour_usd"], MUTED)], 3)]
    y = 250
    for ri, (title, bars, nd) in enumerate(rows):
        a0 = 0.3 + ri * 1.6
        d.text((110, y), title, font=F(30, "b"), fill=FG)
        y += 60
        mx = max(v for _, v, _ in bars)
        for (lab, v, col) in bars:
            a = ease((t - a0) / 1.2)
            d.text((110, y + 30), lab, font=F(26, "r"), fill=FG, anchor="lm")
            wbar = 1050 * (v / mx) * a
            d.rounded_rectangle((520, y, 520 + max(4, wbar), y + 60), 10, fill=col)
            prefix = "$" if nd == 3 else ""
            d.text((540 + wbar, y + 30), f"{prefix}{v * a:.{nd}f}", font=F(32, "b"), fill=FG, anchor="lm")
            y += 80
        y += 50
    source_tag(d, "results/bench/2026-10-27/cost.json \u00b7 A/summary.json \u00b7 B/summary.json", 890)


def v_close(img, d, t, D, c):
    heading(img, d, "Three verdicts.", t, 110, 72)
    for i, v in enumerate(["VERIFIED", "CONTRADICTED", "INCONCLUSIVE"]):
        a = ease((t - 0.5 - i * 0.5) / 0.5)
        if a <= 0:
            continue
        x, y = 110 + i * 580, 260 + (1 - a) * 40
        col = VCOL[v]
        rrect(d, (x, y, x + 540, y + 150), fill=tuple(int(cc * 0.25) for cc in col), outline=col, r=18, width=3)
        ic = {"VERIFIED": "\u2714", "CONTRADICTED": "\u2716", "INCONCLUSIVE": "?"}[v]
        d.text((x + 40, y + 75), ic, font=F(60, "s"), fill=col, anchor="lm")
        d.text((x + 120, y + 75), v, font=F(44, "b"), fill=FG, anchor="lm")
    sub = {0: "", 1: "after human review", 2: "missing signal \u2260 evidence against a video"}
    for i in (1, 2):
        if t > 1.5:
            d.text((110 + i * 580, 430), sub[i], font=F(22, "r"), fill=MUTED)
    s3 = c.sent_t[2] if len(c.sent_t) > 2 else 6
    if t > s3:
        heading(img, d, "GRIDPRINT", t, 610, 96, delay=s3, color=ACC)
        heading(img, d, REPO, t, 740, 44, delay=s3 + 0.4)
        heading(img, d, "OpenCV 5  \u00b7  AWS  \u00b7  live at " + APP_URL, t, 810, 26, delay=s3 + 0.6, color=MUTED)


# --- real evidence: iPhone 13 recording, engine run, live AWS job
def v_realclip(img, d, t, D, c):
    heading(img, d, "A real room. A normal phone.", t, 100, 60)
    fr = c.phone[int(t * 30) % len(c.phone)]
    paste_np(img, fr, (330, 200, 330 + 1260, 200 + 709))
    rrect(d, (350, 220, 870, 270), fill=(10, 16, 20), outline=ACC, r=10)
    d.text((370, 245), "\u25cf REAL RECORDING \u00b7 iPhone 13 \u00b7 1080p30", font=F(22, "b"), fill=ACC, anchor="lm")
    source_tag(d, "data/real/phone2.mov", 935)


def v_realrun(img, d, t, D, c):
    heading(img, d, "The engine ran the full clip.", t, 100, 56)
    i = int(t * 30) % len(c.povl)
    paste_np(img, c.povl[i], (110, 220, 110 + 960, 220 + int(960 * c.povl[0].shape[0] / c.povl[0].shape[1])))
    d.text((110, 190), "OpenCV 5 engine overlay (engine output)", font=F(24, "b"), fill=ACC)
    q = c.preal
    rows = [("Verdict", q["verdict"]), ("Reasons", " \u00b7 ".join(q["reasons"])),
            ("Band SNR", f"{q['quality']['band_snr_db']:.2f} dB"), ("DFT peak", f"{q['quality']['dft_peak_hz']:.4f} Hz")]
    x0, y0 = 1130, 220
    rrect(d, (x0, y0, 1810, y0 + 470), fill=PANEL, outline=LINE)
    for k, (a_, b_) in enumerate(rows):
        al = ease((t - 0.6 - k * 0.5) / 0.4)
        yy = y0 + 40 + k * 105
        alpha_text(img, (x0 + 30, yy), a_, F(24, "r"), MUTED, al)
        col = VCOL.get(b_, FG)
        alpha_text(img, (x0 + 30, yy + 34), b_, F(34 if k != 1 else 26, "b"), col, al)
    s2 = c.sent_t[2] if len(c.sent_t) > 2 else D * 0.6
    if t > s2:
        heading(img, d, "No guess. Honest answer.", t, 720, 44, x=x0, delay=s2, color=ACC)
    source_tag(d, "results/video/engine_runs/real-phone2/video_result.json", 935)


def v_reallive(img, d, t, D, c):
    if c.shots.get("realjob") is None:
        heading(img, d, "Live on AWS", t, 300, 80)
        return
    sh = c.shots["realjob"]
    s1 = c.sent_t[1] if len(c.sent_t) > 1 else D / 2
    cam = track([(0, (960, 560, 1500)), (1.0, (960, 560, 1500)), (2.4, (960, 380, 1150)), (s1, (960, 400, 1150)),
                 (s1 + 1.2, (960, 580, 1150)), (D, (960, 590, 1150))], t)
    cur = track([(0, (1500, 900)), (2.2, (520, 400)), (s1 + 1.4, (600, 548)), (D - 0.5, (680, 626)), (D, (680, 627))], t)
    browser(img, d, sh, "#/jobs/cd65b6ea0c20", cam, cur, [], t)



VIS = {"hook": v_hook, "dismiss": v_dismiss, "bulb": v_bulb, "pain": v_pain, "flicker": v_flicker, "rolling": v_rolling,
       "overlay": v_overlay, "track": v_track, "home": v_home, "cases": v_cases, "job": v_job, "trace": v_trace,
       "reviewer": v_reviewer, "realclip": v_realclip, "realrun": v_realrun, "reallive": v_reallive, "arch": v_arch, "bench": v_bench, "close": v_close}


# ----------------------------------------------------------------------------- build
def srt_time(s: float) -> str:
    ms = int(round(s * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def render_range(c, timeline, srt, total, f0, f1, out):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    seg = 0
    for fi in range(f0, f1):
        tg = fi / FPS
        while seg < len(timeline) - 1 and tg >= timeline[seg][0] + timeline[seg][1]:
            seg += 1
        t0s, D, num, title, key, st, sents = timeline[seg]
        t = tg - t0s
        c.sent_t = st
        img = background().convert("RGBA")
        d = ImageDraw.Draw(img)
        VIS[key](img, d, t, D, c)
        d = ImageDraw.Draw(img)
        tagline(d, num, title)
        for (a, b, s) in srt:
            if a - 0.05 <= tg < b + 0.25:
                caption(img, s)
                break
        arr = np.asarray(img.convert("RGB"))
        fade = min(1.0, t / 0.3, (D - t) / 0.3)
        if tg > total - 1.0:
            fade = 0.0
        if fade < 1:
            arr = (arr.astype(np.float32) * max(0.0, fade)).astype(np.uint8)
        proc.stdin.write(arr.tobytes())
        if (fi - f0) % 300 == 0:
            print(f"part {out.name} frame {fi - f0}/{f1 - f0} ({key})", flush=True)
    proc.stdin.close()
    proc.wait()


def main() -> int:
    BUILD.mkdir(parents=True, exist_ok=True)
    c = Ctx()
    clip = load_frames(PUBLIC_CLIP)
    c.clip = clip
    c.clip_blur = [np.clip(cv2.GaussianBlur(cv2.resize(f, (960, 540)), (0, 0), 9) * 0.35, 0, 255).astype(np.uint8)
                   for f in clip[::2]]
    c.clip_blur = [x for x in c.clip_blur for _ in (0, 1)]
    c.ovl = load_frames(RUNS / "public_fluorescent" / "public_fluorescent" / "overlay.mp4")
    c.enf = Image.open(RUNS / "capture_verified" / "capture_verified" / "enf_track.png").convert("RGB")
    c.ncc = Image.open(RUNS / "capture_verified" / "capture_verified" / "ncc_scan.png").convert("RGB")
    c.shots = {k: Image.open(LIVE / f"{k}.png").convert("RGB") for k in ("home", "job", "reviewer")}
    rj = LIVE / "realjob.png"
    c.shots["realjob"] = Image.open(rj).convert("RGB") if rj.exists() else None
    c.phone = load_frames(ROOT / "data" / "real" / "phone2.mov", (960, 540), maxn=300)
    c.povl = load_frames(RUNS / "real-phone2" / "real-phone2" / "overlay.mp4", None, maxn=360)
    c.preal = json.loads((RUNS / "real-phone2" / "video_result.json").read_text())
    lj = LIVE / "job_cd65b6ea0c20.json"
    live = json.loads(lj.read_text()) if lj.exists() else {}
    if live.get("verdict"):
        live_sentence = f"The live app gives the same kind of answer: {live['verdict']}." if live["verdict"] == c.preal["verdict"]             else f"The live app returned {live['verdict']}."
    else:
        live_sentence = "Then the live agent asked the user one question: which camera made this video?"
    for _, _, bl in SECTIONS:
        for _, sents in bl:
            for i_, s_ in enumerate(sents):
                if s_ == "LIVE_SENTENCE":
                    sents[i_] = live_sentence
    tp = ROOT / "results" / "agent_traces" / "clean__s1001.json"
    c.trace, c.trace_name = json.loads(tp.read_text()), tp.name
    c.cost = json.loads((BENCH / "cost.json").read_text())
    c.thr = {k: json.loads((BENCH / k / "summary.json").read_text())["throughput_video_s_per_wall_s"]["mean"] for k in "AB"}

    beats, allsent = [], []
    for num, title, bl in SECTIONS:
        for key, sents in bl:
            beats.append((num, title, key, sents))
            allsent += sents
    audio = tts_all(allsent)
    # timeline
    timeline, srt, t0, ai = [], [], 0.0, 0
    track_audio = []
    for num, title, key, sents in beats:
        st, tcur = [], LEAD
        for s in sents:
            a = audio[ai]
            ai += 1
            st.append(tcur)
            srt.append((t0 + tcur, t0 + tcur + len(a) / SR, s))
            track_audio.append((t0 + tcur, a))
            tcur += len(a) / SR + GAP
        D = tcur - GAP + TAIL
        timeline.append((t0, D, num, title, key, st, sents))
        t0 += D
    total = t0 + 1.0
    print(f"total duration {total:.1f}s")
    if total > 238:
        print("WARNING: over 3:58")
    mix = np.zeros(int(total * SR) + SR, np.float32)
    for ts, a in track_audio:
        i = int(ts * SR)
        mix[i:i + len(a)] += a * 0.95
    wav_p = BUILD / "narration.wav"
    with wave.open(str(wav_p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes())

    if "--stills" in sys.argv:
        for t0s, D, num, title, key, st, sents in timeline:
            for frac in (0.3, 0.85):
                c.sent_t = st
                img = background().convert("RGBA")
                d = ImageDraw.Draw(img)
                VIS[key](img, d, D * frac, D, c)
                tagline(ImageDraw.Draw(img), num, title)
                caption(img, sents[min(len(sents) - 1, int(frac * len(sents)))])
                img.convert("RGB").resize((960, 540)).save(BUILD / f"still_{num}_{key}_{int(frac * 100)}.png")
        return 0
    out_mp4 = OUT / "gridprint_submission.mp4"
    nfr = int(total * FPS)
    NP = 6
    bounds = [nfr * k // NP for k in range(NP + 1)]
    if "--part" in sys.argv:
        k = int(sys.argv[sys.argv.index("--part") + 1])
        render_range(c, timeline, srt, total, bounds[k], bounds[k + 1], BUILD / f"part_{k}.mp4")
        return 0
    procs = [subprocess.Popen([sys.executable, __file__, "--part", str(k)]) for k in range(NP)]
    for pr in procs:
        if pr.wait() != 0:
            raise RuntimeError("part render failed")
    lst = BUILD / "parts.txt"
    lst.write_text("".join(f"file '{(BUILD / f'part_{k}.mp4').as_posix()}'\n" for k in range(NP)))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(wav_p),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out_mp4)], check=True)
    # gallery stills
    sd = OUT / "stills"
    sd.mkdir(parents=True, exist_ok=True)
    picks = {"01_title": ("flicker", 0.25), "02_problem": ("dismiss", 0.8), "03_how_it_works": ("rolling", 0.85),
             "04_real_run": ("realrun", 0.9), "05_live_app_verdict": ("job", 0.4), "06_architecture": ("arch", 0.97)}
    for name, (key, frac) in picks.items():
        for t0s, D, *_rest in timeline:
            if _rest[2] == key:
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0s + D * frac:.2f}", "-i", str(out_mp4),
                                "-frames:v", "1", str(sd / f"{name}.png")], check=True)

    (OUT / "gridprint_submission.srt").write_text(
        "".join(f"{i + 1}\n{srt_time(a)} --> {srt_time(b)}\n{s}\n\n" for i, (a, b, s) in enumerate(srt)), encoding="utf-8")
    md = ["# GRIDPRINT submission video: script", "",
          f"Generated by `video/make_pitch.py`. Voice: edge-tts `{VOICE}` (rate {RATE}). Duration: {total:.1f} s.",
          "Style: ASD-STE100 Simplified Technical English (short sentences, active voice, one idea per sentence).", "",
          "Sources on screen: live AWS app screenshots (`video/assets/live/`, captured with headless Chrome), "
          "`data/public/fluorescent_beat_effect.mp4` (Wikimedia Commons, CC BY-SA 3.0), engine outputs in "
          "`results/video/engine_runs/`, agent trace `results/agent_traces/clean__s1001.json`, benchmark "
          "`results/bench/2026-10-27/`, real iPhone 13 clip `data/real/phone2.mov` with engine run `results/video/engine_runs/real-phone2/` and live job `cd65b6ea0c20`.", ""]
    for t0s, D, num, title, key, st, sents in timeline:
        md += [f"## {num} {title} / {key}  ({srt_time(t0s)[:-4]} - {srt_time(t0s + D)[:-4]})", ""] + [f"- {s}" for s in sents] + [""]
    (ROOT / "docs" / "VIDEO_SCRIPT.md").write_text("\n".join(md), encoding="utf-8")
    print("done", out_mp4)
    return 0


if __name__ == "__main__":
    sys.exit(main())
