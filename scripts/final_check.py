"""SPEC 17.3 final stop checklist. Prints one line per item and `ALL CHECKS PASSED` only when every item holds.

Items that need the network (CI status, deployed endpoint, GridLog freshness) query them live. Nothing is
assumed: an item that cannot be checked fails.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = ["engine/gridprint_engine", "agent", "mcp_server", "api", "web/src", "node", "calibration_rig", "infra",
           "eval", "bench", "scripts", "capture-android/app/src/main"]
CODE_SUFFIX = {".py", ".ts", ".tsx", ".kt", ".c", ".h"}
STUB = re.compile(r"\bTODO\b|\bFIXME\b|NotImplementedError|pass\s+#\s*stub")
DOCS_14 = ["docs/TECHNICAL_REPORT.md", "docs/diagrams/architecture.mmd", "docs/diagrams/agent_workflow.mmd",
           "README.md", "docs/JUDGE_GUIDE.md", "docs/VIDEO_SCRIPT.md", "docs/ARCHITECTURE.md",
           "docs/RESPONSIBLE_USE.md", "docs/LICENSES.md"]


def read(p: str) -> str:
    f = ROOT / p
    return f.read_text(encoding="utf-8", errors="ignore") if f.exists() else ""


def c1_milestones() -> tuple[bool, str]:
    t = read("docs/PROGRESS.md")
    missing = [f"M{i}" for i in range(13) if not re.search(rf"^## M{i} .*ACCEPTED", t, re.M)]
    return not missing, f"not accepted: {missing}" if missing else "M0–M12 accepted"


def c2_verification() -> tuple[bool, str]:
    t = read("docs/VERIFICATION.md")
    bad = [f"V{i}" for i in range(1, 13)
           if not re.search(rf"^## V{i} .*(VERIFIED|FALLBACK)", t, re.M)
           or re.search(rf"^## V{i} .*BLOCKED-HUMAN", t, re.M)]
    return not bad, f"unresolved: {bad}" if bad else "V1–V12 resolved"


def c3_human() -> tuple[bool, str]:
    t = read("docs/HUMAN_TASKS.md")
    bad = [f"H{i}" for i in range(1, 9) if not re.search(rf"^## H{i} .*DONE", t, re.M)]
    return not bad, f"not DONE: {bad}" if bad else "H1–H8 DONE"


def c4_ci() -> tuple[bool, str]:
    try:
        out = subprocess.run(["gh", "run", "list", "--branch", "main", "--limit", "1", "--json", "conclusion,headSha"],
                             cwd=ROOT, capture_output=True, text=True, timeout=60)
        runs = json.loads(out.stdout or "[]")
    except Exception as e:
        return False, f"cannot read CI status: {e}"
    ok = bool(runs) and runs[0].get("conclusion") == "success"
    return ok, f"latest main CI: {runs[0].get('conclusion') if runs else 'none'}"


def c5_thresholds() -> tuple[bool, str]:
    thr = yaml.safe_load(read("config/thresholds.yaml")) or {}
    gen = str((thr.get("provenance") or {}).get("generated_by", ""))
    hits = []
    for p in ROOT.rglob("*"):
        rel = p.relative_to(ROOT).parts
        if p.is_file() and p.name != "SPEC.md" and not any(x.startswith(".") or x in ("node_modules", "data", "work",
                                                                                         "results") for x in rel[:-1]):
            # the two tools that write and search for the marker are excluded (DECISIONS D-020)
            skip_suffix = p.suffix in {".mp4", ".onnx", ".png", ".jar", ".pdf"}
            if p.name in ("final_check.py", "calibrate_thresholds.py") or skip_suffix:
                continue
            if "PROVISIONAL" in p.read_text(encoding="utf-8", errors="ignore"):
                hits.append(str(p.relative_to(ROOT)))
    ok = gen.startswith("eval/calibrate_thresholds.py") and not hits
    return ok, f"generated_by={gen!r}; PROVISIONAL in {hits[:5]}"


def _endpoint() -> str | None:
    m = re.search(r"^Endpoint:\s*(https?://\S+)", read("docs/JUDGE_GUIDE.md"), re.M)
    return m.group(1).rstrip("/") if m else None


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def c6_endpoint() -> tuple[bool, str]:
    ep = _endpoint()
    if not ep:
        return False, "no Endpoint: line in docs/JUDGE_GUIDE.md"
    try:
        h = _get(f"{ep}/v1/health")
        demo = json.loads(read("results/demo/latest.json") or "{}")
    except Exception as e:
        return False, f"health check failed: {e}"
    cases = demo.get("cases", [])
    ok = h.get("status") == "ok" and len(cases) == 8 and all(c.get("pass") for c in cases) \
        and demo.get("real_phone_upload") is True and demo.get("reviewer_approval") is True
    return ok, f"health={h.get('status')}; demo cases passing={sum(bool(c.get('pass')) for c in cases)}/8"


def c7_gridlog() -> tuple[bool, str]:
    ep = _endpoint()
    if not ep:
        return False, "no endpoint"
    cfg = yaml.safe_load(read("config/default.yaml"))
    zone = (cfg.get("grid") or {}).get("node_zones", ["IN"])[0]
    try:
        s = _get(f"{ep}/v1/grid/{zone}/live").get("samples", [])
    except Exception as e:
        return False, f"grid tile failed: {e}"
    age = time.time() - s[-1]["t_utc_s"] if s else float("inf")
    return age <= cfg["grid"]["freshness_limit_s"], f"newest {zone} sample age {age:.0f} s"


def c8_eval() -> tuple[bool, str]:
    runs = [p for p in (ROOT / "results" / "eval").glob("*/*") if (p / "summary.json").exists()]
    real = [p for p in runs if json.loads((p / "summary.json").read_text()).get("label") == "REAL"]
    if not real:
        return False, "no REAL evaluation results under results/eval"
    gal = max(len(list((p / "failure_gallery").glob("*"))) for p in real)
    return gal >= 10, f"REAL runs: {len(real)}; largest failure gallery entries: {gal}"


def c9_bench() -> tuple[bool, str]:
    b = ROOT / "results" / "bench"
    has = any((p / "evidence").exists() and (p / "parity.json").exists() for p in b.glob("*")) if b.exists() else False
    fallback = "COOL award not claimed" in read("docs/TECHNICAL_REPORT.md")
    return has or fallback, "bench evidence present" if has else ("fallback documented" if fallback else "missing")


def c10_traces() -> tuple[bool, str]:
    d = ROOT / "results" / "agent_traces"
    found = set()
    for p in d.glob("*.json") if d.exists() else []:
        found |= set(re.findall(r"\bB[1-6]\b", p.read_text(encoding="utf-8", errors="ignore")))
    rep = read("docs/TECHNICAL_REPORT.md")
    both = "fallback" in rep and "bedrock" in rep.lower() and "agent metrics" in rep.lower()
    missing = sorted({f"B{i}" for i in range(1, 7)} - found)
    return not missing and both, f"behaviors missing in traces: {missing}; both planners in report: {both}"


def c11_docs() -> tuple[bool, str]:
    missing = [p for p in DOCS_14 if not read(p).strip()]
    clean = json.loads(read("results/fresh_clone/latest.json") or "{}").get("passed") is True
    return not missing and clean, f"missing docs: {missing}; fresh-clone test passed: {clean}"


def c12_video() -> tuple[bool, str]:
    m = re.search(r"^Video:\s*(https?://\S+)", read("README.md"), re.M)
    dur = json.loads(read("results/video/duration.json") or "{}").get("duration_s")
    return bool(m) and dur is not None and dur <= 300, f"link={'yes' if m else 'no'}; duration_s={dur}"


def c13_stubs() -> tuple[bool, str]:
    hits = []
    for d in SHIPPED:
        for p in (ROOT / d).rglob("*") if (ROOT / d).exists() else []:
            if p.suffix in CODE_SUFFIX and "tests" not in p.parts and "test" not in p.name and p.is_file():
                if p.name == "final_check.py":
                    continue
                for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if STUB.search(line):
                        hits.append(f"{p.relative_to(ROOT)}:{i}")
    return not hits, f"stub markers: {hits[:8]}"


def c14_trace() -> tuple[bool, str]:
    rows = [r for r in read("docs/REQUIREMENTS_TRACE.md").splitlines() if r.startswith("| 3.")]
    bad = [r.split("|")[2].strip()[:40] for r in rows if "—" in r.split("|")[4] or "OPEN" in r]
    return bool(rows) and not bad, f"lines without evidence: {len(bad)}"


CHECKS: list[tuple[str, Callable[[], tuple[bool, str]]]] = [
    ("1 milestones M0–M12 accepted", c1_milestones), ("2 verification resolved", c2_verification),
    ("3 human tasks H1–H8 done", c3_human), ("4 CI green on main", c4_ci),
    ("5 calibrated thresholds, no PROVISIONAL", c5_thresholds), ("6 endpoint and demo cases", c6_endpoint),
    ("7 GridLog fresh", c7_gridlog), ("8 evaluation frozen, gallery >= 10", c8_eval),
    ("9 COOL benchmark or documented fallback", c9_bench), ("10 traces B1–B6, both planners", c10_traces),
    ("11 Part 14 docs and fresh-clone test", c11_docs), ("12 video link <= 5:00", c12_video),
    ("13 no stubs in shipped code", c13_stubs), ("14 requirements trace evidence", c14_trace),
]


def main() -> int:
    failed = 0
    for name, fn in CHECKS:
        try:
            ok, msg = fn()
        except Exception as e:  # an item that cannot be checked fails
            ok, msg = False, f"error: {type(e).__name__}: {e}"
        failed += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name} — {msg}")
    if failed:
        print(f"{failed} of {len(CHECKS)} checks failed")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
