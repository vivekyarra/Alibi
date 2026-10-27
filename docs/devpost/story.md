## Inspiration

Generated video is now cheap. The worse side effect: people now dismiss **real** video as "AI". Newsrooms, courts, insurers and human-rights groups receive footage that they cannot easily defend. Pixel detectors guess. Metadata disappears on the first re-upload.

We wanted a physical signal that lives inside the pixels. We found one in the ceiling light.

## What it does

Lights on mains power flicker at twice the grid frequency (100 or 120 Hz). The grid frequency is never exactly 50 or 60 Hz. It drifts all the time. The drift is the same across a whole grid zone and is logged second by second. This is the **electric network frequency (ENF)**.

A phone camera has a rolling shutter: it reads one sensor row at a time. So the flicker turns into faint horizontal bands in every frame. GRIDPRINT:

1. Measures those bands with **OpenCV 5**.
2. Rebuilds the ENF track of the clip.
3. Matches the track to grid reference logs.
4. Reports **when** the video was recorded, whether parts were **cut, inserted or reordered**, and which **grid zone** it matches. It never reports a finer location.

There are exactly three verdicts:

- **VERIFIED**: a grid signal is present and matches the reference log at one time. Final at once.
- **INCONCLUSIVE**: not enough signal or reference to decide. Final at once.
- **CONTRADICTED**: the evidence conflicts with the claim. A human reviewer must approve it before the report is final.

A missing signal never counts against a video. Every verdict carries machine-readable reason codes, a band overlay video and an accessible HTML/PDF report.

**It runs live on AWS:** https://5u7suz00bi.execute-api.us-east-1.amazonaws.com

## How we built it

**OpenCV 5 engine (15 stages).** The signal path stays in float32/float64, in linear light, and never interpolates across the rolling-shutter idle gap.

- **Linear light:** `cv2.LUT` undoes the camera gamma before any normalization.
- **Motion and static-scene masks:** `goodFeaturesToTrack`, `calcOpticalFlowPyrLK`, `findHomography` with `USAC_MAGSAC`, and `DISOpticalFlow`. Each frame registers directly to a reference frame.
- **Person masks:** the `cv2.dnn` module removes moving people from the light patches.
- **Light patches and row signal:** `warpPerspective` samples stable, well-lit surfaces row by row.
- **Phase and frequency:** a per-frame flicker phase fit with `cv2.solve`, cross-checked with `cv2.dft` on a gap-masked time grid.
- **Continuity:** two-sided phase fits find cuts, insertions and reordering.
- **Face region (experimental):** `FaceDetectorYN`.
- **Output:** `applyColorMap` and `VideoWriter` render the band overlay video.

**Agent.** An MCP server exposes 12 engine tools. A planner on **Amazon Bedrock (Amazon Nova Lite)** picks the next tool from OpenCV measurements. For example, it re-selects light patches after a weak signal. Code-enforced policies keep the verdict deterministic, cap the budget, and block a final CONTRADICTED report until a human approves. A deterministic planner takes over if a model step fails or breaks a policy. Every step is traced and shown in the app.

**AWS (all in AWS CDK v2):**

- **Amazon ECS on Graviton4 (c8g)** runs the engine workers, built for `linux/arm64`.
- **AWS Fargate (arm64)** runs the FastAPI service and web app behind **Elastic Load Balancing**.
- **Amazon API Gateway** gives the public HTTPS endpoint through a VPC link.
- **Amazon SQS** queues jobs. **Amazon DynamoDB** stores jobs, reviews, traces and the grid log.
- **Amazon S3 + AWS KMS** hold uploads and reports, encrypted.
- **Amazon Cognito** holds the reviewer group for the CONTRADICTED gate.
- **AWS IoT Core + AWS Lambda** ingest the grid reference Node.
- **Amazon CloudWatch** for logs, dashboards and alarms. **Amazon ECR** for images.

**Capture app (Android, Camera2):** auto-exposure and anti-banding off, short exposure, per-frame sensor timestamps and readout skew in a signed sidecar file.

**Grid reference Node (ESP32 + GPS PPS):** design, firmware and cloud ingest. Safety first: it uses a certified plug-in AC adapter only.

## Graviton4 vs x86

We ran the same engine and the same pinned input on equal-size instances, with stock OpenCV 5.0.0, 5 runs each:

| | x86 `c7i.2xlarge` | Graviton4 `c8g.2xlarge` |
|---|---|---|
| Throughput (video-s per wall-s) | 0.92 | **1.20** |
| Cost per video-hour (on-demand, us-east-1) | $0.390 | **$0.266** |

Graviton4 processes about 31% more video per second and costs about 32% less per hour of video. These are speed and cost numbers only. They say nothing about accuracy.

## Challenges we ran into

- **The wrong readout direction gives a convincing but false frequency track.** We rank the candidates by physical plausibility.
- **Chained homographies drifted.** Frame-to-frame homographies drifted on a fixed camera and smeared the scene. Registering each frame directly to one reference frame fixed it.
- **Some cuts hide in the phase.** If a cut is a whole number of flicker periods long, the phase moves only by the grid deviation. Two-sided phase fits made those small jumps measurable.
- **New-account AWS limits** (vCPU quota, CloudFront verification) shaped the deployment. We moved the public edge to API Gateway with a VPC link.

## Accomplishments that we're proud of

- **An honest product:** three verdicts, a mandatory human review for CONTRADICTED, and no claim beyond the evidence.
- **An agent that reacts to vision measurements,** with policies that keep it safe when the model is wrong.
- **One engine, two architectures:** the same code runs on Graviton4 and x86 with stock OpenCV 5, and Graviton4 wins on throughput and cost.
- **A full system:** capture app, grid reference Node, cloud pipeline, reviewer workflow and reports.

## What we learned

Physics-based provenance is strong but narrow. It needs mains lighting and a camera that does not hide the flicker. Saying so plainly is part of the product.

## What's next

- Grid reference Nodes in more grid zones.
- Real-world evaluation with consenting participants.
- The Capture app on more phones.
- OpenCV-accelerated workers with COOL once our Marketplace subscription is active.

**Code:** https://github.com/vivekyarra/Alibi
