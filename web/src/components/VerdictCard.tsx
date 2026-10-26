import type { LifecycleState, Verdict } from "../api/types";
import { LIFECYCLE_LABEL, VERDICT_MEANING } from "../text";
import { InconclusiveExplainer } from "./InconclusiveExplainer";
import { ReasonList } from "./ReasonList";
import { VerdictIcon } from "./VerdictIcon";

export interface VerdictCardProps {
  verdict: Verdict | null;
  lifecycleState: LifecycleState | null;
  reasons: string[];
  timeEstimateIso?: string | null;
  timeUncertaintyS?: number | null;
  zone?: string | null;
  headingLevel?: 2 | 3;
}

/**
 * Verdict card. Always text + icon (never color alone).
 * A CONTRADICTED verdict that is not FINAL is always marked "Pending human review" (R3).
 */
export function VerdictCard({
  verdict,
  lifecycleState,
  reasons,
  timeEstimateIso,
  timeUncertaintyS,
  zone,
  headingLevel = 2,
}: VerdictCardProps) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  const isFinal = lifecycleState === "FINAL";
  const pendingReview =
    lifecycleState === "PENDING_REVIEW" || (verdict === "CONTRADICTED" && !isFinal);
  const stateLabel = pendingReview
    ? LIFECYCLE_LABEL.PENDING_REVIEW
    : lifecycleState
      ? LIFECYCLE_LABEL[lifecycleState]
      : "Not available";

  return (
    <section
      className={`verdict-card verdict-${(verdict ?? "none").toLowerCase()}`}
      aria-labelledby="verdict-card-heading"
      data-testid="verdict-card"
    >
      <Heading id="verdict-card-heading" className="verdict-heading">
        {pendingReview ? "Draft verdict" : "Verdict"}
      </Heading>
      <p className="verdict-line">
        <VerdictIcon verdict={verdict} />
        <span className="verdict-text" data-testid="verdict-text">
          {verdict ?? "No verdict yet"}
        </span>
      </p>
      {pendingReview && (
        <p className="pending-review" data-testid="pending-review">
          <strong>Pending human review.</strong> This result is not final. A human reviewer must approve it first.
        </p>
      )}
      <p className="lifecycle">
        Report state: <strong data-testid="lifecycle-label">{stateLabel}</strong>
      </p>
      {verdict && <p>{VERDICT_MEANING[verdict]}</p>}
      {(timeEstimateIso || zone) && (
        <dl className="facts">
          {timeEstimateIso && (
            <>
              <dt>Estimated recording time (UTC)</dt>
              <dd data-source="api">
                {timeEstimateIso}
                {timeUncertaintyS !== null && timeUncertaintyS !== undefined && (
                  <> (uncertainty plus or minus {timeUncertaintyS} s)</>
                )}
              </dd>
            </>
          )}
          {zone && (
            <>
              <dt>Grid zone</dt>
              <dd data-source="api">{zone}</dd>
            </>
          )}
        </dl>
      )}
      {reasons.length > 0 && <ReasonList reasons={reasons} />}
      {verdict === "INCONCLUSIVE" && <InconclusiveExplainer />}
    </section>
  );
}
