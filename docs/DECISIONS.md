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
- `analysis_max_width = 640`: frames are reduced only along the column axis (sensor rows are preserved), which reduces cost without changing row timing.
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
