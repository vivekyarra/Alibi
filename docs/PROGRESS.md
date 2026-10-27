# GRIDPRINT progress

Current milestone: M8 (9 of 10 stacks deployed; Web/CloudFront BLOCKED-HUMAN H1), M11 (demo cases on the deployed endpoint), M2/M3 hardening.

Status key: ACCEPTED (all criteria shown with evidence), OPEN (work remains), BLOCKED-HUMAN (waits for a task in `docs/HUMAN_TASKS.md`).

## M0 — Setup and verification — ACCEPTED (2026-10-26)

| Criterion | Evidence |
|---|---|
| Repo layout per Part 6 | All Part 6 directories exist on `main` (PRs #1–#10). |
| CI runs lint, type check, tests, claims_lint | `.github/workflows/ci.yml`; green runs on PRs #1–#8 (python, web, scan jobs). |
| VERIFICATION.md V1–V12 resolved | `docs/VERIFICATION.md`; V5/V6/V7/V11/V12 carry BLOCKED-HUMAN or FALLBACK notes with instructions, as M0 allows. |
| HUMAN_TASKS.md lists H1–H9 | `docs/HUMAN_TASKS.md` |
| REQUIREMENTS_TRACE.md created | `docs/REQUIREMENTS_TRACE.md` |

## M1 — Simulator — OPEN

- Done: `eval/simulator/` renders every factor of SPEC 11.1 with ground truth (`eval/tests/test_simulator.py`, 3 passed).
- Remaining: commit the small sample set (`python -m eval.simulator.make_samples` → `results/synthetic_samples/`).

## M2 — Engine S1–S10 — OPEN

- Done: unit tests for linearization, float32/float64 types, idle-gap zero-fill, clock-bias removal, estimator agreement, readout, matching (`engine/gridprint_engine/tests/test_units.py`).
- Video integration tests: 8 of 8 pass (`engine/gridprint_engine/tests/test_video.py`). Motion now registers each frame directly to the reference frame (D-022).
- Stress and fuzz tests pass (`tests/test_stress.py`).
- Remaining for formal acceptance: commit the evaluation results under `results/`.

## M3 — Engine S11–S15 — OPEN

- Done: verdict rules and R1–R3, R9 tests; report HTML/PDF/JSON and overlay generation; claims_lint on templates.
- Video integration tests: 8 of 8 pass (`engine/gridprint_engine/tests/test_video.py`), including the re-timed cut (`CONTRADICTED`) and dropped frames (`DROPPED_FRAMES_EXPLAINED`). Continuity uses two-sided line fits (D-023, replaces D-014).
- Remaining for formal acceptance: commit the evaluation results under `results/`.

## M4 — Node and reference — BLOCKED-HUMAN (H2)

- Done: firmware, hardware docs with the R11 warning, ingest Lambda, GridLog adapter, simulated publisher, data-quality script, NESO and WAV reference importers (42 tests pass).
- Remaining: ≥ 24 h of real Node data with GPS lock (H2).

## M5 — Calibration — BLOCKED-HUMAN (H3)

- Done: rig firmware (200 Hz, D-017), filming checklist, `calibration_rig/fit_readout.py` with tests.

## M6 — Capture app — BLOCKED-HUMAN (H4)

- Done: Kotlin Camera2 app, sidecar writer, band meter, device check, validator; JVM and Python tests pass.

## M7 — Agent — OPEN

- Done: MCP server (12 tools, stdio test), fallback planner (B1–B6), Bedrock planner, policies, trace; `agent/tests` (13 passed); adversarial-planner fuzz (200 runs) in `tests/test_stress.py`.
- Remaining: saved traces from real runs showing B1–B6; the evaluation run commits them under `results/`. Bedrock planner: Amazon Nova Lite through a cross-account role (D-026); the fallback planner covers failed model calls.

## M8 — AWS deployment — OPEN (Web/CloudFront: BLOCKED-HUMAN H1)

- Account 643700104680, region `us-east-1`, profile `gridprint`, resource prefix `orchard` (D-021).
- Deployed (9 of 10 stacks): Network, Storage (KMS), Data, Ai, Auth, Compute (Graviton4 `c8g.xlarge` workers, max 1 per D-024; SQS with DLQ), Api (Fargate `linux/arm64` behind an internal ALB), Iot, Observability.
- Not deployed: Web (CloudFront waits for AWS account verification, H1). Public HTTPS instead through API Gateway → VPC link → internal ALB → Fargate API, with the web app on the same origin (D-025).
- Endpoint: https://5u7suz00bi.execute-api.us-east-1.amazonaws.com
- Planner: Amazon Nova Lite on Bedrock through a cross-account role (D-026), with the deterministic guard and fallback.
- Images: `linux/arm64`, built on a Graviton EC2 build instance by `infra/build_images.py`.
- Evidence: end-to-end jobs on AWS in `results/aws/<job_id>/` and `results/aws/index.json` (collected by `scripts/collect_aws_runs.py`); table in `docs/TECHNICAL_REPORT.md` §6.
- Remaining blockers: CloudFront (H1 account verification); EC2 vCPU quota increase (H1).

## M9 — Real evaluation — BLOCKED-HUMAN (H5–H7)

- Synthetic evaluation and threshold calibration tooling is in place; the real dataset is needed (public datasets need the owner's login, H5-a).

## M10 — COOL benchmark — OPEN / BLOCKED-HUMAN (COOL subscription)

- Done: configurations A (x86 `c7i.2xlarge`) and B (Graviton4 `c8g.2xlarge`), stock OpenCV 5.0.0, five runs each, with cost, parity and per-instance evidence in `results/bench/2026-10-27/`; reported in `docs/TECHNICAL_REPORT.md` §7. COOL award not claimed.
- Remaining: configuration C (COOL) after the Marketplace subscription (H1 item 4); ENF-track parity on a clip with a usable signal.

## M11 — Demo and UX — OPEN

<!-- m11-aws:begin (from results/aws/index.json) -->
- Demo cases (SYNTHETIC simulator clips from `eval/make_demo_inputs.py`) run end to end on the deployed system. Cases with evidence in `results/aws/`:
  - capture-verified: `VERIFIED` (FINAL), target `VERIFIED`, job `aws3-capture-verified-040158`
  - cut-1s: `VERIFIED` (FINAL), target `CONTRADICTED`, job `aws3-cut-1s-040211` — MISSED target
  - dropped-frames: `VERIFIED` (FINAL), target `VERIFIED`, job `aws3-dropped-frames-040218`
  - agent-recovery: `INCONCLUSIVE` (FINAL), target `second-pass verdict`, job `aws4-agent-recovery-041816`
  - capture-verified: `VERIFIED` (FINAL), target `VERIFIED`, job `aws4-capture-verified-041747`
  - cut-1s: `VERIFIED` (FINAL), target `CONTRADICTED`, job `aws4-cut-1s-041731` — MISSED target
  - daylight-only: `INCONCLUSIVE` (DRAFT), target `INCONCLUSIVE`, job `aws4-daylight-only-041808`
  - dropped-frames: `VERIFIED` (FINAL), target `VERIFIED`, job `aws4-dropped-frames-041757`
  - insertion: job failed on the worker (no result produced), target `CONTRADICTED`, job `aws4-insertion-041739` — MISSED target
- Open: AWS runs for the cases not listed above; investigate cases marked MISSED target (see `docs/TECHNICAL_REPORT.md` §6).
<!-- m11-aws:end -->

## M12 — Docs and video — OPEN (video: H8)

- Done: all Part 14 documents exist; consistency pass on 2026-10-27 (planner Amazon Nova Lite per D-026, benchmark in report §7, COOL not claimed).
- Remaining: video recording, upload and link (H8); README fresh-clone test result under `results/fresh_clone/`.

## M13 — Final check — OPEN (`scripts/final_check.py` reports the open items)
