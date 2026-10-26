import { useEffect, useRef, useState } from "react";
import { ApiProvider } from "./api/context";
import type { ApiClient } from "./api/client";
import { HomePage } from "./pages/HomePage";
import { JobPage } from "./pages/JobPage";
import { JudgeGuidePage } from "./pages/JudgeGuidePage";
import { LimitationsPage } from "./pages/LimitationsPage";
import { ReviewerPage } from "./pages/ReviewerPage";
import { href, useRoute, type Route } from "./router";
import { effectiveTheme, saveTheme, type Theme } from "./theme";

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => effectiveTheme());
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      className="theme-toggle secondary"
      onClick={() => {
        saveTheme(next);
        setTheme(next);
      }}
    >
      {next === "dark" ? "Use dark theme" : "Use light theme"}
    </button>
  );
}

const NAV: { label: string; to: string; match: Route["name"][] }[] = [
  { label: "Home", to: href.home(), match: ["home", "job"] },
  { label: "Reviewer", to: href.reviewer(), match: ["reviewer"] },
  { label: "Limitations", to: href.limitations(), match: ["limitations"] },
  { label: "Judge guide", to: href.judgeGuide(), match: ["judge-guide"] },
];

function Page({ route }: { route: Route }) {
  switch (route.name) {
    case "home":
      return <HomePage />;
    case "job":
      return <JobPage key={route.jobId} jobId={route.jobId} />;
    case "reviewer":
      return <ReviewerPage />;
    case "limitations":
      return <LimitationsPage section={route.section} />;
    case "judge-guide":
      return <JudgeGuidePage />;
    default:
      return (
        <>
          <h1 tabIndex={-1}>Page not found</h1>
          <p>
            This page does not exist. Go to the <a href={href.home()}>home page</a>.
          </p>
        </>
      );
  }
}

const TITLES: Record<Route["name"], string> = {
  home: "Home",
  job: "Job",
  reviewer: "Reviewer",
  limitations: "Limitations",
  "judge-guide": "Judge guide",
  "not-found": "Page not found",
};

export function App({ client }: { client?: ApiClient }) {
  const route = useRoute();
  const mainRef = useRef<HTMLElement>(null);
  const first = useRef(true);

  useEffect(() => {
    document.title = `${TITLES[route.name]} - GRIDPRINT Verify`;
    if (first.current) {
      first.current = false;
      return;
    }
    // Move focus to the page heading after navigation, for keyboard and screen-reader users.
    const h1 = mainRef.current?.querySelector("h1");
    if (h1 instanceof HTMLElement && !(route.name === "limitations" && route.section)) h1.focus();
  }, [route]);

  return (
    <ApiProvider client={client}>
      <a className="skip-link" href="#main" onClick={(e) => {
        e.preventDefault();
        mainRef.current?.focus();
      }}>
        Skip to main content
      </a>
      <header className="site-header">
        <div className="container header-row">
          <a className="brand" href={href.home()}>
            GRIDPRINT <span>Verify</span>
          </a>
          <nav aria-label="Main">
            <ul>
              {NAV.map((n) => (
                <li key={n.to}>
                  <a href={n.to} aria-current={n.match.includes(route.name) ? "page" : undefined}>
                    {n.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <ThemeToggle />
        </div>
      </header>
      <main id="main" ref={mainRef} tabIndex={-1} className="container">
        <Page route={route} />
      </main>
      <footer className="site-footer">
        <div className="container">
          <p>
            GRIDPRINT reads the power-grid frequency from light flicker. It is not cryptographic proof. A missing signal
            is never evidence that a video is fake.
          </p>
        </div>
      </footer>
    </ApiProvider>
  );
}
