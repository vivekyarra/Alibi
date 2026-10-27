# Security Policy

## Reporting a vulnerability

Please do **not** open a public issue for security problems.
Report them privately through GitHub security advisories:
<https://github.com/vivekyarra/Alibi/security/advisories/new>

Include the affected component (`engine/`, `api/`, `agent/`, `mcp_server/`, `infra/`, `web/`, `node/`, `capture-android/`), steps to reproduce, and the impact you observed.

## Scope notes

- **Verdict integrity.** GRIDPRINT returns exactly three verdicts: `VERIFIED`, `CONTRADICTED`, `INCONCLUSIVE`. Any way to obtain `VERIFIED` for a clip whose flicker does not match the reference grid log, or to publish `CONTRADICTED` without human approval, is in scope.
- **Secrets.** No credentials, API keys, AWS account secrets, device certificates (`*.pem`, `*.key`), or `.env` files belong in this repository; they are git-ignored. If you find one committed, report it as a vulnerability.
- **Personal media.** Raw capture videos (`data/`) are never committed. Report any committed personal footage.

## Supported versions

Only the latest commit on the default branch is supported.
