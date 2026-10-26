import { describe, expect, it } from "vitest";
import { ApiError, createApiClient } from "../src/api/client";
import { fakeFetch, makeJob, makeTrace } from "./fakeFetch";

const BASE = "http://api.test/v1";

function bodyOf(call: unknown[]): unknown {
  const init = call[1] as RequestInit | undefined;
  return init?.body ? JSON.parse(String(init.body)) : undefined;
}

describe("API client", () => {
  it("creates a job, PUTs the file to the upload URL, then starts the job", async () => {
    const f = fakeFetch({
      [`POST ${BASE}/jobs`]: { job_id: "j1", upload_url: "https://upload.test/put?sig=x", upload_method: "PUT", expires_s: 60 },
      "PUT https://upload.test/put?sig=x": {},
      [`POST ${BASE}/jobs/j1/start`]: { ok: true },
    });
    const api = createApiClient({ baseUrl: BASE, fetchImpl: f });
    const file = new Blob(["abc"], { type: "video/mp4" });
    const steps: string[] = [];
    const id = await api.submitVideo(file, { claimed_zone: "GB" }, { app_version: "t" }, (s) => steps.push(s));

    expect(id).toBe("j1");
    expect(steps).toEqual(["create", "upload", "start"]);
    expect(f).toHaveBeenCalledTimes(3);
    const put = f.mock.calls[1];
    expect(put[0]).toBe("https://upload.test/put?sig=x");
    expect((put[1] as RequestInit).method).toBe("PUT");
    expect((put[1] as RequestInit).body).toBe(file);
    expect(((put[1] as RequestInit).headers as Record<string, string>)["Content-Type"]).toBe("video/mp4");
    expect(bodyOf(f.mock.calls[2])).toEqual({ claim: { claimed_zone: "GB" }, sidecar: { app_version: "t" } });
  });

  it("omits the sidecar when none is given", async () => {
    const f = fakeFetch({ [`POST ${BASE}/jobs/j2/start`]: {} });
    const api = createApiClient({ baseUrl: BASE, fetchImpl: f });
    await api.startJob("j2", {});
    expect(bodyOf(f.mock.calls[0])).toEqual({ claim: {} });
  });

  it("reads job status and trace", async () => {
    const job = makeJob();
    const f = fakeFetch({ [`GET ${BASE}/jobs/j3`]: job, [`GET ${BASE}/jobs/j3/trace`]: makeTrace() });
    const api = createApiClient({ baseUrl: BASE, fetchImpl: f });
    expect(await api.getJob("j3")).toEqual(job);
    expect((await api.getTrace("j3")).steps).toHaveLength(1);
  });

  it("sends the bearer token to reviewer endpoints", async () => {
    const f = fakeFetch({
      [`GET ${BASE}/reviews`]: [],
      [`POST ${BASE}/reviews/r1/decision`]: {},
    });
    const api = createApiClient({ baseUrl: BASE, fetchImpl: f });
    await api.listReviews("tok");
    await api.decideReview("r1", { approve: false, note: "n", reviewer: "me" }, "tok");
    for (const call of f.mock.calls) {
      const headers = (call[1] as RequestInit).headers as Record<string, string>;
      expect(headers.Authorization).toBe("Bearer tok");
    }
    expect(bodyOf(f.mock.calls[1])).toEqual({ approve: false, note: "n", reviewer: "me" });
  });

  it("posts agent input, runs demo cases, and reads the live grid", async () => {
    const f = fakeFetch({
      [`POST ${BASE}/jobs/j4/input`]: {},
      [`GET ${BASE}/demo-cases`]: [],
      [`POST ${BASE}/demo-cases/d1/run`]: { job_id: "j5" },
      [`GET ${BASE}/grid/US-EI/live`]: { zone: "US-EI", samples: [] },
      [`GET ${BASE}/health`]: { status: "ok" },
    });
    const api = createApiClient({ baseUrl: BASE, fetchImpl: f });
    await api.sendInput("j4", "camera_model", "x");
    expect(bodyOf(f.mock.calls[0])).toEqual({ kind: "camera_model", value: "x" });
    expect(await api.listDemoCases()).toEqual([]);
    expect(await api.runDemoCase("d1")).toEqual({ job_id: "j5" });
    expect((await api.gridLive("US-EI")).zone).toBe("US-EI");
    expect(await api.health()).toEqual({ status: "ok" });
  });

  it("encodes path parameters", async () => {
    const f = fakeFetch({ [`GET ${BASE}/jobs/a%2Fb`]: makeJob() });
    const api = createApiClient({ baseUrl: BASE, fetchImpl: f });
    await api.getJob("a/b");
    expect(f.mock.calls[0][0]).toBe(`${BASE}/jobs/a%2Fb`);
  });

  it("throws ApiError with status and detail on HTTP errors", async () => {
    const f = fakeFetch({}, () => ({ status: 401, body: { detail: "bad token" } }));
    const api = createApiClient({ baseUrl: BASE, fetchImpl: f });
    const err = await api.listReviews("x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(401);
    expect((err as ApiError).message).toBe("bad token");
  });

  it("fails the submit when the upload PUT fails", async () => {
    const f = fakeFetch(
      { [`POST ${BASE}/jobs`]: { job_id: "j6", upload_url: "https://upload.test/x", upload_method: "PUT", expires_s: 60 } },
      (url) => (url === "https://upload.test/x" ? { status: 403, body: {} } : undefined),
    );
    const api = createApiClient({ baseUrl: BASE, fetchImpl: f });
    await expect(api.submitVideo(new Blob(["a"]), {})).rejects.toBeInstanceOf(ApiError);
    expect(f).toHaveBeenCalledTimes(2);
  });
});
