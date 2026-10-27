# GRIDPRINT technical report

GRIDPRINT checks if a video is real from the flicker of the lights in the room. It reads the power-grid frequency from rolling-shutter flicker bands with OpenCV 5 and compares it with a reference log of the real grid.

Status (2026-10-27): sections 1–6 and 11–14 describe the built system. Sections 7–10 receive their tables from `eval/make_report.py` and the benchmark run. This report contains no measured number without a source tag (SPEC Part 14.3).

## Contents

1. Problem
2. Users
3. Physical principle
4. Architecture
5. OpenCV 5 implementation
6. AWS deployment
7. COOL benchmark
8. Agent design and evaluation
9. Evaluation
10. Failure cases
11. Limitations
12. Responsible use
13. Prior art and references
14. Reproducibility

## 1. Problem

AI tools can make fake video quickly and at low cost. Because of this, people now say that real video is fake. Researchers call this the "liar's dividend". Real evidence of abuse, crime, or accidents loses its value when anyone can call it fake.

Current tools fail in two ways:
- AI detectors guess from the pixels. New generators defeat them.
- Metadata and signatures, for example C2PA Content Credentials, can be removed by a re-upload or a screen recording.

GRIDPRINT reads a physical signal that stays inside the pixels: the grid frequency, recorded by the light flicker in the room.

## 2. Users

| User | Need | How GRIDPRINT helps |
|---|---|---|
| News verification desks | Decide fast if a video from an unknown source is real. | Verify gives a verdict, recording time, grid zone, and evidence plots. |
| Courts and lawyers | Answer the claim "this video is AI". | The report states the match with the grid log and the edit evidence, with uncertainty and limitations. |
| Insurance fraud teams | Check videos of damage and accidents for edits. | Continuity analysis marks cuts and insertions and separates them from dropped frames. |
| Human-rights documenters and citizen reporters | Record abuse in a way that can be checked later. | GRIDPRINT Capture records with settings that keep the flicker bands strong and writes sensor timing. |

Positioning: Capture is the core product. It seals the evidence at the moment of recording. Verify is a best-effort check for any other video. Many ordinary videos give `INCONCLUSIVE`, because phone anti-banding hides the flicker.

## 3. Physical principle

1. Most indoor lights use mains power. Their light output flickers at twice the grid frequency: 100 Hz on 50 Hz grids, 120 Hz on 60 Hz grids.
2. The grid frequency is never exactly nominal. It changes by small amounts every second as demand changes. This is the Electric Network Frequency (ENF). All points on one synchronous grid zone share the same ENF, and the ENF pattern is unique in time.
3. Most phone cameras use a rolling shutter. They read the sensor one row at a time. Each row samples a different instant, so the flicker appears as faint horizontal bands.
4. Row time model (SPEC Part 8.4): `t(k, r) = t_k + e_k/2 + r × T_ro / (N − 1)`, where `t_k` is the start of exposure of the first row of frame `k`, `e_k` the exposure time, `T_ro` the readout time, and `N` the number of sensor rows.
5. GRIDPRINT fits the flicker phase in each frame, tracks the phase over frames, and gets the frequency track. It compares the variations of this track with the reference grid log.

What GRIDPRINT reports: when the video was recorded (only inside the reference coverage), whether parts were cut, inserted, or reordered, whether the light carries a real grid signal, and which grid zone it matches. It never reports a location finer than the grid zone.

Verdicts: exactly three, `VERIFIED`, `CONTRADICTED`, `INCONCLUSIVE` (SPEC Part 1.5). `CONTRADICTED` needs recorded human approval before the report is final. A missing signal never gives `CONTRADICTED`.

## 4. Architecture

See `docs/ARCHITECTURE.md` and the diagrams `docs/diagrams/architecture.mmd` and `docs/diagrams/agent_workflow.mmd`.

Summary:
- **Clients:** GRIDPRINT Capture (Android) and GRIDPRINT Verify (web).
- **API:** FastAPI on ECS Fargate `linux/arm64`. Presigned S3 uploads. Jobs go to an SQS queue.
- **Engine workers:** ECS on Graviton4 `c8g`, `linux/arm64`, OpenCV 5 (stock wheel). The stack also supports a COOL AMI when `aws.cool_ami_id` is set; COOL is not active yet (§6). Each worker task holds the agent orchestrator, the MCP client, and the MCP server `gridprint-engine` (stdio).
- **Planner:** an LLM on Amazon Bedrock through the Converse API with tool use (`agent/planner_bedrock.py`; Amazon Nova Lite through a cross-account role, D-026; the model ID is configuration, so a Claude model works unchanged), with the deterministic fallback planner taking over for any step where the model call fails; the fallback planner can also run alone (`agent/fallback_planner.py`). The Bedrock planner is implemented and tested against a recorded-shape client. Bedrock access on the account waits for AWS account verification, so all runs so far use the fallback planner (D-021).
- **Engine:** Python package `engine/gridprint_engine`, stages S1–S15. No AWS imports. Storage, grid log, and job store are reached through adapter interfaces.
- **Reference:** GRIDPRINT Node (ESP32, GPS PPS, certified plug-in AC-to-AC adapter) → AWS IoT Core → Lambda → DynamoDB `GridLog`.
- **Human control:** Cognito reviewer login; reviewer decisions stored in DynamoDB `Reviews`.
- **Observability:** CloudWatch logs, metrics, dashboards, and alarms.

## 5. OpenCV 5 implementation

Pinned build: `opencv-python-headless==5.0.0.93` (OpenCV 5.0.0, main modules). API names were checked on this build (`docs/VERIFICATION.md` V1–V4).

### Stage summary

| Stage | Purpose |
|---|---|
| S1 ingest and timing | SHA-256, probe, per-frame PTS (PyAV; `ffprobe` fallback), timestamp jitter, gaps. Frames stay in coded (sensor) orientation; rotation metadata is recorded, not applied. |
| S2 linear light | Luma to linear luminance with an inverse BT.709/sRGB lookup table, float32. HDR (HLG/PQ) stops with `HDR_UNSUPPORTED`. Saturated and near-black pixels are invalid. |
| S3 readout time | Sidecar skew, then camera profile, then blind estimation by cross-frame phase coherence. |
| S4 motion | Feature tracking and homographies to a reference frame; dense flow marks dynamic pixels. Warping only tells which scene surface a pixel shows; every sample keeps its original sensor row for timing. |
| S5 foreground | Person segmentation with OpenCV `dnn`. |
| S6 patches | Static, well-lit, unsaturated patches, ranked by band SNR. |
| S7 row signal | Fractional modulation `m = (L − L̄) / L̄` in scene coordinates, averaged per sensor row, polynomial detrend across rows. A flicker-compensated temporal mean corrects windows that do not cancel the flicker (DECISIONS D-015). |
| S8 phase and frequency | Per-frame least-squares fit of a cosine and sine at the nominal flicker frequency; phase unwrapping over frames; frequency from weighted sliding phase slopes. Cross-check: DFT on a uniform virtual time grid with idle gaps zero-filled under a known mask (never interpolated). |
| S9 clock bias | Demean the video track and the reference segment. Match variations only. |
| S10 matching | Normalized cross-correlation at one-second steps, sub-second refinement, segment matching. |
| S11 continuity | Phase jump at each frame boundary from two-sided line fits (D-023); gaps that explain the jump give `DROPPED_FRAMES_EXPLAINED`, others give `EDIT_CANDIDATE`. |
| S12 face region | EXPERIMENTAL. Band amplitude in face pixels vs background pixels of the same rows. Never the only basis for `CONTRADICTED`. |
| S13 verdict | Deterministic rules (SPEC Part 8.14). |
| S14 overlay | Visualization only, labeled "Visualization of measured flicker. Not itself evidence." |
| S15 report | JSON, HTML, PDF. |

All signal arithmetic (normalization, row signals, phase, frequency, matching) is float32 or float64 (R6). FP16 is allowed only inside DNN inference.

### OpenCV 5 usage map (SPEC Part 8.17)

Each row lists the calls found in the engine source (`grep -o "cv2\.[A-Za-z_.]*" engine/gridprint_engine/*.py`). Where the SPEC map names an operation that the code does in NumPy instead, the table says so.

| Stage | Module | OpenCV 5 functions used | Notes |
|---|---|---|---|
| S1 | `io.py` | `cv2.VideoCapture` (`CAP_PROP_FRAME_COUNT`, `CAP_PROP_FRAME_WIDTH`, `CAP_PROP_FRAME_HEIGHT`) | Cross-check of frame count and size. Decoding and PTS use PyAV. |
| S2 | `color.py` | `cv2.LUT` | Inverse transfer lookup table to float32 linear luminance. |
| S4 | `motion.py` | `cv2.goodFeaturesToTrack`, `cv2.calcOpticalFlowPyrLK`, `cv2.findHomography` with `cv2.USAC_MAGSAC`, `cv2.DISOpticalFlow_create` (`DISOPTICAL_FLOW_PRESET_FAST`), `cv2.dilate` | Each frame is registered directly to the middle (reference) frame (D-022). |
| S5 | `segment.py` | `cv2.dnn.readNet`, `cv2.dnn.blobFromImage`, `cv2.resize`, `cv2.cvtColor`, `cv2.dilate` | PP-HumanSeg ONNX model from opencv_zoo. |
| S6 | `patches.py` | `cv2.warpPerspective` (`WARP_INVERSE_MAP`, `INTER_NEAREST`) | Patch masks mapped into each frame. Per-patch row sums use NumPy `np.add.reduceat` (not `cv2.reduce`). |
| S7 | `rowsignal.py` | `cv2.warpPerspective` (`INTER_LINEAR`, `INTER_NEAREST`, `WARP_INVERSE_MAP`) | Temporal mean in scene coordinates. Masked moving average and division are NumPy (`np.divide` with `where`), float32. |
| S8 | `phase.py`, `pipeline.py` | `cv2.solve` (`DECOMP_SVD`, float64), `cv2.dft` (`DFT_COMPLEX_OUTPUT`), `cv2.getOptimalDFTSize` | Least-squares phase fit; DFT cross-check. Detrending in S7 uses `np.linalg.lstsq`. |
| S12 | `facecheck.py` | `cv2.FaceDetectorYN.create`, `cv2.cvtColor` | YuNet ONNX model from opencv_zoo. |
| S14 | `overlay.py` | `cv2.applyColorMap` (`COLORMAP_TWILIGHT_SHIFTED`), `cv2.VideoWriter`, `cv2.VideoWriter_fourcc`, `cv2.resize`, `cv2.cvtColor`, `cv2.putText`, `cv2.polylines`, `cv2.line`, `cv2.rectangle` | Temporal band-pass at the flicker alias rate is a NumPy complex demodulation, not an OpenCV filter. |
| Calibration | `calibration_rig/fit_readout.py` (milestone M5) | `cv2.reduce` (`REDUCE_AVG`), `cv2.dft` (`DFT_COMPLEX_OUTPUT`), `cv2.getOptimalDFTSize`, `cv2.magnitude` | Band-period measurement on rig clips; readout time from the fitted band period. |

### Design choices recorded in `docs/DECISIONS.md`

- Analysis grid: frames are block-averaged to a small grid; each block keeps the mean sensor row index of its rows, so timing is kept (D-006).
- Flicker-compensated temporal mean (D-015).
- Readout direction chosen by physical plausibility of the measured flicker frequency, then band SNR (D-016).
- Motion: each frame is registered directly to the reference frame; chaining is only a fallback (D-022).
- Continuity: two-sided line fits of the phase at each frame boundary give the jump and its standard error (D-023, replaces D-014).

## 6. AWS deployment

The infrastructure is AWS CDK v2 (Python) in `infra/` (SPEC Part 10.6).

| Stack | Contents |
|---|---|
| Network | VPC, private subnets, endpoints for S3 and DynamoDB |
| Storage | S3 buckets with SSE-KMS and lifecycle deletion |
| Data | DynamoDB `Jobs`, `Reviews`, `GridLog`, `TraceIndex` |
| Compute | ECS cluster on Graviton4 `c8g`, stock OpenCV 5 (COOL AMI used when `aws.cool_ami_id` is set); SQS queue with DLQ; autoscaling on queue depth |
| API | Fargate `linux/arm64` service behind an internal Application Load Balancer |
| IoT | Thing type, certificates, policy, topic rule |
| Auth | Cognito user pool with `reviewer` group |
| Web | S3 + CloudFront; WAF rate limits |
| Observability | CloudWatch structured logs, dashboards, alarms |
| AI | IAM permission for the pinned Bedrock model only |

Region: `us-east-1` (DECISIONS D-005). `make deploy` creates all stacks; `make destroy` removes them.

### Deployment status (2026-10-27)

Account 643700104680, region `us-east-1`, resource prefix `orchard` (D-021). Nine of ten stacks are deployed.

Public endpoint: https://5u7suz00bi.execute-api.us-east-1.amazonaws.com (API Gateway → VPC link → internal ALB → Fargate arm64 API; web app on the same origin).

| Stack | Status | Note |
|---|---|---|
| Network | Deployed | |
| Storage | Deployed | S3 buckets with SSE-KMS |
| Data | Deployed | DynamoDB `Jobs`, `Reviews`, `GridLog`, `TraceIndex` |
| AI | Deployed | Planner model Amazon Nova Lite on Amazon Bedrock through a cross-account role (D-026); the deterministic guard and fallback planner cover rejected or failed model steps. |
| Auth | Deployed | Cognito user pool with `reviewer` group |
| Compute | Deployed | ECS cluster; Graviton4 `c8g.xlarge` worker Auto Scaling group, at most one instance within the account vCPU quota (D-024); SQS queue and DLQ |
| API | Deployed | Fargate `linux/arm64` behind an internal ALB. Public HTTPS through Amazon API Gateway (HTTP API) and a VPC link to the ALB (D-025). The web app is served from the same origin. |
| IoT | Deployed | IoT topic rule and ingest Lambda |
| Observability | Deployed | CloudWatch dashboard and alarms |
| Web | Not deployed | CloudFront requires AWS account verification (H1). The web app is served by the API service instead. |

Images: `linux/arm64`, built on a Graviton EC2 build instance by `infra/build_images.py` and pushed to Amazon ECR. They run on Graviton.

COOL: not active. The Marketplace subscription is pending (H1). The engine runs stock OpenCV 5.0.0 on Graviton. The COOL award is not claimed unless the benchmark in §7 runs.

### End-to-end runs on AWS

Each run below is a demo case run on the deployed system. The job ran on a Graviton4 `c8g.xlarge` ECS worker, with the planner on Amazon Bedrock (Amazon Nova Lite) and the grid reference read from DynamoDB. The input clips are **SYNTHETIC**: rolling-shutter simulator clips from `eval/make_demo_inputs.py`, all with true recording start 2026-01-20T10:00:00Z. They are not real camera recordings.

Evidence per job: `results/aws/<job_id>/` (`result.json`, `trace.json`, `report.html`, `report.pdf`, plots). The table is generated from `results/aws/index.json` (written by `scripts/collect_aws_runs.py`). "Error" is the recording-time estimate minus the true start. "Total stage time" is the sum of `stage_timings_s`.

<!-- aws-runs:begin (generated from results/aws/index.json) -->
| Job | Demo case | Target verdict | Measured verdict | Lifecycle | Reasons | Recording-time estimate (true start 2026-01-20T10:00:00Z) | Band SNR | Total stage time | Source |
|---|---|---|---|---|---|---|---|---|---|
| `aws3-capture-verified-040158` | capture-verified (SYNTHETIC) | `VERIFIED` | `VERIFIED` | `FINAL` | `READOUT_FROM_SIDECAR`, `MATCH_OK` | 2026-01-20T10:00:00.020533+00:00, error +0.021 s | 11.32 dB | 53.7 s | <!-- src: results/aws/index.json#aws3-capture-verified-040158.verdict --> <!-- src: results/aws/index.json#aws3-capture-verified-040158.time_estimate_iso --> <!-- src: results/aws/index.json#aws3-capture-verified-040158.band_snr_db --> <!-- src: results/aws/index.json#aws3-capture-verified-040158.stage_timings_s --> |
| `aws3-cut-1s-040211` | cut-1s (SYNTHETIC) | `CONTRADICTED` | `VERIFIED` | `FINAL` | `READOUT_ESTIMATED`, `MATCH_OK`, `CLAIM_TIME_MATCH` | 2026-01-20T10:00:00.469923+00:00, error +0.470 s | 11.37 dB | 60.5 s | <!-- src: results/aws/index.json#aws3-cut-1s-040211.verdict --> <!-- src: results/aws/index.json#aws3-cut-1s-040211.time_estimate_iso --> <!-- src: results/aws/index.json#aws3-cut-1s-040211.band_snr_db --> <!-- src: results/aws/index.json#aws3-cut-1s-040211.stage_timings_s --> |
| `aws3-dropped-frames-040218` | dropped-frames (SYNTHETIC) | `VERIFIED` (`DROPPED_FRAMES_EXPLAINED`) | `VERIFIED` | `FINAL` | `READOUT_FROM_SIDECAR`, `MATCH_OK`, `DROPPED_FRAMES_EXPLAINED` | 2026-01-20T10:00:00.014252+00:00, error +0.014 s | 11.43 dB | 52.1 s | <!-- src: results/aws/index.json#aws3-dropped-frames-040218.verdict --> <!-- src: results/aws/index.json#aws3-dropped-frames-040218.time_estimate_iso --> <!-- src: results/aws/index.json#aws3-dropped-frames-040218.band_snr_db --> <!-- src: results/aws/index.json#aws3-dropped-frames-040218.stage_timings_s --> |
| `aws4-agent-recovery-041816` | agent-recovery (SYNTHETIC) | second-pass verdict after re-planning | `INCONCLUSIVE` | `FINAL` | `READOUT_ESTIMATED`, `NO_REFERENCE_COVERAGE` | none | 7.54 dB | 56.6 s | <!-- src: results/aws/index.json#aws4-agent-recovery-041816.verdict --> <!-- src: results/aws/index.json#aws4-agent-recovery-041816.time_estimate_iso --> <!-- src: results/aws/index.json#aws4-agent-recovery-041816.band_snr_db --> <!-- src: results/aws/index.json#aws4-agent-recovery-041816.stage_timings_s --> |
| `aws4-capture-verified-041747` | capture-verified (SYNTHETIC) | `VERIFIED` | `VERIFIED` | `FINAL` | `READOUT_FROM_SIDECAR`, `MATCH_OK` | 2026-01-20T09:59:59.973488+00:00, error -0.027 s | 6.61 dB | 52.5 s | <!-- src: results/aws/index.json#aws4-capture-verified-041747.verdict --> <!-- src: results/aws/index.json#aws4-capture-verified-041747.time_estimate_iso --> <!-- src: results/aws/index.json#aws4-capture-verified-041747.band_snr_db --> <!-- src: results/aws/index.json#aws4-capture-verified-041747.stage_timings_s --> |
| `aws4-cut-1s-041731` | cut-1s (SYNTHETIC) | `CONTRADICTED` | `VERIFIED` | `FINAL` | `READOUT_ESTIMATED`, `MATCH_OK`, `CLAIM_TIME_MATCH` | 2026-01-20T10:00:00.471766+00:00, error +0.472 s | 11.38 dB | 46.3 s | <!-- src: results/aws/index.json#aws4-cut-1s-041731.verdict --> <!-- src: results/aws/index.json#aws4-cut-1s-041731.time_estimate_iso --> <!-- src: results/aws/index.json#aws4-cut-1s-041731.band_snr_db --> <!-- src: results/aws/index.json#aws4-cut-1s-041731.stage_timings_s --> |
| `aws4-daylight-only-041808` | daylight-only (SYNTHETIC) | `INCONCLUSIVE` | `INCONCLUSIVE` | `DRAFT` | `SIGNAL_ABSENT`, `READOUT_ESTIMATED`, `HIGH_COMPRESSION`, `USER_INPUT_REQUESTED` | none | -11.00 dB | 15.2 s | <!-- src: results/aws/index.json#aws4-daylight-only-041808.verdict --> <!-- src: results/aws/index.json#aws4-daylight-only-041808.time_estimate_iso --> <!-- src: results/aws/index.json#aws4-daylight-only-041808.band_snr_db --> <!-- src: results/aws/index.json#aws4-daylight-only-041808.stage_timings_s --> |
| `aws4-dropped-frames-041757` | dropped-frames (SYNTHETIC) | `VERIFIED` (`DROPPED_FRAMES_EXPLAINED`) | `VERIFIED` | `FINAL` | `READOUT_ESTIMATED`, `MATCH_OK` | 2026-01-20T10:00:00.109978+00:00, error +0.110 s | 8.07 dB | 42.8 s | <!-- src: results/aws/index.json#aws4-dropped-frames-041757.verdict --> <!-- src: results/aws/index.json#aws4-dropped-frames-041757.time_estimate_iso --> <!-- src: results/aws/index.json#aws4-dropped-frames-041757.band_snr_db --> <!-- src: results/aws/index.json#aws4-dropped-frames-041757.stage_timings_s --> |
| `aws4-insertion-041739` | insertion (SYNTHETIC) | `CONTRADICTED` | `job failed (no result)` | `None` |  | none | n/a | 0.0 s | <!-- src: results/aws/index.json#aws4-insertion-041739.verdict --> <!-- src: results/aws/index.json#aws4-insertion-041739.time_estimate_iso --> <!-- src: results/aws/index.json#aws4-insertion-041739.band_snr_db --> <!-- src: results/aws/index.json#aws4-insertion-041739.stage_timings_s --> |
<!-- aws-runs:end -->

Findings from these runs:
- The capture-verified and dropped-frames cases gave their target verdicts on AWS.
- The `cut-1s` case did **not** give its target verdict. The continuity check (`check_continuity`) found no edit event, so the job ended `VERIFIED`. This is a missed edit on a SYNTHETIC clip; it is listed as a failure case. The report does not claim edit detection on AWS from these runs.
- Cases without a row (insertion, daylight-only, agent-recovery) have no AWS run evidence yet.

Agent trace evidence (`results/aws/*/trace.json`): every step has `planner: "bedrock"` and `model_id: "us.amazon.nova-lite-v1:0"`. In each run the code-enforced guard rejected the model's proposal and substituted a rule step twice. The `decision_reason` reads "guard: planner proposed extract_flicker … (frequency or axis override before the first extraction); fallback rule: …" (steps 4 and 5). The model had tried to override the nominal frequency or readout axis before the first flicker extraction; the guard ran the deterministic rules (rank light patches, then a first extraction on all eligible patches). The last step is forced by the policy "report must be rendered". Behaviour B2 (readout unknown, so blind estimation) appears in the `cut-1s` run: `estimate_readout` returned `READOUT_ESTIMATED` and the verdict carries that reason. B1 and B3–B6 did not trigger in these runs (no weak signal, no high motion, no `CONTRADICTED` verdict). They are shown by the agent tests (`agent/tests/test_agent.py`).

x86 and Arm: production containers are `linux/arm64`. The `linux/amd64` image exists only for the x86 baseline in the COOL benchmark.


## 7. COOL benchmark

Protocol (SPEC Part 12): same engine code and pinned inputs (`bench/inputs.txt`), three configurations of equal vCPU and memory:
- **A:** x86 instance, stock OpenCV 5 (`linux/amd64` image).
- **B:** Graviton `c8g`, stock OpenCV 5 (`linux/arm64` image).
- **C:** Graviton `c8g`, OpenCV 5 with COOL.

Metrics: throughput (video-seconds per wall-second), per-stage latency p50/p95, CPU utilization, memory, cost per hour of video (on-demand price from the AWS Price List API divided by throughput). At least five runs per configuration, mean and standard deviation. Parity check of ENF tracks and verdicts across A, B, C. Evidence that COOL executes: build information, loaded library paths, version string, profiler capture.

COOL could not be obtained (V5: Marketplace subscription pending, H1), so the COOL award is not claimed. This section reports A vs B only, measured on 2026-10-27 on AWS (run `results/bench/2026-10-27/`). Both instances ran OpenCV 5.0.0 on Amazon Linux 2023 with the same pinned input. The input is a real recording: the public CC BY-SA clip listed in `bench/inputs.txt` and `docs/LICENSES.md`. Five runs per configuration; instances were terminated after the run.

| Config | Instance | Arch | Throughput (video-s per wall-s), mean ± std | S2 linear p50 | S4 motion p50 | S8 phase p50 | Peak RSS | On-demand price | Cost per video-hour |
|---|---|---|---|---|---|---|---|---|---|
| A | `c7i.2xlarge` | x86_64 | 0.916 ± 0.003 <!-- src: results/bench/2026-10-27/A/summary.json#throughput_video_s_per_wall_s --> | 5.12 s <!-- src: results/bench/2026-10-27/A/summary.json#stage_latency_s.S2_linear.p50 --> | 2.38 s <!-- src: results/bench/2026-10-27/A/summary.json#stage_latency_s.S4_motion.p50 --> | 1.61 s <!-- src: results/bench/2026-10-27/A/summary.json#stage_latency_s.S8_phase.p50 --> | 2000 MB <!-- src: results/bench/2026-10-27/A/summary.json#peak_rss_mb_max --> | $0.357/h <!-- src: results/bench/2026-10-27/cost.json#configs.A.ec2_usd_per_hour --> | $0.390 <!-- src: results/bench/2026-10-27/cost.json#configs.A.cost_per_video_hour_usd --> |
| B | `c8g.2xlarge` (Graviton4) | aarch64 | 1.201 ± 0.002 <!-- src: results/bench/2026-10-27/B/summary.json#throughput_video_s_per_wall_s --> | 4.24 s <!-- src: results/bench/2026-10-27/B/summary.json#stage_latency_s.S2_linear.p50 --> | 1.65 s <!-- src: results/bench/2026-10-27/B/summary.json#stage_latency_s.S4_motion.p50 --> | 0.98 s <!-- src: results/bench/2026-10-27/B/summary.json#stage_latency_s.S8_phase.p50 --> | 1958 MB <!-- src: results/bench/2026-10-27/B/summary.json#peak_rss_mb_max --> | $0.319/h <!-- src: results/bench/2026-10-27/cost.json#configs.B.ec2_usd_per_hour --> | $0.266 <!-- src: results/bench/2026-10-27/cost.json#configs.B.cost_per_video_hour_usd --> |

Findings:
- Graviton4 processes the same video faster and at lower cost per video-hour than the x86 baseline of equal vCPU count (table above; full per-stage p50/p95 in the `summary.json` files).
- Parity: verdicts are identical on A and B <!-- src: results/bench/2026-10-27/parity.json#pairs.0.verdicts_identical -->. The ENF tracks differ by up to 0.568 Hz <!-- src: results/bench/2026-10-27/parity.json#pairs.0.max_abs_enf_diff_hz -->, outside the 0.001 Hz tolerance. The clip has no usable flicker signal (verdict `INCONCLUSIVE`, `SIGNAL_ABSENT`), so the tracks are noise estimates and small floating-point differences between the two builds move them freely. A parity check on a clip with a strong signal is still open.
- Evidence of the software stack on each instance: `results/bench/2026-10-27/evidence/{A,B}/` (OpenCV build information, loaded libraries, `lscpu`, instance identity, `pip freeze`).

## 8. Agent design and evaluation

### Design

The runtime agent plans and adapts the analysis of each job. It is the agentic workflow of GRIDPRINT. The AI coding assistant that wrote code is not part of it.

- **Perception:** OpenCV 5 stage outputs returned by MCP tools: band SNR, readout confidence, motion level, patch ranking, match statistics, continuity events.
- **Decision:** a planner chooses the next tool call. Two planners use the same tools: Claude on Amazon Bedrock (`planner_bedrock.py`) and a deterministic fallback (`fallback_planner.py`). Policies in `policies.py` enforce budgets and order rules in code.
- **Action:** MCP tool calls to the `gridprint-engine` server, `request_user_input`, `request_human_review`, `render_report`.

Required adaptive behaviors (SPEC Part 9.3):

| ID | Trigger from OpenCV output | Action |
|---|---|---|
| B1 | `SIGNAL_WEAK` after first extraction | Re-select patches, switch axis, or switch nominal frequency; extract again. |
| B2 | Readout unknown | Blind estimation; if confidence is low, ask for the camera model. |
| B3 | `HIGH_MOTION` | Stricter motion analysis or low-motion frames only; extract again. |
| B4 | `HIGH_COMPRESSION` and weak signal | Ask for the original file. |
| B5 | No usable signal after the budget | `compute_verdict` → `INCONCLUSIVE` with reasons; stop. |
| B6 | Verdict `CONTRADICTED` | `request_human_review`; no FINAL report. |

The agent cannot write or change a verdict, thresholds, or reason codes. Every step is traced: time, planner type, model ID, tool, input summary, output summary, decision reason, duration.

### Evaluation

Metrics (SPEC Part 9.7) for both planners: task success, recovery rate, tool calls per job, unnecessary-call rate, human-review precision, budget-exhaustion rate.

Results: the tables for this section are generated by `eval/make_report.py` into `results/eval/<date>/`. Example traces for B1–B6 are stored under `results/`.

## 9. Evaluation

Real and synthetic results are reported in separate tables. Synthetic results are labeled `SYNTHETIC` and are never presented as real-world accuracy.

### Synthetic evaluation

Simulator: `eval/simulator/`. It makes rolling-shutter videos with known ground truth (ENF track, flicker depth, readout time, exposure, timing jitter, dropped frames, motion, noise, compression, cuts and insertions).

Results: generated by `eval/make_report.py` into `results/`. (Tables are inserted here from those files.)

### Real-world evaluation

Dataset: `eval/DATASET.md`. Splits by recording day and phone. The false-`CONTRADICTED` target is written in `docs/DECISIONS.md` before any test data is seen. Thresholds are calibrated on the calibration split by `eval/calibrate_thresholds.py`. The test split is run once with frozen thresholds.

Metrics (SPEC Part 11.5): confusion matrix against ground-truth classes, false-`CONTRADICTED` rate on authentic clips, `VERIFIED` coverage and `INCONCLUSIVE` rate per condition, time error for `VERIFIED` clips, edit detection rate and localization error, dropped-frame false alarms, signal survival per compression platform, experimental face-region results (separate), runtime per stage.

Results: generated by `eval/make_report.py` into `results/eval/<date>/`. (Tables are inserted here from those files.)

## 10. Failure cases

The failure-case gallery (at least ten cases, with overlays and plain explanations) is generated by `eval/make_report.py` into `results/eval/<date>/`. (Gallery is linked here from those files.)

## 11. Limitations

- **Anti-banding.** Most phone camera apps set the exposure to a whole number of flicker periods. This removes the bands. Ordinary phone videos therefore often give `INCONCLUSIVE`. This is not evidence of a fake.
- **Static bands at some frame rates.** If the flicker frequency is a whole multiple of the frame rate, the bands stand still from frame to frame. Example: 120 Hz flicker recorded at 30 frames per second. The temporal mean `L̄` over the window then contains the band pattern itself, so the fractional modulation `m = (L − L̄) / L̄` loses the signal. Only the slow motion caused by the grid deviation remains. Such recordings are often `SIGNAL_WEAK` or `SIGNAL_ABSENT`.
- **Cuts of a whole number of flicker periods.** A cut that removes exactly a whole number of flicker periods changes the flicker phase only by the grid deviation multiplied by the removed time. This change can be too small to detect. Cuts are found more reliably by segment matching against the reference log than by phase continuity alone.
- **HDR not supported.** HLG and PQ videos stop with `HDR_UNSUPPORTED`.
- **Short clips.** A short frequency track can match many reference times. The result is `TRACK_TOO_SHORT` or `NO_UNIQUE_MATCH`.
- **Compression.** Strong recompression (messaging apps, social platforms) removes the faint bands. The agent asks for the original file (B4).
- **Lighting.** Daylight, incandescent lamps with high thermal inertia, and DC or battery lamps give little or no flicker.
- **Motion.** Fast camera motion and moving people reduce the static area. The agent tries stricter motion analysis (B3).
- **Readout time.** Without a sidecar or a camera profile, the readout time is estimated blindly with lower confidence.
- **Reference coverage.** Time can be found only inside the reference log. Zones without a Node or a public 1-second data source give `NO_REFERENCE_COVERAGE`.
- **Face-region check.** EXPERIMENTAL. It is never the only basis for `CONTRADICTED`.
- **Scope.** GRIDPRINT is not a deepfake classifier, not a face recognition system, not a location tracker, and not cryptographic proof.

## 12. Responsible use

See `docs/RESPONSIBLE_USE.md`. Key controls:
- The uploader notice explains that the result can reveal recording time and grid zone.
- Output location is limited to the grid zone.
- Short retention; reports are not public by default.
- Every `CONTRADICTED` result needs human review before it is final.
- No face recognition; no face crops kept beyond the job retention.
- Node safety: never connect electronics directly to mains; use a certified plug-in AC-to-AC adapter.
- Consent for every person in the dataset.

## 13. Prior art and references

ENF forensics started with audio recordings. Grigoras described the ENF criterion for checking the integrity of digital audio evidence, including finding edits and the recording time by comparison with an ENF database [1]. Garg, Varna, and Wu showed that the ENF can be captured from the flicker of fluorescent lighting by optical sensors and video, and used it as a natural time stamp and for tampering detection in surveillance video [2]. Su, Hajj-Ahmad, Garg, and Wu used the rolling shutter of CMOS cameras to raise the effective sampling rate for ENF extraction from video, by treating each row as a sample [3]. C2PA Content Credentials attach signed provenance metadata to media files [4]; GRIDPRINT is complementary, because it reads a signal inside the pixels, which a re-upload does not remove.

GRIDPRINT builds on [2] and [3]. Its contributions are the engineering for phone video (sensor-row timing, VFR timestamps, motion-compensated static masks, idle-gap handling), the deterministic three-verdict logic with human review, the agent that adapts the analysis, and the GPS-timed reference Node.

References (each checked on 2026-10-26):

1. C. Grigoras, "Digital audio recording analysis: the Electric Network Frequency (ENF) Criterion," *The International Journal of Speech, Language and the Law*, vol. 12, no. 1, pp. 63–76, 2005. DOI: `10.1558/sll.2005.12.1.63`. Checked via Crossref: https://api.crossref.org/works/10.1558/sll.2005.12.1.63
2. R. Garg, A. L. Varna, M. Wu, "'Seeing' ENF: natural time stamp for digital video via optical sensing and signal processing," *Proceedings of the 19th ACM International Conference on Multimedia (MM '11)*, pp. 23–32, 2011. DOI: `10.1145/2072298.2072303`. Checked via Crossref: https://api.crossref.org/works/10.1145/2072298.2072303 ; author copy: https://www.mast.umd.edu/files/paper_ENF/conf_paper1_ACMMM11.pdf
3. H. Su, A. Hajj-Ahmad, R. Garg, M. Wu, "Exploiting rolling shutter for ENF signal extraction from video," *2014 IEEE International Conference on Image Processing (ICIP)*, 2014. DOI: `10.1109/ICIP.2014.7026086`. Checked via Crossref: https://api.crossref.org/works/10.1109/icip.2014.7026086 ; author copy: https://www.mast.umd.edu/files/paper_ENF/conf_paper11_ICIP14.pdf
4. Coalition for Content Provenance and Authenticity, "Content Credentials: C2PA Technical Specification," version `2.3`. https://spec.c2pa.org/specifications/specifications/2.3/specs/C2PA_Specification

## 14. Reproducibility

- Dependencies are pinned in `uv.lock` (DECISIONS D-001). OpenCV is pinned to `opencv-python-headless==5.0.0.93` (D-003).
- Commands: `make setup`, `make lint`, `make test`, `make local`, `make deploy`, `make destroy`, `make eval`, `make bench`, `make final-check`.
- Configuration: `config/default.yaml` (engineering constants, documented in `docs/DECISIONS.md`), `config/thresholds.yaml` (generated by `eval/calibrate_thresholds.py`), `config/zones.yaml`, `config/camera_profiles.yaml`.
- Evaluation outputs: `results/eval/<date>/` with data hash, date, and script version.
- Benchmark outputs: `results/bench/<date>/` with evidence files.
- Every number in this report has a source tag to a file in `results/` (`scripts/check_numbers_sourced.py`).
