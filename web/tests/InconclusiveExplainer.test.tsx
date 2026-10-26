import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VerdictCard } from "../src/components/VerdictCard";

function sentences(text: string): string[] {
  return text
    .split(/(?<=\.)\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

describe("INCONCLUSIVE explanation", () => {
  it("shows two plain sentences about anti-banding and a missing signal, with a Capture link", () => {
    render(<VerdictCard verdict="INCONCLUSIVE" lifecycleState="FINAL" reasons={["SIGNAL_ABSENT"]} />);
    const p = screen.getByTestId("inconclusive-sentences");
    const s = sentences(p.textContent ?? "");
    expect(s).toHaveLength(2);
    expect(s[0]).toMatch(/anti-banding/i);
    expect(s[0]).toMatch(/flicker/i);
    expect(s[1]).toMatch(/missing signal is not evidence that the video is fake/i);
    const link = screen.getByRole("link", { name: /GRIDPRINT Capture/ });
    expect(link).toHaveAttribute("href", "#/limitations/capture");
  });

  it.each(["VERIFIED", "CONTRADICTED"] as const)("is not shown for %s", (verdict) => {
    render(<VerdictCard verdict={verdict} lifecycleState="FINAL" reasons={[]} />);
    expect(screen.queryByTestId("inconclusive-sentences")).toBeNull();
  });
});
