import { useEffect, useState } from "react";

// Small hash router. Hash routes work on static hosting (S3 + CloudFront) with no rewrite rules.

export type Route =
  | { name: "home" }
  | { name: "job"; jobId: string }
  | { name: "reviewer" }
  | { name: "limitations"; section?: string }
  | { name: "judge-guide" }
  | { name: "not-found"; path: string };

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#/, "") || "/";
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  if (parts.length === 0) return { name: "home" };
  if (parts[0] === "jobs" && parts.length === 2) return { name: "job", jobId: parts[1] };
  if (parts[0] === "reviewer" && parts.length === 1) return { name: "reviewer" };
  if (parts[0] === "limitations" && parts.length <= 2) return { name: "limitations", section: parts[1] };
  if (parts[0] === "judge-guide" && parts.length === 1) return { name: "judge-guide" };
  return { name: "not-found", path };
}

export const href = {
  home: () => "#/",
  job: (jobId: string) => `#/jobs/${encodeURIComponent(jobId)}`,
  reviewer: () => "#/reviewer",
  limitations: (section?: string) => (section ? `#/limitations/${section}` : "#/limitations"),
  judgeGuide: () => "#/judge-guide",
};

export function navigate(to: string): void {
  window.location.hash = to.replace(/^#/, "");
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
