# GRIDPRINT architecture

This document describes the system in `SPEC.md` Part 5. If this document and `SPEC.md` disagree, `SPEC.md` is correct.

Diagrams:
- System: [`diagrams/architecture.mmd`](diagrams/architecture.mmd) (SVG export: `diagrams/architecture.svg` when present).
- Agent loop: [`diagrams/agent_workflow.mmd`](diagrams/agent_workflow.mmd) (SVG export: `diagrams/agent_workflow.svg` when present).

## 1. Build status

The components below are the system design. All components have code in the repository. Build and acceptance state is tracked in `docs/PROGRESS.md`; the AWS deployment status is in `docs/TECHNICAL_REPORT.md` §6. On 2026-10-27 all stacks except Web (CloudFront, waiting for AWS account verification) are deployed in `us-east-1`. The engine runs stock OpenCV 5 on Graviton; COOL is supported by the stack but not active yet.

## 2. Components

| Component | Location | Runs on | Purpose |
|---|---|---|---|
| GRIDPRINT Capture | `capture-android/` | Android phone | Records video with AE off, anti-banding off, short exposure. Writes a sidecar JSON with sensor timing. Uploads through the API. |
| GRIDPRINT Verify | `web/` | Amazon S3 + Amazon CloudFront, behind AWS WAF | Upload, demo cases, live grid tile, job page with live agent trace, verdict card, overlay player, reviewer screen. |
| API | `api/` | FastAPI on Amazon ECS Fargate, `linux/arm64` | Jobs, presigned uploads, user input, reviewer queue and decisions, demo cases, live grid samples, health. |
| Jobs queue | CDK in `infra/` | Amazon SQS | Decouples the API from the engine workers. Worker autoscaling uses queue depth. |
| Engine worker | `engine/`, `agent/`, `mcp_server/` | Amazon ECS on Graviton4 `c8g`, `linux/arm64`, OpenCV 5 (stock wheel); COOL AMI supported by the stack when `aws.cool_ami_id` is set | One task holds the agent orchestrator, the MCP client, and the MCP server `gridprint-engine` (stdio transport). |
| GRIDPRINT Engine | `engine/gridprint_engine/` | inside the worker | OpenCV 5 analysis stages S1–S15 (SPEC Part 8). Python package with no AWS imports. |
| GRIDPRINT Agent | `agent/` | inside the worker | Plans and adapts the analysis with engine tools. Planner: Claude on Amazon Bedrock, or the deterministic fallback planner. Never writes a verdict. |
| Reference Store | DynamoDB `GridLog` | Amazon DynamoDB | Grid frequency per zone and UTC second. Key `zone#YYYYMMDD` + epoch second. |
| GRIDPRINT Node | `node/` | ESP32 + GPS PPS at a mains socket (through a certified plug-in AC-to-AC adapter) | Measures grid frequency each UTC second. Publishes over MQTT/TLS to AWS IoT Core. |
| Ingest | `node/ingest/` | AWS Lambda (IoT topic rule) | Writes Node samples to `GridLog`. Median over nodes in one zone. |
| Auth | CDK | Amazon Cognito | User pool with the `reviewer` group. Reviewer endpoints require login. |
| Stores | CDK | Amazon DynamoDB, Amazon S3 | `Jobs`, `Reviews`, `GridLog`, `TraceIndex` tables. Upload and results buckets with SSE-KMS and lifecycle deletion. |
| Observability | CDK | Amazon CloudWatch | Structured JSON logs, metrics, dashboards (jobs, stage latency, verdict counts, agent iterations, errors, Node freshness), alarms. |
| Evaluation | `eval/` | developer machine or AWS | Simulator, dataset validator, edit generator, threshold calibration, reports into `results/`. |
| Benchmark | `bench/` | EC2 instances (configs A, B, C) | COOL vs stock OpenCV 5 on Graviton vs x86 (SPEC Part 12). |

## 3. Data flow for one job

1. The client calls `POST /v1/jobs`. The API creates a `Jobs` item and returns a presigned S3 upload URL with a short expiry.
2. The client uploads the video (and the Capture sidecar, if any) to the uploads bucket.
3. The client calls `POST /v1/jobs/{id}/start` with an optional claim (`claimed_zone`, `claimed_time_utc`, `claimed_time_tolerance_s`). The API puts a message on the SQS jobs queue.
4. An engine worker takes the message. The agent orchestrator starts the planner. The planner calls engine tools through the MCP client and the `gridprint-engine` MCP server.
5. Each MCP tool runs one engine stage group on the `Job` object in `engine/gridprint_engine/pipeline.py` (`probe_video`, `estimate_readout`, `analyze_motion`, `propose_patches`, `extract_flicker`, `match_reference`, `check_continuity`, `face_region_check`, `compute_verdict`, `render_report`).
6. The engine reads the video through `StorageAdapter` and the reference grid log through `GridLogAdapter`.
7. Each agent step is written to the trace (SPEC 9.5): S3 JSON plus a `TraceIndex` item. The web app shows the trace live (`GET /v1/jobs/{id}/trace`).
8. `compute_verdict` runs the deterministic verdict logic (S13). The agent cannot change the result.
9. If the verdict is `CONTRADICTED`, the state is `PENDING_REVIEW`. The agent calls `request_human_review`. `render_report` with FINAL is blocked until a reviewer decides (`POST /v1/reviews/{id}/decision`).
10. Report JSON, HTML, PDF, the band overlay MP4, plots, and the trace go to the results bucket. The API returns links from `GET /v1/jobs/{id}`.

Reference data flow: Node → MQTT/TLS → AWS IoT Core → topic rule → Lambda ingest → DynamoDB `GridLog`. The engine reads `GridLog` in S10. The API reads it for the live grid tile (`GET /v1/grid/{zone}/live`).

## 4. Engine stages

| Stage | Module | Main operations |
|---|---|---|
| S1 ingest and timing | `io.py` | SHA-256, probe, per-frame PTS (PyAV, `ffprobe` fallback), jitter, gaps, `cv2.VideoCapture` cross-check. Frames stay in coded (sensor) orientation. |
| S2 linear light | `color.py` | Inverse BT.709/sRGB transfer by `cv2.LUT`, float32. HDR stops the analysis. |
| S3 readout time | `readout.py` | Sidecar → camera profile → blind estimate → unknown. |
| S4 motion | `motion.py` | `cv2.goodFeaturesToTrack`, `cv2.calcOpticalFlowPyrLK`, `cv2.findHomography` with `cv2.USAC_MAGSAC`, `cv2.DISOpticalFlow_create`. |
| S5 foreground | `segment.py` | `cv2.dnn.readNet` with PP-HumanSeg ONNX. |
| S6 patches | `patches.py` | Patch masks mapped with `cv2.warpPerspective`; per-patch row sums with NumPy `add.reduceat`. |
| S7 row signal | `rowsignal.py` | Fractional modulation in scene coordinates (`cv2.warpPerspective`), original sensor row kept for timing. |
| S8 phase and frequency | `phase.py` | Per-frame least squares with `cv2.solve` (`DECOMP_SVD`, float64); DFT cross-check with `cv2.getOptimalDFTSize` and `cv2.dft` on a zero-filled, masked virtual time grid. |
| S9 clock bias | `enf.py` | Demean both tracks. |
| S10 matching | `match.py` | Normalized cross-correlation at 1 s steps, parabolic refinement, segment matching. |
| S11 continuity | `continuity.py` | Phase jump at each frame boundary from two-sided line fits (D-023), gap explanation. |
| S12 face region (EXPERIMENTAL) | `facecheck.py` | `cv2.FaceDetectorYN`. No recognition, no embeddings, no stored crops. |
| S13 verdict | `verdict.py` | Deterministic rules (SPEC 8.14). |
| S14 overlay | `overlay.py` | Temporal band-pass, `cv2.applyColorMap`, `cv2.VideoWriter`. Labeled as not itself evidence. |
| S15 report | `report.py` | JSON, HTML, PDF. |

The signal path uses float32 or float64 only (R6). Linear light comes before normalization (R7). Idle gaps between frames are zero-filled with a mask in the DFT cross-check, never interpolated.

## 5. Adapters

The engine has no AWS imports. All access to storage and data goes through three interfaces in `engine/gridprint_engine/adapters/__init__.py`:

| Interface | Methods | Local implementation | AWS implementation |
|---|---|---|---|
| `StorageAdapter` | `put_file`, `get_file`, `url` | `LocalStorage` (filesystem) | `S3Storage` in `api/aws_adapters.py` |
| `GridLogAdapter` | `read(zone, t0, t1)`, `write(...)` | `LocalGridLog` (CSV per zone and UTC day; median over nodes) | `DynamoGridLog` in `node/ingest/aws_gridlog.py` |
| `JobStoreAdapter` | `put`, `get`, `scan` | local JSON files (DECISIONS D-013) | `DynamoJobStore` in `api/aws_adapters.py` |

`make local` uses the local implementations. All unit and integration tests run offline with them.

## 6. Agent and MCP

- The orchestrator (`agent/orchestrator.py`) runs the planner loop. The planner is `planner_bedrock.py` (Claude on Amazon Bedrock, model ID pinned in `config/default.yaml`) or `fallback_planner.py` (rules for B1–B6).
- `config/default.yaml` sets `agent.planner: bedrock` with `bedrock.model_id: us.amazon.nova-lite-v1:0`, called through a cross-account role (D-026). The fallback planner runs any step where the model call fails, and the trace records which planner made each decision.
- `policies.py` enforces budgets and order rules in code, not only in the prompt.
- The MCP server `gridprint-engine` runs in the same worker task as the orchestrator. Transport: stdio.
- Tools: see SPEC 9.2. The agent loop is in `diagrams/agent_workflow.mmd`.

## 7. x86 and Arm coexistence

- Production engine containers are `linux/arm64` and run on Graviton `c8g` instances. The API runs on Fargate `linux/arm64`.
- The `linux/amd64` engine image exists only for the x86 baseline of the COOL benchmark (SPEC Part 12, configuration A). It is not deployed in the production stack.
- Images are built by `infra/build_images.py`: the `linux/arm64` images on a Graviton EC2 build instance, from the committed tree, and pushed to Amazon ECR. The `linux/amd64` engine image (benchmark only) is built with `--amd64`. All engine images use `infra/docker/engine.Dockerfile`, the same engine code, the same pinned Python dependencies (`uv.lock`), and the same OpenCV 5 release (`opencv-python-headless==5.0.0.93`, DECISIONS D-003). Configuration C replaces stock OpenCV 5 with the COOL build on Graviton.
- The benchmark parity check compares ENF tracks and verdicts from A, B, and C.
- If COOL cannot be obtained (V5), production runs stock OpenCV 5 on Graviton, the reason is documented, and the COOL award is not claimed.

## 8. Security boundaries

- Clients reach the system only through CloudFront (with WAF) and presigned S3 URLs.
- The API validates container type, file size, and duration before it queues a job. FFmpeg decoding runs in a non-root container with a decode timeout.
- Reviewer endpoints require a Cognito login in the `reviewer` group.
- Each service has its own least-privilege IAM role. The worker role may invoke only the pinned Bedrock model.
- See `docs/RESPONSIBLE_USE.md` for the full list.
