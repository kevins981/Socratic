from pathlib import Path
import json
import shutil
import textwrap
from typing import List

import yaml


def extract_agent_message_from_output(collected_output: List[str]) -> str:
    """
    Extract the agent's message text from Codex output lines.
    
    Searches backwards through the output to find a line containing an item
    with type "agent_message" and a text field.
    
    Args:
        collected_output: List of raw JSON lines from Codex output
        
    Returns:
        The agent's message text
        
    Raises:
        ValueError: If no agent message is found in the output
    """
    for line in reversed(collected_output):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        
        item = payload.get("item")
        if not isinstance(item, dict):
            continue
        
        text = item.get("text")
        if isinstance(text, str):
            return text
    
    raise ValueError("No agent message found in Codex output. Could not find a line with item.text field.")


def load_project_config(project_name: str) -> dict:
    """
    Load project configuration from projects/{project_name}/project.yaml.
    
    Args:
        project_name: Name of the project
        
    Returns:
        Dictionary containing project metadata including input_dir
        
    Raises:
        SystemExit: If project directory or project.yaml doesn't exist
    """
    project_dir = Path("projects") / project_name
    if not project_dir.exists() or not project_dir.is_dir():
        raise SystemExit(
            f"Project '{project_name}' not found under projects/. "
            f"Please create 'projects/{project_name}' and try again."
        )
    
    config_path = project_dir / "project.yaml"
    if not config_path.exists():
        raise SystemExit(
            f"project.yaml not found in {project_dir}. "
            "The project may be corrupted."
        )
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        if not isinstance(config, dict):
            raise SystemExit(f"Invalid project.yaml format in {project_dir}")
        return config
    except yaml.YAMLError as e:
        raise SystemExit(f"Failed to parse project.yaml in {project_dir}: {e}")


def save_as(content: str, path: Path | str) -> None:
    target_path = Path(path)
    playbooks_dir = target_path.parent

    if not playbooks_dir.exists():
        playbooks_dir.mkdir(parents=True, exist_ok=True)

    target_path.write_text(content, encoding="utf-8")


# ------- Simple terminal UI helpers (no external deps) -------

# ANSI styles
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

# Colors
FG_YELLOW = "\033[33m"
FG_CYAN = "\033[36m"
FG_GREEN = "\033[32m"
FG_GREY = "\033[90m"


def _term_width(default: int = 80) -> int:
    try:
        return shutil.get_terminal_size((default, 20)).columns
    except Exception:
        return default


def _wrap_text(text: str, width: int) -> list[str]:
    wrapped: list[str] = []
    for paragraph in text.splitlines() or [""]:
        if not paragraph.strip():
            wrapped.append("")
            continue
        wrapped.extend(
            textwrap.fill(
                paragraph,
                width=width,
                replace_whitespace=False,
                break_long_words=False,
            ).splitlines()
        )
    return wrapped


def print_status(message: str) -> None:
    """Show a lightweight status line indicating agent work."""
    print(f"{FG_YELLOW}[WORKING]{RESET} {message}")


def print_agent_block(text: str, title: str = "Agent") -> None:
    """Render agent output in a simple boxed block for clarity."""
    term_w = max(40, min(_term_width(), 100))
    content_w = term_w - 4  # padding for borders
    lines = _wrap_text(text.strip(), content_w)
    title_str = f" {title} "
    top_border = "+" + "-" * (term_w - 2) + "+"
    title_line = "|" + (title_str.ljust(term_w - 2)) + "|"
    print(FG_CYAN + top_border + RESET)
    print(FG_CYAN + title_line + RESET)
    print(FG_CYAN + ("|" + " " * (term_w - 2) + "|") + RESET)
    for line in lines:
        padded = line.ljust(content_w)
        print(FG_CYAN + "| " + RESET + padded + FG_CYAN + " |" + RESET)
    print(FG_CYAN + top_border + RESET)


def prompt_input(prompt: str) -> str:
    """Prompt clearly when it's the user's turn to type."""
    label = f"{FG_GREEN}[YOUR TURN]{RESET} {prompt}"
    print(label)
    return input("› ").strip()

