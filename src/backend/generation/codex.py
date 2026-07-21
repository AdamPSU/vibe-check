"""Subscription-backed Codex game maker."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Protocol

from openai_codex import ApprovalMode, Codex, CodexConfig, Sandbox

from ..prompts import (
    ADVERSARIAL_TESTER_SYSTEM_PROMPT,
    DELIVERY_CONTRACT,
    MAKER_SYSTEM_PROMPT,
)


class GameMaker(Protocol):
    def generate(self, workspace: Path) -> str: ...


def _toml(value: str) -> str:
    return json.dumps(value)


def _payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if is_dataclass(value):
        return asdict(value)
    return value


def _record_turn(turn: Any, destination: Path) -> str:
    """Persist one turn stream and return its final assistant message."""

    completed: dict[str, Any] | None = None
    final_response = ""
    stream = turn.stream()
    try:
        with destination.open("w", encoding="utf-8") as output:
            for event in stream:
                payload = _payload(event.payload)
                output.write(json.dumps({"method": event.method, "payload": payload}) + "\n")
                output.flush()
                if event.method == "item/completed":
                    item = payload.get("item", {})
                    item = item.get("root", item)
                    if item.get("type") == "agentMessage" and item.get("phase") in (
                        None,
                        "final_answer",
                    ):
                        final_response = item.get("text", "")
                elif event.method == "turn/completed":
                    completed = payload.get("turn")
    finally:
        close = getattr(stream, "close", None)
        if close:
            close()

    if not completed:
        raise RuntimeError("Codex turn completed event not received")
    if completed.get("status") != "completed":
        error = completed.get("error") or {}
        raise RuntimeError(error.get("message") or f"Codex turn {completed.get('status')}")
    return final_response


class CodexSdkMaker:
    """Run one autonomous maker thread using saved Codex authentication."""

    def __init__(self, model: str = "gpt-5.6-luna", smoke_test: bool = False) -> None:
        self.model = model
        self.smoke_test = smoke_test

    @staticmethod
    def _configure_workspace(workspace: Path) -> None:
        workspace = workspace.resolve()
        codex_dir = workspace / ".codex"
        agents_dir = codex_dir / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (workspace / "AGENTS.md").write_text(DELIVERY_CONTRACT + "\n", encoding="utf-8")

        tester_prompt = (
            ADVERSARIAL_TESTER_SYSTEM_PROMPT
            + "\n\nReturn the complete report to the parent maker. Do not spawn another agent."
        )
        (agents_dir / "adversarial_tester.toml").write_text(
            'name = "adversarial_tester"\n'
            'description = "Read-only adversarial tester for the generated game."\n'
            'model = "gpt-5.6-sol"\n'
            'model_reasoning_effort = "xhigh"\n'
            'sandbox_mode = "read-only"\n'
            f"developer_instructions = {_toml(tester_prompt)}\n",
            encoding="utf-8",
        )

        project_root = Path(__file__).resolve().parents[2]
        config = [
            "[mcp_servers.exa]\nenabled = true\n",
            "[mcp_servers.lyria]\nenabled = true\n",
            '[mcp_servers.lyria.tools.lyria_generate_music]\napproval_mode = "approve"\n',
            '[mcp_servers."chrome-devtools"]\nenabled = true\n'
            'default_tools_approval_mode = "approve"\n',
            "[mcp_servers.delivery_validator]\n"
            "enabled = true\n"
            "required = true\n"
            f"command = {_toml(sys.executable)}\n"
            'args = ["-m", "src.backend.delivery.mcp"]\n'
            f"cwd = {_toml(str(workspace))}\n"
            f"env = {{ PYTHONPATH = {_toml(str(project_root))} }}\n"
            'enabled_tools = ["validate_delivery"]\n'
            'default_tools_approval_mode = "approve"\n',
        ]
        for server in (
            "context7",
            "copycat",
            "github",
            "humanizer",
            "llmwiki",
            "node_repl",
            "computer-use",
            "firecrawl",
            "runpod",
            "runpod-docs",
            "wavespeed",
        ):
            name = _toml(server) if "-" in server else server
            config.append(f"[mcp_servers.{name}]\nenabled = false\n")
        (codex_dir / "config.toml").write_text("\n".join(config), encoding="utf-8")

    def generate(self, workspace: Path) -> str:
        self._configure_workspace(workspace)
        work_order = (
            "Build one complete daily game in this workspace. Follow AGENTS.md. Once a "
            "playable build exists, spawn `adversarial_tester` exactly once, save its report "
            "to reports/adversarial-tester.md, repair the game, retest it, and call "
            "`validate_delivery` until it succeeds before finishing."
        )
        if self.smoke_test:
            work_order += (
                " Explicitly use Exa, Chrome DevTools, and `lyria_generate_music` with "
                "model_id `lyria-3-clip-preview`; keep the generated music under dist/audio/."
            )

        agent_file = workspace.resolve() / ".codex/agents/adversarial_tester.toml"
        sdk_config = CodexConfig(
            config_overrides=(
                "agents.max_depth=1",
                "agents.adversarial_tester.description="
                + _toml("Read-only adversarial tester for the generated game."),
                "agents.adversarial_tester.config_file=" + _toml(str(agent_file)),
            )
        )
        with Codex(sdk_config) as codex:
            thread = codex.thread_start(
                approval_mode=ApprovalMode.deny_all,
                config={"model_reasoning_effort": "xhigh"},
                cwd=str(workspace.resolve()),
                developer_instructions=MAKER_SYSTEM_PROMPT,
                ephemeral=True,
                model=self.model,
                sandbox=Sandbox.workspace_write,
            )
            final_response = _record_turn(
                thread.turn(work_order), workspace / "codex-events.jsonl"
            )
        return final_response
