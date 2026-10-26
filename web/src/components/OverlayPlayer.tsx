import { useRef, useState } from "react";
import type { ContinuityEvent } from "../api/types";

function markerLabel(e: ContinuityEvent): string {
  if (e.kind === "EDIT_CANDIDATE") return e.significant ? "Possible edit" : "Small signal break";
  if (e.kind === "DROPPED_FRAMES_EXPLAINED") return "Dropped frames (explained by timestamps)";
  return e.kind;
}

function markerClass(e: ContinuityEvent): string {
  return e.kind === "EDIT_CANDIDATE" && e.significant ? "marker marker-edit" : "marker marker-info";
}

/** Band overlay video with timeline markers from the continuity events. */
export function OverlayPlayer({ src, events }: { src: string; events: ContinuityEvent[] }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [duration, setDuration] = useState<number | null>(null);

  const seek = (t: number) => {
    const v = videoRef.current;
    if (v) {
      v.currentTime = t;
      v.focus();
    }
  };

  return (
    <section aria-labelledby="overlay-heading">
      <h2 id="overlay-heading">Band overlay</h2>
      <p className="muted">The overlay shows the flicker bands that the engine measured. It is a visual aid only.</p>
      <video
        ref={videoRef}
        className="overlay-video"
        src={src}
        controls
        preload="metadata"
        aria-label="Band overlay video"
        onLoadedMetadata={(e) => {
          const d = e.currentTarget.duration;
          setDuration(Number.isFinite(d) && d > 0 ? d : null);
        }}
      />
      {events.length > 0 && (
        <>
          {duration !== null && (
            <div className="timeline" role="group" aria-label="Timeline markers">
              {events.map((e, i) => (
                <button
                  key={`bar-${i}`}
                  type="button"
                  className={markerClass(e)}
                  style={{ left: `${Math.min(100, (e.t_s / duration) * 100)}%` }}
                  aria-label={`${markerLabel(e)} at ${e.t_s} s. Jump to this time.`}
                  title={`${markerLabel(e)} at ${e.t_s} s`}
                  onClick={() => seek(e.t_s)}
                >
                  <span aria-hidden="true">{e.kind === "EDIT_CANDIDATE" ? "!" : "i"}</span>
                </button>
              ))}
            </div>
          )}
          <h3 className="small-heading">Timeline events</h3>
          <ul className="event-list">
            {events.map((e, i) => (
              <li key={`list-${i}`}>
                <button type="button" className="link-button" onClick={() => seek(e.t_s)}>
                  {markerLabel(e)} at <span data-source="api">{e.t_s}</span> s
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
