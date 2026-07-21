"""Serve and exercise a generated game in real headless desktop Chrome."""

from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return


class StaticGameServer:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> "StaticGameServer":
        handler = lambda *args, **kwargs: _QuietHandler(*args, directory=str(self.root), **kwargs)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    @property
    def url(self) -> str:
        if self.server is None:
            raise RuntimeError("server has not started")
        return f"http://127.0.0.1:{self.server.server_port}/index.html"

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=2)


@dataclass(slots=True)
class BrowserResult:
    ok: bool
    data: dict[str, Any]

    @property
    def finished(self) -> bool:
        return bool(self.data.get("finished"))

    @property
    def errors(self) -> list[str]:
        return [
            *self.data.get("console_errors", []),
            *self.data.get("page_errors", []),
            *self.data.get("external_requests", []),
        ]

    def report(self) -> str:
        if self.ok:
            return "browser validation passed: game loaded, completed, and reset in headless Chrome"
        return "browser validation failed: " + "; ".join(self.errors or ["finish or replay signal was not observed"])


class ChromeHarness:
    def __init__(self, runner: Path | None = None, node: str = "node") -> None:
        self.runner = runner or Path(__file__).with_name("browser_runner.mjs")
        self.node = node

    def run(self, dist_dir: Path, evidence_dir: Path) -> BrowserResult:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        screenshot = evidence_dir / "game.png"
        result_file = evidence_dir / "browser-result.json"
        with StaticGameServer(dist_dir) as server:
            process = subprocess.run(
                [
                    self.node,
                    str(self.runner),
                    "--url",
                    server.url,
                    "--screenshot",
                    str(screenshot),
                    "--result",
                    str(result_file),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        output = process.stdout.strip().splitlines()
        raw = output[-1] if output else "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"ok": False, "error": process.stderr.strip() or "browser runner returned invalid JSON"}
        if process.returncode != 0:
            data.setdefault("error", process.stderr.strip() or "browser runner failed")
        return BrowserResult(ok=bool(data.get("ok")) and process.returncode == 0, data=data)
