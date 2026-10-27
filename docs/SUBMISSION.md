# Devpost submission — GRIDPRINT

Copy each section into the matching Devpost field.

## Project name
GRIDPRINT

## Tagline
Checks whether a video is real by reading the power grid from the flicker of the lights in the room.

## Inspiration
AI tools make fake video cheap. The side effect is worse: people now dismiss real video as "AI". Newsrooms, courts,
insurers and human-rights documenters receive footage they cannot easily defend. Detectors that judge pixels guess,
and metadata is lost on the first re-upload. We wanted a physical signal that stays inside the pixels.

## What it does
Mains-powered lights flicker at twice the grid frequency. A phone camera's rolling shutter reads one sensor row at a
time, so the flicker becomes faint bands. GRIDPRINT measures those bands with OpenCV 5, rebuilds the grid-frequency
track (electric network frequency, ENF), and matches it to reference logs of the real grid. It reports when the video
was recorded, whether parts were cut, inserted or reordered, and which grid zone it matches — never a finer location.

There are exactly three verdicts. VERIFIED and INCONCLUSIVE are final at once. CONTRADICTED needs a human reviewer's
approval before the report is final. A missing signal is never evidence that a video is fake.

## How we built it
- **OpenCV 5 engine (15 stages):** linear-light conversion with LUTs; motion and static-scene masks with
  goodFeaturesToTrack, calcOpticalFlowPyrLK, findHomography (USAC_MAGSAC) and DISOpticalFlow; person masks with the
  dnn module; per-frame flicker phase with cv2.solve; a cross-check with cv2.dft on a gap-masked time grid;
  continuity checks with two-sided phase fits; FaceDetectorYN for an experimental face-region check; band overlay
  video and an accessible HTML/PDF report.
- **Agent:** an MCP server exposes twelve engine tools. A planner on Amazon Bedrock (Amazon Nova Lite through a
  cross-account role) chooses the next tool from OpenCV measurements — for example re-selecting light patches after
  a weak signal. Code-enforced policies keep the verdict deterministic, cap the budget, and block a FINAL report for
  CONTRADICTED until a human approves. A deterministic planner covers any failed model step. Every step is traced.
- **AWS:** CDK v2 stacks — Graviton4 (c8g) ECS workers built for linux/arm64, Fargate arm64 API, API Gateway
  endpoint, SQS, DynamoDB, S3 with KMS, Cognito reviewer group, IoT Core ingest for the grid reference Node,
  CloudWatch dashboards and alarms.
- **Capture app (Android, Camera2):** auto-exposure and anti-banding off, short exposure, per-frame sensor
  timestamps and readout skew in a signed sidecar.
- **Grid reference Node (ESP32 + GPS PPS):** design, firmware and ingest; safety-first (certified AC adapter only).
- **Evaluation:** a rolling-shutter simulator with ground truth (results labelled SYNTHETIC), threshold calibration
  against a written false-CONTRADICTED target, fuzz and stress tests.

## Challenges we ran into
- The wrong readout direction produces a convincing but false frequency track; we rank candidates by physical
  plausibility.
- Chained frame-to-frame homographies drifted on a fixed camera and smeared the scene; registering each frame directly
  to a reference frame fixed it.
- A cut whose length is a whole number of flicker periods changes the phase only by the grid deviation; two-sided
  phase fits made those small jumps measurable.
- New-account AWS limits (vCPU quota, CloudFront verification) shaped the deployment.

## Accomplishments that we're proud of
- An honest product: three verdicts, mandatory human review for CONTRADICTED, and no claim beyond the evidence.
- The agent changes its plan from OpenCV measurements, and policies keep it safe even when the model errs.
- The same engine runs on Graviton4 and x86 with stock OpenCV 5; in our benchmark Graviton4 gave higher throughput
  and a lower cost per hour of video (technical report §7).

## What we learned
Physics-based provenance is strong but narrow: it needs mains lighting and a camera that does not hide the flicker.
Saying so plainly is part of the product.

## What's next
Grid reference Nodes in more zones, real-world evaluation with consenting participants, the Capture app on more
phones, and COOL-accelerated workers once the Marketplace subscription is active.

## Built with
opencv, python, numpy, pyav, ffmpeg, fastapi, react, typescript, vite, aws, amazon-bedrock, amazon-ecs,
aws-graviton, aws-fargate, amazon-api-gateway, amazon-sqs, amazon-dynamodb, amazon-s3, amazon-cognito,
aws-iot-core, aws-lambda, amazon-cloudwatch, aws-cdk, model-context-protocol, kotlin, android, esp32

## Links
- Code: https://github.com/vivekyarra/Alibi
- Live endpoint: https://5u7suz00bi.execute-api.us-east-1.amazonaws.com (how to check a result: docs/JUDGE_GUIDE.md; demo clips are SYNTHETIC)
- Technical report: docs/TECHNICAL_REPORT.md
- Video: the link is added at submission (at most 5 minutes)

## Special awards
- **Agentic Vision Award:** opt in. Evidence: agent/, mcp_server/, agent traces under results/, agent tests.
- **Best Use of COOL Award:** not claimed; do not opt in. COOL is not active (Marketplace subscription pending).
  results/bench/2026-10-27/ holds the stock OpenCV 5 benchmark of Graviton4 c8g.2xlarge against x86 c7i.2xlarge
  (technical report §7); it is not a COOL result.
