# GRIDPRINT progress

Current milestone: M2/M3 hardening (video integration tests) and M8 (AWS deployment in progress).

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
- Found by the video integration tests (`engine/gridprint_engine/tests/test_video.py`, 4 of 8 failing on 2026-10-26): the clean 160×120 clip did not reach VERIFIED and a VFR timestamp check failed. Under diagnosis.

## M3 — Engine S11–S15 — OPEN

- Done: verdict rules and R1–R3, R9 tests; report HTML/PDF/JSON and overlay generation; claims_lint on templates.
- Found by the video integration tests: the 1 s cut was not CONTRADICTED and the dropped-frame clip produced an edit candidate in the small-clip configuration. Under diagnosis.

## M4 — Node and reference — BLOCKED-HUMAN (H2)

- Done: firmware, hardware docs with the R11 warning, ingest Lambda, GridLog adapter, simulated publisher, data-quality script, NESO and WAV reference importers (42 tests pass).
- Remaining: ≥ 24 h of real Node data with GPS lock (H2).

## M5 — Calibration — BLOCKED-HUMAN (H3)

- Done: rig firmware (200 Hz, D-017), filming checklist, `calibration_rig/fit_readout.py` with tests.

## M6 — Capture app — BLOCKED-HUMAN (H4)

- Done: Kotlin Camera2 app, sidecar writer, band meter, device check, validator; JVM and Python tests pass.

## M7 — Agent — OPEN

- Done: MCP server (12 tools, stdio test), fallback planner (B1–B6), Bedrock planner, policies, trace; `agent/tests` (13 passed); adversarial-planner fuzz (200 runs) in `tests/test_stress.py`.
- Remaining: saved traces from real runs showing B1–B6 under `results/agent_traces/`; Bedrock planner run (blocked: account verification, D-021).

## M8 — AWS deployment — OPEN

- Account and profile ready (D-021). Remaining: build images, `make deploy`, end-to-end run on the endpoint.

## M9 — Real evaluation — BLOCKED-HUMAN (H5–H7)

- Synthetic evaluation and threshold calibration tooling is in place; the real dataset is needed (public datasets need the owner's login, H5-a).

## M10 — COOL benchmark — OPEN / BLOCKED-HUMAN (COOL subscription)

## M11 — Demo and UX — OPEN

## M12 — Docs and video — OPEN (video: H8)

## M13 — Final check — OPEN (`scripts/final_check.py` reports the open items)
