import { useEffect, useId, useState, type FormEvent } from "react";
import { useApi } from "../api/context";
import type { Claim, DemoCase } from "../api/types";
import type { SubmitStep } from "../api/client";
import { LiveGridTile } from "../components/LiveGridTile";
import { ZONES } from "../config";
import { href, navigate } from "../router";

const STEP_TEXT: Record<SubmitStep, string> = {
  create: "Creating the job.",
  upload: "Uploading the video.",
  start: "Starting the analysis.",
};

/** datetime-local value (read as UTC) to ISO 8601 UTC. */
export function utcInputToIso(v: string): string | undefined {
  if (!v) return undefined;
  const withSeconds = v.length === 16 ? `${v}:00` : v;
  const d = new Date(`${withSeconds}Z`);
  return Number.isNaN(d.getTime()) ? undefined : d.toISOString();
}

function UploadForm() {
  const api = useApi();
  const ids = { file: useId(), zone: useId(), time: useId(), tol: useId(), sidecar: useId(), help: useId() };
  const [file, setFile] = useState<File | null>(null);
  const [sidecarFile, setSidecarFile] = useState<File | null>(null);
  const [zone, setZone] = useState("");
  const [time, setTime] = useState("");
  const [tolerance, setTolerance] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (!file) {
      setError("Choose a video file first.");
      return;
    }
    const claim: Claim = {};
    if (zone) claim.claimed_zone = zone;
    if (time) {
      const iso = utcInputToIso(time);
      if (!iso) {
        setError("The claimed time is not valid.");
        return;
      }
      claim.claimed_time_utc = iso;
    }
    if (tolerance) {
      const t = Number(tolerance);
      if (!Number.isFinite(t) || t < 0) {
        setError("The time tolerance must be zero or more seconds.");
        return;
      }
      claim.claimed_time_tolerance_s = t;
    }
    let sidecar: Record<string, unknown> | undefined;
    if (sidecarFile) {
      try {
        const parsed: unknown = JSON.parse(await sidecarFile.text());
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("not an object");
        sidecar = parsed as Record<string, unknown>;
      } catch {
        setError("The sidecar file is not valid JSON.");
        return;
      }
    }
    setBusy(true);
    try {
      const jobId = await api.submitVideo(file, claim, sidecar, (s) => setStatus(STEP_TEXT[s]));
      setStatus("Analysis started.");
      navigate(href.job(jobId));
    } catch (err) {
      setStatus("");
      setError(`The video was not submitted. ${err instanceof Error ? err.message : ""}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="tile" aria-labelledby="upload-heading">
      <h2 id="upload-heading">Check a video</h2>
      <form onSubmit={onSubmit} noValidate>
        <label htmlFor={ids.file}>Video file (MP4 or MOV)</label>
        <input
          id={ids.file}
          type="file"
          accept="video/mp4,video/quicktime,.mp4,.mov"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          aria-describedby={ids.help}
        />
        <p id={ids.help} className="muted small">
          Videos from GRIDPRINT Capture give the best results. Many ordinary phone videos give INCONCLUSIVE.
        </p>
        <fieldset>
          <legend>Claim (optional)</legend>
          <label htmlFor={ids.zone}>Claimed grid zone</label>
          <select id={ids.zone} value={zone} onChange={(e) => setZone(e.target.value)}>
            <option value="">No claim</option>
            {ZONES.map((z) => (
              <option key={z.id} value={z.id}>
                {z.id} ({z.label})
              </option>
            ))}
          </select>
          <label htmlFor={ids.time}>Claimed recording time (UTC)</label>
          <input id={ids.time} type="datetime-local" step={1} value={time} onChange={(e) => setTime(e.target.value)} />
          <label htmlFor={ids.tol}>Claimed time tolerance (seconds)</label>
          <input id={ids.tol} type="number" min={0} inputMode="decimal" value={tolerance} onChange={(e) => setTolerance(e.target.value)} />
        </fieldset>
        <label htmlFor={ids.sidecar}>Capture sidecar file (optional, JSON)</label>
        <input id={ids.sidecar} type="file" accept="application/json,.json" onChange={(e) => setSidecarFile(e.target.files?.[0] ?? null)} />
        <button type="submit" disabled={busy}>
          Upload and check
        </button>
        <p role="status" className="muted">
          {status}
        </p>
        {error && (
          <p role="alert" className="error-text">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}

function DemoCases() {
  const api = useApi();
  const [cases, setCases] = useState<DemoCase[] | null>(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listDemoCases()
      .then((c) => !cancelled && setCases(c))
      .catch(() => !cancelled && setError("The demo cases are not available now."));
    return () => {
      cancelled = true;
    };
  }, [api]);

  const run = async (c: DemoCase) => {
    setRunning(c.id);
    setError("");
    try {
      const { job_id } = await api.runDemoCase(c.id);
      navigate(href.job(job_id));
    } catch (err) {
      setError(`The demo case did not start. ${err instanceof Error ? err.message : ""}`);
    } finally {
      setRunning(null);
    }
  };

  return (
    <section className="tile" aria-labelledby="demo-heading">
      <h2 id="demo-heading">Demo cases</h2>
      <p className="muted">Each demo case runs through the real analysis pipeline.</p>
      <div aria-live="polite">
        {error && <p className="error-text">{error}</p>}
        {!cases && !error && <p className="muted">Loading demo cases.</p>}
        {cases && cases.length === 0 && <p className="muted">No demo cases are available.</p>}
      </div>
      {cases && cases.length > 0 && (
        <ul className="plain-list demo-list">
          {cases.map((c) => (
            <li key={c.id} className="demo-case">
              <h3 className="small-heading">{c.title}</h3>
              <p>{c.description}</p>
              <p className="muted small">Expected verdict: {c.expected_verdict}</p>
              <button type="button" onClick={() => void run(c)} disabled={running !== null} aria-label={`Run demo case: ${c.title}`}>
                {running === c.id ? "Starting" : "Run"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function HomePage() {
  return (
    <>
      <h1 tabIndex={-1}>Check if a video is real from the light in the room</h1>
      <p className="lead">
        Indoor lights flicker with the power grid. GRIDPRINT reads this flicker from the video and compares it with a
        log of the real grid. It can tell when the video was recorded and if parts were cut or inserted.
      </p>
      <p>
        GRIDPRINT is not a deepfake classifier and is not cryptographic proof. A missing signal is never evidence that a
        video is fake. <a href={href.limitations()}>Read the limitations</a>.
      </p>
      <div className="grid">
        <UploadForm />
        <LiveGridTile />
      </div>
      <DemoCases />
    </>
  );
}
