import { DOCS_BASE_URL } from "../config";
import { href } from "../router";

const DOCS: { path: string; label: string }[] = [
  { path: "docs/JUDGE_GUIDE.md", label: "Judge guide (full version)" },
  { path: "README.md", label: "README: quick start, deploy, test, evaluation" },
  { path: "docs/TECHNICAL_REPORT.md", label: "Technical report" },
  { path: "docs/RESPONSIBLE_USE.md", label: "Responsible use" },
];

function DocLink({ path, label }: { path: string; label: string }) {
  if (DOCS_BASE_URL) {
    return (
      <a href={`${DOCS_BASE_URL}/${path}`}>
        {label} (<code>{path}</code>)
      </a>
    );
  }
  return (
    <span>
      {label}: <code>{path}</code> in the repository
    </span>
  );
}

export function JudgeGuidePage() {
  return (
    <>
      <h1 tabIndex={-1}>Judge guide</h1>
      <p className="lead">This page tells you how to try GRIDPRINT Verify. The full guide is in the repository.</p>
      <section aria-labelledby="jg-steps">
        <h2 id="jg-steps">Steps</h2>
        <ol>
          <li>
            On the <a href={href.home()}>home page</a>, run a demo case. Each demo case runs through the real pipeline.
          </li>
          <li>Watch the agent trace on the job page. It shows each tool call and the reason for it.</li>
          <li>Open the verdict, the band overlay, the plots, and the report downloads.</li>
          <li>
            Open the <a href={href.reviewer()}>reviewer page</a> to approve or reject a CONTRADICTED result. The reviewer
            login is in the submission form, not in the repository.
          </li>
          <li>Upload your own video if you want.</li>
        </ol>
      </section>
      <section aria-labelledby="jg-phone">
        <h2 id="jg-phone">Ordinary phone videos</h2>
        <p>
          Most phone cameras use anti-banding, which hides the light flicker. So an ordinary phone video often gives
          INCONCLUSIVE. This is expected, and it is not evidence that the video is fake.{" "}
          <a href={href.limitations("capture")}>Read about GRIDPRINT Capture</a>.
        </p>
      </section>
      <section aria-labelledby="jg-docs">
        <h2 id="jg-docs">Documents</h2>
        <ul>
          {DOCS.map((d) => (
            <li key={d.path}>
              <DocLink {...d} />
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
