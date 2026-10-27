# GRIDPRINT

GRIDPRINT checks whether a video is real by reading the power-grid frequency from the flicker of the lights in
the room. Mains-powered lights flicker at twice the grid frequency. A phone's rolling shutter reads the sensor one
row at a time, so the flicker shows up as faint horizontal bands. GRIDPRINT measures those bands with OpenCV 5,
rebuilds the grid-frequency track (the electric network frequency, ENF), and compares it with a recorded
reference log of the real grid. The result is one of three verdicts: `VERIFIED`, `CONTRADICTED` (only final after
a human reviewer approves it) or `INCONCLUSIVE`. A missing signal is never evidence that a video is fake. GRIDPRINT
is not a deepfake classifier and not cryptographic proof.

Entry for the OpenCV AI Competition 2026 (OpenCV 5 + AWS). The specification is in [SPEC.md](SPEC.md); current
status is in [docs/PROGRESS.md](docs/PROGRESS.md).

## Live on AWS

- **Live app (HTTPS):** https://5u7suz00bi.execute-api.us-east-1.amazonaws.com — walkthrough in [docs/JUDGE_GUIDE.md](docs/JUDGE_GUIDE.md)
- **9 AWS CDK stacks deployed** in `us-east-1`: API Gateway → VPC link → internal ALB → Fargate `linux/arm64` API,
  Graviton4 `c8g` ECS workers fed by SQS, DynamoDB, S3 with KMS, Cognito reviewer group, IoT Core ingest,
  CloudWatch dashboards and alarms (technical report §6).
- **Agent planner on Amazon Bedrock:** Amazon Nova Lite chooses the next OpenCV tool; code-enforced policies keep
  every verdict deterministic and every step is traced (`results/aws/<job_id>/trace.json`).
- **Real iPhone 13 recording on the live deployment:** job `cd65b6ea0c20` ran end to end on a Graviton4 worker. The
  stock camera app's anti-banding had removed the flicker bands, so the engine reported `INCONCLUSIVE`
  (`SIGNAL_ABSENT`) instead of guessing, and the agent adapted by asking for the original file and the camera model. <!-- src: results/aws/index.json#cd65b6ea0c20.verdict -->
- **End-to-end AWS runs** with full evidence (result, trace, report PDF, plots) under `results/aws/`.

## Graviton4 vs x86 (stock OpenCV 5.0.0, `results/bench/2026-10-27/`)

| Metric | x86 `c7i.2xlarge` | Graviton4 `c8g.2xlarge` |
|---|---|---|
| Throughput, video-s per wall-s | 0.92 <!-- src: results/bench/2026-10-27/A/summary.json#throughput_video_s_per_wall_s --> | 1.20 <!-- src: results/bench/2026-10-27/B/summary.json#throughput_video_s_per_wall_s --> |
| Cost per video-hour | $0.390 <!-- src: results/bench/2026-10-27/cost.json#configs.A.cost_per_video_hour_usd --> | $0.266 <!-- src: results/bench/2026-10-27/cost.json#configs.B.cost_per_video_hour_usd --> |

Same engine, same input, five runs per configuration; Graviton4 processes more video per second at a lower cost per
hour of video (technical report §7).

## Evaluation

- **0 false `CONTRADICTED`** on authentic clips of the frozen-threshold test split (SYNTHETIC simulator clips). <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.false_contradicted_rate -->
- Agent traces for each behaviour: `results/agent_traces/`.
- Full SYNTHETIC tables and the real-recording runs: technical report §9.

## Documents

- Technical report: [docs/TECHNICAL_REPORT.md](docs/TECHNICAL_REPORT.md)
- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · diagrams in [docs/diagrams/](docs/diagrams/)
- Video: the link is on the Devpost page.

## Responsible use

See [docs/RESPONSIBLE_USE.md](docs/RESPONSIBLE_USE.md).

## What is in the repository

| Part | Path |
|---|---|
| Engine (OpenCV 5 stages S1–S15) | `engine/gridprint_engine/` |
| Agent (planner, policies, trace) and MCP tool server | `agent/`, `mcp_server/` |
| API and job worker | `api/` |
| Verify web app | `web/` |
| Capture Android app | `capture-android/` |
| Grid-frequency Node (hardware, firmware, ingest) | `node/` |
| Camera calibration rig | `calibration_rig/` |
| AWS infrastructure (CDK v2) | `infra/` |
| Simulator and evaluation | `eval/` |
| Graviton vs x86 benchmark (COOL-ready) | `bench/` |

## Quick start (local)

Requirements: Python 3.11, [uv](https://docs.astral.sh/uv/), FFmpeg on `PATH`, Node.js 24 (for the web app).

```bash
make setup
```

```bash
make test
```

```bash
python -m eval.make_demo_inputs
```

```bash
make local
```

`make local` serves the API and the built web app at `http://127.0.0.1:8000` with local file storage and the
deterministic agent planner. The reviewer token for local use is written to `work/local_reviewer_token.txt`.
On Windows without GNU make, use `./make <target>` (Git Bash) or `make.cmd <target>`.

## Deploy to AWS

1. Complete human task H1 in [docs/HUMAN_TASKS.md](docs/HUMAN_TASKS.md) (CLI profile `gridprint`).
2. Build the arm64 images (no local Docker needed): `python infra/build_images.py`.
3. Deploy all stacks: `make deploy`. Remove everything: `make destroy`.

## Evaluate and benchmark

```bash
make eval
```

```bash
make bench
```

Synthetic results are labeled SYNTHETIC and are never presented as real-world accuracy. Every reported number
lives under `results/` with a source tag (SPEC 14.3).

## Final check

```bash
make final-check
```

It prints one line per item of the final checklist (SPEC 17.3) and `ALL CHECKS PASSED` only when all hold.
