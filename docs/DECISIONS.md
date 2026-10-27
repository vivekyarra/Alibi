# Decisions (SPEC 0.5)

Format: ID — date — decision — reason — alternatives considered.

## D-001 — 2026-10-26 — Python lockfile tool: uv (`uv.lock`)
- Reason: single tool for venv, lock, and sync; already on the host.
- Alternatives: pip-tools (needs separate venv management).

## D-002 — 2026-10-26 — Task runner: `scripts/tasks.py` behind the Makefile and a repo-root `make` shim
- Reason: the development host (Windows 11) has no GNU make. The `Makefile` targets call `python scripts/tasks.py <target>`; the repo-root `make` (bash) and `make.cmd` (cmd/PowerShell) shims call the same script, so `make <target>` works on Linux CI and on this host with identical behavior.
- Alternatives: installing GNU make system-wide (outside the repo folder; not allowed by the operating rules).

## D-003 — 2026-10-26 — OpenCV pin: `opencv-python-headless==5.0.0.93` (main modules only)
- Reason: V1–V4 verified on this build; prebuilt wheels exist for linux/amd64, linux/arm64 and win_amd64. No contrib module is needed.
- Alternatives: source build (slower, no benefit for stock baseline); contrib wheel (unneeded modules).

## D-004 — 2026-10-26 — Offline venv bootstrap on the development host
- Reason: during M0 the host network ran at ~300–550 B/s to PyPI (`curl -w %{speed_download}` evidence in PROGRESS M0), so `uv sync` timed out. The local `.venv` was assembled from identical wheels already installed on the host (OpenCV 5.0.0.93, PyAV 18.0.0, NumPy 2.4.3, etc.). `uv.lock` remains the source of truth for CI and containers; `make setup` runs `uv sync`.
- Alternatives: wait for the network (blocks all work).

## D-005 — 2026-10-26 — AWS region `us-east-1`
- Reason: broadest availability of Graviton `c8g`, Bedrock Claude inference profiles, and the Price List API endpoint. Grid zone is independent of AWS region.
- Alternatives: `ap-south-1` (Bedrock only through global cross-Region profiles per V6 source).

## D-006 — 2026-10-26 — Engineering constants in `config/default.yaml` → `engine`
- `saturation_cutoff = 0.98` code value and `noise_floor = 0.02` code value: values close to clipping or to the black level have no usable flicker modulation (flicker is a fractional change; clipped pixels lose it, near-black pixels are dominated by noise and quantization).
- `gap_factor = 1.5` is fixed by SPEC 8.2.5.
- `timestamp_jitter_p95_limit_ms = 4.0`: larger than one 120 Hz half period would be needed to alias; 4 ms keeps phase error under 2.5 rad at 100 Hz before the jitter model is applied, and flags files where the jitter dominates.
- `axis_ambiguity_margin = 1.2`: SNR ratio between the two image axes; under 20 % difference the choice is not reliable.
- Analysis grid `analysis_max_height = 240`, `analysis_max_width = 320`: frames are block-averaged to at most this size. A block of `b` sensor rows is assigned the mean sensor row index of the block, so timing is kept. The averaging window of `b` rows spans `b × T_ro/(N−1)`; for 1080 rows, b = 5 and T_ro = 30 ms this is 0.14 ms, attenuating a 100 Hz flicker by sinc(π·100·0.00014) > 0.999. Only valid pixels enter a block mean.
- DFT cross-check virtual grid rate `8 × f0` (800 Hz at 100 Hz): rows are averaged into virtual time bins; bins without rows (idle gaps) are zero with a mask.
- Motion: `residual_limit_px = 1.0`, `high_motion_px = 1.5`, strict mode `0.5`.
- Patches grid 8×8, `min_static_fraction = 0.8`, `min_mean_linear = 0.01`, `max_saturation_fraction = 0.05`.
- Row signal: `window_frames = 15`, `min_pixels_per_row = 4`, `detrend_order = 2`.
- Phase tracking: `window_s = 4.0`, `hop_s = 1.0` (1 s output resolution per SPEC 8.9.3), estimator agreement `0.01 Hz`.
- Matching: `exclusion_s = 10`, `segment_length_s = 30`, `segment_offset_tolerance_s = 3`, minimum claim tolerance `60 s`, minimum search `600 s`, sidecar window `3600 s`, maximum `172800 s` (48 h).
- Compression: `high_bits_per_pixel = 0.04` (bitrate / (width × height × fps)); typical messaging re-encodes are below this.
- Reason: SPEC leaves the values open; these are the simplest values that pass the synthetic acceptance tests. They are not verdict thresholds (those are in `thresholds.yaml`).

## D-007 — 2026-10-26 — Verdict thresholds are PROVISIONAL until M9
- `config/thresholds.yaml` carries `PROVISIONAL`. `scripts/final_check.py` fails while it remains (R8).

## D-008 — 2026-10-26 — Report PDF engine: WeasyPrint, with matplotlib-PDF fallback
- Reason: SPEC 7 names WeasyPrint. WeasyPrint needs Pango on Windows; when it is not importable, `report.py` writes the PDF with matplotlib's PDF backend (text + plots of the same content) and records `pdf_engine` in the result.
- Alternatives: wkhtmltopdf (unmaintained).

## D-009 — 2026-10-26 — Segmentation model for S5
- Decision: S5 uses an OpenCV `dnn`-loadable person segmentation ONNX model configured in `config/default.yaml` (`engine.segmentation.model_path`). If the model file is absent, S5 uses the S4 dynamic mask only and records `segmentation.status = "model_unavailable"` in quality metrics (no verdict effect).
- Model fetched by `scripts/fetch_models.py`; license recorded in `docs/LICENSES.md` at download time.

## D-010 — 2026-10-26 — Synthetic ENF random-walk model
- Ornstein–Uhlenbeck process at 1 s steps: `x[t+1] = x[t] − θ·x[t] + σ·N(0,1)`, θ = 0.02, σ = 0.004 Hz, around nominal. Gives slow wander of tens of mHz, the order seen in published 1 s grid frequency data (V8 sources). Used only when no Node log is given. Output is labeled `SYNTHETIC`.

## D-011 — 2026-10-26 — Timestamps without sidecar: `t_k = PTS`
- SPEC 8.4 allows this assumption; it is recorded in every result as `timing_assumption = "pts_is_first_row_exposure_start"`.

## D-012 — 2026-10-26 — Capture exposure 1 ms
- One flicker period is 10 ms at 100 Hz and 8.33 ms at 120 Hz. An exposure of 1 ms is about 1/10 of a period, so the band contrast loss from exposure integration is small (sinc attenuation ≈ 0.98 at 100 Hz).

## D-013 — 2026-10-26 — Local job store: JSON files; local queue: in-process thread
- Reason: simplest option for `make local` and tests (SPEC 10.7 allows SQLite or local JSON).

## D-014 — 2026-10-26 — Change-point detection in S11
- Decision: robust z-score of first differences of the phase residual at each frame boundary (median/MAD scale). Significance = |z|. Simplest detector that localizes a single phase jump at the frame boundary where it occurs.
- Alternatives: PELT / binary segmentation (more parameters, same result for step changes).

## D-015 — 2026-10-26 — Flicker-compensated temporal mean in S7/S8
- Problem found on synthetic data: when the W-frame window does not cancel the flicker (dropped frames, gaps, or a frame rate whose alias does not divide W), the temporal mean L̄ keeps part of the flicker. That residual is itself a sinusoid across rows and biases the per-frame phase (0.41 rad at a 5-frame gap in the first test).
- Decision: after the first fit, model the flicker gain per row, compute its W-frame mean with the same window, and correct the row signal: m' = (1 + m)·ḡ_W − 1. Two passes, then the final `cv2.solve` fit. This is part of S7–S8; the method (phase of the row flicker) is unchanged.
- Alternatives: longer windows (bias stays at gaps); temporal median (does not remove a periodic term).

## D-016 — 2026-10-26 — Readout direction from physical plausibility
- Per-frame fits cannot tell the readout direction. The wrong direction gives a track offset from f0 by the flicker alias rate (|2f0 − fps·round(2f0/fps)| at the frame level, 10 Hz for 100 Hz at 30 fps). Orientation candidates are ranked first by plausibility (|mean flicker − f0| ≤ 2 Hz, i.e. grid deviation ≤ 1 Hz) and then by band SNR.

## D-017 — 2026-10-26 — Calibration LED frequency 200 Hz
- The Capture exposure is 1 ms (D-012). A 1000 Hz LED completes one cycle inside one exposure, so its bands average out. At 200 Hz the period is 5 ms, the exposure attenuation is sinc(200 × 0.001) ≈ 0.94, and a 25 ms readout shows about 5 bands per frame ("several bands", SPEC 10.5).
- Alternatives: shorter exposure for calibration clips only (extra Capture mode, not in SPEC).

## D-018 — 2026-10-26 — Motion analysis grid and static-camera rule
- Optical flow runs on the analysis grid reduced to at most 160 px width (`engine.motion.downscale_width`), DIS preset ULTRAFAST. Motion levels are reported in analysis-grid pixels.
- Homographies are applied only when the median per-frame camera displacement exceeds `camera_static_px = 0.05` px and the accumulated displacement exceeds 1 px. Chained per-frame homographies drift on a fixed camera; warping a fixed scene only adds interpolation error.

## D-019 — 2026-10-26 — Target maximum false-CONTRADICTED rate: 1 % (written before any test data)
- SPEC 11.4.2 requires this target before test data is examined. No test split has been run when this entry is written.
- Value: 0.01 on authentic clips, in `config/default.yaml` → `evaluation.target_false_contradicted_rate`. The team must confirm or change it before the real-data calibration (H5); a change after the test run must be logged here with a reason.
- Calibration also requires zero VERIFIED results with a wrong time (|error| > 2 s) on the calibration split.

## D-020 — 2026-10-26 — Scope of the placeholder-marker scan in the final check
- `scripts/final_check.py` item 5 searches the repository for the placeholder marker of R8. Two files must contain the marker word to do their job: `eval/calibrate_thresholds.py` (writes it when calibration used SYNTHETIC data only) and `scripts/final_check.py` (searches for it). Both are excluded from the scan; everything else, including `config/` and `docs/`, is scanned. `data/`, `work/`, `results/`, `.venv/` and `node_modules/` are not repository content and are skipped.
## D-021 — 2026-10-26 — Deployment account and neutral resource names
- The owner chose the AWS account behind the local `kittu` CLI credentials for the deployment; the CLI profile `gridprint` (the only profile the code uses) now holds those credentials. Account 643700104680, region `us-east-1`.
- At the owner's request every physical AWS resource name in that account uses a neutral prefix, `aws.resource_prefix: orchard` (stacks `Orchard*`, tables `orchard-*`, IoT topic `orchard/<zone>/<node>`, dashboard, KMS alias). Code and documents keep the product name.
- Bedrock in that account returns "account is currently being verified" and the Claude models are not yet authorized (`get-foundation-model-availability`: `authorizationStatus NOT_AUTHORIZED`). Per V6, the deterministic fallback planner runs (`bedrock.enabled: false`) until access is granted; `scripts/verify_aws.py` re-checks it.

## D-022 — 2026-10-26 — Direct registration to the reference frame; continuity only on usable frames
- Found by `engine/gridprint_engine/tests/test_video.py`: on a fixed 160×120 clip the chained per-frame homographies accumulated several pixels of false drift over 1,200 frames, the warp smeared the scene, and band SNR fell from 11.5 dB to −2.6 dB (all three clips SIGNAL_ABSENT).
- Each frame is now registered directly to the middle frame (features from the reference, pyramidal LK, `findHomography` with USAC_MAGSAC); chaining is a fallback for frames whose direct registration fails. Warping is used only when the 90th-percentile corner displacement exceeds 1 px.
- Continuity (S11) skips tracks marked SIGNAL_ABSENT and uses only frames whose own fit SNR is at least 1 (0 dB) (`engine.continuity.min_frame_snr`). Without this, noise-level phases produced edit candidates on clips with no signal.

## D-023 — 2026-10-26 — Continuity: two-sided line fits replace single frame differences
- Found by the video integration test: a re-timed 1 s cut gave a true phase jump of 0.44 rad at the cut, but the single-difference detector (D-014) reached only z = 3.8 because per-frame phase noise was about 0.1 rad.
- New detector: at each frame boundary, fit a line to the phase on each side (frames within `engine.continuity.jump_window_s` = 1 s, at least 8 frames per side), evaluate both at the boundary, and take the wrapped difference as the jump. Its standard error comes from the two fits; z = |jump|/σ. Local maxima within ±1 s are the change points. Thresholds `edit_significance_sigma` and `edit_min_rad` stay in `thresholds.yaml`.
- Gap rule unchanged: a boundary with an S1 gap whose jump is not significant is DROPPED_FRAMES_EXPLAINED.

## D-024 — 2026-10-27 — Worker instance size within the account vCPU quota
- The deployment account has an on-demand standard vCPU quota of 8 (`service-quotas get-service-quota L-1216C47A`). The ASG could not launch `c8g.2xlarge` (8 vCPU) because another 2-vCPU instance already runs in the account ("You have requested more vCPU capacity than your current vCPU limit of 8").
- Workers now use `c8g.xlarge` (4 vCPU, Graviton4) with at most one instance (`aws.worker_instance_type`, `aws.worker_max_instances`). A quota increase request (H1) restores the default sizes. The benchmark protocol (Part 12) still specifies equal-vCPU pairs and runs separately.
