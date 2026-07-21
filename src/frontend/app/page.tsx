"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { playSfx } from "../lib/sfx";

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

const LAST_INDEX = traces.length - 1;
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Game = {
  id: string;
  release_date: string;
  title: string;
  description: string;
  screenshot_object_key: string | null;
};

function wrapIndex(index: number) {
  if (index < 0) return LAST_INDEX;
  if (index > LAST_INDEX) return 0;
  return index;
}

export default function Home() {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const selectedIndexRef = useRef(selectedIndex);

  useEffect(() => {
    selectedIndexRef.current = selectedIndex;
  }, [selectedIndex]);

  const selectIndex = useCallback((index: number, withSound = true) => {
    setSelectedIndex((current) => {
      const next = wrapIndex(index);
      if (withSound && next !== current) {
        playSfx("move");
      }
      return next;
    });
  }, []);

  const moveSelection = useCallback(
    (delta: number) => {
      selectIndex(selectedIndexRef.current + delta);
    },
    [selectIndex],
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;

      const key = event.key.toLowerCase();
      const isUp = key === "w" || key === "arrowup" || key === "a";
      const isDown = key === "s" || key === "arrowdown" || key === "d";

      if (!isUp && !isDown) return;

      event.preventDefault();
      moveSelection(isUp ? -1 : 1);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [moveSelection]);

  const selectedTrace = traces[selectedIndex];

  return (
    <main className="grounding-page">
      <header className="site-header">
        <div className="nav-actions">
          <a
            className="nav-button nav-button-secondary"
            href="#menu-panel"
            onClick={() => playSfx("click")}
          >
            Build Week
          </a>
          <a
            className="nav-button nav-button-primary"
            href="https://github.com/AdamPSU/vibe-check"
            aria-label="Open the vibe-check GitHub repository"
            onClick={(event) => {
              event.preventDefault();
              playSfx("click");
              window.setTimeout(() => {
                window.open("https://github.com/AdamPSU/vibe-check", "_blank", "noopener,noreferrer");
              }, 90);
            }}
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

      <section className="loading-shell" aria-label="Menu">
        <nav className="menu-panel" id="menu-panel" aria-label="Main menu">
          <Image
            className="menu-logo"
            src="/gotd-logo.png"
            alt="GotD"
            width={2122}
            height={741}
            priority
            unoptimized
          />
          <ul
            className="menu-list"
            role="listbox"
            tabIndex={0}
            aria-activedescendant={selectedTrace.id}
            aria-orientation="vertical"
          >
            {traces.map((trace, index) => {
              const isActive = index === selectedIndex;

              return (
                <li
                  className={`menu-item ${isActive ? "is-active" : ""}`}
                  id={trace.id}
                  key={trace.id}
                  role="option"
                  aria-selected={isActive}
                  onMouseEnter={() => selectIndex(index)}
                  onFocus={() => selectIndex(index)}
                  onClick={() => {
                    selectIndex(index, false);
                    playSfx("click");
                  }}
                >
                  <span className="menu-cursor" aria-hidden="true">
                    {isActive ? ">" : ""}
                  </span>
                  <span className="menu-label">{trace.action}</span>
                </li>
              );
            })}
          </ul>

          <p className="menu-status" role="status">
            {selectedTrace.message}
          </p>
        </nav>
      </section>

      <DailyCatalog />
    </main>
  );
}

function DailyCatalog() {
  const [games, setGames] = useState<Game[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    fetch(`${API_BASE}/catalog`)
      .then((response) => {
        if (!response.ok) throw new Error("catalog unavailable");
        return response.json() as Promise<Game[]>;
      })
      .then((items) => {
        setGames(items);
        setState("ready");
      })
      .catch(() => setState("error"));
  }, []);

  return (
    <section className="daily-catalog" aria-labelledby="daily-catalog-title">
      <div className="daily-catalog-heading">
        <p className="daily-catalog-kicker">THE DAILY ARCADE</p>
        <h1 id="daily-catalog-title">PAST GAMES</h1>
        <p>One shared game every day. Unlimited replay.</p>
      </div>

      {state === "loading" && <p className="daily-catalog-message">LOADING CATALOG...</p>}
      {state === "error" && (
        <p className="daily-catalog-message">CATALOG UNAVAILABLE.</p>
      )}
      {state === "ready" && games.length === 0 && (
        <p className="daily-catalog-message">NO PUBLISHED GAMES YET.</p>
      )}

      <div className="daily-catalog-grid">
        {games.map((game, index) => {
          const screenshot = game.screenshot_object_key
            ? `${API_BASE}/objects/${game.screenshot_object_key}`
            : null;
          return (
            <a className="daily-game-card" href={`/games/${game.release_date}`} key={game.id}>
              {screenshot ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={screenshot} alt={`${game.title} screenshot`} />
              ) : (
                <span className="daily-game-card-placeholder">SCREENSHOT PENDING</span>
              )}
              <span className="daily-game-card-date">
                {index === 0 ? "TODAY / " : ""}{game.release_date}
              </span>
              <strong>{game.title}</strong>
              <span>{game.description}</span>
            </a>
          );
        })}
      </div>
    </section>
  );
}
