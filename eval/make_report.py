"""Write results/eval/<date>/<run>/summary.md, summary.json, CSVs, plots, and the failure-case gallery
(SPEC 11.6). Every table is labeled SYNTHETIC or REAL from the run metadata."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from eval.metrics import summarize  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def _pct(r: dict[str, Any]) -> str:
    if r.get("rate") is None:
        return "n/a"
    lo, hi = r["ci95"]
    return f"{100 * r['rate']:.1f}% [{100 * lo:.1f}–{100 * hi:.1f}] (k={r['k']}, n={r['n']})"


def failure_reason(r: dict[str, Any]) -> str:
    if r.get("error"):
        return f"Pipeline error: {r['error']}"
    rs = set(r.get("reasons") or [])
    if r["expected_verdict"] == "VERIFIED":
        if "SIGNAL_ABSENT" in rs or "SIGNAL_WEAK" in rs:
            return "The flicker signal was too weak in this condition."
        if "NO_UNIQUE_MATCH" in rs:
            return "The frequency track matched several reference times about equally well."
        if "EDIT_CANDIDATE" in rs:
            return "A phase break was found in an unedited clip (false edit candidate)."
        if "TRACK_TOO_SHORT" in rs:
            return "The usable track was shorter than the minimum length."
    if r["expected_verdict"] == "CONTRADICTED":
        return ("The edit did not change the flicker phase or the matched time enough to pass the thresholds. "
                "Cuts whose length is close to a whole number of flicker periods change the phase only a little.")
    if r["expected_verdict"] == "INCONCLUSIVE":
        return f"Expected INCONCLUSIVE; reasons were {sorted(rs)}."
    return f"Reasons: {sorted(rs)}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", nargs="?")
    a = ap.parse_args()
    if a.run_dir:
        runs = [Path(a.run_dir)]
    else:
        root = REPO / "results" / "eval"
        runs = [p for p in sorted(root.glob("*/*")) if (p / "clips").exists()]
    for run in runs:
        write_run(run)


def write_run(run: Path) -> None:
    meta = json.loads((run / "run_meta.json").read_text()) if (run / "run_meta.json").exists() else {}
    label = meta.get("label", "SYNTHETIC")
    recs = [json.loads(p.read_text()) for p in sorted((run / "clips").glob("*.json"))]
    out: dict[str, Any] = {"label": label, "meta": meta}
    for split in ("calibration", "test"):
        sub = [r for r in recs if r.get("split") == split]
        if sub:
            out[split] = summarize(sub)
    (run / "summary.json").write_text(json.dumps(out, indent=1, default=str))
    with (run / "clips.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "split", "condition", "class", "expected", "verdict", "band_snr_db", "time_error_s",
                    "enf_rmse_mhz", "tool_calls", "wall_s", "reasons"])
        for r in recs:
            w.writerow([r["name"], r.get("split"), r["condition"], r["class"], r["expected_verdict"], r.get("verdict"),
                        r.get("band_snr_db"), r.get("time_error_s"), r.get("enf_rmse_mhz"),
                        (r.get("agent") or {}).get("tool_calls"), r.get("wall_s"), ";".join(r.get("reasons") or [])])
    lines = [f"# Evaluation summary — {label}", "",
             f"Run: `{run.name}`, date {meta.get('date')}, planner `{meta.get('planner')}`, thresholds hash "
             f"`{meta.get('thresholds_hash')}`.", ""]
    if label == "SYNTHETIC":
        lines += ["**All results in this file are SYNTHETIC (simulator output). They are not real-world accuracy.**",
                  ""]
    for split in ("calibration", "test"):
        s = out.get(split)
        if not s:
            continue
        lines += [f"## {split} split ({label})", "", "| Metric | Value (95% CI) |", "|---|---|",
                  f"| False-CONTRADICTED rate on authentic clips | {_pct(s['false_contradicted_rate'])} |",
                  f"| VERIFIED coverage, mains-lit clips | {_pct(s['verified_coverage_mains'])} |",
                  f"| Edit detection rate | {_pct(s['edit_detection'])} |",
                  f"| Dropped-frame false alarms | {_pct(s['dropped_frame_false_alarm'])} |",
                  f"| Agent task success | {_pct(s['agent']['task_success'])} |",
                  f"| Agent recovery rate | {_pct(s['agent']['recovery_rate'])} |",
                  f"| Human-review precision | {_pct(s['agent']['human_review_precision'])} |",
                  f"| Budget exhaustion rate | {_pct(s['agent']['budget_exhaustion_rate'])} |", "",
                  "### Confusion matrix (rows: ground-truth class; columns: verdict)", "",
                  "| class | VERIFIED | CONTRADICTED | INCONCLUSIVE | none |", "|---|---|---|---|---|"]
        for c, row in s["confusion"].items():
            lines.append(f"| {c} | {row['VERIFIED']} | {row['CONTRADICTED']} | {row['INCONCLUSIVE']} | {row['None']} |")
        lines += ["", "### Per condition", "", "| condition | n | VERIFIED | INCONCLUSIVE | CONTRADICTED | success |",
                  "|---|---|---|---|---|---|"]
        for c, v in s["per_condition"].items():
            lines.append(f"| {c} | {v['n']} | {v['verified']['k']} | {v['inconclusive']['k']} | "
                         f"{v['contradicted']['k']} | {v['task_success']['k']} |")
        lines += ["", f"Time error of VERIFIED clips (s): `{json.dumps(s['time_error_verified_s'])}`",
                  f"ENF track RMSE vs ground truth (mHz): `{json.dumps(s['enf_rmse_mhz'])}`",
                  f"Edit localization error (s): `{json.dumps(s['edit_localization_error_s'])}`",
                  f"Tool calls per job: `{json.dumps(s['agent']['tool_calls_per_job'])}`", ""]
    # failure gallery
    fails = [r for r in recs if r.get("verdict") != r["expected_verdict"]]
    gal = run / "failure_gallery"
    gal.mkdir(exist_ok=True)
    lines += [f"## Failure-case gallery ({label}, {len(fails)} cases)", ""]
    for r in fails:
        lines += [f"### {r['name']}", f"- Condition: {r['condition']}; expected {r['expected_verdict']}, "
                  f"got {r.get('verdict')}.", f"- Explanation: {failure_reason(r)}"]
        for key in ("overlay_mp4", "plot_phase_residual", "plot_enf_track"):
            src = (r.get("artifacts") or {}).get(key)
            if src and Path(src).exists():
                dst = gal / f"{r['name']}__{Path(src).name}"
                shutil.copyfile(src, dst)
                lines.append(f"- {key}: [{dst.name}](failure_gallery/{dst.name})")
        lines.append("")
    (run / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    _plots(run, recs)
    print(f"wrote {run / 'summary.md'}")


def _plots(run: Path, recs: list[dict[str, Any]]) -> None:
    snr = [(str(r["condition"]), float(r["band_snr_db"])) for r in recs if r.get("band_snr_db") is not None]
    if snr:
        conds = sorted({c for c, _ in snr})
        fig, ax = plt.subplots(figsize=(9, 4))
        for i, c in enumerate(conds):
            ys = [v for cc, v in snr if cc == c]
            ax.plot([i] * len(ys), ys, "o")
        ax.set_xticks(range(len(conds)))
        ax.set_xticklabels(conds, rotation=70, fontsize=7)
        ax.set_ylabel("band SNR (dB)")
        fig.tight_layout()
        fig.savefig(run / "band_snr_by_condition.png", dpi=110)
        plt.close(fig)


if __name__ == "__main__":
    main()
