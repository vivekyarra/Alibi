# GRIDPRINT — Build Specification

**Version:** 1.0 (frozen)
**Target:** OpenCV AI Competition 2026, powered by AWS — Overall prize, Best Use of COOL Award, Agentic Vision Award.
**Audience:** the coding agent (Claude Code) and the human team.

This file is the single source of truth. If any other file, comment, or message conflicts with this file, this file wins.

---

## PART 0 — OPERATING RULES FOR THE CODING AGENT (read first, obey always)

0.1 **Build GRIDPRINT exactly as defined here.** Do not build a different product, a simpler product, or a "demo version" in place of the real one.

0.2 **Read this whole file before writing code.** At the start of every session, re-read Part 0, Part 2, Part 15 (milestones) and Part 17 (stop rules). Then read `docs/PROGRESS.md` to find where work stopped.

0.3 **Scope lock.** Build only what this file specifies. If you have an idea that is not in this file, do not build it. Append it to `docs/IDEAS.md` and continue.

0.4 **Do not change the product.** Do not rename components, verdicts, modes, or reason codes. Do not replace the core method (grid frequency read from rolling-shutter light flicker) with another method, such as an AI deepfake classifier. Do not add "extra" detectors that produce verdicts.

0.5 **Ambiguity rule.** If this file does not specify an implementation detail, choose the simplest option that satisfies the acceptance criteria. Record it in `docs/DECISIONS.md` with: date, decision, reason, alternatives considered. Do not stop to ask the human.

0.6 **Verify-first rule.** Part 4 lists facts that are NOT yet verified (API names, service availability, data sources). Check each against official documentation or by running code before you rely on it. Record the result in `docs/VERIFICATION.md`. If a fact is false, use the fallback written in Part 4. Never use an API name, flag, or service you have not verified.

0.7 **Human-blocked rule.** Some tasks need a human (Part 16): hardware, physical recording, AWS account access, the video. For each, write exact step-by-step instructions in `docs/HUMAN_TASKS.md`, mark it `BLOCKED-HUMAN`, and continue all other work. Build validation scripts that check the human's output when it arrives.

0.8 **No partial stops.** Work milestone by milestone (Part 15). A milestone is done only when its acceptance criteria pass and the evidence is linked in `docs/PROGRESS.md`. Do not declare the project done, "mostly done," or "ready for polish" before Part 17 is fully true.

0.9 **Never fabricate.** No invented numbers, benchmark results, accuracy figures, citations, API names, test outcomes, or screenshots. Every number that appears in the README, technical report, UI copy, or video script must be produced by a script in this repository and stored under `results/`. Next to each number, record its source file (see Part 14.3).

0.10 **Never fake functionality.** No mocked outputs presented as real. No hardcoded verdicts. No canned agent traces. Demo cases must run through the real deployed pipeline. Test doubles are allowed only inside `tests/` and must never be reachable from production code paths.

0.11 **Keep progress files current.** Update `docs/PROGRESS.md` after every completed task: current milestone, done, next, blocked, evidence links.

0.12 **Stop only per Part 17.** If everything except human tasks is done, write the PAUSED message defined in Part 17 and end the session. That is a pause, not completion.

0.13 **Language of all user-facing text:** plain, short, active sentences (ASD-STE100 style). No hype words.

---

## PART 1 — PRODUCT DEFINITION (frozen)

### 1.1 One line

GRIDPRINT proves that a video is real, from the flicker of the lights in the room.

### 1.2 The real-world pain

- AI tools can make fake video quickly and cheaply.
- Because of this, people now say that **real** video is fake. Researchers call this the "liar's dividend." Real evidence of abuse, crime, or accidents loses its value.
- **News verification desks** get video from unknown sources and must decide fast if it is real.
- **Courts and lawyers** get video evidence. One side says "this is AI," and the other side cannot easily prove it is not.
- **Insurance fraud teams** get video of damage and accidents and must check for edits.
- **Human-rights documenters and citizen reporters** record abuse. Officials then say the video is fake.
- Current tools fail in two ways. AI detectors guess, and new generators defeat them. Metadata and signatures (for example C2PA Content Credentials) can be removed by a re-upload or a screen recording.
- **Gap:** no tool reads a physical proof that stays inside the pixels.

### 1.3 The physical principle

1. Most indoor lights use mains (grid) power. They flicker at two times the grid frequency: 100 Hz on 50 Hz grids (India, Europe), 120 Hz on 60 Hz grids (USA).
2. The grid frequency is never exactly nominal. It changes by small amounts every second as power demand changes. This changing frequency is the Electric Network Frequency (ENF). The ENF pattern is shared by all points on one synchronous grid zone and is unique in time.
3. Most phone cameras use a rolling shutter: they read the image one sensor row at a time. So the flicker appears as faint horizontal bands in the video, with each row sampling a different instant.
4. GRIDPRINT extracts the ENF track from these bands and compares it with a recorded reference log of the real grid.

### 1.4 What GRIDPRINT reports

- **When** the video was recorded (only within the time range covered by the reference log).
- **Whether** parts were cut, inserted, or reordered (edit evidence).
- **Whether** the light in the video carries a real grid signal.
- **Which grid zone** the recording matches. NEVER a city, address, or finer location.

### 1.5 Verdicts (exactly three — never more, never fewer)

| Verdict | Meaning |
|---|---|
| `VERIFIED` | A grid signal is present, it matches the reference log uniquely, no significant edit evidence exists, and (if a claimed time was given) the matched time agrees with the claim. |
| `CONTRADICTED` | A grid signal is present AND (it conflicts with a claimed time, OR it shows a significant internal discontinuity that frame timestamps do not explain, OR different segments match inconsistent reference times). Requires human approval before the report is final. |
| `INCONCLUSIVE` | No usable grid signal, or no reference coverage, or no unique match, or another limit in Part 8 (stage S13). |

Report lifecycle states (these are NOT verdicts): `DRAFT` → `PENDING_REVIEW` (only for `CONTRADICTED`) → `FINAL`. A `CONTRADICTED` report is never shown as `FINAL` without a recorded human approval. If the reviewer rejects, the report becomes `FINAL` with verdict `INCONCLUSIVE` and reason `REVIEWER_REJECTED`, and the reviewer note is stored.

### 1.6 Product parts

| Part | What it does | Primary users |
|---|---|---|
| **GRIDPRINT Capture** (Android app) | Records video with settings that keep the flicker bands strong. Writes a sidecar file with sensor timing. Shows a live band-strength meter. | Journalists, rights documenters, insurance inspectors |
| **GRIDPRINT Verify** (web app) | Checks any uploaded video. Shows verdict, evidence, band overlay, agent trace, and a downloadable report. Includes the reviewer approval screen. | Verification desks, lawyers, fraud teams, judges of this competition |
| **GRIDPRINT Node** (hardware + firmware) | Measures grid frequency every second with GPS time and sends it to AWS. | Background reference |
| **GRIDPRINT Engine** (AWS) | Runs the OpenCV 5 analysis on AWS Graviton with COOL. | Background |
| **GRIDPRINT Agent** | Plans and adapts the analysis using Engine tools. Requests user input or human review. | Background |
| **Reference Store** | Stores grid frequency logs per zone and second. | Background |
| **Evaluation harness** | Measures accuracy, failure rates, and agent performance on real and synthetic data. | Team, judges |

### 1.7 Positioning (use in all docs)

- **Capture is the core product:** proof sealed at the moment of recording.
- **Verify is a best-effort check** for any other video. Many ordinary videos return `INCONCLUSIVE`, because phone "anti-banding" hides the flicker. The UI and docs must explain this plainly.

### 1.8 What GRIDPRINT is NOT

- Not a deepfake classifier. It does not judge whether pixels "look AI-made."
- Not a face recognition or identity system.
- Not a location tracker below grid-zone level.
- Not cryptographic proof.
- A missing signal is never evidence that a video is fake.

---

## PART 2 — NON-NEGOTIABLE RULES (enforced in code and CI)

| ID | Rule | Enforcement |
|---|---|---|
| R1 | Only the three verdicts in 1.5. | `Verdict` enum; tests. |
| R2 | Absence of signal never yields `CONTRADICTED`. | Verdict logic tests. |
| R3 | `CONTRADICTED` requires recorded human approval before `FINAL`. | API + agent policy + tests. |
| R4 | No location output finer than grid zone. | Schema has no location field other than `zone`. |
| R5 | Forbidden claims in user-facing text: "cryptographic", "impossible to fake", "detects all deepfakes", "100% accurate", "proves the video is fake", "guaranteed". | `scripts/claims_lint.py` scans `web/`, `docs/` (except `SPEC.md`), `README.md`, report templates, video script. CI fails on match. |
| R6 | The signal path (normalization, row signals, phase, frequency, matching) uses float32 or float64. FP16/BF16 only inside DNN inference. | Type assertions in engine; tests. |
| R7 | Convert pixel values to linear light before normalization. | Engine stage S2; tests. |
| R8 | Verdict decision thresholds come only from `config/thresholds.yaml`, written by `eval/calibrate_thresholds.py`. Development placeholders must carry the marker `PROVISIONAL`. The final check fails if any `PROVISIONAL` remains. Engineering constants (for example saturation cutoffs) are allowed but must be documented in `docs/DECISIONS.md`. | `scripts/final_check.py`. |
| R9 | Experimental face-region evidence is never the sole basis for `CONTRADICTED`. | Verdict logic tests. |
| R10 | Every agent step is traced (tool, inputs, outputs summary, decision reason, timestamps). | Trace schema; tests. |
| R11 | The Node never connects electronics directly to mains. Use a certified plug-in AC-to-AC adapter. | `node/hardware/SAFETY.md`; human task checklist. |
| R12 | Every number in README, report, UI copy, and video script has a source tag pointing to a file in `results/`. | `scripts/check_numbers_sourced.py`. |

---

## PART 3 — COMPETITION REQUIREMENTS (all must be met)

Copy this list into `docs/REQUIREMENTS_TRACE.md` and link evidence for each line before the final stop.

### 3.1 Eligibility (core)
- OpenCV 5 performs substantive image/video analysis. → Engine stages S1–S14 (Part 8).
- A meaningful component runs on AWS. → Part 10.6.

### 3.2 Final submission items
- Technical report: problem, users, architecture, OpenCV 5 implementation, AWS deployment, evaluation, limitations, responsible-use considerations.
- Judge-accessible code repository.
- Pinned dependencies plus clear build, deployment, and test instructions.
- Architecture diagram showing OpenCV 5 and AWS components, plus COOL and agent components.
- Working web endpoint (Verify) or arranged live screen-share.
- Public or unlisted video, maximum 5 minutes, showing the team, the application working, its architecture, and its principal results.
- Evaluation evidence, including failure cases and limitations.

### 3.3 Best Use of COOL Award
- COOL executes the claimed core workload on AWS Graviton.
- Report the COOL version and the AWS instance/deployment configuration.
- Reproducible evaluation method, inputs, baselines, and results.
- Evidence that COOL executes the claimed workload.
- Explain any x86/Arm coexistence.

### 3.4 Agentic Vision Award
- Multi-step perception → decision → action loop where OpenCV 5 results change a later plan, tool call, action, or request for human approval.
- Agent workflow diagram (perception, decision/orchestration, action).
- A trace or demonstration showing OpenCV 5 output changing a later decision.
- Evaluation of task success, failure handling, observability, and appropriate human control.
- Note: using an AI coding assistant to write the code does NOT count as the agentic workflow. The runtime agent (Part 9) is the agentic workflow.

### 3.5 Judging weights (optimize for these)

| Criterion | Weight | Where GRIDPRINT earns it |
|---|---|---|
| Technical execution (correctness and depth of OpenCV 5) | 30% | Part 8 pipeline, Part 11 evaluation |
| Innovation | 20% | Physical proof of authenticity; no indexed competitor uses the grid signal |
| Real-world impact | 20% | Liar's dividend; news, legal, insurance, human-rights users |
| User experience | 10% | Part 10.2 and 10.3; accessibility |
| Documentation and presentation | 10% | Part 14 |
| Cloud delivery, reproducibility, responsible operation | 10% | Part 10.6, Part 12, Part 13 |

Judges include the founder of OpenCV (values correct, deep computer vision and honest limits) and OpenCV's Director of Content & Creative (values clear story and video). Never inflate a claim.

---

## PART 4 — VERIFY-FIRST LIST (unverified facts and fallbacks)

Resolve every item in milestone M0. Record: source URL or command run, result, date, decision.

| ID | Fact to verify | Fallback if false |
|---|---|---|
| V1 | The exact OpenCV 5.x release to pin, and how to build it for linux/arm64 and linux/amd64. Whether `cv::dnn` exposes an engine-selection option in 5.x and its exact name. | Use the default DNN engine. Do not mention a nonexistent engine name anywhere. |
| V2 | `findHomography` with the `USAC_MAGSAC` method flag exists in the pinned version, and which module/namespace contains it. | `USAC_DEFAULT`, then `RANSAC`. |
| V3 | `DISOpticalFlow` and `calcOpticalFlowPyrLK` exist in the pinned core build (not only contrib). | `calcOpticalFlowFarneback`. |
| V4 | `FaceDetectorYN` (YuNet) exists in the pinned build, and the model license. | Any OpenCV `dnn`-loadable face detector with a permissive license. |
| V5 | COOL (Cloud-Optimized OpenCV Library): distribution form (AMI, container, or package), supported Graviton instance types, version string, which operations it accelerates, license terms, and how to prove at runtime that it is loaded and executing. | If COOL cannot be obtained, run on Graviton with stock OpenCV 5, document the reason, and mark the COOL award as not claimed. Do not claim COOL use without proof. |
| V6 | A Claude model with tool use is available on Amazon Bedrock in the chosen region. Pin the exact model ID in `config/default.yaml`. | Another supported region; if none, the deterministic fallback planner (Part 9.6) runs and the docs state it. |
| V7 | Android Camera2 on each test device supports: `CONTROL_AE_MODE_OFF`, manual `SENSOR_EXPOSURE_TIME`, `CONTROL_AE_ANTIBANDING_MODE_OFF`, `SENSOR_ROLLING_SHUTTER_SKEW`, `SENSOR_TIMESTAMP` with `SENSOR_INFO_TIMESTAMP_SOURCE_REALTIME`. | Use calibration-rig readout values (Part 10.5) and document per device. |
| V8 | Public historical grid-frequency data: Grid-India publications (resolution, history, terms); open European/US grid-frequency datasets (resolution must be 1 s or finer). | Use only GRIDPRINT Node data. Demo cases and evaluation are restricted to zones and times the Node covers. |
| V9 | PyAV/FFmpeg gives exact per-frame presentation timestamps (PTS) and time base for MP4/MOV from Android and iPhone, including variable-frame-rate files. | Use `ffprobe -show_frames` output. |
| V10 | How to read color transfer metadata (BT.709/sRGB vs HLG/PQ HDR) from the container. | Treat unknown transfer as BT.709 and add reason `TRANSFER_ASSUMED`. |
| V11 | GPS module with PPS output works with the chosen ESP32 board, and MQTT over TLS to AWS IoT Core works from it. | NTP-disciplined timing; mark data `quality=ntp` and document the larger timing uncertainty. |
| V12 | Current on-demand prices for the benchmark instance types in the chosen region (for cost per hour). | Record the price source and date; never guess a price. |

---

## PART 5 — SYSTEM ARCHITECTURE

```
                       ┌──────────────────────────┐
  GRIDPRINT Capture ───┤  upload (presigned S3)    │
  (Android, sidecar)   └────────────┬─────────────┘
                                    │
  GRIDPRINT Verify (web) ──► CloudFront + S3 (static) ──► API (FastAPI, arm64 Fargate) ──► SQS jobs queue
        ▲   reviewer login (Cognito)                         │                                  │
        │                                                    ▼                                  ▼
        │                                         DynamoDB: Jobs, Reviews        Engine workers (ECS on Graviton c8g,
        │                                                    ▲                    OpenCV 5 + COOL, linux/arm64)
        │                                                    │                    ┌──────────────────────────────┐
        │                                                    │                    │ Agent orchestrator            │
        │                                                    │                    │  ├─ Planner: Claude on Bedrock│
        │                                                    │                    │  └─ MCP client                │
        │                                                    │                    │ MCP server: gridprint-engine  │
        │                                                    │                    │  └─ Engine stages S1–S15      │
        │                                                    │                    └──────────────────────────────┘
        │                                                    │                                  │
        └──── results: S3 (report PDF/JSON, overlay MP4, plots, trace) ◄────────────────────────┘
                                                                                                 ▲
  GRIDPRINT Node ──MQTT/TLS──► AWS IoT Core ──rule──► Lambda ingest ──► DynamoDB GridLog ────────┘ (read)

  Observability: CloudWatch structured logs, metrics, dashboards, alarms (all services).
```

Rules:
- Production engine containers are `linux/arm64` on Graviton. The `linux/amd64` image exists only for the x86 baseline benchmark (Part 12).
- The agent orchestrator and the MCP server run in the same worker task. MCP transport: stdio.
- The engine is a Python package with no AWS imports. AWS access goes through adapter interfaces (`StorageAdapter`, `GridLogAdapter`, `JobStoreAdapter`) with a local implementation for development and tests and an AWS implementation for production.

---

## PART 6 — REPOSITORY LAYOUT

```
gridprint/
├── CLAUDE.md                    # short operating rules; points to SPEC.md
├── SPEC.md                      # this file
├── README.md
├── Makefile                     # setup, test, lint, local, deploy, destroy, eval, bench, final-check
├── config/
│   ├── default.yaml             # region, model IDs, limits, engineering constants
│   ├── thresholds.yaml          # GENERATED by eval/calibrate_thresholds.py
│   ├── zones.yaml               # grid zones: id, nominal Hz, timezone, description
│   └── camera_profiles.yaml     # readout times per device/mode from calibration
├── engine/gridprint_engine/
│   ├── io.py  color.py  readout.py  motion.py  segment.py  patches.py
│   ├── rowsignal.py  phase.py  enf.py  match.py  continuity.py  facecheck.py
│   ├── verdict.py  overlay.py  report.py  schemas.py  pipeline.py  adapters/
│   └── tests/
├── mcp_server/                  # MCP tools wrapping engine stages
├── agent/
│   ├── orchestrator.py  planner_bedrock.py  fallback_planner.py
│   ├── policies.py  trace.py  prompts/planner.md
│   └── tests/
├── api/                         # FastAPI service
├── web/                         # React + TypeScript + Vite
├── capture-android/             # Kotlin, Camera2
├── node/
│   ├── firmware/                # ESP32
│   ├── hardware/                # BOM, schematic, SAFETY.md, assembly guide
│   └── ingest/                  # Lambda
├── calibration_rig/             # LED rig firmware, procedure, fit script
├── infra/                       # AWS CDK v2 (Python)
├── eval/
│   ├── DATASET.md  manifest_schema.json  validate_dataset.py
│   ├── simulator/               # synthetic rolling-shutter ENF videos
│   ├── generate_edits.py  run_eval.py  metrics.py
│   ├── calibrate_thresholds.py  make_report.py
├── bench/                       # COOL vs baselines
├── scripts/
│   ├── claims_lint.py  check_numbers_sourced.py  final_check.py
├── docs/
│   ├── PROGRESS.md  DECISIONS.md  VERIFICATION.md  HUMAN_TASKS.md  IDEAS.md
│   ├── REQUIREMENTS_TRACE.md  ARCHITECTURE.md  TECHNICAL_REPORT.md
│   ├── RESPONSIBLE_USE.md  JUDGE_GUIDE.md  VIDEO_SCRIPT.md
│   └── diagrams/  architecture.mmd  agent_workflow.mmd  (+ exported SVG/PNG)
├── results/                     # GENERATED ONLY: eval, bench, demo outputs
└── .github/workflows/ci.yml
```

---

## PART 7 — TECHNOLOGY STACK (pin every version in lockfiles)

| Area | Choice |
|---|---|
| Engine language | Python 3.11 |
| Vision | OpenCV 5.x (pinned per V1), built from source for amd64; COOL build on Graviton per V5 |
| Video I/O and timestamps | PyAV (FFmpeg); `ffprobe` fallback |
| Numerics | NumPy (float32/float64 only in signal path) |
| API | FastAPI, Pydantic, Uvicorn |
| Agent | Anthropic model via Amazon Bedrock (boto3), MCP Python SDK |
| Report | HTML template → PDF (WeasyPrint or equivalent; record choice) |
| Tests and quality | pytest, ruff, mypy, pre-commit |
| Web | TypeScript, React, Vite; axe-core for accessibility checks |
| Capture | Kotlin, Camera2, MediaCodec/MediaRecorder |
| Node | ESP32 + GPS module with PPS; MQTT over TLS |
| Infrastructure | AWS CDK v2 (Python) |
| Containers | Docker buildx, multi-arch (arm64 production, amd64 benchmark baseline) |

Python deps pinned with a lockfile (uv or pip-tools; record choice). Node deps with `package-lock.json`. Android with Gradle version catalog.

---

## PART 8 — ENGINE SPECIFICATION (the core)

### 8.0 Inputs and outputs

**Inputs**
- Video file (MP4/MOV).
- Optional Capture sidecar JSON (schema `engine/gridprint_engine/schemas.py::CaptureSidecar`): app version, device model, sensor orientation, per-frame sensor timestamp (ns, start of exposure of first row), per-frame exposure time (ns), frame duration (ns), rolling-shutter skew (ns), ISO, wall-clock time at start (UTC, with clock source), zone chosen by the user, SHA-256 of the video file.
- Optional user claim: `claimed_zone`, `claimed_time_utc`, `claimed_time_tolerance_s`.

**Outputs**
- `AnalysisResult` JSON (schema in `schemas.py`) with: job id, file hash, engine version, config hash, thresholds hash, verdict, lifecycle state, reason codes, time estimate and uncertainty, zone, match statistics, continuity events, experimental face-region stats, quality metrics, stage timings, and links to artifacts.
- Band overlay MP4, evidence plots (PNG/SVG), report HTML + PDF.

### 8.1 Reason codes (closed list; add new ones only via DECISIONS.md)

`SIGNAL_ABSENT`, `SIGNAL_WEAK`, `READOUT_FROM_SIDECAR`, `READOUT_FROM_PROFILE`, `READOUT_ESTIMATED`, `READOUT_UNKNOWN`, `HDR_UNSUPPORTED`, `TRANSFER_ASSUMED`, `TRACK_TOO_SHORT`, `NO_REFERENCE_COVERAGE`, `NO_UNIQUE_MATCH`, `MATCH_OK`, `CLAIM_TIME_MISMATCH`, `CLAIM_TIME_MATCH`, `EDIT_CANDIDATE`, `SEGMENT_OFFSET_INCONSISTENT`, `DROPPED_FRAMES_EXPLAINED`, `HIGH_MOTION`, `HIGH_COMPRESSION`, `TIMESTAMP_JITTER_HIGH`, `AXIS_AMBIGUOUS`, `FACE_REGION_ANOMALY_EXPERIMENTAL`, `REVIEWER_APPROVED`, `REVIEWER_REJECTED`, `USER_INPUT_REQUESTED`, `BUDGET_EXHAUSTED`.

### 8.2 Stage S1 — Ingest and timing

1. Compute SHA-256 of the file. If a sidecar exists, compare hashes; mismatch → reject the sidecar and add a note.
2. Probe: codec, resolution, frame count, bitrate, color transfer (V10), rotation metadata, time base.
3. Read the per-frame PTS (float64 seconds). If the sidecar exists, use sensor timestamps instead and record `timestamp_source=sensor`.
4. Compute timestamp jitter: residual of timestamps against a robust linear fit; store p50/p95 in ms. If p95 exceeds the configured limit, add `TIMESTAMP_JITTER_HIGH` and pass jitter into the uncertainty model.
5. Detect gaps: any interval larger than 1.5 × median frame interval is a `GAP` event with its size.
6. Determine the **sensor row axis**. With a sidecar, use the sensor orientation. Without one, test both image axes in S7–S8 and choose the axis with higher band SNR; if the two are within the configured margin, add `AXIS_AMBIGUOUS`. Rows used for timing are always **sensor rows**, never display rows.
7. Decode frames to float32.

### 8.3 Stage S2 — Linear light

1. If the transfer is HDR (HLG/PQ) → stop analysis with `INCONCLUSIVE`, reason `HDR_UNSUPPORTED`.
2. Convert to luma, then apply the inverse BT.709/sRGB transfer to get linear luminance (float32).
3. Mark pixels as invalid if the code value is at or above the saturation cutoff or at or below the noise floor (engineering constants; document in DECISIONS.md).

### 8.4 Stage S3 — Readout time

Priority order:
1. Sidecar `rolling_shutter_skew` → `READOUT_FROM_SIDECAR`.
2. `config/camera_profiles.yaml` entry for device + resolution + frame rate → `READOUT_FROM_PROFILE`.
3. Blind estimation: search readout time in [configured minimum, frame period] to maximize cross-frame phase coherence of S8 → `READOUT_ESTIMATED` (lower confidence).
4. Otherwise `INCONCLUSIVE`, `READOUT_UNKNOWN`.

Row time model (sensor row `r` of frame `k`, `N` sensor rows):
`t(k, r) = t_k + e_k/2 + r × T_ro / (N − 1)`
where `t_k` = start of exposure of the first row, `e_k` = exposure time (0 if unknown), `T_ro` = readout time. With PTS only, `t_k` = PTS (document the assumption).

### 8.5 Stage S4 — Motion and static background

1. On downscaled luminance, track features (`goodFeaturesToTrack` + `calcOpticalFlowPyrLK`) and estimate frame-to-reference homographies with `findHomography` using `USAC_MAGSAC` (per V2).
2. Compute dense flow with `DISOpticalFlow` (per V3). Pixels whose flow deviates from the homography by more than the configured limit are dynamic.
3. Output: per-frame homography, static mask, `motion_level` (median residual flow, px/frame). Above the configured limit → `HIGH_MOTION`.
4. **Critical:** warping is used only to track which scene surface a pixel belongs to. Every sample keeps its **original sensor row index** for timing.

### 8.6 Stage S5 — Foreground masking

1. Run a person/semantic segmentation model with OpenCV 5 `dnn` (record the model, source, and license in DECISIONS.md). FP16 is allowed here only.
2. Final static mask = S4 static mask AND NOT segmentation foreground AND valid pixels from S2.

### 8.7 Stage S6 — Light patches

1. Divide the reference frame into a grid of patches (size in config).
2. A patch is eligible if: static in at least the configured fraction of frames, mean linear luminance above the floor, and saturation fraction below the limit.
3. Score each patch by band SNR from a first pass of S7–S8. Return a ranked list. The agent may select a different subset.

### 8.8 Stage S7 — Row signal (fractional modulation)

1. For each eligible pixel, compute its temporal mean linear luminance `L̄` over a sliding window of `W` frames, in warped (scene) coordinates.
2. Fractional modulation: `m = (L − L̄) / L̄` (float32).
3. For each frame `k` and sensor row `r`: `m(k, r)` = weighted mean of `m` over selected pixels in that sensor row. Rows with fewer than the configured minimum pixels are masked.
4. Remove a low-order polynomial trend across rows per frame (exposure ramps, vignetting changes).

### 8.9 Stage S8 — Phase and frequency track (primary estimator)

1. Nominal flicker `f0 = 2 × zone nominal` (100 or 120 Hz). If the zone is unknown, evaluate both and keep the higher-SNR one.
2. **Per-frame phase fit:** for each frame `k`, fit `m(k, r) ≈ a_k cos(2π f0 t(k, r)) + b_k sin(2π f0 t(k, r)) + c_k` by least squares over valid rows (`cv::solve` or NumPy lstsq, float64). Amplitude `A_k = √(a_k² + b_k²)`, phase `φ_k = atan2(−b_k, a_k)`, frame SNR from residual variance.
3. **Phase tracking:** unwrap `φ_k` over frames using `t_k`. The phase slope over time gives the deviation `δf`. Estimate `f(t)` at 1 s resolution by weighted linear fits of unwrapped phase over a sliding window (length and hop in config), weighted by frame SNR. `ENF(t) = (f0 + δf(t)) / 2`.
4. **Cross-check estimator:** build the row-time series on a uniform virtual time grid, **zero-fill the inter-frame idle gaps with a known mask (never interpolate across gaps)**, apply a Hann window, run `cv::dft`, take the peak near `f0` with parabolic interpolation. If the two estimators disagree beyond the configured tolerance, lower confidence and log it.
5. Compute overall band SNR. Below the signal threshold → `SIGNAL_ABSENT`; between thresholds → `SIGNAL_WEAK`.
6. Frame-timestamp jitter (S1) enters the per-frame phase uncertainty.

### 8.10 Stage S9 — Clock-bias removal

The phone clock may be off by parts per million, which shifts the measured frequency by a near-constant amount. Before matching, subtract the mean from both the video ENF track and the reference segment. Match **variations only**.

### 8.11 Stage S10 — Reference matching

1. Search window: if a claimed time exists, `claimed_time ± max(tolerance, configured minimum)`. Else, if the sidecar has a wall-clock time, that time ± configured window. Else, the configured maximum search window (coarse-to-fine). No reference data for the zone/window → `NO_REFERENCE_COVERAGE`.
2. Normalized cross-correlation of demeaned tracks over offsets at 1 s steps; refine the best peak to sub-second by interpolation.
3. Output: best offset, peak value `ρ1`, best competing peak `ρ2` outside an exclusion zone, peak-to-sidelobe ratio, track length, time uncertainty.
4. A match passes only if `ρ1`, the margin `ρ1 − ρ2`, and track length all meet the thresholds in `thresholds.yaml` (which may depend on track length). Fail → `NO_UNIQUE_MATCH` or `TRACK_TOO_SHORT`.
5. Segment matching: split long tracks into segments (length in config) and match each. Segments that match inconsistent offsets → `SEGMENT_OFFSET_INCONSISTENT`.

### 8.12 Stage S11 — Continuity (works with or without reference)

1. Fit a smooth frequency model to the phase track; compute phase residuals.
2. Run change-point detection on the residuals at frame boundaries.
3. For each change point, check S1 gaps. If a gap exists and the expected phase advance across the gap explains the residual → `DROPPED_FRAMES_EXPLAINED` (not an edit). If not explained and significant (threshold from `thresholds.yaml`) → `EDIT_CANDIDATE` with time, magnitude, significance.

### 8.13 Stage S12 — Face-region check (EXPERIMENTAL)

1. Detect faces with `FaceDetectorYN` (per V4). No identity recognition, no embeddings stored.
2. For sensor rows covered by a face, compare band amplitude in face pixels against background pixels in the same rows.
3. Output ratio and significance. Label `EXPERIMENTAL` everywhere. May add `FACE_REGION_ANOMALY_EXPERIMENTAL`. Never the sole basis for `CONTRADICTED` (R9).

### 8.14 Stage S13 — Verdict logic (deterministic; `verdict.py`)

Evaluate in this order:
1. Any of `HDR_UNSUPPORTED`, `READOUT_UNKNOWN`, `SIGNAL_ABSENT` → `INCONCLUSIVE`.
2. The signal is strong (no `SIGNAL_WEAK`) AND (`EDIT_CANDIDATE` is significant OR `SEGMENT_OFFSET_INCONSISTENT`) → `CONTRADICTED` (state `PENDING_REVIEW`).
3. A claimed time exists, the match passes, and the offset is outside tolerance → `CONTRADICTED` with `CLAIM_TIME_MISMATCH` (state `PENDING_REVIEW`).
4. The match passes, no significant edit evidence, and (claim absent or `CLAIM_TIME_MATCH`) → `VERIFIED`.
5. Everything else → `INCONCLUSIVE` with all applicable reason codes.

The agent cannot change a verdict. Only a reviewer decision changes the lifecycle state (Part 1.5).

### 8.15 Stage S14 — Band overlay (visualization only)

1. Temporally band-pass the fractional modulation at the flicker alias rate, colorize, and blend over the original video.
2. Add a timeline strip: phase residual, edit candidates (red), dropped-frame gaps (grey), matched segments.
3. Label the overlay "Visualization of measured flicker. Not itself evidence."

### 8.16 Stage S15 — Report

1. JSON (`AnalysisResult`) + HTML + PDF, one page main section plus an appendix.
2. Main section: verdict in words and icon (never color only), lifecycle state, estimated recording time ± uncertainty, zone, plain-language reasons, key plots, a fixed "Limitations" box, file hash, engine/config/threshold versions, reviewer approval (name, time, note) if any.
3. HTML report meets WCAG 2.1 AA (headings, alt text, contrast).

### 8.17 OpenCV 5 usage map (keep updated in TECHNICAL_REPORT.md)

| Stage | OpenCV 5 functionality (names per V1–V4) |
|---|---|
| S1 | `VideoCapture` cross-check of frame count/size |
| S2 | color conversion, LUT-based inverse transfer |
| S4 | `goodFeaturesToTrack`, `calcOpticalFlowPyrLK`, `findHomography` (USAC), `DISOpticalFlow`, `warpPerspective` |
| S5 | `dnn` segmentation |
| S6–S7 | matrix ops (`reduce`, `divide`, masking) in float32 |
| S8 | `solve` (least squares), `dft` |
| S12 | `FaceDetectorYN` |
| S14 | filtering, color maps, `VideoWriter` |
| Calibration | band-period measurement on rig footage (`dft` / `reduce`) |

---

## PART 9 — AGENT SPECIFICATION

### 9.1 Role
The agent plans and adapts the analysis for each job. It perceives quality signals from OpenCV stages, decides the next tool call, and acts (re-runs stages, requests user input, requests human review). It never writes a verdict itself.

### 9.2 MCP tools (`mcp_server`, name `gridprint-engine`)

| Tool | Input | Output |
|---|---|---|
| `probe_video` | job_id | metadata, timestamp source, jitter, gaps, HDR flag, axis info |
| `estimate_readout` | job_id, method | readout time, source, confidence |
| `analyze_motion` | job_id, strictness | motion_level, static fraction, mask id |
| `propose_patches` | job_id, strategy | ranked patches with scores |
| `extract_flicker` | job_id, patch_ids, axis, nominal_hz, frame_subset | band SNR, per-frame stats, track id |
| `match_reference` | job_id, track_id, zone, window | match statistics |
| `check_continuity` | job_id, track_id | events |
| `face_region_check` | job_id, track_id | experimental stats |
| `compute_verdict` | job_id | verdict, reasons (deterministic S13) |
| `request_user_input` | job_id, kind, message | creates a request (original file, camera model, claimed time, longer clip) |
| `request_human_review` | job_id | creates a review task |
| `render_report` | job_id | report artifacts |

### 9.3 Required adaptive behaviors (each must appear in tests and saved traces)

| ID | Trigger (from OpenCV output) | Required action |
|---|---|---|
| B1 | `SIGNAL_WEAK` after first extraction | Re-select patches, switch axis, or switch nominal frequency; re-extract. |
| B2 | Readout unknown | Run blind estimation; if confidence is low, request the camera model. |
| B3 | `HIGH_MOTION` | Re-run motion analysis with higher strictness or restrict to low-motion frames; re-extract. |
| B4 | `HIGH_COMPRESSION` and weak signal | Request the original file. |
| B5 | No usable signal after the iteration budget | Call `compute_verdict` → `INCONCLUSIVE` with reasons; stop. |
| B6 | Verdict `CONTRADICTED` | Call `request_human_review`; do not render a FINAL report. |

### 9.4 Policies (enforced in `policies.py`, not only in the prompt)
- Maximum iterations and tool calls per job (config). On exhaustion → `BUDGET_EXHAUSTED` + `compute_verdict`.
- `compute_verdict` must be the last analysis call. `render_report` FINAL is blocked for `PENDING_REVIEW`.
- The agent cannot edit thresholds, verdicts, or reason codes.
- The planner prompt (`agent/prompts/planner.md`) includes the forbidden-claims list (R5).

### 9.5 Trace
Every step: timestamp, planner type (`bedrock` or `fallback`), model ID, tool, input summary, output summary, decision reason (short text), duration. Stored as JSON in S3 and indexed in DynamoDB. Shown live in the web UI.

### 9.6 Deterministic fallback planner
`fallback_planner.py` implements B1–B6 as rules using the same tools. It runs when Bedrock is unavailable or disabled. The trace marks it. Evaluation reports results for both planners.

### 9.7 Agent evaluation (in Part 11)
Task success (final verdict matches ground truth), recovery rate (first pass failed, later pass succeeded), tool calls per job, unnecessary-call rate, human-review precision (share of `CONTRADICTED` cases that ground truth confirms), budget-exhaustion rate.

---

## PART 10 — OTHER COMPONENTS

### 10.1 API (FastAPI, arm64 Fargate)

| Method & path | Purpose |
|---|---|
| `POST /v1/jobs` | Create a job; return a presigned S3 upload URL (short expiry). |
| `POST /v1/jobs/{id}/start` | Start analysis; optional claim and sidecar. |
| `GET /v1/jobs/{id}` | Status, lifecycle state, verdict, reasons, artifact links. |
| `GET /v1/jobs/{id}/trace` | Agent trace (streamable). |
| `POST /v1/jobs/{id}/input` | Answer an agent request (upload original, camera model, claimed time). |
| `GET /v1/reviews` | Reviewer queue (Cognito, reviewer group). |
| `POST /v1/reviews/{id}/decision` | Approve or reject with a note. |
| `GET /v1/demo-cases` / `POST /v1/demo-cases/{id}/run` | List and run demo cases through the real pipeline. |
| `GET /v1/grid/{zone}/live` | Latest reference frequency samples for the live tile. |
| `GET /v1/health` | Health. |

Limits (config): maximum file size, maximum duration, allowed containers. Anonymous uploads are rate-limited (WAF). Reviewer endpoints require login.

### 10.2 Verify web app
Pages: Home (upload, demo cases, live grid tile), Job (progress, live agent trace, verdict card, overlay player with timeline markers, plots, downloads), Reviewer (login, queue, evidence, approve/reject), Limitations, Judge Guide.
- The verdict card always shows text + icon. Never color alone.
- If a judge uploads an ordinary phone video and the result is `INCONCLUSIVE`, the page explains anti-banding in two plain sentences and links to Capture.
- Keyboard navigable, WCAG 2.1 AA contrast, light and dark themes, screen-reader labels. Automated axe-core check in CI.

### 10.3 Capture Android app
1. Camera2. AE off, anti-banding off, manual short exposure (value in config, much shorter than one flicker period; document in DECISIONS.md), ISO raised to compensate, fixed 30 fps.
2. Record H.264/HEVC at high bitrate.
3. Log per frame: `SENSOR_TIMESTAMP`, exposure time, frame duration, rolling-shutter skew, ISO. Log device model, sensor orientation, wall-clock at start with clock source, app version, user-selected zone. **No GPS location.**
4. Live band-strength meter on preview frames (row-variance at the flicker alias rate).
5. Compute SHA-256; write the sidecar JSON; upload video + sidecar through the API; also allow local save.
6. Show a one-screen consent and privacy notice on first run.

### 10.4 Node
**Hardware:** ESP32 board, GPS module with PPS, certified plug-in AC-to-AC adapter (low-voltage AC output), resistor divider + bias + comparator/op-amp to produce a zero-crossing signal, enclosure. Bill of materials, schematic, and assembly guide in `node/hardware/`.

> **WARNING (must appear at the top of `node/hardware/SAFETY.md` and the assembly guide):** Do not connect the Node electronics directly to mains voltage. Use only a certified plug-in AC-to-AC adapter. Mains voltage can kill.

**Firmware:**
1. Timestamp each zero crossing with a hardware timer disciplined by GPS PPS.
2. Filter harmonics and noise; compute frequency for each UTC second.
3. Publish `{zone, node_id, t_utc_s, freq_hz, quality, gps_lock}` each second over MQTT/TLS to IoT Core.
4. Buffer when offline; back-fill on reconnect.

**Ingest:** IoT rule → Lambda → DynamoDB `GridLog` (PK `zone#YYYYMMDD`, SK epoch second; attributes: freq, node, quality, source). Multiple nodes per zone → median. Importers for public datasets (if V8 passes) write the same schema with `source` set.

**Data quality script:** reports gaps, GPS lock ratio, outliers per day.

### 10.5 Calibration rig
1. A microcontroller drives an LED at an exact known frequency (crystal or GPS-disciplined; frequency in config, chosen to give several bands per frame).
2. The LED lights a matte white card. Film it with each phone, in each mode used.
3. `calibration_rig/fit_readout.py` measures the band spatial period `P` (rows) → row time `= 1 / (f_led × P)` → readout time `T_ro`. Writes `camera_profiles.yaml` entries with uncertainty.
4. For Android devices that report `SENSOR_ROLLING_SHUTTER_SKEW`, compare and record the difference.

### 10.6 AWS infrastructure (CDK stacks)

| Stack | Contents |
|---|---|
| Network | VPC, private subnets, endpoints for S3/DynamoDB |
| Storage | S3 buckets with SSE-KMS; lifecycle: uploads deleted after the configured hours; results after the configured days |
| Data | DynamoDB `Jobs`, `Reviews`, `GridLog`, `TraceIndex` |
| Compute | ECS cluster on Graviton (`c8g` family per V5) with COOL; SQS queue; autoscaling on queue depth |
| API | Fargate arm64 service + ALB or API Gateway HTTP API |
| IoT | Thing type, certificates, policy, topic rule |
| Auth | Cognito user pool with `reviewer` group |
| Web | S3 + CloudFront; WAF rate limits |
| Observability | CloudWatch structured JSON logs, dashboards (jobs, stage latency, verdict counts, agent iterations, errors, Node freshness), alarms |
| AI | IAM permission for the pinned Bedrock model only |

IAM least privilege per service. Secrets in Secrets Manager. Region pinned in config. `make deploy` deploys everything; `make destroy` removes everything. A budget alarm is a human task (H1).

### 10.7 Local development mode
`make local` runs engine + MCP server + agent (fallback planner by default; Bedrock optional) + API + web with local adapters (filesystem storage, SQLite or local JSON stores). All unit and integration tests run offline.

---

## PART 11 — EVALUATION (the largest scoring lever)

### 11.1 Synthetic simulator (`eval/simulator/`)
Generates rolling-shutter videos with known ground truth: ENF track (from real Node logs when available, else a documented random-walk model), flicker depth, readout time, exposure, frame timing jitter, dropped frames, camera motion, moving objects, noise, compression presets (FFmpeg), cuts and insertions. Output: video + ground-truth JSON.
**Rule:** simulator results are labeled `SYNTHETIC` in every table and are never presented as real-world accuracy.

### 11.2 Real dataset (`eval/DATASET.md`, collected by humans — task H5)

| Factor | Levels |
|---|---|
| Phone | at least 3 models; at least 1 model not used for calibration |
| App | Capture mode; stock camera app |
| Lighting | fluorescent tube; low-cost AC LED; quality LED bulb; incandescent/halogen if available; daylight only; DC/battery lamp |
| Motion | tripod; handheld still; handheld walking; people moving in scene |
| Duration | 10 s, 30 s, 60 s, 120 s |
| Compression | original; WhatsApp round trip; YouTube upload/download; Instagram round trip; FFmpeg presets |

- Minimum 5 clips per cell of the core matrix (phone × app × lighting × motion at 30 s), plus duration and compression subsets. Total originals target: at least 300.
- Record on at least 5 different days, at different times of day.
- Ground truth: sidecar wall-clock (Capture) or the file creation time from an NTP-synced phone plus a filmed NTP clock at the start (stock app). Record the uncertainty.
- Consent forms for every person who appears. Store forms outside the repo.
- `eval/validate_dataset.py` checks the manifest, hashes, counts per cell, and ground-truth fields.

### 11.3 Derived sets (`eval/generate_edits.py`)
- Cuts: remove 0.5 s, 1 s, 2 s at random positions, then re-time so timestamps look continuous (true edit).
- Dropped frames: remove frames but keep original timestamps (must NOT be flagged as an edit).
- Insertions: insert a segment from the same room recorded at another time.
- Reorder: swap two segments.
- Face composites: only consenting team members, made with an open-source face-swap tool (record tool and license) — task H7.
- Synthetic room videos from a public video generator (record tool, prompt, license, date).

### 11.4 Splits and threshold calibration
1. Split by recording day and by phone into a calibration set and a held-out test set. No clip from the same session appears in both.
2. Before looking at any test data, the team writes in DECISIONS.md the target maximum false-`CONTRADICTED` rate on authentic clips.
3. `eval/calibrate_thresholds.py` chooses thresholds on the calibration set to meet that target and then maximize `VERIFIED` coverage. It writes `config/thresholds.yaml` with provenance (data hash, date, script version).
4. Run the test set **once** with frozen thresholds. Save to `results/eval/<date>/`. Any re-run is logged with a reason in DECISIONS.md.

### 11.5 Metrics (all with 95% confidence intervals where applicable)
- Confusion matrix of verdicts against ground-truth classes: authentic-with-mains-light, authentic-without-mains-light, edited, synthetic.
- False-`CONTRADICTED` rate on authentic clips (headline safety metric).
- `VERIFIED` coverage per condition; `INCONCLUSIVE` rate per condition.
- Time error distribution for `VERIFIED` clips.
- Edit detection rate and localization error; dropped-frame false-alarm rate.
- Signal survival per compression platform.
- Experimental face-region results reported separately.
- Agent metrics (Part 9.7) for both planners.
- Runtime per stage.

### 11.6 Outputs
`eval/make_report.py` writes `results/eval/<date>/summary.md`, CSVs, and plots. The technical report pulls tables from these files by script (Part 14.3). Include a failure-case gallery of at least 10 cases with overlays and plain explanations.

---

## PART 12 — COOL BENCHMARK PROTOCOL (`bench/`)

1. Same engine code and same pinned inputs (list file hashes in `bench/inputs.txt`).
2. Configurations of equal vCPU and memory:
   - **A:** x86 instance, stock OpenCV 5 (amd64 image).
   - **B:** Graviton `c8g`, stock OpenCV 5 (arm64 image).
   - **C:** Graviton `c8g`, OpenCV 5 with COOL.
3. Metrics: throughput (video-seconds processed per wall-second), per-stage latency p50/p95, CPU utilization, memory, and cost per hour of video = on-demand hourly price (source and date per V12) ÷ throughput. Document the formula in code.
4. At least 5 repeated runs per configuration; report mean and standard deviation.
5. **Parity check:** ENF tracks and verdicts from A, B, C must agree within the configured tolerance. Report the differences.
6. **Evidence that COOL executes:** build-information output, loaded library paths, version string, and a profiler capture showing COOL symbols in the hot stages. Save all under `results/bench/<date>/evidence/`.
7. Report which stages COOL accelerates and which it does not. Never claim a speedup for a stage the profile does not show.

---

## PART 13 — SECURITY AND RESPONSIBLE USE (`docs/RESPONSIBLE_USE.md`)

**Risks and controls**

| Risk | Control |
|---|---|
| Revealing when an anonymous source recorded a video could endanger them | Uploader notice before analysis; output limited to time and grid zone; short retention; no public sharing of reports by default; guidance for newsrooms on secure handling. |
| A false `CONTRADICTED` harms a truthful person | Mandatory human review; calibrated false-rate target; limitations box on every report; reviewer notes stored. |
| Over-trust in a `VERIFIED` result | Report states what is and is not checked; uncertainty shown; experimental items labeled. |
| Face data misuse | Face detection only for the experimental band check; no recognition; no face crops stored beyond the job retention. |
| Electrical injury (Node) | R11 and SAFETY.md. |
| Dataset privacy | Consent for every filmed person; dataset access restricted; no faces of non-consenting people. |
| Licenses | Record licenses of all models, tools, and datasets in `docs/LICENSES.md`. |

**Security:** TLS everywhere; SSE-KMS at rest; presigned URLs with short expiry; strict input validation (container whitelist, size and duration limits, decode timeouts, FFmpeg in a non-root container); dependency and container scanning in CI; least-privilege IAM; Cognito for reviewers; structured audit log of reviewer decisions.

---

## PART 14 — SUBMISSION DELIVERABLES

### 14.1 Documents
- `docs/TECHNICAL_REPORT.md` (+ PDF export) with sections: Problem, Users, Physical principle, Architecture, OpenCV 5 implementation (with 8.17 map), AWS deployment, COOL benchmark, Agent design and evaluation, Evaluation (real and synthetic, clearly separated), Failure cases, Limitations, Responsible use, Prior art and references (ENF forensics on audio, ENF from video via rolling shutter, C2PA — cite real, checked sources only), Reproducibility.
- `docs/diagrams/architecture.mmd` and `agent_workflow.mmd` with exported SVG/PNG. Show OpenCV 5, AWS services, COOL, agent, Node.
- `README.md`: what it is (one paragraph), quick start (local), deploy, test, eval, bench, links to the endpoint, video, report, judge guide.
- `docs/JUDGE_GUIDE.md`: endpoint URL, demo-case list, reviewer demo login (credentials provided in the submission form, not in the repo), what to expect from ordinary phone videos and why.
- `docs/VIDEO_SCRIPT.md`: timed script (below), shot list, all numbers with source tags.

### 14.2 Demo cases (all run through the deployed pipeline)
1. Capture clip → `VERIFIED` with time.
2. Same clip with a 1 s cut → `CONTRADICTED` → reviewer approval shown.
3. Insertion from another time → `CONTRADICTED` (`SEGMENT_OFFSET_INCONSISTENT`).
4. Dropped frames with original timestamps → `VERIFIED` with `DROPPED_FRAMES_EXPLAINED`.
5. Synthetic room video → `INCONCLUSIVE` (`SIGNAL_ABSENT`), with the plain explanation that this alone does not mean fake.
6. Daylight-only clip → `INCONCLUSIVE`.
7. Agent recovery case: first pass `SIGNAL_WEAK`, agent re-selects patches, signal locks.
8. Experimental face-composite case with the `EXPERIMENTAL` label.

### 14.3 Number sourcing
Every number in README, report, UI copy, and video script uses the tag format `<!-- src: results/<path>#<key> -->` (Markdown) or a data attribute in the web UI. `scripts/check_numbers_sourced.py` fails if a digit sequence that represents a measured value lacks a tag. Allowed untagged numbers: versions, dates, physical constants (50/60/100/120 Hz), and configuration values that are documented in DECISIONS.md.

### 14.4 Five-minute video plan (human records — H8)

| Time | Content |
|---|---|
| 0:00–0:20 | Hook: "AI can fake a video. Now people call real videos fake. We prove a video is real with the light in the room." Bands sweep across a wall. |
| 0:20–1:20 | Capture → upload → `VERIFIED` with recording time. |
| 1:20–2:10 | Cut clip → `CONTRADICTED` with red marker → reviewer approves. |
| 2:10–2:40 | Synthetic video → `INCONCLUSIVE`; explain why that alone is not "fake." |
| 2:40–3:30 | Agent trace: weak signal → new patches → lock. |
| 3:30–4:20 | Architecture diagram + measured COOL benchmark. |
| 4:20–5:00 | Failure cases, limitations, team on camera. |

---

## PART 15 — MILESTONES AND ACCEPTANCE CRITERIA

Work in order. Record evidence (command output, file paths, URLs) in `docs/PROGRESS.md` for every criterion.

| ID | Milestone | Acceptance criteria |
|---|---|---|
| M0 | Setup and verification | Repo layout per Part 6; CI runs lint, type check, tests, `claims_lint`; `VERIFICATION.md` has a resolved entry for V1–V12 (V5/V6/V7/V11/V12 may be `BLOCKED-HUMAN` with instructions); `HUMAN_TASKS.md` lists H1–H9; `REQUIREMENTS_TRACE.md` created. |
| M1 | Simulator | Simulator produces videos + ground truth for every factor in 11.1; unit tests; sample set committed under `results/synthetic_samples/` (small). |
| M2 | Engine S1–S10 | On synthetic data: ENF track recovered and time offset found; tests for VFR timestamps, gaps, sensor-row axis, rotation, linearization, float32 enforcement, idle-gap zero-fill (no interpolation), clock-bias removal; both estimators agree within tolerance on clean data. |
| M3 | Engine S11–S15 | Synthetic cuts detected; dropped frames with true timestamps not flagged; verdict logic tests cover every rule in S13 and R1–R3, R9; overlay MP4 and report HTML/PDF/JSON generated; claims_lint passes on templates. |
| M4 | Node and reference | Firmware, ingest Lambda, GridLog table, live tile. With hardware (H2): ≥ 24 h continuous data with GPS lock and data-quality report. Without hardware yet: ingest tested with a simulated publisher, and M4 stays open. |
| M5 | Calibration | Rig firmware and fit script; `camera_profiles.yaml` entries for every test phone mode with uncertainty (needs H3). |
| M6 | Capture app | On each test device: AE and anti-banding off, short exposure, complete sidecar, live meter, upload via API (needs H4). |
| M7 | Agent | MCP server with all tools; Bedrock planner and fallback planner; policies; traces; automated tests show B1–B6; `compute_verdict` deterministic. |
| M8 | AWS deployment | `make deploy` works from a clean account (documented); end-to-end upload → agent → verdict → report on the deployed endpoint; reviewer flow gates `CONTRADICTED`; dashboards and alarms live (needs H1). |
| M9 | Real evaluation | Dataset validated (H5–H7); thresholds calibrated; no `PROVISIONAL` left; test set run once; results frozen; failure gallery ≥ 10. |
| M10 | COOL benchmark | A/B/C results, evidence artifacts, parity report under `results/bench/`. |
| M11 | Demo and UX | All 8 demo cases run on the deployed endpoint; axe-core passes; keyboard-only walkthrough documented; Capture → Verify flow works on a real phone. |
| M12 | Docs and video | All Part 14 documents complete; numbers sourced; README reproduced from a fresh clone by a scripted clean-environment test; video ≤ 5:00 recorded and linked (H8). |
| M13 | Final check | `make final-check` passes every item in Part 17. |

---

## PART 16 — HUMAN TASKS (the agent prepares instructions and validators; humans execute)

| ID | Task | Agent prepares |
|---|---|---|
| H1 | AWS account, credentials, region, budget alarm; Bedrock model access; COOL Marketplace subscription | Step list, IAM policy JSON, verification commands |
| H2 | Buy and assemble the Node; install it; keep it running | BOM with part specs, schematic, assembly guide, SAFETY.md, flashing guide, self-test |
| H3 | Build the calibration rig; film calibration clips per phone/mode | Rig guide, filming checklist, `fit_readout.py` |
| H4 | Install Capture on test phones | Build/install guide, device checklist |
| H5 | Record the real dataset | DATASET.md shot list, manifest template, consent form template, `validate_dataset.py` |
| H6 | Platform round trips (WhatsApp, YouTube, Instagram) | Step list and naming rules |
| H7 | Face-composite clips with consenting team members | Tool setup guide, consent template |
| H8 | Record and edit the ≤ 5-minute video | VIDEO_SCRIPT.md, shot list, sourced numbers |
| H9 | Submit on Devpost | Submission checklist with every link |

---

## PART 17 — STOP RULES

### 17.1 Never stop when
- Any milestone M0–M13 is not accepted.
- Any test fails, CI is red, or `make final-check` fails.
- You are unsure what to build next. (Answer: the next unaccepted milestone in Part 15. Apply 0.5 for details.)
- A feature "works locally" but is not deployed and tested end to end.
- Any item in 17.3 is false and is not a human task.

### 17.2 Pause (not completion) when
Every remaining open item is a human task (H1–H8). Then write at the top of `docs/PROGRESS.md`:

```
PAUSED — WAITING FOR HUMAN TASKS
Open: <list of H IDs with one-line status>
Next agent action after completion: <exact next step>
```
and end the session. When the human reports completion, validate their output with the prepared scripts and continue.

### 17.3 FINAL STOP CHECKLIST — stop only when every line is TRUE

1. Milestones M0–M12 are accepted in `docs/PROGRESS.md`, each with evidence links.
2. `docs/VERIFICATION.md`: every V item resolved (verified or fallback applied and documented).
3. `docs/HUMAN_TASKS.md`: H1–H8 marked DONE and validated by script where a validator exists.
4. CI is green on the main branch: lint, type check, unit tests, integration tests, `claims_lint`, `check_numbers_sourced`, axe-core.
5. `config/thresholds.yaml` was generated by `eval/calibrate_thresholds.py`; `grep -r PROVISIONAL` returns nothing outside `SPEC.md`.
6. The deployed endpoint is live; `/v1/health` is OK; all 8 demo cases pass end to end; a fresh upload from a real phone completes; reviewer approval works.
7. Node data in GridLog is fresh (configured freshness limit) at check time.
8. Evaluation results are frozen under `results/eval/`; the test set was run once (or re-runs are logged); failure gallery has at least 10 cases.
9. COOL benchmark results, evidence, and parity report exist under `results/bench/` (or, if V5 failed, the documented fallback and the COOL award marked not claimed).
10. Agent traces demonstrate B1–B6; agent metrics for both planners are in the report.
11. All Part 14 documents exist and are complete; the README fresh-clone test passes.
12. The video link is in README and is ≤ 5:00.
13. No `TODO`, `FIXME`, `NotImplementedError`, or `pass  # stub` in shipped code paths (checked by `final_check.py`).
14. Every line in `docs/REQUIREMENTS_TRACE.md` has an evidence link.
15. `make final-check` prints `ALL CHECKS PASSED`.

When all 15 lines are true:
1. Write `PROJECT COMPLETE` with the date and a one-paragraph summary at the top of `docs/PROGRESS.md`.
2. Write the submission checklist for H9 in `docs/HUMAN_TASKS.md`.
3. Stop. Do not add features, refactors, or "improvements" after this point.
