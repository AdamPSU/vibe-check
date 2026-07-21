"""Maker and tester adapters for local and provider-backed sessions."""

from __future__ import annotations

import math
import os
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .browser import BrowserResult, ChromeHarness
from .prompts import ADVERSARIAL_TESTER_SYSTEM_PROMPT, MAKER_SYSTEM_PROMPT


@dataclass(slots=True)
class MakerResult:
    final_response: str
    provider: str


@dataclass(slots=True)
class TesterResult:
    report: str
    browser: BrowserResult
    provider: str


class GameMaker(Protocol):
    def generate(self, workspace: Path) -> MakerResult: ...

    def repair(self, workspace: Path, feedback: str) -> MakerResult: ...


class GameTester(Protocol):
    def inspect(self, workspace: Path, evidence_dir: Path, label: str) -> TesterResult: ...


def _write_music_loop(path: Path) -> None:
    sample_rate = 8_000
    duration = 0.35
    amplitude = 8_000
    frames = int(sample_rate * duration)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(
            b"".join(
                int(amplitude * math.sin(2 * math.pi * 220 * index / sample_rate)).to_bytes(
                    2, "little", signed=True
                )
                for index in range(frames)
            )
        )


class DemoGameMaker:
    """Deterministic local maker used by the end-to-end test and demo command."""

    def generate(self, workspace: Path) -> MakerResult:
        dist = workspace / "dist"
        dist.mkdir(parents=True, exist_ok=True)
        (dist / "index.html").write_text(
            """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Button Bloom</title>
    <link rel="stylesheet" href="style.css">
  </head>
  <body>
    <main id="game" aria-live="polite">
      <p class="eyebrow">DAILY MICROGAME</p>
      <h1>BUTTON BLOOM</h1>
      <p id="instructions">Press SPACE or click the bloom three times.</p>
      <button id="bloom" type="button">BLOOM <span id="count">0/3</span></button>
      <p id="status">The garden is waiting.</p>
      <audio id="music" preload="auto" src="music-loop.wav"></audio>
    </main>
    <script src="game.js"></script>
  </body>
</html>
""",
            encoding="utf-8",
        )
        (dist / "style.css").write_text(
            """html,body{height:100%;margin:0}body{display:grid;place-items:center;background:#111;color:#fff;font:20px system-ui,sans-serif}main{text-align:center;padding:4rem;border:2px solid #6f6;background:#1d281d}button{padding:1rem 2rem;font:inherit;background:#c8ff72;color:#102010;border:0;border-radius:999px;cursor:pointer}.eyebrow{color:#c8ff72;letter-spacing:.2em;font-size:.75rem}#status{min-height:1.5em}h1{letter-spacing:.08em}""",
            encoding="utf-8",
        )
        (dist / "game.js").write_text(
            """(() => {
  let blooms = 0;
  let finished = false;
  const button = document.querySelector('#bloom');
  const count = document.querySelector('#count');
  const status = document.querySelector('#status');
  const music = document.querySelector('#music');
  function update() {
    count.textContent = `${blooms}/3`;
    if (finished) status.textContent = 'The garden is in full bloom!';
    else status.textContent = blooms ? 'Keep going...' : 'The garden is waiting.';
  }
  function bloom() {
    if (finished) return;
    blooms += 1;
    if (music) music.play().catch(() => {});
    if (blooms >= 3) finished = true;
    update();
  }
  button.addEventListener('click', bloom);
  window.addEventListener('keydown', (event) => {
    if (event.code === 'Space') { event.preventDefault(); bloom(); }
  });
  window.__GAME_TEST__ = {
    ready: () => true,
    reset: () => { blooms = 0; finished = false; update(); },
    getState: () => ({ blooms, finished }),
    getControls: () => ({ key: 'Space' }),
    isFinished: () => finished,
  };
  update();
})();
""",
            encoding="utf-8",
        )
        _write_music_loop(dist / "music-loop.wav")
        return MakerResult(
            provider="demo",
            final_response=(
                "TITLE: Button Bloom\n"
                "DESCRIPTION: Wake a tiny garden with three quick blooms.\n\n"
                "Built and validated as a local browser game."
            ),
        )

    def repair(self, workspace: Path, feedback: str) -> MakerResult:
        return MakerResult(
            provider="demo",
            final_response=(
                "TITLE: Button Bloom\n"
                "DESCRIPTION: Wake a tiny garden with three quick blooms.\n\n"
                f"Local demo repair received tester feedback: {bool(feedback)}"
            ),
        )


class ChromeTester:
    def __init__(self, harness: ChromeHarness | None = None) -> None:
        self.harness = harness or ChromeHarness()

    def inspect(self, workspace: Path, evidence_dir: Path, label: str) -> TesterResult:
        browser = self.harness.run(workspace / "dist", evidence_dir / label)
        return TesterResult(
            provider="chrome-local",
            browser=browser,
            report=browser.report(),
        )


class CodexCliMaker:
    def __init__(self, model: str | None = None, executable: str = "codex") -> None:
        self.model = model or os.getenv("VIBE_CHECK_MAKER_MODEL", "gpt-5.6-luna")
        self.executable = executable

    def _run(self, workspace: Path, task: str, output_path: Path) -> str:
        prompt = MAKER_SYSTEM_PROMPT + "\n\nWORK ORDER:\n" + task
        command = [
            self.executable,
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "--cd",
            str(workspace),
            "--model",
            self.model,
            "--config",
            'model_reasoning_effort="xhigh"',
            "--output-last-message",
            str(output_path),
            "-",
        ]
        result = subprocess.run(command, input=prompt, text=True, capture_output=True, check=False)
        (workspace / "maker-codex-events.jsonl").write_text(result.stdout, encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Codex maker exited unsuccessfully")
        return output_path.read_text(encoding="utf-8")

    def generate(self, workspace: Path) -> MakerResult:
        response = self._run(
            workspace,
            "Build the game in this workspace. Run it locally, call the independent tester if available, and leave the final build at dist/index.html.",
            workspace / "maker-final-response.txt",
        )
        return MakerResult(final_response=response, provider=f"codex:{self.model}")

    def repair(self, workspace: Path, feedback: str) -> MakerResult:
        response = self._run(
            workspace,
            "Review this independent tester report, repair the game where appropriate, rerun validation, and leave the final build at dist/index.html.\n\nTESTER REPORT:\n" + feedback,
            workspace / "maker-repair-response.txt",
        )
        return MakerResult(final_response=response, provider=f"codex:{self.model}")


class CodexCliTester:
    def __init__(self, model: str | None = None, executable: str = "codex", harness: ChromeHarness | None = None) -> None:
        self.model = model or os.getenv("VIBE_CHECK_TESTER_MODEL", "gpt-5.6-sol")
        self.executable = executable
        self.harness = harness or ChromeHarness()

    def inspect(self, workspace: Path, evidence_dir: Path, label: str) -> TesterResult:
        browser = self.harness.run(workspace / "dist", evidence_dir / label)
        prompt = (
            ADVERSARIAL_TESTER_SYSTEM_PROMPT
            + "\n\nBROWSER EVIDENCE FROM THE HOST HARNESS:\n"
            + str(browser.data)
            + "\n\nInspect the workspace read-only, explain the evidence, and return the requested natural-language report."
        )
        report_path = evidence_dir / label / "tester-codex-report.txt"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.executable,
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--cd",
            str(workspace),
            "--model",
            self.model,
            "--config",
            'model_reasoning_effort="xhigh"',
            "--output-last-message",
            str(report_path),
            "-",
        ]
        result = subprocess.run(command, input=prompt, text=True, capture_output=True, check=False)
        (evidence_dir / label / "tester-codex-events.jsonl").write_text(result.stdout, encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Codex tester exited unsuccessfully")
        return TesterResult(
            provider=f"codex:{self.model}",
            browser=browser,
            report=report_path.read_text(encoding="utf-8"),
        )
