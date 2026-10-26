import { useId, useState, type FormEvent } from "react";
import { useApi } from "../api/context";
import type { UserRequest } from "../api/types";

function RequestForm({ jobId, req }: { jobId: string; req: UserRequest }) {
  const api = useApi();
  const inputId = useId();
  const [value, setValue] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [message, setMessage] = useState("");

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!value.trim()) {
      setState("error");
      setMessage("Type an answer first.");
      return;
    }
    setState("sending");
    try {
      await api.sendInput(jobId, req.kind, value.trim());
      setState("sent");
      setMessage("Answer sent. The agent continues the analysis.");
    } catch (err) {
      setState("error");
      setMessage(`The answer was not sent. ${err instanceof Error ? err.message : ""}`);
    }
  };

  return (
    <li className="request">
      <p>
        <strong>{req.message}</strong> <span className="muted small">({req.kind}, {req.created})</span>
      </p>
      <form onSubmit={onSubmit}>
        <label htmlFor={inputId}>Your answer</label>
        <input id={inputId} type="text" value={value} onChange={(e) => setValue(e.target.value)} disabled={state === "sent"} />
        <button type="submit" disabled={state === "sending" || state === "sent"}>
          Send answer
        </button>
      </form>
      <p role="status" className={state === "error" ? "error-text" : "muted"}>
        {message}
      </p>
    </li>
  );
}

/** Requests from the agent for more input (SPEC Part 9.3). */
export function UserRequests({ jobId, requests }: { jobId: string; requests: UserRequest[] }) {
  if (requests.length === 0) return null;
  return (
    <section aria-labelledby="requests-heading" className="tile tile-attention">
      <h2 id="requests-heading">The agent needs more information</h2>
      <ul className="plain-list">
        {requests.map((r, i) => (
          <RequestForm key={`${r.kind}-${i}`} jobId={jobId} req={r} />
        ))}
      </ul>
    </section>
  );
}
