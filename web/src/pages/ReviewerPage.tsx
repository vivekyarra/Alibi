import { useEffect, useId, useState, type FormEvent } from "react";
import { useApi } from "../api/context";
import { ApiError } from "../api/client";
import { continuityEvents, type Job, type Review } from "../api/types";
import { Downloads, Plots } from "../components/Evidence";
import { OverlayPlayer } from "../components/OverlayPlayer";
import { VerdictCard } from "../components/VerdictCard";
import { href } from "../router";

function errText(err: unknown): string {
  if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
    return "The access token was not accepted. Check the token and try again.";
  }
  return err instanceof Error ? err.message : "Unknown error.";
}

function DecisionForm({
  review,
  token,
  reviewer,
  onDone,
}: {
  review: Review;
  token: string;
  reviewer: string;
  onDone: (msg: string) => void;
}) {
  const api = useApi();
  const noteId = useId();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const decide = async (approve: boolean) => {
    setError("");
    if (!note.trim()) {
      setError("Write a note before you approve or reject.");
      return;
    }
    setBusy(true);
    try {
      await api.decideReview(review.review_id, { approve, note: note.trim(), reviewer }, token);
      onDone(
        approve
          ? `Review ${review.review_id} approved. The report is now final with verdict CONTRADICTED.`
          : `Review ${review.review_id} rejected. The report is now final with verdict INCONCLUSIVE.`,
      );
    } catch (err) {
      setError(`The decision was not saved. ${errText(err)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(e) => e.preventDefault()} className="decision">
      <label htmlFor={noteId}>Reviewer note (required)</label>
      <textarea id={noteId} rows={4} value={note} onChange={(e) => setNote(e.target.value)} required />
      <div className="button-row">
        <button type="button" onClick={() => void decide(true)} disabled={busy}>
          Approve CONTRADICTED
        </button>
        <button type="button" className="secondary" onClick={() => void decide(false)} disabled={busy}>
          Reject (report becomes INCONCLUSIVE)
        </button>
      </div>
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
    </form>
  );
}

function EvidencePanel({ review, token, reviewer, onDone }: { review: Review; token: string; reviewer: string; onDone: (m: string) => void }) {
  const api = useApi();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setJob(null);
    setError("");
    api
      .getJob(review.job_id)
      .then((j) => !cancelled && setJob(j))
      .catch((err: unknown) => !cancelled && setError(`The evidence is not available. ${errText(err)}`));
    return () => {
      cancelled = true;
    };
  }, [api, review.job_id]);

  return (
    <section aria-labelledby="evidence-heading" className="tile">
      <h2 id="evidence-heading">
        Evidence for review <code>{review.review_id}</code>
      </h2>
      <p>
        Job: <a href={href.job(review.job_id)}>{review.job_id}</a> (opens the full job page with the agent trace)
      </p>
      <div aria-live="polite">
        {error && <p className="error-text">{error}</p>}
        {!job && !error && <p className="muted">Loading evidence.</p>}
      </div>
      {job && (
        <>
          <VerdictCard
            verdict={job.verdict}
            lifecycleState={job.lifecycle_state}
            reasons={job.reasons ?? []}
            timeEstimateIso={job.time_estimate_iso}
            timeUncertaintyS={job.time_uncertainty_s}
            zone={job.zone}
            headingLevel={3}
          />
          {job.artifacts?.overlay_mp4 && <OverlayPlayer src={job.artifacts.overlay_mp4} events={continuityEvents(job.result)} />}
          <Plots plots={job.artifacts?.plots} />
          <Downloads artifacts={job.artifacts ?? {}} />
        </>
      )}
      <h3>Decision</h3>
      <DecisionForm review={review} token={token} reviewer={reviewer} onDone={onDone} />
    </section>
  );
}

export function ReviewerPage() {
  const api = useApi();
  const ids = { name: useId(), token: useId() };
  const [reviewer, setReviewer] = useState("");
  const [token, setToken] = useState("");
  const [queue, setQueue] = useState<Review[] | null>(null);
  const [selected, setSelected] = useState<Review | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setBusy(true);
    setError("");
    try {
      setQueue(await api.listReviews(token.trim()));
    } catch (err) {
      setQueue(null);
      setError(`The review queue did not load. ${errText(err)}`);
    } finally {
      setBusy(false);
    }
  };

  const onLogin = (e: FormEvent) => {
    e.preventDefault();
    if (!reviewer.trim() || !token.trim()) {
      setError("Enter your reviewer name and access token.");
      return;
    }
    void load();
  };

  const onDone = (msg: string) => {
    setNotice(msg);
    setSelected(null);
    void load();
  };

  return (
    <>
      <h1 tabIndex={-1}>Reviewer</h1>
      <p>
        A CONTRADICTED result is not final until a human reviewer approves it. If you reject it, the report becomes
        final with verdict INCONCLUSIVE and reason <code>REVIEWER_REJECTED</code>.
      </p>
      <section className="tile" aria-labelledby="login-heading">
        <h2 id="login-heading">Sign in</h2>
        <form onSubmit={onLogin}>
          <label htmlFor={ids.name}>Reviewer name</label>
          <input id={ids.name} type="text" autoComplete="name" value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
          <label htmlFor={ids.token}>Access token</label>
          <input id={ids.token} type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} />
          <button type="submit" disabled={busy}>
            {queue ? "Reload queue" : "Load review queue"}
          </button>
        </form>
        <p className="muted small">The token stays in this page only. It is not stored.</p>
      </section>
      <div aria-live="polite">
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
        {notice && <p className="notice">{notice}</p>}
      </div>
      {queue && (
        <section aria-labelledby="queue-heading">
          <h2 id="queue-heading">Review queue</h2>
          {queue.length === 0 ? (
            <p className="muted">No reviews are waiting.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <caption className="visually-hidden">Reviews waiting for a decision</caption>
                <thead>
                  <tr>
                    <th scope="col">Review</th>
                    <th scope="col">Job</th>
                    <th scope="col">Verdict</th>
                    <th scope="col">Reasons</th>
                    <th scope="col">Created</th>
                    <th scope="col">Status</th>
                    <th scope="col">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {queue.map((r) => (
                    <tr key={r.review_id} className={selected?.review_id === r.review_id ? "row-selected" : undefined}>
                      <td>
                        <code>{r.review_id}</code>
                      </td>
                      <td>
                        <code>{r.job_id}</code>
                      </td>
                      <td>{r.verdict}</td>
                      <td>{r.reasons.join(", ")}</td>
                      <td>{r.created}</td>
                      <td>{r.status}</td>
                      <td>
                        <button type="button" onClick={() => setSelected(r)} aria-label={`Open evidence for review ${r.review_id}`}>
                          Open evidence
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
      {selected && <EvidencePanel review={selected} token={token.trim()} reviewer={reviewer.trim()} onDone={onDone} />}
    </>
  );
}
