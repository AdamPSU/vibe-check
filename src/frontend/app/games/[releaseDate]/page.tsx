import Link from "next/link";

type Game = {
  release_date: string;
  title: string;
  description: string;
  build_object_key: string;
};

const API_BASE = process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function loadGame(releaseDate: string): Promise<Game | null> {
  try {
    const response = await fetch(`${API_BASE}/games/${encodeURIComponent(releaseDate)}`, {
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as Game;
  } catch {
    return null;
  }
}

export default async function GamePage({
  params,
}: {
  params: Promise<{ releaseDate: string }>;
}) {
  const { releaseDate } = await params;
  const game = await loadGame(releaseDate);

  if (!game) {
    return (
      <main className="game-page game-page-empty">
        <p className="catalog-kicker">{releaseDate}</p>
        <h1>GAME NOT AVAILABLE</h1>
        <p>This release has not been published.</p>
        <Link className="play-button" href="/">
          BACK TO CATALOG
        </Link>
      </main>
    );
  }

  const source = `${API_BASE}/objects/${game.build_object_key}/index.html`;
  return (
    <main className="game-page">
      <header className="game-page-header">
        <Link className="back-link" href="/">
          ← CATALOG
        </Link>
        <div>
          <p className="catalog-kicker">{game.release_date}</p>
          <h1>{game.title}</h1>
          <p>{game.description}</p>
        </div>
      </header>
      <section className="game-frame-shell" aria-label={`${game.title} game`}>
        <iframe className="game-frame" src={source} title={game.title} allow="autoplay" />
      </section>
    </main>
  );
}
