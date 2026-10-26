// Types for the GRIDPRINT API contract (SPEC 10.1).

export const VERDICTS = ["VERIFIED", "CONTRADICTED", "INCONCLUSIVE"] as const;
export type Verdict = (typeof VERDICTS)[number];

export const LIFECYCLE_STATES = ["DRAFT", "PENDING_REVIEW", "FINAL"] as const;
export type LifecycleState = (typeof LIFECYCLE_STATES)[number];

export const JOB_STATUSES = ["created", "uploaded", "queued", "running", "done", "failed"] as const;
export type JobStatus = (typeof JOB_STATUSES)[number];

export interface CreateJobResponse {
  job_id: string;
  upload_url: string;
  upload_method: "PUT";
  expires_s: number;
}

export interface Claim {
  claimed_zone?: string;
  claimed_time_utc?: string;
  claimed_time_tolerance_s?: number;
}

export interface StartJobRequest {
  claim: Claim;
  sidecar?: Record<string, unknown>;
}

export interface JobArtifacts {
  overlay_mp4?: string;
  report_html?: string;
  report_pdf?: string;
  report_json?: string;
  plots?: Record<string, string>;
}

export interface UserRequest {
  kind: string;
  message: string;
  created: string;
}

export interface Job {
  job_id: string;
  status: JobStatus;
  error?: string | null;
  lifecycle_state: LifecycleState | null;
  verdict: Verdict | null;
  reasons: string[];
  time_estimate_iso: string | null;
  time_uncertainty_s: number | null;
  zone: string | null;
  artifacts: JobArtifacts;
  user_requests: UserRequest[];
  result?: Record<string, unknown> | null;
}

export interface TraceStep {
  index: number;
  t_start: string | number;
  t_end: string | number;
  planner: "bedrock" | "fallback";
  model_id: string | null;
  tool: string;
  input_summary: string;
  output_summary: string;
  decision_reason: string;
  duration_s: number;
}

export interface Trace {
  steps: TraceStep[];
}

export interface Review {
  review_id: string;
  job_id: string;
  verdict: Verdict;
  reasons: string[];
  created: string;
  status: string;
}

export interface ReviewDecision {
  approve: boolean;
  note: string;
  reviewer: string;
}

export interface DemoCase {
  id: string;
  title: string;
  description: string;
  expected_verdict: Verdict;
}

export interface GridSample {
  t_utc_s: number;
  freq_hz: number;
}

export interface GridLive {
  zone: string;
  samples: GridSample[];
}

export interface Health {
  status: "ok";
}

/** Continuity event from AnalysisResult (engine schemas.py::ContinuityEvent). */
export interface ContinuityEvent {
  kind: string;
  frame_index: number;
  t_s: number;
  significant: boolean;
}

export function isTerminalStatus(s: JobStatus): boolean {
  return s === "done" || s === "failed";
}

/** Read continuity events from the opaque result object. Unknown shapes give an empty list. */
export function continuityEvents(result: Record<string, unknown> | null | undefined): ContinuityEvent[] {
  const raw = result?.["continuity_events"];
  if (!Array.isArray(raw)) return [];
  const out: ContinuityEvent[] = [];
  for (const e of raw) {
    if (e && typeof e === "object") {
      const o = e as Record<string, unknown>;
      if (typeof o.t_s === "number" && typeof o.kind === "string") {
        out.push({
          kind: o.kind,
          t_s: o.t_s,
          frame_index: typeof o.frame_index === "number" ? o.frame_index : -1,
          significant: o.significant === true,
        });
      }
    }
  }
  return out;
}
