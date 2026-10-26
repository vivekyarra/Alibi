import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "../src/App";
import { createApiClient } from "../src/api/client";
import { parseHash } from "../src/router";
import { utcInputToIso } from "../src/pages/HomePage";
import { fakeFetch, makeJob, makeTrace } from "./fakeFetch";

const BASE = "http://api.test/v1";

async function flush() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 30));
  });
}

describe("router", () => {
  it("parses routes", () => {
    expect(parseHash("")).toEqual({ name: "home" });
    expect(parseHash("#/jobs/abc")).toEqual({ name: "job", jobId: "abc" });
    expect(parseHash("#/limitations/capture")).toEqual({ name: "limitations", section: "capture" });
    expect(parseHash("#/judge-guide")).toEqual({ name: "judge-guide" });
    expect(parseHash("#/x").name).toBe("not-found");
  });
});

describe("utcInputToIso", () => {
  it("reads datetime-local input as UTC", () => {
    expect(utcInputToIso("2026-01-02T03:04")).toBe("2026-01-02T03:04:00.000Z");
    expect(utcInputToIso("")).toBeUndefined();
    expect(utcInputToIso("garbage")).toBeUndefined();
  });
});

describe("Job page", () => {
  it("shows API values, the trace, markers, plots and downloads", async () => {
    const f = fakeFetch({
      [`GET ${BASE}/jobs/job-test`]: makeJob(),
      [`GET ${BASE}/jobs/job-test/trace`]: makeTrace(),
    });
    window.location.hash = "#/jobs/job-test";
    render(<App client={createApiClient({ baseUrl: BASE, fetchImpl: f })} />);
    await flush();
    expect(screen.getByTestId("verdict-text")).toHaveTextContent("VERIFIED");
    expect(screen.getByText("probe_video")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Possible edit at/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Evidence plot: frequency track/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Report (PDF)" })).toHaveAttribute("href", "/files/report.pdf");
    // Done jobs stop polling: one job fetch and one trace fetch.
    expect(f).toHaveBeenCalledTimes(2);
  });

  it("shows a running job without a verdict", async () => {
    const f = fakeFetch({
      [`GET ${BASE}/jobs/job-test`]: makeJob({ status: "running", verdict: null, lifecycle_state: "DRAFT" }),
      [`GET ${BASE}/jobs/job-test/trace`]: { steps: [] },
    });
    window.location.hash = "#/jobs/job-test";
    const { unmount } = render(<App client={createApiClient({ baseUrl: BASE, fetchImpl: f })} />);
    await flush();
    expect(screen.getByTestId("job-status")).toHaveTextContent("Analysis running");
    expect(screen.getByTestId("verdict-text")).toHaveTextContent("No verdict yet");
    unmount();
  });
});

describe("Reviewer page", () => {
  it("sends approve with note and reviewer name, using the bearer token", async () => {
    const f = fakeFetch({
      [`GET ${BASE}/reviews`]: [
        { review_id: "r1", job_id: "job-test", verdict: "CONTRADICTED", reasons: ["EDIT_CANDIDATE"], created: "2026-01-01T00:00:00Z", status: "PENDING" },
      ],
      [`GET ${BASE}/jobs/job-test`]: makeJob({ verdict: "CONTRADICTED", lifecycle_state: "PENDING_REVIEW" }),
      [`POST ${BASE}/reviews/r1/decision`]: {},
    });
    window.location.hash = "#/reviewer";
    render(<App client={createApiClient({ baseUrl: BASE, fetchImpl: f })} />);
    fireEvent.change(screen.getByLabelText("Reviewer name"), { target: { value: "Rev" } });
    fireEvent.change(screen.getByLabelText("Access token"), { target: { value: "tok" } });
    fireEvent.click(screen.getByRole("button", { name: "Load review queue" }));
    await flush();
    fireEvent.click(screen.getByRole("button", { name: "Open evidence for review r1" }));
    await flush();
    expect(screen.getByTestId("pending-review")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Approve CONTRADICTED" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Write a note");

    fireEvent.change(screen.getByLabelText("Reviewer note (required)"), { target: { value: "Cut confirmed." } });
    fireEvent.click(screen.getByRole("button", { name: "Approve CONTRADICTED" }));
    await flush();
    const call = f.mock.calls.find((c) => String(c[0]).endsWith("/reviews/r1/decision"));
    expect(call).toBeDefined();
    const init = call![1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({ approve: true, note: "Cut confirmed.", reviewer: "Rev" });
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });
});
