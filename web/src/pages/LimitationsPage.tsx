import { useEffect } from "react";

export function LimitationsPage({ section }: { section?: string }) {
  useEffect(() => {
    if (section) {
      const el = document.getElementById(section);
      if (el) {
        el.scrollIntoView?.();
        el.focus();
      }
    }
  }, [section]);

  return (
    <>
      <h1 tabIndex={-1}>Limitations</h1>
      <p className="lead">GRIDPRINT reads one physical signal. When the signal is not in the video, GRIDPRINT cannot give a result.</p>

      <section aria-labelledby="lim-what">
        <h2 id="lim-what">What GRIDPRINT is not</h2>
        <ul>
          <li>It is not a deepfake classifier. It does not judge if pixels look AI-made.</li>
          <li>It is not a face recognition or identity system.</li>
          <li>It does not give a location. It gives only the grid zone, never a city or an address.</li>
          <li>It is not cryptographic proof.</li>
          <li>A missing signal is never evidence that a video is fake.</li>
        </ul>
      </section>

      <section aria-labelledby="lim-inconclusive">
        <h2 id="lim-inconclusive">Why many videos give INCONCLUSIVE</h2>
        <ul>
          <li>Most phone cameras use anti-banding. Anti-banding removes the light flicker that GRIDPRINT reads.</li>
          <li>Daylight, battery lights, and some LED lights do not flicker with the grid.</li>
          <li>Strong motion, strong compression, and HDR video make the signal weak or unusable.</li>
          <li>The reference log must cover the time when the video was recorded.</li>
          <li>A short video can match more than one time in the reference log.</li>
        </ul>
      </section>

      <section aria-labelledby="lim-review">
        <h2 id="lim-review">Human review</h2>
        <p>
          A CONTRADICTED result is a draft until a human reviewer approves it. If the reviewer rejects it, the report
          becomes INCONCLUSIVE. Evidence from the face region is EXPERIMENTAL and never the only reason for CONTRADICTED.
        </p>
      </section>

      <section aria-labelledby="capture-heading" id="capture" tabIndex={-1}>
        <h2 id="capture-heading">GRIDPRINT Capture</h2>
        <p>
          GRIDPRINT Capture is an Android app for recording video that GRIDPRINT can check. It turns anti-banding off and
          uses a short exposure, so the flicker bands stay in the video. It also writes a sidecar file with the sensor
          timing.
        </p>
        <p>
          Record with Capture when you expect someone to question your video later. Upload the video and its sidecar file
          on the home page.
        </p>
      </section>
    </>
  );
}
