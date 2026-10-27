# Evaluation summary — SYNTHETIC

Run: `synthetic-v1-fallback`, date 2026-10-27, planner `fallback`, thresholds hash `5c105287d4e1c479`.

**All results in this file are SYNTHETIC (simulator output). They are not real-world accuracy.**

## calibration split (SYNTHETIC)

| Metric | Value (95% CI) |
|---|---|
| False-CONTRADICTED rate on authentic clips | 0.0% [0.0–18.4] (k=0, n=17) |
| VERIFIED coverage, mains-lit clips | 0.0% [0.0–19.4] (k=0, n=16) |
| Edit detection rate | 0.0% [0.0–43.4] (k=0, n=5) |
| Dropped-frame false alarms | 0.0% [0.0–79.3] (k=0, n=1) |
| Agent task success | 9.1% [2.5–27.8] (k=2, n=22) |
| Agent recovery rate | 14.3% [2.6–51.3] (k=1, n=7) |
| Human-review precision | 100.0% [20.7–100.0] (k=1, n=1) |
| Budget exhaustion rate | 0.0% [0.0–14.9] (k=0, n=22) |

### Confusion matrix (rows: ground-truth class; columns: verdict)

| class | VERIFIED | CONTRADICTED | INCONCLUSIVE | none |
|---|---|---|---|---|
| authentic-with-mains-light | 0 | 0 | 16 | 0 |
| authentic-without-mains-light | 0 | 0 | 1 | 0 |
| edited | 0 | 1 | 4 | 0 |
| synthetic | 0 | 0 | 0 | 0 |

### Per condition

| condition | n | VERIFIED | INCONCLUSIVE | CONTRADICTED | success |
|---|---|---|---|---|---|
| camera_motion | 1 | 0 | 1 | 0 | 0 |
| clean | 1 | 0 | 1 | 0 | 0 |
| clock_ppm | 1 | 0 | 1 | 0 | 0 |
| cols_axis | 1 | 0 | 1 | 0 | 0 |
| cut_0p5s | 1 | 0 | 1 | 0 | 0 |
| cut_1s | 1 | 0 | 1 | 0 | 0 |
| cut_2s | 1 | 0 | 1 | 0 | 0 |
| daylight_partial | 1 | 0 | 1 | 0 | 0 |
| dropped_frames | 1 | 0 | 1 | 0 | 0 |
| hdr | 1 | 0 | 1 | 0 | 0 |
| insert_other_time | 1 | 0 | 1 | 0 | 0 |
| jitter | 1 | 0 | 1 | 0 | 0 |
| messaging_compression | 1 | 0 | 1 | 0 | 0 |
| moving_objects | 1 | 0 | 1 | 0 | 0 |
| no_mains_light | 1 | 0 | 1 | 0 | 1 |
| no_sidecar | 1 | 0 | 1 | 0 | 0 |
| noisy | 1 | 0 | 1 | 0 | 0 |
| reorder | 1 | 0 | 0 | 1 | 1 |
| rotation_meta | 1 | 0 | 1 | 0 | 0 |
| short_readout_long_expo | 1 | 0 | 1 | 0 | 0 |
| weak_flicker | 1 | 0 | 1 | 0 | 0 |
| web_compression | 1 | 0 | 1 | 0 | 0 |

Time error of VERIFIED clips (s): `{"n": 0}`
ENF track RMSE vs ground truth (mHz): `{"n": 16, "mean": 24.588760286265053, "median": 1.8429577821540974, "p95": 114.38792472782673, "max": 322.77616720003294}`
Edit localization error (s): `{"n": 0}`
Tool calls per job: `{"n": 22, "mean": 10.181818181818182, "median": 10.0, "p95": 12.0, "max": 12.0}`

## Failure-case gallery (SYNTHETIC, 20 cases)

### camera_motion__s1060
- Condition: camera_motion; expected VERIFIED, got INCONCLUSIVE.
- Explanation: The flicker signal was too weak in this condition.
- overlay_mp4: `camera_motion__s1060__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_enf_track: [camera_motion__s1060__enf_track.png](failure_gallery/camera_motion__s1060__enf_track.png)

### clean__s1000
- Condition: clean; expected VERIFIED, got INCONCLUSIVE.
- Explanation: The frequency track matched several reference times about equally well.
- overlay_mp4: `clean__s1000__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [clean__s1000__phase_residual.png](failure_gallery/clean__s1000__phase_residual.png)
- plot_enf_track: [clean__s1000__enf_track.png](failure_gallery/clean__s1000__enf_track.png)

### clock_ppm__s1110
- Condition: clock_ppm; expected VERIFIED, got INCONCLUSIVE.
- Explanation: The frequency track matched several reference times about equally well.
- overlay_mp4: `clock_ppm__s1110__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [clock_ppm__s1110__phase_residual.png](failure_gallery/clock_ppm__s1110__phase_residual.png)
- plot_enf_track: [clock_ppm__s1110__enf_track.png](failure_gallery/clock_ppm__s1110__enf_track.png)

### cols_axis__s1120
- Condition: cols_axis; expected VERIFIED, got INCONCLUSIVE.
- Explanation: The frequency track matched several reference times about equally well.
- overlay_mp4: `cols_axis__s1120__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [cols_axis__s1120__phase_residual.png](failure_gallery/cols_axis__s1120__phase_residual.png)
- plot_enf_track: [cols_axis__s1120__enf_track.png](failure_gallery/cols_axis__s1120__enf_track.png)

### cut_0p5s__s1160
- Condition: cut_0p5s; expected CONTRADICTED, got INCONCLUSIVE.
- Explanation: The edit did not change the flicker phase or the matched time enough to pass the thresholds. Cuts whose length is close to a whole number of flicker periods change the phase only a little.
- overlay_mp4: `cut_0p5s__s1160__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [cut_0p5s__s1160__phase_residual.png](failure_gallery/cut_0p5s__s1160__phase_residual.png)
- plot_enf_track: [cut_0p5s__s1160__enf_track.png](failure_gallery/cut_0p5s__s1160__enf_track.png)

### cut_1s__s1170
- Condition: cut_1s; expected CONTRADICTED, got INCONCLUSIVE.
- Explanation: The edit did not change the flicker phase or the matched time enough to pass the thresholds. Cuts whose length is close to a whole number of flicker periods change the phase only a little.
- overlay_mp4: `cut_1s__s1170__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [cut_1s__s1170__phase_residual.png](failure_gallery/cut_1s__s1170__phase_residual.png)
- plot_enf_track: [cut_1s__s1170__enf_track.png](failure_gallery/cut_1s__s1170__enf_track.png)

### cut_2s__s1180
- Condition: cut_2s; expected CONTRADICTED, got INCONCLUSIVE.
- Explanation: The edit did not change the flicker phase or the matched time enough to pass the thresholds. Cuts whose length is close to a whole number of flicker periods change the phase only a little.
- overlay_mp4: `cut_2s__s1180__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [cut_2s__s1180__phase_residual.png](failure_gallery/cut_2s__s1180__phase_residual.png)
- plot_enf_track: [cut_2s__s1180__enf_track.png](failure_gallery/cut_2s__s1180__enf_track.png)

### daylight_partial__s1150
- Condition: daylight_partial; expected VERIFIED, got INCONCLUSIVE.
- Explanation: The flicker signal was too weak in this condition.
- overlay_mp4: `daylight_partial__s1150__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_enf_track: [daylight_partial__s1150__enf_track.png](failure_gallery/daylight_partial__s1150__enf_track.png)

### dropped_frames__s1050
- Condition: dropped_frames; expected VERIFIED, got INCONCLUSIVE.
- Explanation: The frequency track matched several reference times about equally well.
- overlay_mp4: `dropped_frames__s1050__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [dropped_frames__s1050__phase_residual.png](failure_gallery/dropped_frames__s1050__phase_residual.png)
- plot_enf_track: [dropped_frames__s1050__enf_track.png](failure_gallery/dropped_frames__s1050__enf_track.png)

### hdr__s1210
- Condition: hdr; expected VERIFIED, got INCONCLUSIVE.
- Explanation: Reasons: ['HDR_UNSUPPORTED']

### insert_other_time__s1190
- Condition: insert_other_time; expected CONTRADICTED, got INCONCLUSIVE.
- Explanation: The edit did not change the flicker phase or the matched time enough to pass the thresholds. Cuts whose length is close to a whole number of flicker periods change the phase only a little.
- overlay_mp4: `insert_other_time__s1190__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [insert_other_time__s1190__phase_residual.png](failure_gallery/insert_other_time__s1190__phase_residual.png)
- plot_enf_track: [insert_other_time__s1190__enf_track.png](failure_gallery/insert_other_time__s1190__enf_track.png)

### jitter__s1040
- Condition: jitter; expected VERIFIED, got INCONCLUSIVE.
- Explanation: The frequency track matched several reference times about equally well.
- overlay_mp4: `jitter__s1040__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [jitter__s1040__phase_residual.png](failure_gallery/jitter__s1040__phase_residual.png)
- plot_enf_track: [jitter__s1040__enf_track.png](failure_gallery/jitter__s1040__enf_track.png)

### messaging_compression__s1100
- Condition: messaging_compression; expected VERIFIED, got INCONCLUSIVE.
- Explanation: The flicker signal was too weak in this condition.
- overlay_mp4: `messaging_compression__s1100__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_enf_track: [messaging_compression__s1100__enf_track.png](failure_gallery/messaging_compression__s1100__enf_track.png)

### moving_objects__s1070
- Condition: moving_objects; expected VERIFIED, got INCONCLUSIVE.
- Explanation: The frequency track matched several reference times about equally well.
- overlay_mp4: `moving_objects__s1070__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [moving_objects__s1070__phase_residual.png](failure_gallery/moving_objects__s1070__phase_residual.png)
- plot_enf_track: [moving_objects__s1070__enf_track.png](failure_gallery/moving_objects__s1070__enf_track.png)

### no_sidecar__s1010
- Condition: no_sidecar; expected VERIFIED, got INCONCLUSIVE.
- Explanation: The frequency track matched several reference times about equally well.
- overlay_mp4: `no_sidecar__s1010__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [no_sidecar__s1010__phase_residual.png](failure_gallery/no_sidecar__s1010__phase_residual.png)
- plot_enf_track: [no_sidecar__s1010__enf_track.png](failure_gallery/no_sidecar__s1010__enf_track.png)

### noisy__s1080
- Condition: noisy; expected VERIFIED, got INCONCLUSIVE.
- Explanation: The frequency track matched several reference times about equally well.
- overlay_mp4: `noisy__s1080__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [noisy__s1080__phase_residual.png](failure_gallery/noisy__s1080__phase_residual.png)
- plot_enf_track: [noisy__s1080__enf_track.png](failure_gallery/noisy__s1080__enf_track.png)

### rotation_meta__s1130
- Condition: rotation_meta; expected VERIFIED, got INCONCLUSIVE.
- Explanation: The frequency track matched several reference times about equally well.
- overlay_mp4: `rotation_meta__s1130__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [rotation_meta__s1130__phase_residual.png](failure_gallery/rotation_meta__s1130__phase_residual.png)
- plot_enf_track: [rotation_meta__s1130__enf_track.png](failure_gallery/rotation_meta__s1130__enf_track.png)

### short_readout_long_expo__s1030
- Condition: short_readout_long_expo; expected VERIFIED, got INCONCLUSIVE.
- Explanation: The flicker signal was too weak in this condition.
- overlay_mp4: `short_readout_long_expo__s1030__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_enf_track: [short_readout_long_expo__s1030__enf_track.png](failure_gallery/short_readout_long_expo__s1030__enf_track.png)

### weak_flicker__s1020
- Condition: weak_flicker; expected VERIFIED, got INCONCLUSIVE.
- Explanation: The flicker signal was too weak in this condition.
- overlay_mp4: `weak_flicker__s1020__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_enf_track: [weak_flicker__s1020__enf_track.png](failure_gallery/weak_flicker__s1020__enf_track.png)

### web_compression__s1090
- Condition: web_compression; expected VERIFIED, got INCONCLUSIVE.
- Explanation: The frequency track matched several reference times about equally well.
- overlay_mp4: `web_compression__s1090__overlay.mp4` (removed from results/ to keep the repository small: file larger than 5 MB; regenerate with eval/run_eval.py)
- plot_phase_residual: [web_compression__s1090__phase_residual.png](failure_gallery/web_compression__s1090__phase_residual.png)
- plot_enf_track: [web_compression__s1090__enf_track.png](failure_gallery/web_compression__s1090__enf_track.png)
