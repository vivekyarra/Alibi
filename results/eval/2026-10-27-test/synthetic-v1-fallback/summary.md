# Evaluation summary — SYNTHETIC

Run: `synthetic-v1-fallback`, date 2026-10-27-test, planner `fallback`, thresholds hash `0161b96f77d3e925`.

**All results in this file are SYNTHETIC (simulator output). They are not real-world accuracy.**

## test split (SYNTHETIC)

| Metric | Value (95% CI) |
|---|---|
| False-CONTRADICTED rate on authentic clips | 0.0% [0.0–18.4] (k=0, n=17) |
| VERIFIED coverage, mains-lit clips | 75.0% [50.5–89.8] (k=12, n=16) |
| Edit detection rate | 20.0% [3.6–62.4] (k=1, n=5) |
| Dropped-frame false alarms | 0.0% [0.0–79.3] (k=0, n=1) |
| Agent task success | 68.2% [47.3–83.6] (k=15, n=22) |
| Agent recovery rate | 33.3% [6.1–79.2] (k=1, n=3) |
| Human-review precision | 100.0% [34.2–100.0] (k=2, n=2) |
| Budget exhaustion rate | 0.0% [0.0–14.9] (k=0, n=22) |

### Confusion matrix (rows: ground-truth class; columns: verdict)

| class | VERIFIED | CONTRADICTED | INCONCLUSIVE | none |
|---|---|---|---|---|
| authentic-with-mains-light | 12 | 0 | 4 | 0 |
| authentic-without-mains-light | 0 | 0 | 1 | 0 |
| edited | 2 | 2 | 1 | 0 |
| synthetic | 0 | 0 | 0 | 0 |

### Per condition

| condition | n | VERIFIED | INCONCLUSIVE | CONTRADICTED | success |
|---|---|---|---|---|---|
| camera_motion | 1 | 1 | 0 | 0 | 1 |
| clean | 1 | 1 | 0 | 0 | 1 |
| clock_ppm | 1 | 1 | 0 | 0 | 1 |
| cols_axis | 1 | 1 | 0 | 0 | 1 |
| cut_0p5s | 1 | 1 | 0 | 0 | 0 |
| cut_1s | 1 | 1 | 0 | 0 | 0 |
| cut_2s | 1 | 0 | 1 | 0 | 0 |
| daylight_partial | 1 | 1 | 0 | 0 | 1 |
| dropped_frames | 1 | 1 | 0 | 0 | 1 |
| hdr | 1 | 0 | 1 | 0 | 0 |
| insert_other_time | 1 | 0 | 0 | 1 | 1 |
| jitter | 1 | 0 | 1 | 0 | 0 |
| messaging_compression | 1 | 1 | 0 | 0 | 1 |
| moving_objects | 1 | 1 | 0 | 0 | 1 |
| no_mains_light | 1 | 0 | 1 | 0 | 1 |
| no_sidecar | 1 | 1 | 0 | 0 | 1 |
| noisy | 1 | 1 | 0 | 0 | 1 |
| reorder | 1 | 0 | 0 | 1 | 1 |
| rotation_meta | 1 | 1 | 0 | 0 | 1 |
| short_readout_long_expo | 1 | 1 | 0 | 0 | 1 |
| weak_flicker | 1 | 0 | 1 | 0 | 0 |
| web_compression | 1 | 0 | 1 | 0 | 0 |

Time error of VERIFIED clips (s): `{"n": 14, "mean": 96.05530772890363, "median": 0.1567763090133667, "p95": 470.26410706043197, "max": 1342.181851387024}`
ENF track RMSE vs ground truth (mHz): `{"n": 16, "mean": 30.435116222759106, "median": 2.0459228070855087, "p95": 202.64355585146734, "max": 277.78156740840694}`
Edit localization error (s): `{"n": 1, "mean": 1478.0666666660002, "median": 1478.0666666660002, "p95": 1478.0666666660002, "max": 1478.0666666660002}`
Tool calls per job: `{"n": 22, "mean": 10.045454545454545, "median": 10.0, "p95": 11.95, "max": 13.0}`

## Failure-case gallery (SYNTHETIC, 7 cases)

### cut_0p5s__s1161
- Condition: cut_0p5s; expected CONTRADICTED, got VERIFIED.
- Explanation: The edit did not change the flicker phase or the matched time enough to pass the thresholds. Cuts whose length is close to a whole number of flicker periods change the phase only a little.
- overlay_mp4: `cut_0p5s__s1161__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [cut_0p5s__s1161__phase_residual.png](failure_gallery/cut_0p5s__s1161__phase_residual.png)
- plot_enf_track: [cut_0p5s__s1161__enf_track.png](failure_gallery/cut_0p5s__s1161__enf_track.png)

### cut_1s__s1171
- Condition: cut_1s; expected CONTRADICTED, got VERIFIED.
- Explanation: The edit did not change the flicker phase or the matched time enough to pass the thresholds. Cuts whose length is close to a whole number of flicker periods change the phase only a little.
- overlay_mp4: `cut_1s__s1171__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [cut_1s__s1171__phase_residual.png](failure_gallery/cut_1s__s1171__phase_residual.png)
- plot_enf_track: [cut_1s__s1171__enf_track.png](failure_gallery/cut_1s__s1171__enf_track.png)

### cut_2s__s1181
- Condition: cut_2s; expected CONTRADICTED, got INCONCLUSIVE.
- Explanation: The edit did not change the flicker phase or the matched time enough to pass the thresholds. Cuts whose length is close to a whole number of flicker periods change the phase only a little.
- overlay_mp4: `cut_2s__s1181__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [cut_2s__s1181__phase_residual.png](failure_gallery/cut_2s__s1181__phase_residual.png)
- plot_enf_track: [cut_2s__s1181__enf_track.png](failure_gallery/cut_2s__s1181__enf_track.png)

### hdr__s1211
- Condition: hdr; expected VERIFIED, got INCONCLUSIVE.
- Explanation: Reasons: ['HDR_UNSUPPORTED']

### jitter__s1041
- Condition: jitter; expected VERIFIED, got INCONCLUSIVE.
- Explanation: The frequency track matched several reference times about equally well.
- overlay_mp4: `jitter__s1041__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [jitter__s1041__phase_residual.png](failure_gallery/jitter__s1041__phase_residual.png)
- plot_enf_track: [jitter__s1041__enf_track.png](failure_gallery/jitter__s1041__enf_track.png)

### weak_flicker__s1021
- Condition: weak_flicker; expected VERIFIED, got INCONCLUSIVE.
- Explanation: The flicker signal was too weak in this condition.
- overlay_mp4: `weak_flicker__s1021__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_enf_track: [weak_flicker__s1021__enf_track.png](failure_gallery/weak_flicker__s1021__enf_track.png)

### web_compression__s1091
- Condition: web_compression; expected VERIFIED, got INCONCLUSIVE.
- Explanation: The frequency track matched several reference times about equally well.
- overlay_mp4: `web_compression__s1091__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [web_compression__s1091__phase_residual.png](failure_gallery/web_compression__s1091__phase_residual.png)
- plot_enf_track: [web_compression__s1091__enf_track.png](failure_gallery/web_compression__s1091__enf_track.png)
