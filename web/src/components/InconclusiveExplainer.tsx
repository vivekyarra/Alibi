import { href } from "../router";

// SPEC Part 1.7 and Part 10.2: explain anti-banding in two plain sentences and link to Capture.
export function InconclusiveExplainer() {
  return (
    <aside className="explainer" aria-labelledby="inconclusive-why">
      <h3 id="inconclusive-why">Why is the result inconclusive?</h3>
      <p data-testid="inconclusive-sentences">
        Most phone cameras use anti-banding, which hides the light flicker that GRIDPRINT reads. A missing
        signal is not evidence that the video is fake.
      </p>
      <p>
        <a href={href.limitations("capture")}>Learn about GRIDPRINT Capture</a>, the app that records video
        with the flicker kept.
      </p>
    </aside>
  );
}
