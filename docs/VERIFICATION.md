# Verification log (SPEC Part 4)

Each entry: source URL or command, result, date, decision. Status is one of `VERIFIED`, `FALLBACK`, `BLOCKED-HUMAN`.

## V1 — OpenCV 5.x release and DNN engine option — VERIFIED (2026-10-26)
- Source: GitHub releases API `https://api.github.com/repos/opencv/opencv/releases` lists `5.0.0` (published 2026-06-06, not prerelease). PyPI `https://pypi.org/pypi/opencv-python-headless/5.0.0.93/json` lists wheels for `manylinux_2_28_aarch64`, `manylinux_2_28_x86_64`, `win_amd64`, macOS.
- Command: `.venv/Scripts/python -c "import cv2; print(cv2.__version__)"` → `5.0.0`. `cv2.getBuildInformation()` → `General configuration for OpenCV 5.0.0`, modules `calib core dnn features flann geometry highgui imgcodecs imgproc objdetect photo ptcloud python3 stereo stitching video videoio`.
- DNN engine selection: `cv2.dnn.readNet(model[, config[, framework[, engine]]])`; constants `cv2.dnn.ENGINE_AUTO=3`, `ENGINE_CLASSIC=1`, `ENGINE_NEW=2`, `ENGINE_ORT=4` exist in the pinned build.
- Decision: pin `opencv-python-headless==5.0.0.93` for linux/amd64 and linux/arm64 images (prebuilt manylinux wheels; no source build needed). Engine selection uses the default (`ENGINE_AUTO`) unless a DECISIONS entry says otherwise.

## V2 — `findHomography` with `USAC_MAGSAC` — VERIFIED (2026-10-26)
- Command: `hasattr(cv2,'USAC_MAGSAC')` → `True` (value 38); `cv2.findHomography(srcPoints, dstPoints[, method[, ransacReprojThreshold[, mask[, maxIters[, confidence]]]]])`. Declared in the top-level `cv2` namespace (`cv2/__init__.pyi`); in the C++ tree it is part of the 5.x `geometry`/`calib` split (both modules present in build info).
- Decision: use `cv2.findHomography(..., cv2.USAC_MAGSAC, ...)`. Fallbacks `USAC_DEFAULT` (32) and `RANSAC` (8) also present.

## V3 — `DISOpticalFlow` and `calcOpticalFlowPyrLK` in core build — VERIFIED (2026-10-26)
- Command: `cv2.DISOpticalFlow_create([, preset])` and `cv2.calcOpticalFlowPyrLK` exist in `opencv-python-headless` (main modules only, no contrib). Module `video` is listed in build info.
- Decision: use both as specified.

## V4 — `FaceDetectorYN` (YuNet) and model license — VERIFIED (API) / model file BLOCKED by network
- Command: `cv2.FaceDetectorYN.create(model, config, input_size[, score_threshold[, nms_threshold[, top_k[, backend_id[, target_id]]]]])` exists.
- Model: `face_detection_yunet_2023mar.onnx` from the `opencv/opencv_zoo` repository, MIT license (opencv_zoo `models/face_detection_yunet/LICENSE`). The download is done by `make setup` (`scripts/fetch_models.py`) with a pinned SHA-256 recorded after the first successful download. Without the file, S12 reports `facecheck.status = "model_unavailable"` and adds no reason code.

## V5 — COOL (Cloud-Optimized OpenCV Library) — BLOCKED-HUMAN (partial facts recorded)
- Sources (search results, 2026-10-26): AWS Marketplace listings "Cloud Optimized OpenCV For Graviton3" (`https://aws.amazon.com/marketplace/pp/prodview-5b2boxpyztidw`) and "Cloud Optimized OpenCV For AWS Graviton4" (`https://aws.amazon.com/marketplace/pp/prodview-fdvbfiewzuehs`); OpenCV page `https://opencv.org/cool/`; AWS blog "Accelerating OpenCV on Graviton: the COOL framework".
- Facts from these sources: distributed as an AWS Marketplace AMI (Ubuntu 24.04 LTS, precompiled OpenCV based on OpenCV 5, Arm KleidiCV optimizations), separate listings for Graviton3 and Graviton4.
- NOT yet verified (direct page fetch failed: network/Cloudflare): exact version string, instance-type list, license/EULA text, accelerated function list, runtime proof method.
- Runtime proof plan (implemented in `bench/cool_evidence.py`): `cv2.getBuildInformation()` text, `cv2.__file__` and loaded shared-library paths from `/proc/self/maps`, and a `perf record` capture of the hot stages, all saved under `results/bench/<date>/evidence/`.
- Additional facts (infra agent, Marketplace listing fetched 2026-10-26): Graviton4 listing says Ubuntu 24.04 LTS, "Built on OpenCV 5.0", Arm KleidiCV, compatible families c8g/m8g/r8g, Python venvs under `/opt/cool/venvs/` (3.10, 3.11, 3.12), C++ SDK under `/opt/cool/cpp_sdk/lib`, hourly software fee, 7-day trial. A separate COOL Docker listing exists (not opened). A Graviton5 listing targets c9g/m9g with OpenCV 5.1.0 (not used).
- Still unverified: whether COOL libraries load inside the Debian-based `python:3.11-slim` container (`bench/run_remote.md` step C3 tests this and gives a native fallback).
- Needs H1 (Marketplace subscription). Until then the COOL award is not claimed.

## V6 — Claude with tool use on Amazon Bedrock — BLOCKED-HUMAN (partial)
- Sources: AWS ML blog "Access Anthropic Claude models in India on Amazon Bedrock with global cross-Region inference" (`https://aws.amazon.com/blogs/machine-learning/access-anthropic-claude-models-in-india-on-amazon-bedrock-with-global-cross-region-inference`) names the global inference profile ID `global.anthropic.claude-sonnet-4-6`. Anthropic docs `https://platform.claude.com/docs/en/build-with-claude/claude-on-amazon-bedrock` state newer models need an inference profile ID and that tool use is supported through the Converse/Messages APIs.
- 2026-10-26, profile `gridprint` (account 643700104680, us-east-1): `aws bedrock list-inference-profiles` lists Claude profiles (e.g. `us.anthropic.claude-sonnet-5`, `us.anthropic.claude-haiku-4-5-20251001-v1:0`), but `converse` returns `ValidationException: Operation not allowed` (us-east-1, us-west-2) and `AccessDeniedException: Your account is currently being verified` (eu-central-1); `get-foundation-model-availability` reports `authorizationStatus: NOT_AUTHORIZED`. The second account (profile `vivek`) returns `INVALID_PAYMENT_INSTRUMENT`.
- Status: FALLBACK applied for now (deterministic planner, documented in D-021). Re-check after AWS completes the account verification and model access is granted (H1).
- Decision: `config/default.yaml` holds `bedrock.model_id: global.anthropic.claude-sonnet-4-6`, `bedrock.enabled: false`. The deterministic fallback planner runs until H1 completes and `scripts/verify_aws.py` confirms the model with `bedrock:ListInferenceProfiles` and a one-call Converse test.

## V7 — Android Camera2 capabilities on test devices — BLOCKED-HUMAN (method ready)
- Keys exist in the Android API reference (`CaptureRequest.CONTROL_AE_MODE`, `CONTROL_AE_ANTIBANDING_MODE_OFF`, `SENSOR_EXPOSURE_TIME`, `CaptureResult.SENSOR_ROLLING_SHUTTER_SKEW`, `SENSOR_TIMESTAMP`, `CameraCharacteristics.SENSOR_INFO_TIMESTAMP_SOURCE`). Per-device support must be checked on hardware. The Capture app writes a capability report on first run (H4). Fallback: calibration-rig readout (Part 10.5).

## V8 — Public grid-frequency data — VERIFIED (partial)
- GB: NESO "System Frequency" data portal (`https://www.neso.energy/data-portal/system-frequency-data`) publishes historic system frequency at 1 s resolution, monthly CSV, GMT, from 2014. Licence: NESO Open Data Licence (to be confirmed on download by `node/ingest/import_neso.py` header check).
- Multi-zone research data: "Database of Power Grid Frequency Measurements" (`https://arxiv.org/abs/2006.01771`) — 1 s resolution, twelve synchronous areas; historic, not live.
- India (Grid-India), TransnetBW, Fingrid: not verified (no 1 s source found). Fallback for zone `IN`: GRIDPRINT Node data only.
- Decision: implement `node/ingest/import_neso.py` for zone `GB`; all other zones use Node data.

## V9 — Per-frame PTS from PyAV — VERIFIED (2026-10-26)
- Command: made a VFR H.264 MP4 with `ffmpeg ... -vf setpts=... -fps_mode vfr`; PyAV 18.0.0 gives `stream.time_base = 1/15360` and per-frame `frame.pts` `[0, 512, ..., 4608, 6656, ...]` showing the injected gap. `frame.rotation` attribute exists.
- Decision: PyAV primary; `ffprobe -show_frames` fallback implemented in `io.py`.

## V10 — Color transfer metadata — VERIFIED (2026-10-26)
- Command: encoded with `-x264-params transfer=<t>`; PyAV `frame.color_trc` and `codec_context.color_trc` returned `bt709→1`, `arib-std-b67 (HLG)→18`, `smpte2084 (PQ)→16`, `iec61966-2-1 (sRGB)→13`; ffprobe `color_transfer` gives the same names. Value `2` = unspecified.
- Decision: 16/18 → `HDR_UNSUPPORTED`; 1/6/13/14/15 → SDR linearization; unspecified/other → BT.709 with `TRANSFER_ASSUMED`.

## V11 — GPS PPS with ESP32 and MQTT/TLS to IoT Core — BLOCKED-HUMAN
- Needs hardware (H2). Firmware uses ESP-IDF GPIO interrupt + `esp_timer_get_time()` for PPS and zero-cross capture, and `esp-mqtt` with TLS client certificates. Validation: `node/selftest.md` checklist + `node/ingest/data_quality.py`.

## V12 — On-demand prices — BLOCKED-HUMAN
- Needs AWS account (H1). `bench/prices.py` reads prices through the AWS Price List API (`pricing:GetProducts`, endpoint region `us-east-1`) and stores the raw response with date in `results/bench/<date>/prices.json`. No price is written by hand.

## Extra — CI action versions — VERIFIED (2026-10-26)
- Command: `curl https://api.github.com/repos/<repo>/releases/latest` → `actions/checkout v7.0.1`, `astral-sh/setup-uv v10.3.2`, `actions/setup-node v7.1.0`, `aquasecurity/trivy-action v0.36.0`. Pinned in `.github/workflows/ci.yml`.
