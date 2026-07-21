"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import Image from "next/image";
import { playSfx } from "../lib/sfx";

type MenuAction = "play" | "past-games" | "about" | "settings";

const menuItems: {
  id: string;
  action: string;
  message: string;
  intent: MenuAction;
}[] = [
  {
    id: "play",
    action: "Play",
    message: "One shared game. Unlimited replay.",
    intent: "play",
  },
  {
    id: "past-games",
    action: "Past Games",
    message: "Browse every published daily release.",
    intent: "past-games",
  },
  {
    id: "about",
    action: "About",
    message: "Game of the Day — autonomous short games for everyone.",
    intent: "about",
  },
  {
    id: "settings",
    action: "Settings",
    message: "Sound, motion, and display preferences.",
    intent: "settings",
  },
];

const LAST_INDEX = menuItems.length - 1;
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const REPO_URL = "https://github.com/AdamPSU/vibe-check";
const TRANSITION_FALLBACK_MS = 12_000;
const MUSIC_VOLUME = 0.45;
const MUSIC_FADE_MS = 2800;

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

function nyDateString(date = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export default function Home() {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [musicVolume, setMusicVolume] = useState(MUSIC_VOLUME);
  const [brightness, setBrightness] = useState(1);
  const [logoPhase, setLogoPhase] = useState<"intro" | "idle">("intro");
  const selectedIndexRef = useRef(selectedIndex);
  const musicVolumeRef = useRef(musicVolume);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const musicRef = useRef<HTMLAudioElement | null>(null);
  const musicStartedRef = useRef(false);
  const fadeFrameRef = useRef<number | null>(null);
  const transitioningRef = useRef(false);

  useEffect(() => {
    if (prefersReducedMotion()) {
      setLogoPhase("idle");
      return;
    }
    const fallback = window.setTimeout(() => {
      setLogoPhase("idle");
    }, 1600);
    return () => window.clearTimeout(fallback);
  }, []);

  useEffect(() => {
    selectedIndexRef.current = selectedIndex;
  }, [selectedIndex]);

  useEffect(() => {
    musicVolumeRef.current = musicVolume;
    const music = musicRef.current;
    if (!music || fadeFrameRef.current != null) return;
    music.volume = musicVolume;
    music.muted = musicVolume <= 0;
  }, [musicVolume]);

  const ensureMusic = useCallback(async () => {
    const music = musicRef.current;
    if (!music) return;

    music.loop = true;
    music.volume = musicVolumeRef.current;
    music.muted = musicVolumeRef.current <= 0;

    if (musicStartedRef.current) {
      if (music.paused && musicVolumeRef.current > 0) {
        try {
          await music.play();
        } catch {
          // Ignore blocked resume.
        }
      }
      return;
    }

    try {
      await music.play();
      musicStartedRef.current = true;
    } catch {
      // Autoplay blocked until a later gesture.
    }
  }, []);

  const setMusicLevel = useCallback(
    (next: number) => {
      const clamped = Math.min(1, Math.max(0, next));
      setMusicVolume(clamped);
      void ensureMusic();
    },
    [ensureMusic],
  );

  const fadeOutMusic = useCallback(() => {
    const music = musicRef.current;
    if (!music) return;

    if (fadeFrameRef.current != null) {
      window.cancelAnimationFrame(fadeFrameRef.current);
    }

    const startVolume = music.volume;
    const startedAt = performance.now();

    const tick = (now: number) => {
      const progress = Math.min(1, (now - startedAt) / MUSIC_FADE_MS);
      music.volume = startVolume * (1 - progress);

      if (progress < 1) {
        fadeFrameRef.current = window.requestAnimationFrame(tick);
        return;
      }

      music.pause();
      music.currentTime = 0;
      music.volume = 0;
      fadeFrameRef.current = null;
    };

    fadeFrameRef.current = window.requestAnimationFrame(tick);
  }, []);

  useEffect(() => {
    const unlock = () => {
      void ensureMusic();
    };

    window.addEventListener("pointerdown", unlock, { once: true });
    window.addEventListener("keydown", unlock, { once: true });

    return () => {
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
      if (fadeFrameRef.current != null) {
        window.cancelAnimationFrame(fadeFrameRef.current);
      }
    };
  }, [ensureMusic]);

  const selectIndex = useCallback(
    (index: number, withSound = true) => {
      if (transitioningRef.current) return;
      void ensureMusic();
      setSelectedIndex((current) => {
        const next = wrapIndex(index);
        if (withSound && next !== current) {
          playSfx("move");
        }
        return next;
      });
    },
    [ensureMusic],
  );

  const moveSelection = useCallback(
    (delta: number) => {
      selectIndex(selectedIndexRef.current + delta);
    },
    [selectIndex],
  );

  const goToGame = useCallback(() => {
    window.location.href = `/games/${nyDateString()}`;
  }, []);

  const startPlayTransition = useCallback(async () => {
    if (transitioningRef.current) return;
    transitioningRef.current = true;
    playSfx("click");
    fadeOutMusic();

    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    document.documentElement.classList.add("is-play-transition");
    document.body.classList.add("is-play-transition");
    setIsTransitioning(true);

    if (prefersReducedMotion()) {
      goToGame();
      return;
    }

    const video = videoRef.current;
    if (!video) {
      goToGame();
      return;
    }

    const finish = () => {
      video.removeEventListener("ended", finish);
      window.clearTimeout(fallbackTimer);
      goToGame();
    };

    const fallbackTimer = window.setTimeout(finish, TRANSITION_FALLBACK_MS);

    video.loop = false;
    video.muted = true;
    video.playsInline = true;
    video.classList.add("is-playing");

    try {
      video.pause();
      video.currentTime = 0;
      video.addEventListener("ended", finish, { once: true });
      await video.play();
    } catch {
      finish();
    }
  }, [fadeOutMusic, goToGame]);

  const activateItem = useCallback(
    (intent: MenuAction) => {
      if (transitioningRef.current) return;

      if (intent === "play") {
        setSettingsOpen(false);
        void startPlayTransition();
        return;
      }

      playSfx("click");
      void ensureMusic();

      if (intent === "past-games") {
        setSettingsOpen(false);
        document.getElementById("daily-catalog")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
        return;
      }

      if (intent === "settings") {
        setSettingsOpen((open) => !open);
        return;
      }

      if (intent === "about") {
        setSettingsOpen(false);
      }
    },
    [ensureMusic, startPlayTransition],
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (transitioningRef.current) {
        event.preventDefault();
        return;
      }

      if (event.metaKey || event.ctrlKey || event.altKey) return;

      const key = event.key.toLowerCase();

      if (key === "escape" && settingsOpen) {
        event.preventDefault();
        setSettingsOpen(false);
        return;
      }

      if (settingsOpen) {
        if (key === "arrowleft" || key === "a") {
          event.preventDefault();
          setMusicLevel(musicVolumeRef.current - 0.05);
          return;
        }
        if (key === "arrowright" || key === "d") {
          event.preventDefault();
          setMusicLevel(musicVolumeRef.current + 0.05);
          return;
        }
        return;
      }

      const isUp = key === "w" || key === "arrowup" || key === "a";
      const isDown = key === "s" || key === "arrowdown" || key === "d";
      const isConfirm = key === "enter" || key === " ";

      if (isConfirm) {
        event.preventDefault();
        activateItem(menuItems[selectedIndexRef.current].intent);
        return;
      }

      if (!isUp && !isDown) return;

      event.preventDefault();
      moveSelection(isUp ? -1 : 1);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activateItem, moveSelection, setMusicLevel, settingsOpen]);

  useEffect(() => {
    return () => {
      document.documentElement.classList.remove("is-play-transition");
      document.body.classList.remove("is-play-transition");
    };
  }, []);

  const selectedItem = menuItems[selectedIndex];

  return (
    <main
      className={`grounding-page${isTransitioning ? " is-transitioning" : ""}`}
      style={{ ["--page-brightness" as string]: String(brightness) }}
      aria-busy={isTransitioning}
    >
      <div className="hero-stage">
        <audio
          ref={musicRef}
          className="landing-theme"
          src="/landing-theme.mp3"
          loop
          preload="auto"
          aria-hidden="true"
        />
        <video
          ref={videoRef}
          className="hero-video"
          muted
          playsInline
          preload="auto"
          poster="/menu-wallpaper.png"
          aria-hidden="true"
        >
          <source src="/menu-transition.mp4" type="video/mp4" />
        </video>

        <header className="site-header">
          <div className="nav-ticker" aria-hidden="true">
            <p className="nav-ticker-track">
              MADE FOR THE OPENAI BUILD WEEK. GOTD: A SELF-GENERATING DAILY
              GAME, BROUGHT TO YOU BY CODEX.
            </p>
          </div>
          <div className="nav-actions">
            <a
              className="nav-button nav-button-secondary"
              href="#daily-catalog"
              onClick={() => playSfx("click")}
            >
              Past Games
            </a>
            <a
              className="nav-button nav-button-primary"
              href={REPO_URL}
              aria-label="Open the vibe-check GitHub repository"
              onClick={(event) => {
                event.preventDefault();
                if (transitioningRef.current) return;
                playSfx("click");
                window.setTimeout(() => {
                  window.open(REPO_URL, "_blank", "noopener,noreferrer");
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
            <div className="menu-logo-wrap">
              <Image
                className={`menu-logo is-${logoPhase}`}
                src="/gotd-logo.png"
                alt="GotD"
                width={2122}
                height={741}
                priority
                unoptimized
                onAnimationEnd={(event) => {
                  if (
                    event.target === event.currentTarget &&
                    event.animationName === "menu-logo-intro"
                  ) {
                    setLogoPhase("idle");
                  }
                }}
              />
            </div>
            {settingsOpen ? (
              <>
                <div className="settings-view" aria-label="Settings">
                  <label className="settings-row" htmlFor="music-volume">
                    <span className="settings-label">
                      Sound {Math.round(musicVolume * 100)}%
                    </span>
                    <input
                      id="music-volume"
                      className="settings-slider"
                      type="range"
                      min={0}
                      max={100}
                      step={1}
                      value={Math.round(musicVolume * 100)}
                      autoFocus
                      onChange={(event) => {
                        setMusicLevel(Number(event.target.value) / 100);
                      }}
                      onPointerDown={() => {
                        void ensureMusic();
                      }}
                    />
                  </label>
                  <label className="settings-row" htmlFor="brightness">
                    <span className="settings-label">
                      Brightness {Math.round(brightness * 100)}%
                    </span>
                    <input
                      id="brightness"
                      className="settings-slider"
                      type="range"
                      min={40}
                      max={140}
                      step={1}
                      value={Math.round(brightness * 100)}
                      onChange={(event) => {
                        setBrightness(Number(event.target.value) / 100);
                      }}
                    />
                  </label>
                  <button
                    type="button"
                    className="settings-back"
                    onClick={() => {
                      playSfx("click");
                      setSettingsOpen(false);
                    }}
                  >
                    Back
                  </button>
                </div>
                <p className="menu-status" role="status">
                  Esc to return.
                </p>
              </>
            ) : (
              <>
                <ul
                  className="menu-list"
                  role="listbox"
                  tabIndex={0}
                  aria-activedescendant={selectedItem.id}
                  aria-orientation="vertical"
                >
                  {menuItems.map((item, index) => {
                    const isActive = index === selectedIndex;

                    return (
                      <li
                        className={`menu-item ${isActive ? "is-active" : ""}`}
                        id={item.id}
                        key={item.id}
                        role="option"
                        aria-selected={isActive}
                        onMouseEnter={() => selectIndex(index)}
                        onFocus={() => selectIndex(index)}
                        onClick={() => {
                          selectIndex(index, false);
                          activateItem(item.intent);
                        }}
                      >
                        <span className="menu-cursor" aria-hidden="true">
                          {isActive ? ">" : ""}
                        </span>
                        <span className="menu-label">{item.action}</span>
                      </li>
                    );
                  })}
                </ul>

                <p className="menu-status" role="status">
                  {selectedItem.message}
                </p>
              </>
            )}
          </nav>
        </section>

        <div className="section-curve" aria-hidden="true">
          <svg
            className="section-curve-svg"
            viewBox="0 0 1440 160"
            preserveAspectRatio="none"
            shapeRendering="crispEdges"
          >
            <path d="M0,0H90V6H156V12H192V18H222V24H252V30H276V36H294V42H318V48H336V54H354V60H372V66H390V72H408V78H426V84H450V90H474V96H510V102H624V96H666V90H696V84H720V78H744V72H774V66H810V60H948V66H978V72H1002V78H1020V84H1044V90H1062V96H1074V102H1098V108H1110V114H1134V120H1152V126H1176V132H1200V138H1230V144H1260V150H1308V156H1386V160H1440V160H0Z" />
          </svg>
        </div>
      </div>

      <DailyCatalog />
    </main>
  );
}

type CatalogCard = {
  id: string;
  release_date: string;
  title: string;
  href: string | null;
  image: string | null;
};

const MOCK_CATALOG: CatalogCard[] = [
  {
    id: "mock-1",
    release_date: "2026-07-19",
    title: "Neon Drift",
    href: null,
    image:
      "https://images.unsplash.com/photo-1518495973542-4542c06a5843?q=80&w=800&auto=format&fit=crop",
  },
  {
    id: "mock-2",
    release_date: "2026-07-18",
    title: "Forest Circuit",
    href: null,
    image:
      "https://images.unsplash.com/photo-1472396961693-142e6e269027?q=80&w=800&auto=format&fit=crop",
  },
  {
    id: "mock-3",
    release_date: "2026-07-17",
    title: "Tide Breaker",
    href: null,
    image:
      "https://images.unsplash.com/photo-1505142468610-359e7d316be0?q=80&w=800&auto=format&fit=crop",
  },
  {
    id: "mock-4",
    release_date: "2026-07-16",
    title: "Sandglass Run",
    href: null,
    image:
      "https://images.unsplash.com/photo-1482881497185-d4a9ddbe4151?q=80&w=800&auto=format&fit=crop",
  },
  {
    id: "mock-5",
    release_date: "2026-07-15",
    title: "Signal Peak",
    href: null,
    image:
      "https://images.unsplash.com/photo-1524799526615-766a9833dec0?q=80&w=800&auto=format&fit=crop",
  },
  {
    id: "mock-6",
    release_date: "2026-07-14",
    title: "Midnight Loop",
    href: null,
    image:
      "https://plus.unsplash.com/premium_photo-1673264933212-d78737f38e48?q=80&w=800&auto=format&fit=crop",
  },
  {
    id: "mock-7",
    release_date: "2026-07-13",
    title: "Orbit Hop",
    href: null,
    image:
      "https://plus.unsplash.com/premium_photo-1711434824963-ca894373272e?q=80&w=800&auto=format&fit=crop",
  },
  {
    id: "mock-8",
    release_date: "2026-07-12",
    title: "Crystal Vault",
    href: null,
    image:
      "https://plus.unsplash.com/premium_photo-1675705721263-0bbeec261c49?q=80&w=800&auto=format&fit=crop",
  },
];

function buildCatalogTrack(cards: CatalogCard[]) {
  if (cards.length === 0) return [];
  const minHalf = 8;
  let half = [...cards];
  while (half.length < minHalf) {
    half = [...half, ...cards];
  }
  return [...half, ...half];
}

function toCatalogCards(games: Game[]): CatalogCard[] {
  return games.map((game) => ({
    id: game.id,
    release_date: game.release_date,
    title: game.title,
    href: `/games/${game.release_date}`,
    image: game.screenshot_object_key
      ? `${API_BASE}/objects/${game.screenshot_object_key}`
      : null,
  }));
}

const CATALOG_STARS = Array.from({ length: 28 }, (_, index) => {
  const seed = index * 97;
  const top = ((seed * 13) % 1000) / 10;
  const left = ((seed * 29) % 1000) / 10;
  const size = 1 + ((seed * 7) % 3);
  const duration = 7 + ((seed * 11) % 90) / 10;
  const delay = -((seed * 17) % 120) / 10;
  const driftX = 40 + ((seed * 3) % 120);
  const driftY = -30 + ((seed * 5) % 60);
  return { id: index, top, left, size, duration, delay, driftX, driftY };
});

function DailyCatalog() {
  const [cards, setCards] = useState<CatalogCard[]>(MOCK_CATALOG);
  const [usingMock, setUsingMock] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/catalog`)
      .then((response) => {
        if (!response.ok) throw new Error("catalog unavailable");
        return response.json() as Promise<Game[]>;
      })
      .then((items) => {
        if (cancelled || items.length === 0) return;
        setCards(toCatalogCards(items));
        setUsingMock(false);
      })
      .catch(() => {
        /* keep mock gallery when API is down or empty */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const track = buildCatalogTrack(cards);

  return (
    <section
      className="daily-catalog"
      id="daily-catalog"
      aria-label="Past games"
    >
      <div className="catalog-stars" aria-hidden="true">
        {CATALOG_STARS.map((star) => (
          <span
            key={star.id}
            className="catalog-star"
            style={
              {
                top: `${star.top}%`,
                left: `${star.left}%`,
                width: `${star.size}px`,
                height: `${star.size}px`,
                "--star-duration": `${star.duration}s`,
                "--star-delay": `${star.delay}s`,
                "--star-dx": `${star.driftX}px`,
                "--star-dy": `${star.driftY}px`,
              } as CSSProperties
            }
          />
        ))}
      </div>
      <div
        className="catalog-slider"
        aria-label={usingMock ? "Past games preview gallery" : "Past games gallery"}
      >
        <div className="catalog-slider-mask">
          <div className="catalog-slider-track">
            {track.map((card, index) => {
              const body = (
                <>
                  {card.image ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={card.image}
                      alt={`${card.title} screenshot`}
                      loading="lazy"
                    />
                  ) : (
                    <span className="catalog-slider-placeholder">
                      SCREENSHOT PENDING
                    </span>
                  )}
                  <span className="catalog-slider-meta">
                    <span className="catalog-slider-date">{card.release_date}</span>
                    <strong>{card.title}</strong>
                  </span>
                </>
              );

              if (card.href) {
                return (
                  <a
                    className="catalog-slider-item"
                    href={card.href}
                    key={`${card.id}-${index}`}
                  >
                    {body}
                  </a>
                );
              }

              return (
                <div
                  className="catalog-slider-item is-static"
                  key={`${card.id}-${index}`}
                >
                  {body}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
