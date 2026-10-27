"""Stage S15 — report: JSON (AnalysisResult) + HTML + PDF (SPEC 8.16, DECISIONS D-008)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402

from gridprint_engine.enf import reference_window_mean  # noqa: E402
from gridprint_engine.schemas import AnalysisResult  # noqa: E402

if TYPE_CHECKING:
    from gridprint_engine.pipeline import Job

TEMPLATES = Path(__file__).parent / "templates"

ICONS = {"VERIFIED": "✓", "CONTRADICTED": "!", "INCONCLUSIVE": "?"}
VERDICT_TEXT = {
    "VERIFIED": "A grid signal is present and matches the reference log at one time. No significant edit "
                "evidence was found.",
    "CONTRADICTED": "A grid signal is present and it conflicts with the claim or shows an internal break that "
                    "frame timestamps do not explain.",
    "INCONCLUSIVE": "The analysis could not reach a result. This alone does not mean the video is fake.",
}
REASON_TEXT = {
    "SIGNAL_ABSENT": "No usable flicker signal was found. This is not evidence of a fake.",
    "SIGNAL_WEAK": "The flicker signal is weak.",
    "READOUT_FROM_SIDECAR": "Readout time came from the Capture sidecar.",
    "READOUT_FROM_PROFILE": "Readout time came from a calibrated camera profile.",
    "READOUT_ESTIMATED": "Readout time was estimated from the video (lower confidence).",
    "READOUT_UNKNOWN": "Readout time is unknown, so row timing cannot be modeled.",
    "HDR_UNSUPPORTED": "HDR video is not supported.",
    "TRANSFER_ASSUMED": "The color transfer was not stated; BT.709 was assumed.",
    "TRACK_TOO_SHORT": "The frequency track is too short for a reliable match.",
    "NO_REFERENCE_COVERAGE": "No reference grid data covers the search window.",
    "NO_UNIQUE_MATCH": "The track does not match one time clearly.",
    "MATCH_OK": "The track matches the reference log at one time.",
    "CLAIM_TIME_MISMATCH": "The matched time does not agree with the claimed time.",
    "CLAIM_TIME_MATCH": "The matched time agrees with the claimed time.",
    "EDIT_CANDIDATE": "The flicker phase breaks at a point that frame timestamps do not explain.",
    "SEGMENT_OFFSET_INCONSISTENT": "Different parts of the video match different reference times.",
    "DROPPED_FRAMES_EXPLAINED": "Frame gaps were found; the flicker phase across them is consistent (not an edit).",
    "HIGH_MOTION": "The scene or camera moves a lot.",
    "HIGH_COMPRESSION": "The file is strongly compressed.",
    "TIMESTAMP_JITTER_HIGH": "Frame timestamps are irregular.",
    "AXIS_AMBIGUOUS": "The sensor row direction could not be determined with confidence.",
    "FACE_REGION_ANOMALY_EXPERIMENTAL": "Experimental: face regions show a different flicker amplitude.",
    "REVIEWER_APPROVED": "A human reviewer approved this result.",
    "REVIEWER_REJECTED": "A human reviewer rejected the CONTRADICTED result.",
    "USER_INPUT_REQUESTED": "The analysis asked the user for more information.",
    "BUDGET_EXHAUSTED": "The analysis reached its step limit.",
}


def _fmt(x: Any) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def _plots(job: Job, outdir: Path) -> list[dict[str, str]]:
    plots: list[dict[str, str]] = []
    tr = job.primary_track()
    if tr is None or job.timing is None:
        return plots
    # 1. ENF track vs matched reference
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(tr.track.tau_s, tr.track.enf_hz - np.nanmean(tr.track.enf_hz) if len(tr.track.enf_hz) else [],
            "o-", label="video (demeaned)")
    ms = job.matches.get(tr.id, (None,))[0]
    if ms is not None and ms.best_offset_utc is not None and len(tr.track.tau_s):
        ref_t, ref_f = job.gridlog.read(ms.zone, ms.best_offset_utc - 10, ms.best_offset_utc + tr.track.tau_s[-1] + 10)
        ref = reference_window_mean(ref_t, ref_f, ms.best_offset_utc + tr.track.tau_s, job.E["phase"]["window_s"])
        if not np.all(np.isnan(ref)):
            ax.plot(tr.track.tau_s, ref - np.nanmean(ref), "s--", label=f"reference {ms.zone} (demeaned)")
    ax.set_xlabel("time in video (s)")
    ax.set_ylabel("grid frequency deviation (Hz)")
    ax.legend()
    fig.tight_layout()
    _save(fig, outdir, "enf_track")
    plots.append({"file": "enf_track.png", "alt": "Grid frequency deviation measured from the video and the "
                  "matched reference segment, plotted against time in the video.",
                  "caption": "Measured grid frequency variation and matched reference."})
    # 2. correlation scan
    scan = job.matches.get(tr.id, (None, None, None))[2]
    if scan is not None and not np.all(np.isnan(scan.rho)):
        fig, ax = plt.subplots(figsize=(8, 2.6))
        ax.plot(scan.offsets - scan.offsets[0], scan.rho, lw=0.8)
        ax.set_xlabel("candidate start time (s from window start)")
        ax.set_ylabel("correlation")
        fig.tight_layout()
        _save(fig, outdir, "ncc_scan")
        plots.append({"file": "ncc_scan.png", "alt": "Normalized correlation between the video track and the "
                      "reference for every candidate start time in the search window.",
                      "caption": "Correlation against candidate start times."})
    # 3. phase residual with events
    c = job.continuity.get(tr.id)
    if c is not None and len(c.residual_t):
        fig, ax = plt.subplots(figsize=(8, 2.6))
        ax.plot(c.residual_t, c.residual_rad, lw=0.8, color="#333333")
        for g in job.timing.gaps:
            ax.axvline(g.t_s, color="#999999", ls=":", lw=1.5)
        for e in c.events:
            if e.kind == "EDIT_CANDIDATE":
                ax.axvline(e.t_s, color="#b00000", lw=1.5)
        ax.set_xlabel("time in video (s)")
        ax.set_ylabel("phase jump at boundary (rad)")
        fig.tight_layout()
        _save(fig, outdir, "phase_residual")
        plots.append({"file": "phase_residual.png",
                      "alt": "Estimated flicker phase jump at each frame boundary. Solid vertical lines mark edit "
                             "candidates; dotted lines mark frame-timestamp gaps.",
                      "caption": "Phase jump at frame boundaries. Solid line: edit candidate. "
                                 "Dotted line: timestamp gap."})
    # 4. per-frame band amplitude
    fig, ax = plt.subplots(figsize=(8, 2.4))
    ax.plot(job.timing.t_s, np.where(tr.fits.ok, tr.fits.amp, np.nan), lw=0.8)
    ax.set_xlabel("time in video (s)")
    ax.set_ylabel("band amplitude")
    fig.tight_layout()
    _save(fig, outdir, "band_amplitude")
    plots.append({"file": "band_amplitude.png", "alt": "Fitted flicker band amplitude for each frame.",
                  "caption": "Flicker band amplitude per frame (fractional modulation)."})
    return plots


def _save(fig: Any, outdir: Path, name: str) -> None:
    fig.savefig(outdir / f"{name}.png", dpi=110)
    fig.savefig(outdir / f"{name}.svg")
    plt.close(fig)


def render_html(r: AnalysisResult, plots: list[dict[str, str]]) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html", "j2"]))
    reasons = [{"code": x.value, "text": REASON_TEXT.get(x.value, "")} for x in r.reasons]
    q = sorted((k, v) for k, v in r.quality.items() if not isinstance(v, list | dict))
    return env.get_template("report.html.j2").render(
        r=r, icon=ICONS[r.verdict.value], verdict_text=VERDICT_TEXT[r.verdict.value], reasons=reasons,
        plots=plots, quality=q, fmt=_fmt)


def write_pdf(html: str, outdir: Path, r: AnalysisResult, plots: list[dict[str, str]]) -> tuple[Path, str]:
    pdf = outdir / "report.pdf"
    try:
        from weasyprint import HTML  # type: ignore[import-not-found]

        HTML(string=html, base_url=str(outdir)).write_pdf(str(pdf))
        return pdf, "weasyprint"
    except Exception:  # WeasyPrint missing or its native libraries unavailable (D-008)
        pass
    from matplotlib.backends.backend_pdf import PdfPages

    with PdfPages(pdf) as pp:
        fig = plt.figure(figsize=(8.27, 11.69))
        lines = [
            "GRIDPRINT analysis report", "",
            f"Verdict: {r.verdict.value} ({ICONS[r.verdict.value]})",
            f"Report state: {r.lifecycle_state.value}",
            VERDICT_TEXT[r.verdict.value], "",
            f"Estimated recording start (UTC): {r.time_estimate_iso or 'not determined'}"
            + (f" ± {r.time_uncertainty_s:.1f} s" if r.time_uncertainty_s else ""),
            f"Grid zone: {r.zone or 'not determined'}", "", "Reasons:",
            *[f"  {x.value}: {REASON_TEXT.get(x.value, '')}" for x in r.reasons], "",
            "Limitations:",
            "  Not a deepfake classifier; not cryptographic proof.",
            "  A missing signal is never evidence that a video is fake.",
            "  Time estimates exist only inside the reference log range. Location: grid zone only.",
            "  CONTRADICTED needs human review before the report is final.", "",
            f"File SHA-256: {r.file_sha256}",
            f"Engine {r.engine_version}  config {r.config_hash}  thresholds {r.thresholds_hash}",
        ]
        if r.reviewer:
            lines.append(f"Reviewer: {r.reviewer['decision']} by {r.reviewer['name']} at {r.reviewer['time_utc']}")
        fig.text(0.06, 0.96, "\n".join(lines), va="top", family="monospace", fontsize=8, wrap=True)
        pp.savefig(fig)
        plt.close(fig)
        for p in plots:
            img = plt.imread(outdir / p["file"])
            fig = plt.figure(figsize=(8.27, 4))
            plt.imshow(img)
            plt.axis("off")
            plt.title(p["caption"], fontsize=9)
            pp.savefig(fig)
            plt.close(fig)
    return pdf, "matplotlib"


def write_report(job: Job, outdir: Path) -> dict[str, str]:
    assert job.result is not None
    outdir.mkdir(parents=True, exist_ok=True)
    plots = _plots(job, outdir)
    (outdir / "plots.json").write_text(json.dumps(plots), encoding="utf-8")
    html = render_html(job.result, plots)
    (outdir / "report.html").write_text(html, encoding="utf-8")
    pdf, engine = write_pdf(html, outdir, job.result, plots)
    job.quality["pdf_engine"] = engine
    job.result.quality["pdf_engine"] = engine
    arts = {"report_html": str(outdir / "report.html"), "report_pdf": str(pdf),
            "report_json": str(outdir / "result.json")}
    for p in plots:
        arts[f"plot_{Path(p['file']).stem}"] = str(outdir / p["file"])
    return arts


def write_json(job: Job, outdir: Path) -> Path:
    assert job.result is not None
    p = outdir / "result.json"
    p.write_text(json.dumps(job.result.model_dump(mode="json"), indent=1), encoding="utf-8")
    return p


def rerender(outdir: Path, result: AnalysisResult) -> None:
    """Re-write result.json, HTML and PDF from a stored result (used after a reviewer decision)."""
    pj = outdir / "plots.json"
    plots = json.loads(pj.read_text(encoding="utf-8")) if pj.exists() else []
    (outdir / "result.json").write_text(json.dumps(result.model_dump(mode="json"), indent=1), encoding="utf-8")
    html = render_html(result, plots)
    (outdir / "report.html").write_text(html, encoding="utf-8")
    write_pdf(html, outdir, result, plots)
