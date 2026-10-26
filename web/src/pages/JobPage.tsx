import { useCallback, useEffect, useState } from "react";
import { useApi } from "../api/context";
import { ApiError } from "../api/client";
import { continuityEvents, isTerminalStatus, type Job, type TraceStep } from "../api/types";
import { AgentTrace } from "../components/AgentTrace";
import { Downloads, Plots } from "../components/Evidence";
import { JobProgress } from "../components/JobProgress";
import { OverlayPlayer } from "../components/OverlayPlayer";
import { UserRequests } from "../components/UserRequests";
import { VerdictCard } from "../components/VerdictCard";
import { POLL_INTERVAL_MS } from "../config";

export function JobPage({ jobId }: { jobId: string }) {
  const api = useApi();
  const [job, setJob] = useState<Job | null>(null);
  const [steps, setSteps] = useState<TraceStep[]>([]);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      let terminal = false;
      try {
        const j = await api.getJob(jobId);
        if (cancelled) return;
        setJob(j);
        setError("");
        terminal = isTerminalStatus(j.status);
        try {
          const t = await api.getTrace(jobId);
          if (!cancelled) setSteps(t.steps ?? []);
        } catch {
          // The trace can be empty before the agent starts. Keep the last known steps.
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setError("This job does not exist.");
          return;
        }
        setError(`The job status is not available now. ${err instanceof Error ? err.message : ""} Trying again.`);
      }
      if (!cancelled && !terminal) timer = setTimeout(tick, POLL_INTERVAL_MS);
    };
    void tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [api, jobId, refreshKey]);

  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);
  const running = job ? !isTerminalStatus(job.status) : true;
  const events = continuityEvents(job?.result);

  return (
    <>
      <h1 tabIndex={-1}>
        Job <code>{jobId}</code>
      </h1>
      <div aria-live="polite">
        {error && <p className="error-text">{error}</p>}
        {!job && !error && <p className="muted">Loading the job.</p>}
      </div>
      {job && (
        <>
          <div className="grid">
            <JobProgress status={job.status} error={job.error} />
            <VerdictCard
              verdict={job.status === "done" ? job.verdict : null}
              lifecycleState={job.lifecycle_state}
              reasons={job.reasons ?? []}
              timeEstimateIso={job.time_estimate_iso}
              timeUncertaintyS={job.time_uncertainty_s}
              zone={job.zone}
            />
          </div>
          {!running && (
            <p>
              <button type="button" onClick={refresh}>
                Refresh status
              </button>
            </p>
          )}
          <UserRequests jobId={job.job_id} requests={job.user_requests ?? []} />
          {job.artifacts?.overlay_mp4 && <OverlayPlayer src={job.artifacts.overlay_mp4} events={events} />}
          <Plots plots={job.artifacts?.plots} />
          <AgentTrace steps={steps} running={running} />
          <Downloads artifacts={job.artifacts ?? {}} />
        </>
      )}
    </>
  );
}
