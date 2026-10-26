import type { TraceStep } from "../api/types";

function fmtT(t: string | number): string {
  if (typeof t === "number") return new Date(t * 1000).toISOString();
  return t;
}

/** Live agent trace (R10). Each step shows planner, tool, inputs, outputs and the decision reason. */
export function AgentTrace({ steps, running }: { steps: TraceStep[]; running: boolean }) {
  return (
    <section aria-labelledby="trace-heading">
      <h2 id="trace-heading">Agent trace</h2>
      <p className="muted" aria-live="polite">
        {steps.length === 0
          ? running
            ? "Waiting for the first agent step."
            : "No agent steps were recorded."
          : `${steps.length} ${steps.length === 1 ? "step" : "steps"}${running ? " so far" : ""}.`}
      </p>
      {steps.length > 0 && (
        <ol className="trace">
          {steps.map((s) => (
            <li key={s.index} className="trace-step">
              <h3 className="small-heading">
                Step {s.index}: <code>{s.tool}</code>
              </h3>
              <dl className="facts">
                <dt>Planner</dt>
                <dd>
                  {s.planner === "bedrock" ? "Bedrock model" : "Fallback (deterministic rules)"}
                  {s.model_id ? <> (<code>{s.model_id}</code>)</> : null}
                </dd>
                <dt>Input</dt>
                <dd>{s.input_summary}</dd>
                <dt>Output</dt>
                <dd>{s.output_summary}</dd>
                <dt>Decision reason</dt>
                <dd>{s.decision_reason}</dd>
                <dt>Time</dt>
                <dd>
                  {fmtT(s.t_start)} to {fmtT(s.t_end)} (<span data-source="api">{s.duration_s}</span> s)
                </dd>
              </dl>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
