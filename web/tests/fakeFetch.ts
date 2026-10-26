// Test double for fetch. Lives only in tests/ (SPEC 0.10). The values below are test fixtures,
// not measured results.
import { vi } from "vitest";
import type { Job, Trace } from "../src/api/types";

export type Handler = (url: string, init: RequestInit | undefined) => { status?: number; body?: unknown } | undefined;

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function fakeFetch(routes: Record<string, unknown | ((init?: RequestInit) => unknown)>, fallback?: Handler) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    const key = `${method} ${url}`;
    if (key in routes) {
      const r = routes[key];
      const body = typeof r === "function" ? (r as (i?: RequestInit) => unknown)(init) : r;
      return jsonResponse(body);
    }
    const fb = fallback?.(url, init);
    if (fb) return jsonResponse(fb.body, fb.status ?? 200);
    return jsonResponse({ detail: `no fake route for ${key}` }, 404);
  });
}

export function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    job_id: "job-test",
    status: "done",
    error: null,
    lifecycle_state: "FINAL",
    verdict: "VERIFIED",
    reasons: ["MATCH_OK"],
    time_estimate_iso: "2026-01-01T00:00:00Z",
    time_uncertainty_s: 1,
    zone: "SIM50",
    artifacts: {
      overlay_mp4: "/files/overlay.mp4",
      report_pdf: "/files/report.pdf",
      report_html: "/files/report.html",
      report_json: "/files/result.json",
      plots: { frequency_track: "/files/track.png" },
    },
    user_requests: [],
    result: {
      continuity_events: [{ kind: "EDIT_CANDIDATE", frame_index: 3, t_s: 2, significant: true }],
    },
    ...overrides,
  };
}

export function makeTrace(): Trace {
  return {
    steps: [
      {
        index: 1,
        t_start: "2026-01-01T00:00:00Z",
        t_end: "2026-01-01T00:00:01Z",
        planner: "fallback",
        model_id: null,
        tool: "probe_video",
        input_summary: "test input",
        output_summary: "test output",
        decision_reason: "test reason",
        duration_s: 1,
      },
    ],
  };
}
