// Configuration values for the web app. These are settings, not measured results.

function trimSlash(s: string): string {
  return s.replace(/\/+$/, "");
}

export const API_BASE: string = trimSlash(import.meta.env.VITE_API_BASE || "/v1");

/** Base URL of the repository docs (for example a GitHub tree URL). Empty means: show paths only. */
export const DOCS_BASE_URL: string = trimSlash(import.meta.env.VITE_DOCS_BASE_URL || "");

/** Poll interval for job status and agent trace while a job runs (contract: every 2 s). */
export const POLL_INTERVAL_MS = 2000;

/** Refresh interval of the live grid tile. */
export const LIVE_TILE_INTERVAL_MS = 5000;

/** Grid zone ids. Keep in sync with config/zones.yaml (real zones only; SIM zones are for tests). */
export const ZONES: ReadonlyArray<{ id: string; label: string }> = [
  { id: "IN", label: "India national synchronous grid" },
  { id: "CE", label: "Continental Europe synchronous area" },
  { id: "GB", label: "Great Britain synchronous area" },
  { id: "US-EI", label: "US Eastern Interconnection" },
];

export const LIVE_ZONE_DEFAULT: string = import.meta.env.VITE_LIVE_ZONE || "GB";
