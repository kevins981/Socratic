from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import BuiltinMethodType
from typing import Any
from openai import OpenAI
from datetime import datetime
import os

try:
    from InquirerPy import inquirer
except ImportError:
    inquirer = None

from .io_utils import save_as, print_status, print_agent_block
from .llm_config import load_llm_config


def _get_unit_display_name(unit: dict) -> str:
    """Create a display name for a knowledge unit."""
    knowledge_unit_type = unit.get("heading", "unknown")
    body = unit.get("body", "unnamed")
    return f"[{knowledge_unit_type}]"


def _get_knowledge_units_from_files(project_dir: Path) -> list[tuple[dict, str]]:
    """
    Extract all knowledge units from synth-consolidated.json file.
    
    Returns a list of tuples: (knowledge_unit_dict, concept_file_name)
    """
    consolidated_file = project_dir / "synth-consolidated.json"
    
    if not consolidated_file.exists():
        print(f"[ERROR] File not found: {consolidated_file}")
        return []
    
    all_units = []
    try:
        with open(consolidated_file, "r") as f:
            data = json.load(f)
        
        knowledge_units = data.get("knowledge_units", [])
        for unit in knowledge_units:
            all_units.append((unit, consolidated_file.name))
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse {consolidated_file.name}: {e}")
    except Exception as e:
        print(f"[ERROR] Error processing {consolidated_file.name}: {e}")
    
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
        full_display = f"{display_name}"
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


def _load_kbs_json(project_dir: Path) -> dict:
    """
    Load existing socratic_kbs.json from project directory.
    
    Returns an empty dict if file doesn't exist.
    """
    kbs_file = project_dir / "socratic_kbs.json"
    if not kbs_file.exists():
        return {}
    
    try:
        with open(kbs_file, "r") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"[WARNING] Failed to parse {kbs_file}: {e}. Starting with empty dict.")
        return {}
    except Exception as e:
        print(f"[WARNING] Error reading {kbs_file}: {e}. Starting with empty dict.")
        return {}


def _save_kbs_json(project_dir: Path, data: dict) -> None:
    """
    Save data to socratic_kbs.json in project directory.
    """
    kbs_file = project_dir / "socratic_kbs.json"
    try:
        with open(kbs_file, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ERROR] Failed to save {kbs_file}: {e}")
        raise


def _check_name_exists(project_dir: Path, name: str) -> bool:
    """
    Check if the given name already exists in socratic_kbs.json.
    """
    kbs_data = _load_kbs_json(project_dir)
    return name in kbs_data


def _generate_python_file(project_dir: Path, kbs_data: dict) -> None:
    """
    Generate socratic_kbs.py from the knowledge base JSON data.
    
    Backs up existing file to socratic_kbs.py.old if it exists.
    """
    py_file = project_dir / "socratic_kbs.py"
    py_old_file = project_dir / "socratic_kbs.py.old"
    
    # Backup existing file if it exists
    if py_file.exists():
        # Remove old backup if it exists
        if py_old_file.exists():
            py_old_file.unlink()
        # Rename current file to .old
        py_file.rename(py_old_file)
        print(f"[INFO] Backed up existing socratic_kbs.py to socratic_kbs.py.old")
    
    # Generate Python file content
    lines = [
        '"""Auto-generated file containing knowledge base prompts.',
        '',
        'This file is generated from socratic_kbs.json.',
        'Do not edit manually - changes will be overwritten.',
        '',
        'Usage:',
        '    from socratic_kbs import prompts',
        '    print(prompts["your_prompt_name"])',
        '"""',
        '',
        'prompts = {',
    ]
    
    # Add each prompt as a dictionary entry
    for key, value in kbs_data.items():
        # Escape backslashes and quotes for Python string literal
        escaped_value = value.replace('\\', '\\\\').replace('"""', r'\"\"\"')
        lines.append(f'    "{key}": """{escaped_value}""",')
    
    lines.append('}')
    
    # Write the file
    content = '\n'.join(lines)
    with open(py_file, 'w') as f:
        f.write(content)
    
    print(f"[INFO] Generated {py_file} with {len(kbs_data)} prompt(s)")


def compose_prompt(selected_units: list[dict], model: str, project_dir: Path, output_name: str) -> None:
    """
    Compose a prompt using the selected knowledge units.
    
    Args:
        selected_units: List of knowledge unit dictionaries selected by the user
        model: OpenAI model to use
        project_dir: Project directory path
        output_name: Name for the output files
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
Don't expose internal citations/filenames (e.g., wiki.md:34) in user-visible messaging. Those are provenance for the agent only.
Respect scope. Output only the snippet; do not add "You are…", system/meta instructions, or formatting fences.
Tone: concise, neutral, and clear; avoid legalese unless mandated by a policy.

Now, please process the following JSON list of knowledge units and generate the complete prompt snippet based on all the rules specified above.

{formatted_units}"""

    print(f"[INFO] sending compose prompt to model")
    response = client.responses.create(
        model=model,
        reasoning={"effort": "none"} if model == "gpt-5.1" else {"effort": "minimal"},
        input=prompt
    )

    print("\n[INFO] Compose process completed.")
    
    # Save to socratic_kbs.json first
    kbs_data = _load_kbs_json(project_dir)
    kbs_data[output_name] = response.output_text
    _save_kbs_json(project_dir, kbs_data)
    print(f"[INFO] Saved to socratic_kbs.json with key '{output_name}'")
    
    # Generate Python file from all knowledge base entries
    _generate_python_file(project_dir, kbs_data)
    
    # Then save markdown file
    save_as(response.output_text, project_dir / f"{output_name}.md")
    print(f"[INFO] Compose result saved to {project_dir / f'{output_name}.md'}")

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
        "--units-json-file",
        default=None,
        help="Path to JSON file containing pre-selected knowledge units (for web UI mode). If not provided, uses interactive terminal selection.",
    )
    parser.add_argument(
        "--export-format",
        default="markdown",
        help="Export format for the output (default: markdown).",
    )
    parser.add_argument(
        "--output-name",
        default=None,
        help="Name for the output file. If not provided, uses current datetime.",
    )
    return parser


def run_compose(args: argparse.Namespace) -> None:
    # Load and print LLM configuration from .env
    try:
        llm_config = load_llm_config()
        print(f"[INFO] LLM Configuration from .env:")
        print(f"[INFO]   MODEL: {llm_config['model']}")
        print(f"[INFO]   BASE_URL: {llm_config['base_url']}")
        print(f"[INFO]   ENV_KEY: {llm_config['env_key']}")
    except SystemExit as e:
        # If .env loading fails, it will exit with appropriate error message
        raise
    
    # Extract model from config
    model = llm_config['model']

    project_dir = Path("projects") / args.project
    if not project_dir.exists() or not project_dir.is_dir():
        raise SystemExit(
            f"Project '{args.project}' not found under projects/. Please create 'projects/{args.project}' and try again."
        )
    print(f"[INFO] Compose command with project: {args.project}, model: {model}")
    
    # Determine output name
    if args.output_name:
        output_name = args.output_name
    else:
        output_name = datetime.now().isoformat(timespec="seconds")
    
    # Check if name already exists in socratic_kbs.json
    if _check_name_exists(project_dir, output_name):
        raise SystemExit(f"[ERROR] Output name '{output_name}' already exists in socratic_kbs.json. Please choose a different name.")
    
    # Check if units are provided via JSON file (web UI mode) or need interactive selection (terminal mode)
    if args.units_json_file:
        # Web UI mode: load pre-selected units from JSON file
        try:
            with open(args.units_json_file, "r") as f:
                selected_units = json.load(f)
            
            if not isinstance(selected_units, list):
                raise SystemExit("[ERROR] Units JSON file must contain a list of knowledge units.")
            
            print(f"[INFO] Loaded {len(selected_units)} pre-selected knowledge units from {args.units_json_file}")
        except FileNotFoundError:
            raise SystemExit(f"[ERROR] Units JSON file not found: {args.units_json_file}")
        except json.JSONDecodeError as e:
            raise SystemExit(f"[ERROR] Failed to parse units JSON file: {e}")
    else:
        # Terminal mode: use interactive selection
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
    compose_prompt(selected_units, model, project_dir, output_name)


__all__ = [
    "build_compose_parser",
    "run_compose",
    "compose_prompt",
]

