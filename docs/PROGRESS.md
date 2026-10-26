# GRIDPRINT progress

Current milestone: M1 (simulator)

## M0 — Setup and verification — ACCEPTED (2026-10-26)

| Criterion | Evidence |
|---|---|
| Repo layout per Part 6 | Directories created: `config/ engine/gridprint_engine/{adapters,tests} mcp_server/ agent/{prompts,tests} api/ web/ capture-android/ node/{firmware,hardware,ingest} calibration_rig/ infra/ eval/simulator/ bench/ scripts/ docs/diagrams/ results/ .github/workflows/` |
| CI runs lint, type check, tests, claims_lint | `.github/workflows/ci.yml` (jobs `python`: `make lint` = ruff + mypy + `claims_lint` + `check_numbers_sourced`, `make test` = pytest; `web`: typecheck, tests, axe; `scan`: trivy). Local run: `ruff check scripts tests` → `All checks passed!`; `mypy scripts` → `Success: no issues found in 6 source files`; `pytest tests` → `2 passed`; `claims_lint` → `5 files scanned, 0 violations`. No Git remote exists yet, so CI has not run on GitHub (needs the repository to be pushed — part of H9 prep). |
| VERIFICATION.md V1–V12 resolved | `docs/VERIFICATION.md`: V1, V2, V3, V9, V10 VERIFIED by command; V4 API VERIFIED; V8 partial (NESO GB 1 s); V5, V6, V7, V11, V12 BLOCKED-HUMAN with instructions. `scripts/verify_aws.py` → `AWS FAIL: The config profile (gridprint) could not be found` (H1). |
| HUMAN_TASKS.md lists H1–H9 | `docs/HUMAN_TASKS.md` |
| REQUIREMENTS_TRACE.md created | `docs/REQUIREMENTS_TRACE.md` (18 lines, all OPEN) |

Notes: host has no GNU make → `make`/`make.cmd` shims (D-002). Host network ran at 275–551 B/s to PyPI (`curl -w %{speed_download}`), so `.venv` was bootstrapped offline (D-004); `uv.lock` pins all versions.
