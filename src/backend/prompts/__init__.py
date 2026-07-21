"""System prompts used by the daily-game generation agents."""

from importlib.resources import files


def load_system_prompt(filename: str) -> str:
    """Load a packaged system prompt as UTF-8 text."""

    return files(__name__).joinpath(filename).read_text(encoding="utf-8").strip()


MAKER_SYSTEM_PROMPT = load_system_prompt("maker_system.txt")
ADVERSARIAL_TESTER_SYSTEM_PROMPT = load_system_prompt("adversarial_tester_system.txt")

__all__ = [
    "ADVERSARIAL_TESTER_SYSTEM_PROMPT",
    "MAKER_SYSTEM_PROMPT",
    "load_system_prompt",
]
