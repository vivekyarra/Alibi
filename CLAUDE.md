# CLAUDE.md — GRIDPRINT

You are building **GRIDPRINT**: a system that proves a video is real by reading the power-grid frequency from the flicker of indoor lights, captured by the camera's rolling shutter. Entry for the OpenCV AI Competition 2026 (OpenCV 5 + AWS).

## Start of every session
1. Read `SPEC.md` Part 0, Part 2, Part 15, Part 17.
2. Read `docs/PROGRESS.md` (create it in M0 if missing).
3. Continue with the next unaccepted milestone in `SPEC.md` Part 15.

## Hard rules (full list in SPEC.md Parts 0 and 2)
- `SPEC.md` is the single source of truth. Do not change the product, its verdicts, or its method.
- Scope lock: ideas not in SPEC.md go to `docs/IDEAS.md`, not into code.
- Ambiguity: choose the simplest option that meets acceptance criteria; log it in `docs/DECISIONS.md`; continue.
- Verify unverified facts (SPEC.md Part 4) before use; log in `docs/VERIFICATION.md`.
- Never fabricate numbers, results, API names, citations, or traces. Every reported number comes from `results/` with a source tag.
- Never fake functionality or hardcode verdicts. Test doubles live only in `tests/`.
- Exactly three verdicts: `VERIFIED`, `CONTRADICTED`, `INCONCLUSIVE`. `CONTRADICTED` needs human approval. Missing signal never means fake.
- Signal path in float32/float64 only. Linear light before normalization. Never interpolate across rolling-shutter idle gaps.
- Human-only tasks: write instructions in `docs/HUMAN_TASKS.md`, mark `BLOCKED-HUMAN`, continue other work.

## Stopping
- Never stop at a partial build or because you are unsure what is next. The next step is always the next unaccepted milestone.
- If only human tasks remain: write the PAUSED block (SPEC.md 17.2) and end the session.
- Stop for good only when every line of SPEC.md 17.3 is true and `make final-check` prints `ALL CHECKS PASSED`. Then write `PROJECT COMPLETE` in `docs/PROGRESS.md` and add nothing more.

## Commands (create in M0)
`make setup` · `make lint` · `make test` · `make local` · `make deploy` · `make destroy` · `make eval` · `make bench` · `make final-check`
