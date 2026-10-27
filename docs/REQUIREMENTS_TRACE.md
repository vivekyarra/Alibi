# Requirements trace (SPEC Part 3)

Every line needs an evidence link before the final stop.

Status values: `MET` (the evidence exists in the repository or on the account now), `PARTIAL` (the note says what is missing), `OPEN` (no evidence yet).

| Section | Requirement | Status | Evidence |
|---|---|---|---|
| 3.1 | OpenCV 5 performs substantive image/video analysis (Engine S1–S14) | MET | `engine/gridprint_engine/*.py` (stages S1–S15); OpenCV 5 usage map in `docs/TECHNICAL_REPORT.md` §5; video integration tests `engine/gridprint_engine/tests/test_video.py` |
| 3.1 | A meaningful component runs on AWS (Part 10.6) | PARTIAL | Deployed stacks (Network, Storage, Data, Ai, Auth, Compute, Api, Iot, Observability) from `infra/`; status table in `docs/TECHNICAL_REPORT.md` §6. Missing: a completed end-to-end job on AWS (in progress). |
| 3.2 | Technical report: problem, users, architecture, OpenCV 5 implementation, AWS deployment, evaluation, limitations, responsible use | PARTIAL | `docs/TECHNICAL_REPORT.md`. Missing: result tables in §7–§10 from the evaluation and benchmark runs. |
| 3.2 | Judge-accessible code repository | MET | https://github.com/vivekyarra/Alibi (public) |
| 3.2 | Pinned dependencies plus clear build, deployment and test instructions | MET | `uv.lock`, `pyproject.toml`, `web/package-lock.json`; `README.md` (quick start, deploy, evaluate); `Makefile`; `.github/workflows/ci.yml` |
| 3.2 | Architecture diagram showing OpenCV 5, AWS, COOL and agent components | MET | `docs/diagrams/architecture.svg` (source `docs/diagrams/architecture.mmd`), `docs/diagrams/agent_workflow.svg`; COOL is shown as supported by the stack, not active (§3.3 lines). |
| 3.2 | Working web endpoint (Verify) or arranged live screen-share | OPEN | Public HTTPS endpoint pending (CloudFront needs AWS account verification; API Gateway endpoint in progress). Live screen-share with `make local` offered in `docs/JUDGE_GUIDE.md`. |
| 3.2 | Public or unlisted video, max 5 minutes | OPEN | Script `docs/VIDEO_SCRIPT.md`; recording is human task H8. |
| 3.2 | Evaluation evidence, including failure cases and limitations | PARTIAL | Limitations in `docs/TECHNICAL_REPORT.md` §11; simulator `eval/simulator/`; evaluation tools `eval/run_eval.py`, `eval/make_report.py`; first SYNTHETIC run folder `results/eval/2026-10-27/`. Missing: committed result tables and the failure gallery. |
| 3.3 | COOL executes the claimed core workload on AWS Graviton | OPEN | COOL not active: Marketplace subscription pending (H1). The engine runs stock OpenCV 5.0.0 on Graviton. The stack uses a COOL AMI when `aws.cool_ami_id` is set. |
| 3.3 | Report COOL version and AWS instance/deployment configuration | PARTIAL | AWS configuration: `docs/TECHNICAL_REPORT.md` §6, `config/default.yaml`, `infra/gridprint_infra/compute.py`. Missing: COOL version (needs the COOL AMI). |
| 3.3 | Reproducible evaluation method, inputs, baselines and results | PARTIAL | Method and inputs: `bench/README.md`, `bench/configs.yaml`, `bench/inputs.txt`, `bench/run_bench.py`, `bench/prices.py`; `eval/`. Missing: benchmark results under `results/bench/`. |
| 3.3 | Evidence that COOL executes the claimed workload | OPEN | Collector `bench/cool_evidence.py` with tests `bench/tests/test_cool_evidence.py`; no evidence file until the COOL benchmark runs. |
| 3.3 | Explain any x86/Arm coexistence | MET | `docs/ARCHITECTURE.md` §7; `docs/TECHNICAL_REPORT.md` §6; `infra/build_images.py` (`linux/arm64` images, `--amd64` for benchmark baseline A only) |
| 3.4 | Multi-step perception → decision → action loop where OpenCV 5 results change a later plan, tool call, action or human-approval request | MET | `agent/orchestrator.py`, `agent/fallback_planner.py`, `agent/planner_bedrock.py`, `agent/policies.py`, `mcp_server/tools.py`, `mcp_server/server.py`; tests `agent/tests/test_agent.py` (B1–B6), `mcp_server/tests/test_mcp_stdio.py` |
| 3.4 | Agent workflow diagram (perception, decision/orchestration, action) | MET | `docs/diagrams/agent_workflow.svg` (source `docs/diagrams/agent_workflow.mmd`) |
| 3.4 | Trace or demonstration showing OpenCV 5 output changing a later decision | PARTIAL | Tested in `agent/tests/test_agent.py` (`test_b1_weak_signal_reselects_patches_and_reextracts` and others); trace writer `agent/trace.py`. Missing: saved traces from real runs under `results/` (the evaluation run commits them). |
| 3.4 | Evaluation of task success, failure handling, observability and human control | PARTIAL | Metrics code `eval/metrics.py`; human control tests `agent/tests/test_agent.py` (`test_b6_contradicted_requests_review_and_no_final_report`); planner fuzz `tests/test_stress.py`; CloudWatch dashboard and alarms in `infra/gridprint_infra/observability.py`. Missing: measured results under `results/`. |
