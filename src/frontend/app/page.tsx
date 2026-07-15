"use client";

import { useEffect, useState } from "react";
import Image from "next/image";

const GROUNDING_DURATION = 10_000;
const TRACE_INTERVAL = 1_100;
const SNAKE_PATH =
  "M 0 191.294 C 133 59.529 285 59.529 437 191.294 C 589 323.059 741 323.059 893 171.529 C 1045 20 1216 20 1368 171.529 C 1520 323.059 1691 323.059 1900 158.353 L 1900 435.059 C 1710 540.471 1539 540.471 1368 408.706 C 1197 276.941 1045 276.941 893 435.059 C 741 580 589 580 437 408.706 C 285 250.588 133 250.588 0 395.529 Z";

const traces = [
  {
    id: "map-repository",
    source: "codex",
    action: "Map",
    message: "Finding the repository entry points",
  },
  {
    id: "search-framework",
    source: "exa",
    action: "Search",
    message: "Looking up framework and deployment context",
  },
  {
    id: "inspect-data-path",
    source: "codex",
    action: "Inspect",
    message: "Following the data path through the app",
  },
  {
    id: "search-dependencies",
    source: "exa",
    action: "Search",
    message: "Checking public docs for dependency context",
  },
  {
    id: "synthesize-brief",
    source: "codex",
    action: "Synthesize",
    message: "Preparing a repo brief for the voice exam",
  },
];

export default function Home() {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      const nextElapsed = Math.min(Date.now() - startedAt, GROUNDING_DURATION);
      setElapsed(nextElapsed);

      if (nextElapsed >= GROUNDING_DURATION) {
        window.clearInterval(timer);
      }
    }, 100);

    return () => window.clearInterval(timer);
  }, []);

  const progress = Math.round((elapsed / GROUNDING_DURATION) * 100);
  const isComplete = elapsed >= GROUNDING_DURATION;
  const activeTrace = isComplete
    ? traces.length - 1
    : Math.floor(elapsed / TRACE_INTERVAL) % traces.length;
  const visibleTrace = traces[activeTrace];

  return (
    <main className="grounding-page">
      <header className="site-header">
        <a
          className="wordmark"
          href="https://github.com/AdamPSU/vibe-check"
          aria-label="Open vibe-check on GitHub"
        >
          <span className="wordmark-mark" aria-hidden="true">
            /
          </span>
          vibe-check
        </a>
        <div className="nav-actions">
          <a className="nav-button nav-button-secondary" href="#trace-panel">
            Build Week
          </a>
          <a
            className="nav-button nav-button-primary"
            href="https://github.com/AdamPSU/vibe-check"
            aria-label="Open the vibe-check GitHub repository"
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.084-.729.084-.729 1.205.084 1.84 1.237 1.84 1.237 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
            </svg>
            <span>Repo</span>
            <span className="nav-button-arrow" aria-hidden="true">
              →
            </span>
          </a>
        </div>
      </header>

      <section
        className="loading-shell"
        aria-label="Grounding your repository"
        aria-busy={!isComplete}
      >
        <div className="snake-image-slot" aria-hidden="true">
          <svg
            className="snake-image-shape"
            viewBox="0 0 1900 600"
            preserveAspectRatio="xMidYMid slice"
          >
            <defs>
              <clipPath id="snake-cutout" clipPathUnits="userSpaceOnUse">
                <path d={SNAKE_PATH} />
              </clipPath>
            </defs>
            <image
              href="/loading-bg.jpeg"
              x="0"
              y="0"
              width="1900"
              height="600"
              preserveAspectRatio="xMidYMid meet"
              clipPath="url(#snake-cutout)"
            />
            <path
              className="snake-image-outline"
              d={SNAKE_PATH}
              fill="none"
            />
          </svg>
        </div>

        <div
          className={`loading-intro ${isComplete ? "is-complete" : ""}`}
          role="img"
          aria-label={isComplete ? "Repository ready" : "Grounding your repository"}
        >
          <Image
            className="loading-spinner"
            src="/spinner-mark.png"
            width="128"
            height="128"
            alt=""
            aria-hidden="true"
            unoptimized
          />
        </div>

        <section
          className="trace-panel"
          id="trace-panel"
          aria-labelledby="trace-title"
        >
          <div className="trace-panel-header">
            <div>
              <h2 id="trace-title">The search, in plain sight.</h2>
            </div>
          </div>

          <div className="trace-console" aria-live="polite">
            <div className="console-toolbar">
              <div className="console-lights" aria-hidden="true">
                <span />
                <span />
                <span />
              </div>
              <span>AdamPSU/vibe-check</span>
              <span className="console-time">{isComplete ? "done" : "live"}</span>
            </div>

            <div className="trace-list">
              {traces.map((trace, index) => (
                <div
                  className={`trace-row ${
                    index === activeTrace ? "is-active" : ""
                  } ${index < activeTrace || isComplete ? "is-finished" : ""}`}
                  key={trace.id}
                >
                  <span className="trace-marker" aria-hidden="true">
                    {index < activeTrace || isComplete ? "✓" : "·"}
                  </span>
                  <span className="trace-source">{trace.source}</span>
                  <span className="trace-action">{trace.action}</span>
                  <span className="trace-message">{trace.message}</span>
                </div>
              ))}
            </div>

            <div className="active-trace" role="status">
              <span className={`trace-spinner ${isComplete ? "is-done" : ""}`} aria-hidden="true" />
              <span>{isComplete ? "Repo brief assembled" : visibleTrace.message}</span>
            </div>
          </div>

          <div className="trace-panel-footer">
            <span>Codex SDK</span>
            <span className="footer-separator" aria-hidden="true">
              /
            </span>
            <span>Exa search</span>
            <span className="footer-separator" aria-hidden="true">
              /
            </span>
            <span>repo context</span>
          </div>
        </section>

        <div className="progress-block" aria-label={`${progress}% grounded`}>
          <div className="progress-heading">
            <span>{isComplete ? "Grounding complete" : "Grounding in progress"}</span>
            <span className="progress-value">{progress}%</span>
          </div>
          <div className="progress-track" aria-hidden="true">
            <span style={{ width: `${progress}%` }} />
          </div>
          <p className="progress-caption">
            {isComplete
              ? "Your repo brief is ready for the next step."
              : "Usually ready in under 30 seconds."}
          </p>
        </div>
      </section>
    </main>
  );
}
