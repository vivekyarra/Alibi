# Human tasks (SPEC Part 16)

Status values: `BLOCKED-HUMAN` (waiting for a person), `DONE` (validated by script where a validator exists).

---

## H1 — AWS account: remaining items — BLOCKED-HUMAN

Done (2026-10-27): account 643700104680, deployer access, CLI profile `gridprint` in `us-east-1`, CDK bootstrap. Nine of ten stacks are deployed; the public endpoint is https://5u7suz00bi.execute-api.us-east-1.amazonaws.com (API Gateway, D-025); the planner runs on Amazon Nova Lite through a cross-account role (D-026). Evidence: `results/aws/`.

Remaining items (each needs the account owner):
1. **AWS account verification (unblocks CloudFront).** AWS Console → Support Center → open the account-verification case or notice and complete it. Then run `make deploy` to add the Web stack (CloudFront).
2. **EC2 vCPU quota increase.** AWS Console → Service Quotas → Amazon EC2 → "Running On-Demand Standard (A, C, D, H, I, M, R, T, Z) instances" (`L-1216C47A`) → Request increase to at least 32 vCPUs. This restores the default worker size and allows the benchmark instances (D-024).
3. **Claude model access through AWS Marketplace needs a valid payment method.** AWS Console → Billing and Cost Management → Payment preferences → add or fix a valid payment method. Then Bedrock console (`us-east-1`) → Model access → enable Anthropic Claude Sonnet 4.6 (accept the Anthropic use-case form if asked). Only after that, switch the planner model in `config/default.yaml`. Until then the planner stays on Amazon Nova Lite (D-026).
4. **COOL subscription.** Open the AWS Marketplace listing "Cloud Optimized OpenCV For AWS Graviton4" (`https://aws.amazon.com/marketplace/pp/prodview-fdvbfiewzuehs`) and subscribe (needs the payment method from item 3). Put the `us-east-1` AMI ID in `config/default.yaml` under `aws.cool_ami_id`.
5. Validate:
   ```bash
   make verify-aws
   ```
   It must print `AWS OK`, `BEDROCK OK <model id>` and `COOL AMI OK <ami id>`.

## H2 — Build, install and run the GRIDPRINT Node — BLOCKED-HUMAN

> **WARNING:** Do not connect the Node electronics directly to mains voltage. Use only a certified plug-in AC-to-AC adapter. Mains voltage can kill.

1. Buy the parts in `node/hardware/BOM.md`.
2. Read `node/hardware/SAFETY.md` completely.
3. Assemble per `node/hardware/ASSEMBLY.md` and `node/hardware/schematic.md`.
4. Create the IoT thing and certificates: `make deploy` creates the IoT stack; then run `python node/provision.py --profile gridprint --node-id node-01 --zone IN` which writes certificates to `node/firmware/certs/` (git-ignored).
5. Flash the firmware per `node/firmware/FLASHING.md`.
6. Place the GPS antenna with sky view. Wait for `gps_lock=true` in the serial log.
7. Run the self-test `node/SELFTEST.md`.
8. Keep the Node running at least 24 h. Validate:
   ```bash
   make node-quality ZONE=IN HOURS=24
   ```
   Pass: coverage ≥ 99 %, GPS lock ratio ≥ 99 %.

## H3 — Calibration rig and calibration clips — BLOCKED-HUMAN

1. Build the rig per `calibration_rig/RIG_GUIDE.md` and flash `calibration_rig/firmware/`.
2. For each phone and each mode (resolution × fps) used in the dataset, film 10 s of the lit card per `calibration_rig/FILMING_CHECKLIST.md`.
3. Copy clips into `data/calibration/<device>/<mode>.mp4` (outside git; `data/` is ignored).
4. Run:
   ```bash
   make calibrate
   ```
   This runs `calibration_rig/fit_readout.py` on every clip and writes `config/camera_profiles.yaml`.

## H4 — Install GRIDPRINT Capture on test phones — BLOCKED-HUMAN

1. Install Android Studio (or the command-line SDK) and accept the SDK licences.
2. Build: `cd capture-android && ./gradlew assembleDebug` (see `capture-android/BUILD.md`).
3. Install on each phone: `adb install -r app/build/outputs/apk/debug/app-debug.apk`.
4. Open the app; accept the consent screen; tap "Device check". Copy the report file `gridprint_capability.json` to `data/devices/<model>.json`.
5. Validate: `python capture-android/validate_capability.py data/devices/*.json`.

## H5 — Record the real dataset — BLOCKED-HUMAN

### H5-a — Download the public ENF video datasets (needs your login; the agent cannot create accounts) — BLOCKED-HUMAN
Both sets have real rolling-shutter videos plus a recorded mains reference.
1. EV-ENFD (Xu et al., CVPR 2023, code MIT): open the TeraBox link in https://github.com/xlx-creater/E-ENF (README, "Data").
   Download the video sequences and the `ENF_Reference` folder (each `.wav` is one hour of grid voltage).
2. Choi, Wong, Su, Wu rolling-shutter set: log in at https://ieee-dataport.org/documents/rolling-shutter-videos-enf-extraction
   and download `vids.zip` (and `mats.zip` if offered).
3. Upload the downloaded archives unchanged to your Google Drive folder `GRIDPRINT-data/` and tell the agent.
   The agent copies them to `data/public/` (git-ignored), converts the mains `.wav` references to 1 s GridLog
   entries, and runs the evaluation on them.

Follow `eval/DATASET.md` (shot list, manifest template, consent form template). Validate with:
```bash
make validate-dataset
```

## H6 — Platform round trips (WhatsApp, YouTube, Instagram) — BLOCKED-HUMAN

Follow `eval/DATASET.md` section "Platform round trips". File naming: `<clip_id>__<platform>.mp4`. Validator: `make validate-dataset`.

## H7 — Face-composite clips with consenting team members — BLOCKED-HUMAN

Follow `eval/FACE_COMPOSITES.md`. Every person signs `eval/templates/consent_form.md`. Store forms outside the repository.

## H8 — Record and edit the ≤ 5-minute video — BLOCKED-HUMAN

1. **Team clip needed.** Record a short clip of the team (consenting members only) and save it as `video/assets/team.mp4`. `video/scenes.yaml` uses this file; until it exists, `video/make_video.py` shows a placeholder card in the team scene.
2. Build and check the video per `docs/VIDEO_SCRIPT.md`. Any demo clip shown must be labelled SYNTHETIC where it comes from the simulator.
3. Upload as public or unlisted. Put the link in `README.md` (line "Video:") and in `docs/SUBMISSION.md` (Links). `scripts/final_check.py` checks the link exists; record the duration with `python scripts/check_video_duration.py <file>`.

## H9 — Submit on Devpost — BLOCKED-HUMAN

The submission checklist is written here when Part 17.3 is complete.
