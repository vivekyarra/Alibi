import { API_BASE } from "../config";
import type {
  Claim,
  CreateJobResponse,
  DemoCase,
  GridLive,
  Health,
  Job,
  Review,
  ReviewDecision,
  Trace,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export interface ApiClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}

interface RequestOptions {
  body?: unknown;
  token?: string;
}

function detailMessage(detail: unknown): string | null {
  if (detail && typeof detail === "object" && "detail" in detail) {
    const d = (detail as { detail: unknown }).detail;
    if (typeof d === "string") return d;
  }
  return null;
}

export type SubmitStep = "create" | "upload" | "start";

export function createApiClient(options: ApiClientOptions = {}) {
  const base = (options.baseUrl ?? API_BASE).replace(/\/+$/, "");
  const doFetch: typeof fetch = options.fetchImpl ?? ((input, init) => fetch(input, init));

  async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (opts.body !== undefined) headers["Content-Type"] = "application/json";
    if (opts.token) headers["Authorization"] = `Bearer ${opts.token}`;
    const res = await doFetch(`${base}${path}`, {
      method,
      headers,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    });
    if (!res.ok) {
      let detail: unknown = undefined;
      try {
        detail = await res.json();
      } catch {
        detail = undefined;
      }
      throw new ApiError(res.status, detailMessage(detail) ?? `Request failed with status ${res.status}`, detail);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  const id = (s: string) => encodeURIComponent(s);

  const client = {
    health: () => request<Health>("GET", "/health"),

    createJob: () => request<CreateJobResponse>("POST", "/jobs"),

    /** PUT the raw file bytes to the presigned upload URL. */
    async uploadFile(uploadUrl: string, file: Blob): Promise<void> {
      const res = await doFetch(uploadUrl, {
        method: "PUT",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file,
      });
      if (!res.ok) throw new ApiError(res.status, `Upload failed with status ${res.status}`);
    },

    startJob: (jobId: string, claim: Claim, sidecar?: Record<string, unknown>) =>
      request<unknown>("POST", `/jobs/${id(jobId)}/start`, {
        body: sidecar === undefined ? { claim } : { claim, sidecar },
      }),

    getJob: (jobId: string) => request<Job>("GET", `/jobs/${id(jobId)}`),

    getTrace: (jobId: string) => request<Trace>("GET", `/jobs/${id(jobId)}/trace`),

    sendInput: (jobId: string, kind: string, value: string) =>
      request<unknown>("POST", `/jobs/${id(jobId)}/input`, { body: { kind, value } }),

    listReviews: (token: string) => request<Review[]>("GET", "/reviews", { token }),

    decideReview: (reviewId: string, decision: ReviewDecision, token: string) =>
      request<unknown>("POST", `/reviews/${id(reviewId)}/decision`, { body: decision, token }),

    listDemoCases: () => request<DemoCase[]>("GET", "/demo-cases"),

    runDemoCase: (caseId: string) => request<{ job_id: string }>("POST", `/demo-cases/${id(caseId)}/run`),

    gridLive: (zone: string) => request<GridLive>("GET", `/grid/${id(zone)}/live`),

    /** Create a job, upload the file, and start the analysis. Returns the job id. */
    async submitVideo(
      file: Blob,
      claim: Claim,
      sidecar?: Record<string, unknown>,
      onStep?: (step: SubmitStep) => void,
    ): Promise<string> {
      onStep?.("create");
      const job = await client.createJob();
      if (job.upload_method !== "PUT") {
        throw new ApiError(0, `Unsupported upload method: ${String(job.upload_method)}`);
      }
      onStep?.("upload");
      await client.uploadFile(job.upload_url, file);
      onStep?.("start");
      await client.startJob(job.job_id, claim, sidecar);
      return job.job_id;
    },
  };
  return client;
}

export type ApiClient = ReturnType<typeof createApiClient>;
