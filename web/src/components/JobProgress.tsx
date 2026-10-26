import type { JobStatus } from "../api/types";

const STEPS: { status: JobStatus; label: string }[] = [
  { status: "created", label: "Job created" },
  { status: "uploaded", label: "Video uploaded" },
  { status: "queued", label: "Waiting in queue" },
  { status: "running", label: "Analysis running" },
  { status: "done", label: "Analysis done" },
];

export function JobProgress({ status, error }: { status: JobStatus; error?: string | null }) {
  const failed = status === "failed";
  const current = STEPS.findIndex((s) => s.status === status);
  return (
    <section aria-labelledby="progress-heading">
      <h2 id="progress-heading">Progress</h2>
      <p role="status" data-testid="job-status">
        Status: <strong>{failed ? "Failed" : STEPS[current]?.label ?? status}</strong>
      </p>
      {failed && (
        <p className="error-text" role="alert">
          The analysis failed{error ? `: ${error}` : "."} A failed analysis is not evidence that the video is fake.
        </p>
      )}
      <ol className="progress">
        {STEPS.map((s, i) => {
          const state = failed ? "todo" : i < current ? "done" : i === current ? "current" : "todo";
          return (
            <li key={s.status} className={`progress-${state}`} aria-current={state === "current" ? "step" : undefined}>
              <span aria-hidden="true" className="progress-mark">
                {state === "done" ? "✓" : state === "current" ? "▶" : "○"}
              </span>{" "}
              {s.label}
              <span className="visually-hidden">
                {state === "done" ? " (complete)" : state === "current" ? " (current)" : " (not started)"}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
