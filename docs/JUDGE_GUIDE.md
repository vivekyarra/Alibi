# Judge guide

GRIDPRINT checks if a video is real by reading the power-grid frequency from the flicker of indoor lights. The camera's rolling shutter records the flicker as faint horizontal bands. GRIDPRINT compares the measured frequency track with a reference log of the real grid.

Endpoint: https://5u7suz00bi.execute-api.us-east-1.amazonaws.com

## What is running

- **Live AWS deployment (`us-east-1`), 9 CDK stacks:** Amazon API Gateway → VPC link → internal Application Load Balancer → Fargate `linux/arm64` API; jobs run on Graviton4 `c8g` ECS workers fed by SQS; DynamoDB, S3 with KMS, Cognito reviewer group, IoT Core ingest, CloudWatch dashboards and alarms. The web app is served from the same address (technical report §6).
- **Agent planner on Amazon Bedrock (Amazon Nova Lite).** It picks the next OpenCV tool from the measurements; code-enforced policies keep the verdict deterministic and every step is traced.
- **Real iPhone 13 recording on the live deployment** (job `cd65b6ea0c20`). The Graviton4 worker ran the full pipeline. The stock camera app's anti-banding had removed the flicker bands, so the result is `INCONCLUSIVE` (`SIGNAL_ABSENT`) rather than a guess, and the agent adapted by asking for the original file and the camera model. <!-- src: results/aws/index.json#cd65b6ea0c20.verdict -->
- **Graviton4 vs x86 benchmark** (stock OpenCV 5.0.0): 1.20 vs 0.92 video-seconds per wall-second <!-- src: results/bench/2026-10-27/B/summary.json#throughput_video_s_per_wall_s --> <!-- src: results/bench/2026-10-27/A/summary.json#throughput_video_s_per_wall_s -->, $0.266 vs $0.390 per hour of video <!-- src: results/bench/2026-10-27/cost.json#configs.B.cost_per_video_hour_usd --> <!-- src: results/bench/2026-10-27/cost.json#configs.A.cost_per_video_hour_usd --> (technical report §7).
- **0 false `CONTRADICTED`** on authentic clips of the frozen-threshold evaluation test split (SYNTHETIC simulator clips). <!-- src: results/eval/2026-10-27-test/synthetic-v1-fallback/summary.json#test.false_contradicted_rate --> Agent traces: `results/agent_traces/`.

**Live walkthrough.** On request, the team also runs the full system with `make local` in a screen-share: the same engine, agent and web app as the AWS deployment, with local storage and the deterministic planner.

## 1. What you can do on the endpoint

1. Open the endpoint. The home page has three parts: upload, ready-made test cases, and the live grid tile.
2. Run a test case, or upload your own MP4 or MOV file.
3. Watch the job page. It shows progress, the live agent trace, the verdict card, the band overlay player with timeline markers, plots, and downloads (report PDF, report JSON, overlay MP4).
4. Log in as a reviewer to see the approval screen for `CONTRADICTED` results.

### How to verify a result on the live app

1. Open a finished job page directly, for example
   https://5u7suz00bi.execute-api.us-east-1.amazonaws.com/#/jobs/aws3-capture-verified-040158
   Other finished jobs: `#/jobs/aws3-dropped-frames-040218`, `#/jobs/cd65b6ea0c20` (real iPhone 13 recording).
2. Check the verdict card (verdict, reasons, recording-time estimate), the plots, and the agent trace. Each trace step shows the planner, the tool, and the decision reason; steps where the code guard replaced the model's proposal start with "guard:".
3. Download the report PDF or JSON from the job page and compare it with the copy in the repository under `results/aws/<job_id>/` (`result.json`, `trace.json`, `report.pdf`).
4. The same job is also readable as JSON: `GET /v1/jobs/<job_id>`.

The `aws3-*` and `aws4-*` jobs use **SYNTHETIC** test clips made by the rolling-shutter simulator (`eval/make_demo_inputs.py`), with known ground truth. All measured results, per job, are in `docs/TECHNICAL_REPORT.md` §6.

## 2. Verdicts

GRIDPRINT gives exactly three verdicts:

| Verdict | Meaning |
|---|---|
| `VERIFIED` | A grid signal is present. It matches the reference log at one time only. No significant edit evidence exists. If you gave a claimed time, the matched time agrees with it. |
| `CONTRADICTED` | A grid signal is present, and it conflicts with the claimed time, or it shows a break that frame timestamps do not explain, or different parts match different times. A human reviewer must approve this result before the report is final. |
| `INCONCLUSIVE` | The check could not be completed. For example: no usable grid signal, no reference data for the zone and time, or no unique match. |

`INCONCLUSIVE` is not evidence that a video is fake.

## 3. Ready-made test cases

All test cases run through the live pipeline (`POST /v1/demo-cases/{id}/run`). No result is stored in advance. The latest measured verdicts are in `results/`. The "Target verdict" column is the result that `SPEC.md` defines for each case; the verdict you see is the one the pipeline measures on the run.

| # | Case | Target verdict |
|---|---|---|
| 1 | Capture clip | `VERIFIED` with recording time |
| 2 | Same clip with a one-second cut | `CONTRADICTED`, then reviewer approval |
| 3 | Insertion of a segment recorded at another time | `CONTRADICTED` (`SEGMENT_OFFSET_INCONSISTENT`) |
| 4 | Dropped frames with their original timestamps | `VERIFIED` with `DROPPED_FRAMES_EXPLAINED` |
| 5 | Synthetic room video from a public video generator | `INCONCLUSIVE` (`SIGNAL_ABSENT`). This alone does not mean the video is fake. |
| 6 | Daylight-only clip | `INCONCLUSIVE` |
| 7 | Agent recovery: first pass `SIGNAL_WEAK`, the agent selects new patches, the signal locks | Final verdict from the second pass; the trace shows the change of plan |
| 8 | Face-composite clip (consenting team members) | Face-region result labeled `EXPERIMENTAL`. This result is never the only basis for `CONTRADICTED`. |

## 4. Reviewer login

Reviewer credentials for the endpoint are provided to judges on request. They are not in this repository. With `make local`, the reviewer token is in `work/local_reviewer_token.txt`.

Use the reviewer screen to approve or reject a `CONTRADICTED` result. A rejection makes the report final with verdict `INCONCLUSIVE` and reason `REVIEWER_REJECTED`. The note you write is stored.

## 5. Getting the strongest signal

GRIDPRINT reads the flicker bands that mains lighting leaves in rolling-shutter video. The best input is a clip from GRIDPRINT Capture (the Android app): it turns off anti-banding, uses a short exposure, and records sensor timing in a sidecar file.

Many stock phone camera apps turn on "anti-banding", which sets the exposure to a whole number of flicker periods and smooths the bands away. For such videos GRIDPRINT reports `INCONCLUSIVE` with a clear reason instead of guessing, and the agent asks for what would help (the original file, the camera model). The same applies to scenes lit only by daylight or battery lights, very short clips, strongly recompressed files, HDR video, and zones or times without reference data.

## 6. Scope

GRIDPRINT checks the physical grid signal in the pixels. It reports the grid zone and the recording time. It does not judge whether pixels look AI-made, does not recognize faces or identify people, reports no location finer than the grid zone, and is not cryptographic proof.

## 7. More information

- Architecture: `docs/ARCHITECTURE.md`
- Technical report: `docs/TECHNICAL_REPORT.md`
- Responsible use: `docs/RESPONSIBLE_USE.md`
