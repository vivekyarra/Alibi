# Agent notes: web (GRIDPRINT Verify, SPEC 10.2)

Scope: `web/` only. Nothing committed (the lead commits).

## Decisions

| Date | Decision | Reason |
|---|---|---|
| 2026-10-26 | Small built-in hash router (`src/router.ts`), no router library. | Five pages only. Hash routes work on S3 + CloudFront with no rewrite rules. One fewer dependency. |
| 2026-10-26 | API client is a factory `createApiClient({baseUrl, fetchImpl})`, given to pages through React context. | Tests inject a fake fetch from `tests/` only; production code has no test doubles. |
| 2026-10-26 | `POST /v1/jobs` is sent with no body. | The contract defines no request body. |
| 2026-10-26 | Upload PUT sends `Content-Type` = file type (or `application/octet-stream`). | Presigned S3 PUT. If the API signs a fixed content type, this must match; check with the API agent. |
| 2026-10-26 | Claimed time is entered in a `datetime-local` field labeled UTC and sent as ISO 8601 with `Z`. | Avoids local-time-zone ambiguity. |
| 2026-10-26 | Job and trace poll every 2 s until status is `done` or `failed`; after that a "Refresh status" button reloads. | Contract says poll while running. No endless polling while a review is pending. |
| 2026-10-26 | Live grid tile refreshes every 5 s; default zone `GB` (override `VITE_LIVE_ZONE`). Zone list `IN, CE, GB, US-EI` mirrors `config/zones.yaml` (SIM zones left out). | GB is the zone with a verified 1 s public source (V8). Configuration, not measured values. |
| 2026-10-26 | Any `CONTRADICTED` verdict whose lifecycle state is not `FINAL` (DRAFT or PENDING_REVIEW) shows "Pending human review" and the heading "Draft verdict". | R3: never show CONTRADICTED as final without approval. Stricter than the minimum. |
| 2026-10-26 | Verdict is shown only when job status is `done`. | Avoid showing a partial verdict during the run. |
| 2026-10-26 | Timeline markers come from `result.continuity_events` (`kind`, `t_s`, `significant`, per engine `schemas.py::ContinuityEvent`). Unknown shapes give no markers. | Only API data; no invented markers. |
| 2026-10-26 | Capture info lives in a section of the Limitations page (`#/limitations/capture`). | SPEC 10.2 lists no separate Capture page. |
| 2026-10-26 | Judge Guide page links to repo docs through `VITE_DOCS_BASE_URL`; when unset it shows the file paths as text. | No Git remote exists yet; avoid broken links. |
| 2026-10-26 | Reviewer bearer token is kept in React state only (not stored). | Least exposure of the credential. |
| 2026-10-26 | `npm run a11y` = vitest + jsdom + axe-core over the whole `App` at each route (Home, Job x3 verdicts + running, Reviewer signed-out and with evidence, Limitations, Capture section, Judge Guide, Not found) plus a harness self-check. Any violation fails. | SPEC 10.2 "automated axe-core check in CI". Verified: removing an `alt` makes the run exit 1. |
| 2026-10-26 | Color contrast is checked by `tests/a11y/contrast.test.ts` on the CSS tokens (light, dark via media query, dark via toggle). | jsdom has no layout/canvas, so axe cannot measure contrast there. |
| 2026-10-26 | Tests live in `web/tests/`, not `web/src/`. | `scripts/check_numbers_sourced.py` scans `web/src/**/*.tsx`; test fixtures must not be in scope, and test doubles stay out of production paths. |
| 2026-10-26 | No decimal literals in `.tsx` (icons use integer SVG geometry; spec refs written "Part x.y"). | Keeps `check_numbers_sourced.py` clean without tags on non-measured numbers. Measured values render from API data and carry `data-source="api"`. |
| 2026-10-26 | jsdom pinned to 29.1.1, not 30.x. | jsdom 30 deps require Node >= 24.15; host has Node 24.12.0. |
| 2026-10-26 | TypeScript 7.0.2 (native compiler). | Latest stable; `tsc --noEmit` passes. |

## Package versions (exact, from package-lock.json)

react 19.3.1, react-dom 19.3.1, vite 8.3.5, @vitejs/plugin-react 6.1.2, typescript 7.0.2, vitest 5.0.5, jsdom 29.1.1, axe-core 4.14.0, @testing-library/react 16.3.3, @testing-library/dom 10.4.2, @testing-library/jest-dom 7.0.1, @types/react 19.3.0, @types/react-dom 19.3.0, @types/node 24.19.2.

## Env vars

`VITE_API_BASE` (default `/v1`, proxied to `http://localhost:8000` in `npm run dev`), `VITE_DOCS_BASE_URL`, `VITE_LIVE_ZONE`.

## Open points for other components

- API must allow CORS (or same-origin via CloudFront) for `/v1/*` and the S3 upload origin.
- Reviewer endpoints: the web sends `Authorization: Bearer <token>` on both `GET /v1/reviews` and `POST /v1/reviews/{id}/decision`.
- Artifact URLs (overlay, plots, reports) are used as given; they must be fetchable by the browser (presigned or public via CloudFront).
