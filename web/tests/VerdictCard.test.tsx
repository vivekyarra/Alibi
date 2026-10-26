import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VerdictCard } from "../src/components/VerdictCard";
import { VERDICTS } from "../src/api/types";

describe("VerdictCard", () => {
  it.each(VERDICTS)("shows text and an icon for %s", (verdict) => {
    render(<VerdictCard verdict={verdict} lifecycleState="FINAL" reasons={[]} />);
    expect(screen.getByTestId("verdict-text")).toHaveTextContent(verdict);
    const icon = screen.getByTestId(`verdict-icon-${verdict}`);
    expect(icon.tagName.toLowerCase()).toBe("svg");
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });

  it("uses a different icon shape for each verdict", () => {
    const shapes = VERDICTS.map((v) => {
      const { container, unmount } = render(<VerdictCard verdict={v} lifecycleState="FINAL" reasons={[]} />);
      const html = container.querySelector("svg")?.innerHTML ?? "";
      unmount();
      return html;
    });
    expect(new Set(shapes).size).toBe(VERDICTS.length);
  });

  it("marks a CONTRADICTED report in PENDING_REVIEW as pending human review, not final", () => {
    render(<VerdictCard verdict="CONTRADICTED" lifecycleState="PENDING_REVIEW" reasons={["EDIT_CANDIDATE"]} />);
    expect(screen.getByTestId("pending-review")).toHaveTextContent("Pending human review");
    expect(screen.getByTestId("lifecycle-label")).toHaveTextContent("Pending human review");
    expect(screen.getByTestId("lifecycle-label")).not.toHaveTextContent("Final");
    expect(screen.getByRole("heading", { name: "Draft verdict" })).toBeInTheDocument();
  });

  it("never shows a non-final CONTRADICTED report as final, even in DRAFT", () => {
    render(<VerdictCard verdict="CONTRADICTED" lifecycleState="DRAFT" reasons={[]} />);
    expect(screen.getByTestId("pending-review")).toBeInTheDocument();
    expect(screen.getByTestId("lifecycle-label")).not.toHaveTextContent("Final");
  });

  it("shows an approved CONTRADICTED report as final without the pending label", () => {
    render(<VerdictCard verdict="CONTRADICTED" lifecycleState="FINAL" reasons={["REVIEWER_APPROVED"]} />);
    expect(screen.queryByTestId("pending-review")).toBeNull();
    expect(screen.getByTestId("lifecycle-label")).toHaveTextContent("Final");
  });

  it("does not show the pending label for VERIFIED", () => {
    render(<VerdictCard verdict="VERIFIED" lifecycleState="FINAL" reasons={["MATCH_OK"]} />);
    expect(screen.queryByTestId("pending-review")).toBeNull();
    expect(screen.getByText(/No significant edit evidence was found/)).toBeInTheDocument();
  });

  it("shows the time estimate and zone from props", () => {
    render(
      <VerdictCard
        verdict="VERIFIED"
        lifecycleState="FINAL"
        reasons={[]}
        timeEstimateIso="2026-01-01T00:00:00Z"
        timeUncertaintyS={2}
        zone="SIM50"
      />,
    );
    expect(screen.getByText(/2026-01-01T00:00:00Z/)).toBeInTheDocument();
    expect(screen.getByText("SIM50")).toBeInTheDocument();
  });

  it("shows a neutral state when there is no verdict yet", () => {
    render(<VerdictCard verdict={null} lifecycleState={null} reasons={[]} />);
    expect(screen.getByTestId("verdict-text")).toHaveTextContent("No verdict yet");
  });
});
