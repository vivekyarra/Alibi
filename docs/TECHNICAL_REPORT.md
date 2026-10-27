# GRIDPRINT technical report

GRIDPRINT checks if a video is real from the flicker of the lights in the room. It reads the power-grid frequency from rolling-shutter flicker bands with OpenCV 5 and compares it with a reference log of the real grid.

Status (2026-10-27): sections 1–6 and 11–14 describe the built system. Sections 7–10 report measured results from `results/`: the Graviton vs x86 benchmark (§7) and the SYNTHETIC agent and pipeline evaluation (§8–§10); §6 has the AWS runs. Real-world results wait for the real dataset (H5). This report contains no measured number without a source tag (SPEC Part 14.3).

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
- **Planner:** an LLM on Amazon Bedrock through the Converse API with tool use (`agent/planner_bedrock.py`; Amazon Nova Lite through a cross-account role, D-026; the model ID is configuration, so a Claude model works unchanged), with the deterministic fallback planner taking over for any step where the model call fails; the fallback planner can also run alone (`agent/fallback_planner.py`). The AWS runs in §6 use the Bedrock planner (Amazon Nova Lite); the SYNTHETIC evaluation suite in §8–§9 uses the fallback planner.
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

COOL: not active, and the COOL award is not claimed. The Marketplace subscription is pending (H1). The engine runs stock OpenCV 5.0.0 on Graviton; §7 reports the Graviton vs x86 benchmark.

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

x86 and Arm: production containers are `linux/arm64`. The `linux/amd64` image exists only for the x86 baseline (configuration A) of the benchmark in §7.


## 7. COOL benchmark

**COOL award not claimed.** Configuration C (Graviton with COOL) needs the COOL AMI from AWS Marketplace, and that subscription is still pending (H1, V5). Configurations A and B ran on 2026-10-27: the same engine on x86 and on Graviton4, both with stock OpenCV 5.0.0. They show what the move to Graviton gives before any COOL acceleration.

Protocol (SPEC Part 12): same engine code and pinned inputs (`bench/inputs.txt`), configurations of equal vCPU and memory:
- **A:** x86 `c7i.2xlarge`, stock OpenCV 5 (`linux/amd64` image).
- **B:** Graviton4 `c8g.2xlarge`, stock OpenCV 5 (`linux/arm64` image).
- **C:** Graviton `c8g`, OpenCV 5 with COOL. Not run (see above).

Metrics: throughput (video-seconds per wall-second), per-stage latency p50/p95, CPU utilization, memory, cost per hour of video (on-demand price from the AWS Price List API divided by throughput). Five runs per configuration, mean and standard deviation. Parity check of ENF tracks and verdicts across configurations. Evidence per instance: instance identity, `cv2.getBuildInformation()`, loaded library paths, versions, `lscpu`, `pip freeze`.

Input: one pinned real clip, the public Creative Commons (CC BY-SA) clip "Fluorescent beat effect" from Wikimedia Commons (license in `docs/LICENSES.md`), with an empty grid log. These are speed and cost measurements only; they say nothing about verification accuracy.

### Results A vs B (stock OpenCV 5.0.0, `results/bench/2026-10-27/`)

| Metric | A: x86 `c7i.2xlarge` | B: Graviton4 `c8g.2xlarge` |
|---|---|---|
| Throughput, video-s per wall-s (mean ± std, 5 runs) | 0.916 ± 0.003 <!-- src: results/bench/2026-10-27/A/summary.json#throughput_video_s_per_wall_s --> | 1.201 ± 0.002 <!-- src: results/bench/2026-10-27/B/summary.json#throughput_video_s_per_wall_s --> |
| On-demand price, `us-east-1` | $0.357 per hour <!-- src: results/bench/2026-10-27/cost.json#configs.A.ec2_usd_per_hour --> | $0.31904 per hour <!-- src: results/bench/2026-10-27/cost.json#configs.B.ec2_usd_per_hour --> |
| Cost per video-hour | $0.390 <!-- src: results/bench/2026-10-27/cost.json#configs.A.cost_per_video_hour_usd --> | $0.266 <!-- src: results/bench/2026-10-27/cost.json#configs.B.cost_per_video_hour_usd --> |
| Mean CPU utilization (fraction of all vCPUs) | 0.180 <!-- src: results/bench/2026-10-27/A/summary.json#cpu_util_mean --> | 0.174 <!-- src: results/bench/2026-10-27/B/summary.json#cpu_util_mean --> |
| Peak memory (RSS) | 1999.9 MB <!-- src: results/bench/2026-10-27/A/summary.json#peak_rss_mb_max --> | 1957.8 MB <!-- src: results/bench/2026-10-27/B/summary.json#peak_rss_mb_max --> |
| Verdict, all runs | `INCONCLUSIVE` (5 of 5) <!-- src: results/bench/2026-10-27/A/runs.json#verdict --> | `INCONCLUSIVE` (5 of 5) <!-- src: results/bench/2026-10-27/B/runs.json#verdict --> |

Stage latency p50 in seconds (S5 and S12 take about 0.0001 s on both and are left out): <!-- src: results/bench/2026-10-27/A/summary.json#stage_latency_s.S5_segment.p50 --> <!-- src: results/bench/2026-10-27/B/summary.json#stage_latency_s.S12_face.p50 -->

| Stage | A: x86 `c7i.2xlarge` | B: Graviton4 `c8g.2xlarge` |
|---|---|---|
| S1 ingest | 0.961 <!-- src: results/bench/2026-10-27/A/summary.json#stage_latency_s.S1_ingest.p50 --> | 1.038 <!-- src: results/bench/2026-10-27/B/summary.json#stage_latency_s.S1_ingest.p50 --> |
| S2 linear light | 5.123 <!-- src: results/bench/2026-10-27/A/summary.json#stage_latency_s.S2_linear.p50 --> | 4.242 <!-- src: results/bench/2026-10-27/B/summary.json#stage_latency_s.S2_linear.p50 --> |
| S3 readout | 4.002 <!-- src: results/bench/2026-10-27/A/summary.json#stage_latency_s.S3_readout.p50 --> | 3.324 <!-- src: results/bench/2026-10-27/B/summary.json#stage_latency_s.S3_readout.p50 --> |
| S4 motion | 2.385 <!-- src: results/bench/2026-10-27/A/summary.json#stage_latency_s.S4_motion.p50 --> | 1.646 <!-- src: results/bench/2026-10-27/B/summary.json#stage_latency_s.S4_motion.p50 --> |
| S6 patches | 1.964 <!-- src: results/bench/2026-10-27/A/summary.json#stage_latency_s.S6_patches.p50 --> | 1.143 <!-- src: results/bench/2026-10-27/B/summary.json#stage_latency_s.S6_patches.p50 --> |
| S7 row signal | 0.752 <!-- src: results/bench/2026-10-27/A/summary.json#stage_latency_s.S7_rowsignal.p50 --> | 0.410 <!-- src: results/bench/2026-10-27/B/summary.json#stage_latency_s.S7_rowsignal.p50 --> |
| S8 phase | 1.614 <!-- src: results/bench/2026-10-27/A/summary.json#stage_latency_s.S8_phase.p50 --> | 0.978 <!-- src: results/bench/2026-10-27/B/summary.json#stage_latency_s.S8_phase.p50 --> |

p95 values are in the same files. On this workload Graviton4 B processes more video per second than x86 A and costs less per hour of video, with stock OpenCV on both. Of the stages in the table, all except S1 (decoding with PyAV) are faster on B.

**Parity.** Verdicts are identical on A and B. <!-- src: results/bench/2026-10-27/parity.json#pairs.0.verdicts_identical --> The ENF tracks are not within the 0.001 Hz tolerance (largest difference 0.568 Hz). <!-- src: results/bench/2026-10-27/parity.json#pairs.0.max_abs_enf_diff_hz --> This clip carries no usable grid signal, so its extracted tracks are noise, and small numeric differences between the x86 and Arm builds give different noise. Track parity can only be judged on a clip with a usable signal; that run is open, together with configuration C.

Evidence that each run used the stated instance and build: `results/bench/2026-10-27/evidence/A/` and `evidence/B/` (`instance_identity.json`, `build_information.txt`, `loaded_libraries.txt`, `versions.json`, `lscpu.txt`, `pip_freeze.txt`). Per-run records: `A/runs.json`, `B/runs.json`; logs: `logs/`; prices: `prices.json` (AWS Price List API).

Tooling in `bench/`: `run_bench.py` (runner), `configs.yaml` (configurations A, B, C), `inputs.txt` (pinned inputs), `make_inputs.py`, `prices.py` (AWS Price List API), `cool_evidence.py` (build info, loaded libraries, version capture), and `run_remote.md` (how to run it on EC2). Output goes to `results/bench/<date>/`. When the COOL subscription is active, configuration C runs with the same command and adds its row to these tables.

## 8. Agent design and evaluation

### Design

The runtime agent plans and adapts the analysis of each job. It is the agentic workflow of GRIDPRINT. The AI coding assistant that wrote code is not part of it.

- **Perception:** OpenCV 5 stage outputs returned by MCP tools: band SNR, readout confidence, motion level, patch ranking, match statistics, continuity events.
- **Decision:** a planner chooses the next tool call. Two planners use the same tools: an LLM planner on Amazon Bedrock through the Converse API with tool use (`planner_bedrock.py`; Amazon Nova Lite `us.amazon.nova-lite-v1:0` through a cross-account role, D-026; the model ID is configuration) and a deterministic fallback (`fallback_planner.py`). Policies in `policies.py` enforce budgets and order rules in code.
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

Metrics (SPEC Part 9.7): task success, recovery rate, tool calls per job, unnecessary-call rate, human-review precision, budget-exhaustion rate.

**Planner coverage.** The evaluation suite below ran with the deterministic **fallback planner** only. The Bedrock planner was not run on the evaluation suite, so there are no Bedrock-planner metrics in this section. (The AWS demo runs in §6 used the Bedrock planner on the SYNTHETIC demo clips; they are not part of this evaluation.)

All values are **SYNTHETIC** (simulator clips, `synthetic-v1` suite, test split, 22 clips, frozen thresholds). They are not real-world accuracy.

| Agent metric (SYNTHETIC, fallback planner, test split) | Value [Wilson CI, 95 percent] |
|---|---|
| Task success (final verdict = expected verdict) | 68.2% [47.3–83.6] (k=15, n=22) <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.agent.task_success --> |
| Recovery rate (first extraction weak, a later extraction usable) | 33.3% [6.1–79.2] (k=1, n=3) <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.agent.recovery_rate --> |
| Unnecessary-call rate (repeated identical calls + tool errors) | 0.0% [0.0–1.7] (k=0, n=221) <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.agent.unnecessary_call_rate --> |
| Human-review precision (`CONTRADICTED` jobs that were edited clips) | 100.0% [34.2–100.0] (k=2, n=2) <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.agent.human_review_precision --> |
| Budget-exhaustion rate | 0.0% [0.0–14.9] (k=0, n=22) <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.agent.budget_exhaustion_rate --> |

Tool calls per job: mean 10.05, median 10.0, max 13.0 (n=22). <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.agent.tool_calls_per_job -->
`request_user_input` requests: one `original_file` request (B4). <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.agent.user_input_requests -->

Task success is mostly an engine result: the fallback planner follows fixed rules, so a wrong verdict usually comes from the signal or the thresholds, not the plan (see §10).

**Example traces.** Six full traces are copied unchanged from the evaluation runs to `results/agent_traces/`:

| Trace | Behaviour shown | What happens |
|---|---|---|
| [`short_readout_long_expo__s1031.json`](../results/agent_traces/short_readout_long_expo__s1031.json) | B1 with recovery | The first extraction is weak. The agent re-ranks patches and extracts again on the top patches. The second track is usable, so matching continues. (This job then ended in a wrong-time `VERIFIED`; see §10.) |
| [`weak_flicker__s1021.json`](../results/agent_traces/weak_flicker__s1021.json) | B1 → B5 | Re-rank patches, re-extract, switch nominal frequency, switch sensor axis; no usable signal, so `compute_verdict` gives `INCONCLUSIVE`. |
| [`messaging_compression__s1100.json`](../results/agent_traces/messaging_compression__s1100.json) (calibration split) | B4, B1, B5 | Strong compression and a weak signal: `request_user_input(kind=original_file)`, then the B1 alternatives, then B5. |
| [`no_mains_light__s1141.json`](../results/agent_traces/no_mains_light__s1141.json) | B4, B1, B5 | No mains-powered light: the same path ends `INCONCLUSIVE`. The missing signal is not treated as evidence of a fake. |
| [`reorder__s1201.json`](../results/agent_traces/reorder__s1201.json) | B6 | Verdict `CONTRADICTED` → `request_human_review` → `render_report(final=false)` (pending review). |
| [`clean__s1001.json`](../results/agent_traces/clean__s1001.json) | none (baseline) | Strong signal: the plain path probe → readout → motion → patches → extract → match → continuity → face check → verdict → final report. |

Behaviours **B2** (readout unknown or low-confidence blind estimate → ask for camera model) and **B3** (`HIGH_MOTION` → strict motion analysis) did not trigger on any of the 44 suite clips, so no suite trace shows them. In the camera-motion clips the motion stage did not report high motion. B2 and B3 are covered only by the agent tests (`agent/tests/`).

## 9. Evaluation

Real and synthetic results are reported in separate tables. Synthetic results are labeled `SYNTHETIC` and are never presented as real-world accuracy (SPEC 11.1).

### Synthetic evaluation

Simulator: `eval/simulator/`. It makes rolling-shutter videos with known ground truth (ENF track, flicker depth, readout time, exposure, timing jitter, dropped frames, motion, noise, compression, cuts and insertions). Suite `synthetic-v1` (`data/synthetic/v1/manifest.json`): 44 clips, 22 per split, one clip per condition per split. Each split has 16 authentic mains-lit clips, 1 authentic clip without mains light, and 5 edited clips. Every clip goes through the full agent (fallback planner) and engine.

**All numbers in this section are SYNTHETIC. They measure the pipeline against simulator ground truth, not real-world accuracy.**

Protocol (SPEC 11.4), followed in this order:
1. Calibration split run with the placeholder thresholds → `results/eval/2026-10-27/synthetic-v1-fallback/`.
2. `eval/calibrate_thresholds.py` grid search on the calibration split (target false-`CONTRADICTED` rate from `config/default.yaml`, no wrong-time `VERIFIED`). It wrote `config/thresholds.yaml` with provenance status `PROVISIONAL` (synthetic data only; must be recalibrated on the real dataset).
3. Test split run **once** with the frozen thresholds → `results/eval/2026-10-27-test/synthetic-v1-fallback/` (`run_meta.json` records the thresholds hash).

#### Test split (SYNTHETIC, frozen thresholds, fallback planner)

Full summary: [`summary.md`](../results/eval/2026-10-27-test/synthetic-v1-fallback/summary.md); per-clip table: [`clips.csv`](../results/eval/2026-10-27-test/synthetic-v1-fallback/clips.csv).

| Metric (SYNTHETIC) | Value [Wilson CI, 95 percent] |
|---|---|
| False-`CONTRADICTED` rate on authentic clips | 0.0% [0.0–18.4] (k=0, n=17) <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.false_contradicted_rate --> |
| `VERIFIED` coverage, mains-lit clips | 75.0% [50.5–89.8] (k=12, n=16) <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.verified_coverage_mains --> |
| Edit detection rate | 20.0% [3.6–62.4] (k=1, n=5) <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.edit_detection --> |
| Dropped-frame false alarms | 0.0% [0.0–79.3] (k=0, n=1) <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.dropped_frame_false_alarm --> |
| Agent task success (verdict = expected) | 68.2% [47.3–83.6] (k=15, n=22) <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.agent.task_success --> |
| Agent recovery rate (weak first extraction later usable) | 33.3% [6.1–79.2] (k=1, n=3) <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.agent.recovery_rate --> |
| Unnecessary-call rate | 0.0% [0.0–1.7] (k=0, n=221) <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.agent.unnecessary_call_rate --> |
| Human-review precision | 100.0% [34.2–100.0] (k=2, n=2) <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.agent.human_review_precision --> |
| Budget-exhaustion rate | 0.0% [0.0–14.9] (k=0, n=22) <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.agent.budget_exhaustion_rate --> |

| class (SYNTHETIC) | VERIFIED | CONTRADICTED | INCONCLUSIVE | no result |
|---|---|---|---|---|
| authentic-with-mains-light | 12 | 0 | 4 | 0 <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.confusion.authentic-with-mains-light --> |
| authentic-without-mains-light | 0 | 0 | 1 | 0 <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.confusion.authentic-without-mains-light --> |
| edited | 2 | 2 | 1 | 0 <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.confusion.edited --> |

Rows are ground-truth classes; columns are verdicts. The suite has no `synthetic` (generated-video) class.

- Time error of `VERIFIED` clips: median 0.157 s, max 1342.182 s (n=14). <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.time_error_verified_s -->
- ENF track RMSE against ground truth: median 2.046 mHz, p95 202.644 mHz (n=16). <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.enf_rmse_mhz -->
- Edit localization error: one localized edit, error 1478.067 s (n=1); see §10. <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.edit_localization_error_s -->
- Runtime per job is dominated by motion analysis (S4, mean 114.32 s) and overlay rendering (S14, mean 128.92 s), measured on the development PC with four clips in parallel. <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.runtime_per_stage_s.S4_motion --> <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.runtime_per_stage_s.S14_overlay -->
- Pipeline errors: none. <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.errors -->

**Edit-detection metric caveat.** The edit detection rate counts only edited clips whose ground truth lists an edit time. The `reorder` clip has no edit time in its ground truth, so its correct `CONTRADICTED` is not counted there. The `edited` row of the confusion matrix is the complete count.

#### Calibration split (SYNTHETIC, placeholder thresholds)

Full summary: [`summary.md`](../results/eval/2026-10-27/synthetic-v1-fallback/summary.md). These verdicts were produced with the hand-written placeholder thresholds **before** calibration, so they are not the operating point:

| Metric (SYNTHETIC) | Value [Wilson CI, 95 percent] |
|---|---|
| False-`CONTRADICTED` rate on authentic clips | 0.0% [0.0–18.4] (k=0, n=17) <!-- src: results/eval/2026-10-27/synthetic-v1-fallback/summary.json#calibration.false_contradicted_rate --> |
| `VERIFIED` coverage, mains-lit clips | 0.0% [0.0–19.4] (k=0, n=16) <!-- src: results/eval/2026-10-27/synthetic-v1-fallback/summary.json#calibration.verified_coverage_mains --> |
| Edit detection rate | 0.0% [0.0–43.4] (k=0, n=5) <!-- src: results/eval/2026-10-27/synthetic-v1-fallback/summary.json#calibration.edit_detection --> |
| Dropped-frame false alarms | 0.0% [0.0–79.3] (k=0, n=1) <!-- src: results/eval/2026-10-27/synthetic-v1-fallback/summary.json#calibration.dropped_frame_false_alarm --> |
| Agent task success (verdict = expected) | 9.1% [2.5–27.8] (k=2, n=22) <!-- src: results/eval/2026-10-27/synthetic-v1-fallback/summary.json#calibration.agent.task_success --> |
| Agent recovery rate (weak first extraction later usable) | 14.3% [2.6–51.3] (k=1, n=7) <!-- src: results/eval/2026-10-27/synthetic-v1-fallback/summary.json#calibration.agent.recovery_rate --> |
| Unnecessary-call rate | 0.0% [0.0–1.7] (k=0, n=224) <!-- src: results/eval/2026-10-27/synthetic-v1-fallback/summary.json#calibration.agent.unnecessary_call_rate --> |
| Human-review precision | 100.0% [20.7–100.0] (k=1, n=1) <!-- src: results/eval/2026-10-27/synthetic-v1-fallback/summary.json#calibration.agent.human_review_precision --> |
| Budget-exhaustion rate | 0.0% [0.0–14.9] (k=0, n=22) <!-- src: results/eval/2026-10-27/synthetic-v1-fallback/summary.json#calibration.agent.budget_exhaustion_rate --> |

| class (SYNTHETIC) | VERIFIED | CONTRADICTED | INCONCLUSIVE | no result |
|---|---|---|---|---|
| authentic-with-mains-light | 0 | 0 | 16 | 0 <!-- src: results/eval/2026-10-27/synthetic-v1-fallback/summary.json#calibration.confusion.authentic-with-mains-light --> |
| authentic-without-mains-light | 0 | 0 | 1 | 0 <!-- src: results/eval/2026-10-27/synthetic-v1-fallback/summary.json#calibration.confusion.authentic-without-mains-light --> |
| edited | 0 | 1 | 4 | 0 <!-- src: results/eval/2026-10-27/synthetic-v1-fallback/summary.json#calibration.confusion.edited --> |

With the placeholder match margin, every mains-lit calibration clip ended `NO_UNIQUE_MATCH` or `SIGNAL_WEAK`. Replaying the calibration statistics with the selected thresholds gives `VERIFIED` coverage 0.5625 and edit detection 0.4 with no false `CONTRADICTED` (fit recorded in the thresholds file). <!-- cfg: config/thresholds.yaml#provenance.calibration_fit -->

#### Reproduce

```
# from the repository root; PYTHONPATH must include the repo root and engine/
python -m eval.run_eval --suite synthetic-v1 --split calibration --workers 4 --date 2026-10-27 --data data/synthetic/v1
python -m eval.calibrate_thresholds results/eval/2026-10-27/synthetic-v1-fallback
python -m eval.run_eval --suite synthetic-v1 --split test --workers 4 --date 2026-10-27-test --data data/synthetic/v1
python -m eval.make_report results/eval/2026-10-27/synthetic-v1-fallback
python -m eval.make_report results/eval/2026-10-27-test/synthetic-v1-fallback
```

To keep the repository small, overlay videos and per-job plots and PDFs were removed from `results/eval/` after the runs. Per-job `result.json`, `trace.json` and `job.json`, the clip records, the summaries and the failure-gallery PNG plots are kept. Re-running the commands regenerates the removed files.

### Real-world evaluation

Dataset: `eval/DATASET.md`. Splits by recording day and phone. The false-`CONTRADICTED` target is written in `docs/DECISIONS.md` before any test data is seen. Thresholds are calibrated on the calibration split by `eval/calibrate_thresholds.py`. The test split is run once with frozen thresholds.

Metrics (SPEC Part 11.5): confusion matrix against ground-truth classes, false-`CONTRADICTED` rate on authentic clips, `VERIFIED` coverage and `INCONCLUSIVE` rate per condition, time error for `VERIFIED` clips, edit detection rate and localization error, dropped-frame false alarms, signal survival per compression platform, experimental face-region results (separate), runtime per stage.

**Status: first real recordings, no accuracy claim.** The real dataset has not been recorded yet (human task, see `docs/HUMAN_TASKS.md`), and the thresholds in use are `PROVISIONAL` (synthetic calibration). On 2026-10-27 two real clips were recorded on an iPhone 13 with the stock camera app (1080p, 30 fps, indoor mains lighting in India, 50 Hz grid, about 44 s each) and run through the full engine <!-- src: results/real/2026-10-27/phone1/run_meta.json#video -->:

| Clip | Verdict | Reasons | Band SNR | DFT peak | Source |
|---|---|---|---|---|---|
| phone1 | `INCONCLUSIVE` | `SIGNAL_ABSENT`, `READOUT_ESTIMATED` | −5.68 dB | 120.0003 Hz | <!-- src: results/real/2026-10-27/phone1/video_result.json#quality --> |
| phone2 | `INCONCLUSIVE` | `SIGNAL_ABSENT`, `READOUT_ESTIMATED` | −5.60 dB | 99.9957 Hz | <!-- src: results/real/2026-10-27/phone2/video_result.json#quality --> |

The stock camera app uses auto exposure and anti-banding, which suppress the flicker bands. The engine therefore reports no usable signal and does not guess. This is the expected behaviour for ordinary phone video (§11), and the reason the Capture app turns anti-banding off. The weak spectral peak near 100 Hz in phone2 (twice the 50 Hz grid) is below the detection threshold and is not used.

## 10. Failure cases

Galleries (generated by `eval/make_report.py`, SYNTHETIC):
- Test split: [`failure_gallery/`](../results/eval/2026-10-27-test/synthetic-v1-fallback/failure_gallery/), listed with explanations at the end of its [`summary.md`](../results/eval/2026-10-27-test/synthetic-v1-fallback/summary.md).
- Calibration split (placeholder thresholds): [`failure_gallery/`](../results/eval/2026-10-27/synthetic-v1-fallback/failure_gallery/).

The galleries keep the ENF-track and phase-residual PNG plots; the overlay videos were removed for size (see §9).

The test split has 7 failures out of 22 clips. They fall into five groups, worst first:

1. **Missed edits that ended `VERIFIED`** (`cut_0p5s__s1161`, `cut_1s__s1171`). The short cuts were explained as dropped frames (`DROPPED_FRAMES_EXPLAINED`), and the remaining track still matched the true time. Match margins were 0.054 and 0.065, above the calibrated minimum. This is the most serious failure: an edited clip received `VERIFIED`. The same miss happened in the AWS run of the `cut-1s` demo case (§6). <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/clips/cut_0p5s__s1161.json#raw.match.margin --> <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/clips/cut_1s__s1171.json#raw.match.margin -->
2. **Wrong-time `VERIFIED`** (`short_readout_long_expo__s1031`). After B1 recovery the track was poor (ENF RMSE 177.598 mHz) and matched a reference time 1342.182 s away from the truth, with margin 0.016. The calibrated margin minimum (the lowest value in the search grid) let it through. Calibration had no wrong-time `VERIFIED` on its own split; the test split shows the margin threshold is too loose. <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/clips.csv#short_readout_long_expo__s1031 --> <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/clips/short_readout_long_expo__s1031.json#raw.match.margin -->
3. **No unique match** (`jitter__s1041`, `web_compression__s1091`, and the edited `cut_2s__s1181`). The best and second-best reference offsets scored almost equally (margins 0.013, 0.005 and 0.003), so the verdict was `INCONCLUSIVE`. This is the intended safe outcome when the match is ambiguous. <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/clips/jitter__s1041.json#raw.match.margin --> <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/clips/web_compression__s1091.json#raw.match.margin --> <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/clips/cut_2s__s1181.json#raw.match.margin -->
4. **Signal too weak** (`weak_flicker__s1021`, band SNR 3.062 dB). The agent tried every B1 alternative and then stopped with `INCONCLUSIVE` (B5). <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/clips.csv#weak_flicker__s1021 -->
5. **HDR input** (`hdr__s1211`). The engine stops on HDR transfer functions by design (`HDR_UNSUPPORTED`), so the clip is `INCONCLUSIVE`; the manifest expected `VERIFIED`.

Measurement issue found during the evaluation: for `insert_other_time__s1191` (correctly `CONTRADICTED`), the reported edit-event time lies outside the clip, which gives the 1478.067 s localization error above. The verdict is correct, but the edit-event timestamp cannot be used for localization until this is fixed. <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/clips/insert_other_time__s1191.json#edit_localization_error_s -->

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
