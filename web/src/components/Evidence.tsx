import type { JobArtifacts } from "../api/types";

export function Plots({ plots }: { plots?: Record<string, string> }) {
  const entries = Object.entries(plots ?? {});
  if (entries.length === 0) return null;
  return (
    <section aria-labelledby="plots-heading">
      <h2 id="plots-heading">Evidence plots</h2>
      <div className="plots">
        {entries.map(([name, url]) => (
          <figure key={name} className="plot">
            <img src={url} alt={`Evidence plot: ${name.replace(/_/g, " ")}`} loading="lazy" />
            <figcaption>{name.replace(/_/g, " ")}</figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}

export function Downloads({ artifacts }: { artifacts: JobArtifacts }) {
  const items: { url?: string; label: string }[] = [
    { url: artifacts.report_pdf, label: "Report (PDF)" },
    { url: artifacts.report_html, label: "Report (HTML)" },
    { url: artifacts.report_json, label: "Analysis result (JSON)" },
    { url: artifacts.overlay_mp4, label: "Band overlay video (MP4)" },
  ];
  const present = items.filter((i) => i.url);
  return (
    <section aria-labelledby="downloads-heading">
      <h2 id="downloads-heading">Downloads</h2>
      {present.length === 0 ? (
        <p className="muted">No files are available yet.</p>
      ) : (
        <ul>
          {present.map((i) => (
            <li key={i.label}>
              <a href={i.url} download>
                {i.label}
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
