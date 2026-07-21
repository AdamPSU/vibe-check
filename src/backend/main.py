import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from .data.catalog import LocalCatalogStore, PostgresCatalogStore
from .data.objects import LocalObjectStore

app = FastAPI(title="Vibe Check API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
DATA_DIR = Path(os.getenv("VIBE_CHECK_DATA_DIR", "var/daily-games"))
DATABASE_URL = os.getenv("VIBE_CHECK_DATABASE_URL")
catalog = PostgresCatalogStore(DATABASE_URL) if DATABASE_URL else LocalCatalogStore(DATA_DIR / "catalog.json")
objects = LocalObjectStore(DATA_DIR / "objects")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/catalog")
async def get_catalog() -> list[dict[str, object]]:
    return catalog.list_games()


@app.get("/games/{release_date}")
async def get_game(release_date: str) -> dict[str, object]:
    game = catalog.get_game(release_date)
    if game is None:
        raise HTTPException(status_code=404, detail="game not found")
    return game


@app.get("/generation/status")
async def get_generation_status() -> list[dict[str, object]]:
    return catalog.list_sessions()


@app.get("/objects/{key:path}")
async def get_object(key: str) -> FileResponse:
    try:
        path = objects.path_for(key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid object key") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="object not found")
    return FileResponse(path)
