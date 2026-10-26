// Automated axe-core check of every page (SPEC 10.2). Any violation fails the run.
import { act, fireEvent, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it } from "vitest";
import { App } from "../../src/App";
import { createApiClient } from "../../src/api/client";
import type { Verdict, LifecycleState } from "../../src/api/types";
import { fakeFetch, makeJob, makeTrace } from "../fakeFetch";

const BASE = "http://api.test/v1";

function client(job = makeJob()) {
  return createApiClient({
    baseUrl: BASE,
    fetchImpl: fakeFetch({
      [`GET ${BASE}/demo-cases`]: [
        { id: "d1", title: "Test case one", description: "Test description.", expected_verdict: "VERIFIED" },
      ],
      [`GET ${BASE}/grid/GB/live`]: {
        zone: "GB",
        samples: [
          { t_utc_s: 1, freq_hz: 50 },
          { t_utc_s: 2, freq_hz: 50 },
        ],
      },
      [`GET ${BASE}/jobs/job-test`]: job,
      [`GET ${BASE}/jobs/job-test/trace`]: makeTrace(),
      [`GET ${BASE}/reviews`]: [
        { review_id: "r1", job_id: "job-test", verdict: "CONTRADICTED", reasons: ["EDIT_CANDIDATE"], created: "2026-01-01T00:00:00Z", status: "PENDING" },
      ],
    }),
  });
}

async function axeViolations(): Promise<string[]> {
  const results = await axe.run(document.body, { resultTypes: ["violations"] });
  return results.violations.map(
    (v) => `${v.id} (${v.impact}): ${v.help}\n  ${v.nodes.map((n) => n.target.join(" ")).join("\n  ")}`,
  );
}

async function renderAt(hash: string, c = client()) {
  window.location.hash = hash;
  render(<App client={c} />);
  // Let fetches resolve.
  await act(async () => {
    await new Promise((r) => setTimeout(r, 30));
  });
}

describe("axe-core accessibility check", () => {
  it("harness self-check: axe reports a known violation", async () => {
    render(
      <main>
        <h1>Self-check</h1>
        <img src="/x.png" />
      </main>,
    );
    const v = await axeViolations();
    expect(v.some((s) => s.startsWith("image-alt"))).toBe(true);
  });

  it.each([
    ["Home", "#/"],
    ["Limitations", "#/limitations"],
    ["Limitations, Capture section", "#/limitations/capture"],
    ["Judge guide", "#/judge-guide"],
    ["Reviewer (signed out)", "#/reviewer"],
    ["Not found", "#/nope/nope/nope"],
  ])("%s page has no violations", async (_name, hash) => {
    await renderAt(hash);
    expect(await axeViolations()).toEqual([]);
  });

  const jobCases: [Verdict, LifecycleState][] = [
    ["VERIFIED", "FINAL"],
    ["CONTRADICTED", "PENDING_REVIEW"],
    ["INCONCLUSIVE", "FINAL"],
  ];
  it.each(jobCases)("Job page with %s / %s has no violations", async (verdict, lifecycle_state) => {
    await renderAt(
      "#/jobs/job-test",
      client(
        makeJob({
          verdict,
          lifecycle_state,
          user_requests: [{ kind: "camera_model", message: "Which camera recorded this video?", created: "2026-01-01T00:00:00Z" }],
        }),
      ),
    );
    expect(screen.getByTestId("verdict-text")).toHaveTextContent(verdict);
    expect(await axeViolations()).toEqual([]);
  });

  it("Job page while running has no violations", async () => {
    await renderAt("#/jobs/job-test", client(makeJob({ status: "done", verdict: null, lifecycle_state: "DRAFT" })));
    expect(await axeViolations()).toEqual([]);
  });

  it("Reviewer page with queue and evidence has no violations", async () => {
    await renderAt("#/reviewer");
    fireEvent.change(screen.getByLabelText("Reviewer name"), { target: { value: "Test Reviewer" } });
    fireEvent.change(screen.getByLabelText("Access token"), { target: { value: "test-token" } });
    fireEvent.click(screen.getByRole("button", { name: "Load review queue" }));
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30));
    });
    fireEvent.click(screen.getByRole("button", { name: "Open evidence for review r1" }));
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30));
    });
    expect(screen.getByRole("button", { name: "Approve CONTRADICTED" })).toBeInTheDocument();
    expect(await axeViolations()).toEqual([]);
  });
});
