from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from openai import OpenAI
from datetime import datetime
import os

try:
    from InquirerPy import inquirer
except ImportError:
    inquirer = None

from .io_utils import save_as, print_status, print_agent_block


def _get_unit_display_name(unit: dict) -> str:
    """Create a display name for a knowledge unit."""
    knowledge_unit_type = unit.get("knowledge_unit_type", "unknown")
    name = unit.get("name", "unnamed")
    return f"[{knowledge_unit_type}] {name}"


def _get_knowledge_units_from_files(project_dir: Path) -> list[tuple[dict, str]]:
    """
    Extract all knowledge units from concept files.
    
    Returns a list of tuples: (knowledge_unit_dict, concept_file_name)
    """
    pattern = re.compile(r"concept(\d+)-synth\.json$")
    concept_files = []
    for file_path in project_dir.iterdir():
        if file_path.is_file() and pattern.match(file_path.name):
            concept_files.append(file_path)
    
    # Sort by concept number
    concept_files.sort(key=lambda f: int(pattern.match(f.name).group(1)))
    
    all_units = []
    for concept_file in concept_files:
        try:
            with open(concept_file, "r") as f:
                data = json.load(f)
            
            knowledge_units = data.get("knowledge_units", [])
            for unit in knowledge_units:
                all_units.append((unit, concept_file.name))
        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to parse {concept_file.name}: {e}")
        except Exception as e:
            print(f"[ERROR] Error processing {concept_file.name}: {e}")
    
    return all_units


def _select_knowledge_units_interactive(
    units: list[tuple[dict, str]]
) -> list[dict]:
    """
    Show an interactive terminal UI for selecting knowledge units.
    
    Returns a list of selected knowledge unit dictionaries.
    """
    if not inquirer:
        print("[ERROR] 'InquirerPy' library is required for interactive selection.")
        print("Install it with: pip install InquirerPy")
        return []
    
    if not units:
        print("[INFO] No knowledge units found.")
        return []
    
    # Create choices list
    choices = []
    unit_map = {}  # Map display names to units
    for unit, concept_file in units:
        display_name = _get_unit_display_name(unit)
        full_display = f"{display_name} ({concept_file})"
        choices.append(full_display)
        unit_map[full_display] = unit
    
    # Use InquirerPy to show checkbox selection with full terminal height
    try:
        selected_displays = inquirer.checkbox(
            message="Select the knowledge units to include in compose:\n\n" +
                   "SELECTION INSTRUCTIONS:\n" +
                   "  • Use ↑/↓ Arrow Keys to navigate through the list\n" +
                   "  • Press SPACE to select/deselect an item\n" +
                   "  • Press ENTER to confirm your selection\n" +
                   "  • Press Ctrl+C to cancel\n\n" +
                   "Select the knowledge units to include in compose:",
            choices=choices,
            height="100%",
        ).execute()
        
        selected_units = [
            unit_map[display]
            for display in selected_displays
            if display in unit_map
        ]
        return selected_units
    except KeyboardInterrupt:
        print("\n[INFO] Selection cancelled.")
        return []


def compose_prompt(selected_units: list[dict], model: str, project_dir: Path) -> None:
    """
    Compose a prompt using the selected knowledge units.
    
    Args:
        selected_units: List of knowledge unit dictionaries selected by the user
    """
    print(f"\n[INFO] Composing with {len(selected_units)} selected knowledge units:")
    
    client = OpenAI()

    formatted_units = json.dumps(selected_units, indent=2, ensure_ascii=False)
    prompt = f"""You are a "Knowledge-to-Prompt" specialist, an expert LLM prompt engineer with a specialization in designing autonomous agents.

Your mission is to convert a given list of structured knowledge units (provided in JSON format) into a clear, actionable, and precise "prompt snippet."

This snippet is NOT a complete system prompt (e.g., do not include instructions like "You are an agent..."). Instead, it is a set of rules, policies, and procedural instructions intended to be injected into a larger system prompt for a downstream agent to use.

## Input Format
You will receive a JSON array of "knowledge units." These are structured objects, but their types and fields will vary. They could represent policies, UI rules, API logic, or any other form of knowledge.

## Output Requirements
Format: Use clear and readable Markdown. Use headings to logically separate different knowledge units. Generate one ## heading for each knowledge unit.
Tone & Style: The generated text must be in an imperative, unambiguous, and direct command-style. It is giving direct instructions to the consumer agent.
Be precise: Your primary goal is to retain all specific details, calculations, tool names, and field names mentioned in the knowledge unit. Do not summarize or lose critical information.

## Transformation rules
Do not make up or infer any information. Only derive from the provided knowledge units.
Don’t expose internal citations/filenames (e.g., wiki.md:34) in user-visible messaging. Those are provenance for the agent only.
Respect scope. Output only the snippet; do not add “You are…”, system/meta instructions, or formatting fences.
Tone: concise, neutral, and clear; avoid legalese unless mandated by a policy.

Now, please process the following JSON list of knowledge units and generate the complete prompt snippet based on all the rules specified above.

{formatted_units}"""

    response = client.responses.create(
        model=model,
        reasoning={"effort": "low"},
        input=prompt
    )

    print("\n[INFO] Compose process completed.")
    cur_time = datetime.now().isoformat(timespec="seconds")
    save_as(response.output_text, project_dir / f"compose-{cur_time}.md")
    print(f"\n[INFO] Compose result saved to {project_dir / f'compose-{cur_time}.md'}")

    # Print token usage
    if hasattr(response, 'usage') and response.usage:
        usage = response.usage
        print(f"[INFO] Token usage: {usage}")


def build_compose_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="socratic-cli compose",
        description=(
            "Compose command."
        ),
    )
    parser.add_argument(
        "--project",
        required=True,
        help="Project name; must match a folder under projects/",
    )
    parser.add_argument(
        "--model",
        default="gpt-5",
        help="OpenAI model to use.",
    )
    return parser


def run_compose(args: argparse.Namespace) -> None:
    # Check for required OPENAI_API_KEY environment variable
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required but not defined in the environment. Currenlty only OpenAI models are supported.")

    project_dir = Path("projects") / args.project
    if not project_dir.exists() or not project_dir.is_dir():
        raise SystemExit(
            f"Project '{args.project}' not found under projects/. Please create 'projects/{args.project}' and try again."
        )
    print(f"[INFO] Compose command with project: {args.project}, model: {args.model}")
    
    # Get all knowledge units from concept files
    all_units = _get_knowledge_units_from_files(project_dir)
    
    if not all_units:
        print(f"[INFO] No knowledge units found in {project_dir}")
        return
    
    print(f"\n[INFO] Found {len(all_units)} knowledge units")
    
    # Show interactive selection interface
    selected_units = _select_knowledge_units_interactive(all_units)
    
    if not selected_units:
        print("[INFO] No units selected. Exiting.")
        return
    
    # Pass selected units to compose_prompt
    compose_prompt(selected_units, args.model, project_dir)


__all__ = [
    "build_compose_parser",
    "run_compose",
    "compose_prompt",
]

