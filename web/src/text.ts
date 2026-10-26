// Plain-language text for verdicts, lifecycle states and reason codes (SPEC 1.5, 8.1).
import type { LifecycleState, Verdict } from "./api/types";

export const VERDICT_MEANING: Record<Verdict, string> = {
  VERIFIED:
    "A grid signal is present. It matches the reference log at one time. No significant edit evidence was found.",
  CONTRADICTED:
    "A grid signal is present, but it conflicts with the claim, shows an unexplained break, or different parts match different times.",
  INCONCLUSIVE: "GRIDPRINT cannot give a result for this video. This is not evidence that the video is fake.",
};

export const LIFECYCLE_LABEL: Record<LifecycleState, string> = {
  DRAFT: "Draft",
  PENDING_REVIEW: "Pending human review",
  FINAL: "Final",
};

export const REASON_TEXT: Record<string, string> = {
  SIGNAL_ABSENT: "No grid flicker signal was found in the video.",
  SIGNAL_WEAK: "The grid flicker signal is weak.",
  READOUT_FROM_SIDECAR: "Sensor readout timing came from the Capture sidecar file.",
  READOUT_FROM_PROFILE: "Sensor readout timing came from a known camera profile.",
  READOUT_ESTIMATED: "Sensor readout timing was estimated from the video.",
  READOUT_UNKNOWN: "Sensor readout timing is not known.",
  HDR_UNSUPPORTED: "The video uses HDR. This version does not support HDR video.",
  TRANSFER_ASSUMED: "The video does not state its color transfer. A standard transfer was assumed.",
  TRACK_TOO_SHORT: "The frequency track is too short for a reliable match.",
  NO_REFERENCE_COVERAGE: "The reference log does not cover the possible recording time.",
  NO_UNIQUE_MATCH: "The track does not match exactly one time in the reference log.",
  MATCH_OK: "The track matches the reference log at one time.",
  CLAIM_TIME_MISMATCH: "The matched time does not agree with the claimed time.",
  CLAIM_TIME_MATCH: "The matched time agrees with the claimed time.",
  EDIT_CANDIDATE: "The signal has a break that frame timestamps do not explain. This can show a cut.",
  SEGMENT_OFFSET_INCONSISTENT: "Different parts of the video match different reference times.",
  DROPPED_FRAMES_EXPLAINED: "Frame timestamps explain a break in the signal (dropped frames).",
  HIGH_MOTION: "The video has much motion. This lowers signal quality.",
  HIGH_COMPRESSION: "The video has strong compression. This lowers signal quality.",
  TIMESTAMP_JITTER_HIGH: "Frame timestamps are irregular.",
  AXIS_AMBIGUOUS: "The rolling-shutter direction is not clear.",
  FACE_REGION_ANOMALY_EXPERIMENTAL:
    "EXPERIMENTAL: the light on a face region differs from the background. This alone never gives a CONTRADICTED verdict.",
  REVIEWER_APPROVED: "A human reviewer approved this result.",
  REVIEWER_REJECTED: "A human reviewer rejected the CONTRADICTED result.",
  USER_INPUT_REQUESTED: "The analysis needs more information from you.",
  BUDGET_EXHAUSTED: "The analysis stopped because it used all of its step budget.",
};

export function reasonText(code: string): string | undefined {
  return REASON_TEXT[code];
}
