import type { Verdict } from "../api/types";

// Each verdict has its own shape, so the card never depends on color alone.
// The icon is decorative: the verdict text next to it carries the meaning.
// Integer geometry on a 48-unit grid (SVG drawing coordinates, not measured values).
export function VerdictIcon({ verdict }: { verdict: Verdict | null }) {
  const common = {
    className: "verdict-icon",
    width: 32,
    height: 32,
    viewBox: "0 0 48 48",
    "aria-hidden": true,
    focusable: false,
    "data-testid": `verdict-icon-${verdict ?? "NONE"}`,
  } as const;
  switch (verdict) {
    case "VERIFIED":
      return (
        <svg {...common}>
          <circle cx="24" cy="24" r="20" fill="none" stroke="currentColor" strokeWidth="4" />
          <path d="M14 25l6 6 14-14" fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "CONTRADICTED":
      return (
        <svg {...common}>
          <path d="M24 5l20 36H4z" fill="none" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
          <path d="M24 18v11" stroke="currentColor" strokeWidth="5" strokeLinecap="round" />
          <circle cx="24" cy="35" r="3" fill="currentColor" />
        </svg>
      );
    case "INCONCLUSIVE":
      return (
        <svg {...common}>
          <circle cx="24" cy="24" r="20" fill="none" stroke="currentColor" strokeWidth="4" />
          <path d="M18 19a6 6 0 1 1 8 5c-2 1-2 2-2 4v1" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
          <circle cx="24" cy="35" r="3" fill="currentColor" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <circle cx="24" cy="24" r="20" fill="none" stroke="currentColor" strokeWidth="4" strokeDasharray="6 6" />
        </svg>
      );
  }
}
