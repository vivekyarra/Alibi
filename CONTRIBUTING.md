# Contributing to GRIDPRINT

Thanks for helping. GRIDPRINT proves a video is real by reading mains-grid frequency from indoor light flicker captured by a rolling shutter.

## Ground rules

- `SPEC.md` is the single source of truth. Changes to the product, its verdicts, or its method need a spec change first.
- Ideas outside the spec go in `docs/IDEAS.md`; design choices made under ambiguity go in `docs/DECISIONS.md`.
- Exactly three verdicts: `VERIFIED`, `CONTRADICTED`, `INCONCLUSIVE`. A missing signal never means fake.
- Never hardcode verdicts or fabricate numbers. Every reported number must come from `results/` with a source tag. Test doubles live only in `tests/`.
- Keep the signal path in float32/float64, work in linear light, and never interpolate across rolling-shutter idle gaps.

## Setup

Requires Python 3.11 and [uv](https://docs.astral.sh/uv/). On Windows use `make.cmd` (or `./make` in Git Bash).

```sh
make setup   # create the environment and install dependencies
make lint    # ruff + mypy
make test    # unit and integration tests
make local   # run the stack locally
```

`make eval`, `make bench`, and `make final-check` reproduce the published results. `make deploy` / `make destroy` need your own AWS account.

## Workflow

1. Branch from the default branch (`feat/...`, `fix/...`, `docs/...`). Do not push to the default branch directly.
2. Keep each pull request focused; update tests and docs with the code.
3. Run `make lint` and `make test` locally before pushing.
4. Open a pull request using the template. **CI must be green before merge.**
5. Do not commit large media, raw captures (`data/`), logs, or secrets; see `.gitignore`.

## Reporting bugs

Use the bug report issue template. For security issues see `SECURITY.md`.
