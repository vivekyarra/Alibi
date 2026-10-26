import { useEffect, useId, useState } from "react";
import { useApi } from "../api/context";
import type { GridLive } from "../api/types";
import { LIVE_TILE_INTERVAL_MS, LIVE_ZONE_DEFAULT, ZONES } from "../config";

const W = 300;
const H = 60;

function sparkPoints(values: number[]): string {
  if (values.length < 2) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * W;
      const y = H - ((v - min) / span) * H;
      return `${x},${y}`;
    })
    .join(" ");
}

function fmtTime(tUtcS: number): string {
  return new Date(tUtcS * 1000).toISOString().replace(".000Z", "Z");
}

/** Live reference frequency for one grid zone. All values come from GET /v1/grid/{zone}/live. */
export function LiveGridTile() {
  const api = useApi();
  const selectId = useId();
  const [zone, setZone] = useState(LIVE_ZONE_DEFAULT);
  const [data, setData] = useState<GridLive | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      try {
        const d = await api.gridLive(zone);
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      } catch {
        if (!cancelled) {
          setData(null);
          setError("Live grid data is not available now.");
        }
      }
      if (!cancelled) timer = setTimeout(load, LIVE_TILE_INTERVAL_MS);
    };
    setData(null);
    void load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [api, zone]);

  const samples = data?.samples ?? [];
  const latest = samples.length ? samples[samples.length - 1] : null;
  const values = samples.map((s) => s.freq_hz);
  const min = values.length ? Math.min(...values) : null;
  const max = values.length ? Math.max(...values) : null;

  return (
    <section className="tile" aria-labelledby="live-grid-heading">
      <h2 id="live-grid-heading">Live grid frequency</h2>
      <p className="muted">The reference log that GRIDPRINT compares videos with.</p>
      <label htmlFor={selectId}>Grid zone</label>
      <select id={selectId} value={zone} onChange={(e) => setZone(e.target.value)}>
        {ZONES.map((z) => (
          <option key={z.id} value={z.id}>
            {z.id} ({z.label})
          </option>
        ))}
      </select>
      <div aria-live="polite">
        {error && <p className="error-text">{error}</p>}
        {!error && !data && <p className="muted">Loading live data.</p>}
        {data && !latest && <p className="muted">No recent samples for this zone.</p>}
        {latest && (
          <p className="big-number">
            <span data-source="api">{latest.freq_hz.toFixed(3)}</span> Hz
            <span className="muted small"> at {fmtTime(latest.t_utc_s)}</span>
          </p>
        )}
      </div>
      {values.length >= 2 && min !== null && max !== null && (
        <svg
          className="sparkline"
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={`Grid frequency in zone ${data?.zone ?? zone}, last ${values.length} samples, from ${min.toFixed(3)} Hz to ${max.toFixed(3)} Hz.`}
        >
          <polyline points={sparkPoints(values)} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />
        </svg>
      )}
    </section>
  );
}
