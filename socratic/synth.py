from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openai import OpenAI

from .constants import MAX_KEY_PROCESSES_PER_PLAYBOOK
from .io_utils import save_as, print_status, print_agent_block, prompt_input
from .ingest import run_ingest



synth_schema = {
    "type": "object",
    "properties": {
        "knowledge_units": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "body": {"type": "string"}
                },
                "required": ["heading", "body"],
                "additionalProperties": False
            },
        }
    },
    "required": ["knowledge_units"],
    "additionalProperties": False
}


MODIFY_AGENT_PROMPT = """You are an expert Senior Staff Engineer and technical architect. Your primary skill is the ability to analyze complex, multi-modal systems—including code, documentation, configuration files, specifications, and other text-based artifacts—and rapidly synthesize a deep, conceptual understanding of their structure, intent, and logic.

Your task is to analyze a provided system to investigate a specific "Concept". Your output will be consumed by another AI coding agent to perform tasks, so clarity, precision, and verifiability are paramount. The downstream agent has no room for ambiguity.

IMPORTANT:
There is an existing knowledge base of concepts stored in .socratic/synth-consolidated.json. You can use this to help you understand the existing concepts and how they are related to each other. Your goal is to add one or more knowledge units to this existing knowledge base, by collaborating with the user. As your final output, return the knowledge units you wish to add to the existing knowledge base. Use markdown format, NOT JSON format.

The Concept/topic to research and add to the existing knowledge base: {concept}

# Core Philosophy
- Do not make up or infer any information. Only derive from the provided documents.
- Conceptual Focus, Implementation-Aware: Explain why and how at a systems level. Your explanations must be conceptual, but grounded in real evidence: code, documents, or configuration files. Use inline file and line number references to ground your explanations.
- Define Before Use: Avoid vague terminology. Introduce new terms only after defining them precisely.
- Anchor Concepts to Evidence: For each conceptual element, specify the system artifact(s)—e.g., code modules, design docs, architecture diagrams, or data schemas—that embody or describe that element.
- Verifiable Reasoning: Any logical flow or algorithm must be represented with verifiable pseudo-code or structured reasoning steps. Each must clearly map to system evidence.

# Final Instructions
- Generate your output in markdown format.
- Do not include any other text, greetings, or sign-offs like "Here is the Playbook..." or "Would you like me to..."
"""


RESEARCH_AGENT_PROMPT = """You are an expert Senior Staff Engineer and technical architect. Your primary skill is the ability to analyze complex, multi-modal systems—including code, documentation, configuration files, specifications, and other text-based artifacts—and rapidly synthesize a deep, conceptual understanding of their structure, intent, and logic.

Your task is to analyze a provided system to investigate a specific "Concept". Your output will be consumed by another AI coding agent to perform tasks, so clarity, precision, and verifiability are paramount. The downstream agent has no room for ambiguity.

The Concept/topic to research: {concept}


# Core Philosophy
- Do not make up or infer any information. Only derive from the provided documents.
- Conceptual Focus, Implementation-Aware: Explain why and how at a systems level. Your explanations must be conceptual, but grounded in real evidence: code, documents, or configuration files. Use inline file and line number references to ground your explanations.
- Define Before Use: Avoid vague terminology. Introduce new terms only after defining them precisely.
- Anchor Concepts to Evidence: For each conceptual element, specify the system artifact(s)—e.g., code modules, design docs, architecture diagrams, or data schemas—that embody or describe that element.
- Verifiable Reasoning: Any logical flow or algorithm must be represented with verifiable pseudo-code or structured reasoning steps. Each must clearly map to system evidence.

# Final Instructions
- Generate your output in markdown format.
- Do not include any other text, greetings, or sign-offs like "Here is the Playbook...
"""


def build_synth_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="socratic-cli synth",
        description=(
            "Synthesize design notes for key concepts in the provided input directory."
        ),
    )
    parser.add_argument(
        "--input_dir",
        # required=False,
        default=None,
        help="Path to the directory containing files to summarize.",
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
    parser.add_argument(
        "-n",
        "--workers",
        type=int,
        default=4,
        help="Maximum number of concurrent workers to use.",
    )
    # CRUD and utility flags
    parser.add_argument(
        "--list_concepts",
        action="store_true",
        help="List knowledge units with ephemeral IDs from synth-consolidated.json.",
    )
    parser.add_argument(
        "--delete_concept",
        type=int,
        help="Delete a knowledge unit by its ephemeral ID.",
    )
    parser.add_argument(
        "--add_concept",
        type=str,
        help="Describe a knowledge unit to add (stubbed for now).",
    )
    parser.add_argument(
        "--modify_concept",
        type=str,
        help="Describe how to modify a knowledge unit (stubbed for now).",
    )
    parser.add_argument(
        "--concept_id",
        type=int,
        help="Target knowledge unit ID for --modify-concept.",
    )
    return parser


def research_concept_design(concept: str, model: str, directory: Path) -> tuple[str, str, dict]:
    env = os.environ.copy()
    env["CODEX_API_KEY"] = os.environ["OPENAI_API_KEY"]

    instruction = RESEARCH_AGENT_PROMPT.format(concept=concept)

    command = [
        "codex",
        "exec",
        "--cd",
        str(directory.resolve()),
        "--model",
        model,
        "--json",
        instruction,
        # "--output-schema",
        # "socratic/synth_output_schema.json"
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )

    collected_output: list[str] = []

    assert process.stdout is not None
    for raw_line in process.stdout:
        collected_output.append(raw_line)

    return_code = process.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, command)

    if len(collected_output) < 2:
        raise ValueError("Unexpected Codex output: fewer than two lines returned.")

    second_last_line = collected_output[-2]
    resource_usage = collected_output[-1]
    usage_dict = json.loads(resource_usage).get("usage", {})

    try:
        payload = json.loads(second_last_line)
    except json.JSONDecodeError as error:
        raise ValueError("Failed to parse Codex output as JSON.") from error

    item = payload.get("item")
    if not isinstance(item, dict):
        raise ValueError("Codex output missing item field.")

    text = item.get("text")
    if not isinstance(text, str):
        raise ValueError("Codex output missing item.text field.")

    collected_output = "\n".join(collected_output)
    return text, collected_output, usage_dict

def convert_synth_output_to_json(synth_output: str) -> dict:
    """
    Takes the raw text output of research_concept_design and converts it to JSON following the given schema.
    """
    # print(f"[DEBUG] converting synth_output to JSON: {synth_output[:50]}...")
    client = OpenAI()
    prompt = f"""Convert the following raw text output to JSON following the given schema. Convert text as is, do not change or modify the text. Do not attempt to summarize or paraphrase the given text. Do not add any additional text or comments.
    
    The given text:
    {synth_output}"""

    response = client.responses.create(
        model="gpt-5-mini",
        reasoning={"effort": "minimal"},
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "synth_schema",
                "schema": synth_schema,
            }
        },
    )

    # Print token usage
    if hasattr(response, 'usage') and response.usage:
        usage = response.usage
        print(f"[INFO] Token usage: {usage}")

    try:
        output_json = json.loads(response.output_text)
    except json.JSONDecodeError as error:
        raise ValueError("Failed to parse Codex output as JSON in convert_synth_output_to_json().") from error

    return output_json


def load_consolidated(project_dir: Path) -> dict | None:
    """
    Load the consolidated knowledge base JSON if it exists, otherwise return None.
    """
    path = project_dir / "synth-consolidated.json"
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return json.loads(text)
    except Exception as error:
        raise ValueError(f"Failed to read consolidated synth JSON: {path}") from error


def save_consolidated(project_dir: Path, data: dict) -> Path:
    """
    Save the consolidated knowledge base JSON to synth-consolidated.json.
    """
    out_path = project_dir / "synth-consolidated.json"
    save_as(json.dumps(data, indent=2, ensure_ascii=False), out_path)
    return out_path


def ensure_ids(data: dict) -> dict:
    """
    Assign sequential ephemeral IDs to each knowledge unit starting at 1.
    Existing IDs are overwritten to keep them consistent and simple.
    """
    units = data.get("knowledge_units", [])
    for index, unit in enumerate(units, start=1):
        if isinstance(unit, dict):
            unit["id"] = index
    return data


def consolidate(project_dir: Path, model: str = "gpt-5-mini"):
    """
    Read all concept*-synth.json files under project_dir, concatenate their raw
    contents, and ask an LLM to consolidate them into a single JSON following
    synth_schema. Saves to project_dir / 'synth-consolidated.json'.
    """
    files = sorted(project_dir.glob("concept*-synth.json"))
    if not files:
        print_status(f"No per-concept synth JSON files found in {project_dir}. Skipping consolidation.")
        return

    parts: list[str] = []
    for fpath in files:
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception as error:
            raise ValueError(f"Failed to read synth JSON file: {fpath}") from error
        parts.append(f"### {fpath.name}\n{text}")

    combined = "\n\n".join(parts)

    client = OpenAI()
    prompt = (
        "Consolidate the following JSON files into a single JSON output that follows the given schema. "
        "You have the freedom to merge redundant knowledge units into a single knowledge unit. Do not create new knowledge units or delete any.\n\n"
        f"Here are the JSON files to consolidate: \n {combined}"
    )
    print(f"[DEBUG] prompt: {prompt[:500]}...")


    response = client.responses.create(
        model=model,
        reasoning={"effort": "minimal"},
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "synth_schema",
                "schema": synth_schema,
            }
        },
    )

    if hasattr(response, "usage") and response.usage:
        print(f"[INFO] Token usage (consolidate): {response.usage}")

    try:
        output_json = json.loads(response.output_text)
    except json.JSONDecodeError as error:
        raise ValueError("Failed to parse LLM output as JSON in consolidate().") from error
    
    # Assign ephemeral IDs before saving
    output_json = ensure_ids(output_json)

    out_path = project_dir / "synth-consolidated.json"
    save_as(json.dumps(output_json, indent=2, ensure_ascii=False), out_path)
    print_status(f"Saved consolidated synth JSON → {out_path.name}")
    return out_path


def add_concept(args: argparse.Namespace, project_dir: Path) -> None:
    """Add a new knowledge unit by launching a codex agent to modify synth-consolidated.json."""
    input_dir = Path(args.input_dir)
    
    # Create .socratic directory in input_dir
    socratic_dir = input_dir / ".socratic"
    socratic_dir.mkdir(parents=True, exist_ok=True)
    print_status(f"Created directory: {socratic_dir}")
    
    # Copy consolidated file from project_dir to .socratic
    source_file = project_dir / "synth-consolidated.json"
    dest_file = socratic_dir / "synth-consolidated.json"
    
    if not source_file.exists():
        raise SystemExit(
            f"synth-consolidated.json not found in {project_dir}. "
            "Run 'socratic-cli synth' first to generate it."
        )
    
    shutil.copy(source_file, dest_file)
    print_status(f"Copied {source_file} → {dest_file}")
    
    # Launch codex agent
    env = os.environ.copy()
    env["CODEX_API_KEY"] = os.environ["OPENAI_API_KEY"]
    
    instruction = MODIFY_AGENT_PROMPT.format(concept=args.add_concept)
    
    command = [
        "codex",
        "exec",
        "--cd",
        str(input_dir.resolve()),
        "--model",
        args.model,
        "--json",
        instruction,
        # "--output-schema",
        # "knowledge_units_schema.json"
    ]
    
    # print_status(f"Launching codex agent with instruction: {instruction}")
    
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    
    collected_output: list[str] = []
    
    assert process.stdout is not None
    for raw_line in process.stdout:
        collected_output.append(raw_line)
    
    return_code = process.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, command)
    
    # Parse and display the initial agent message (2nd last line)
    if len(collected_output) < 2:
        raise ValueError("Unexpected Codex output: fewer than two lines returned.")
    second_last_line = collected_output[-2]
    try:
        payload = json.loads(second_last_line)
    except json.JSONDecodeError as error:
        raise ValueError("Failed to parse Codex output as JSON.") from error
    item = payload.get("item")
    if not isinstance(item, dict):
        raise ValueError("Codex output missing item field.")
    text = item.get("text")
    if not isinstance(text, str):
        raise ValueError("Codex output missing item.text field.")
    print_agent_block(text, title="Agent Draft")

    # Extract thread_id from the first line
    thread_start_line = collected_output[0]
    try:
        thread_start_obj = json.loads(thread_start_line)
    except json.JSONDecodeError as error:
        raise ValueError("Failed to parse Codex thread start line as JSON.") from error
    if isinstance(thread_start_obj, dict) and thread_start_obj.get("type") == "thread.started" and "thread_id" in thread_start_obj:
        thread_id = thread_start_obj.get("thread_id")
    else:
        raise ValueError(f"Unexpected Codex output: thread_id not found in the first line: {thread_start_line}")

    # Interactive loop: send user feedback until DONE
    last_text = text
    while True:
        user_feedback = prompt_input("Type feedback (or DONE to finish)")
        if user_feedback.strip().upper() == "DONE":
            break

        resume_command = [
            "codex",
            "exec",
            "--cd",
            str(input_dir.resolve()),
            "--model",
            args.model,
            "--json",
            "resume",
            thread_id,
            user_feedback,
        ]

        print_status("Continuing agent with your input…")
        process2 = subprocess.Popen(
            resume_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        resume_output: list[str] = []
        assert process2.stdout is not None
        for raw_line in process2.stdout:
            resume_output.append(raw_line)
        return_code2 = process2.wait()
        if return_code2:
            raise subprocess.CalledProcessError(return_code2, resume_command)
        if len(resume_output) < 2:
            raise ValueError("Unexpected Codex resume output: fewer than two lines returned.")
        second_last_line2 = resume_output[-2]
        try:
            payload2 = json.loads(second_last_line2)
        except json.JSONDecodeError as error:
            raise ValueError("Failed to parse Codex resume output as JSON.") from error
        item2 = payload2.get("item")
        if not isinstance(item2, dict):
            raise ValueError("Codex resume output missing item field.")
        text2 = item2.get("text")
        if not isinstance(text2, str):
            raise ValueError("Codex resume output missing item.text field.")

        last_text = text2
        print_agent_block(text2, title="Agent Update")

    # User issued DONE command, meaning that they are happy with the final output of the agent. So grab that, convert to JSON, and add it to the existing knowledge base.
    print_status(f"Done. Adding new knowledge unit(s) to the existing knowledge base. This may take a few seconds...")

    knowledge_units_to_add = convert_synth_output_to_json(last_text)
    existing_knowledge_base_file = load_consolidated(project_dir)
    if existing_knowledge_base_file is None:
        raise ValueError("No existing knowledge base file found.")
    existing_knowledge_base = existing_knowledge_base_file.get("knowledge_units", [])
    existing_knowledge_base.extend(knowledge_units_to_add.get("knowledge_units", []))
    existing_knowledge_base_file["knowledge_units"] = existing_knowledge_base
    save_consolidated(project_dir, existing_knowledge_base_file)
    print_status(f"Added new knowledge unit(s) to the existing knowledge base.")


def modify_concept(args: argparse.Namespace, project_dir: Path) -> None:
    """Modify an existing knowledge unit (stub for now)."""
    if args.concept_id is None:
        print_status("Please provide --concept-id with --modify-concept.")
        return
    print_status("Modify concept is not implemented yet. This is a stub.")
    print(f"[INFO] Target ID: {args.concept_id} | Description: {args.modify_concept}")


def list_concepts(project_dir: Path) -> None:
    """List all knowledge units from the consolidated knowledge base."""
    data = load_consolidated(project_dir)
    if data is None:
        print_status("No consolidated synth JSON found. Run 'socratic-cli synth' to generate it first.")
        return
    
    data = ensure_ids(data)
    units = data.get("knowledge_units", [])
    
    if not units:
        print_status("Knowledge base is empty.")
        return
    
    print_status("Listing knowledge units (ephemeral IDs):")
    print("ID | Heading")
    print("-- | -------")
    for unit in units:
        hid = unit.get("id")
        heading = unit.get("heading", "")
        print(f"{hid} | {heading}")


def delete_concept(args: argparse.Namespace, project_dir: Path) -> None:
    """Delete a knowledge unit by its ephemeral ID."""
    data = load_consolidated(project_dir)
    if data is None:
        print_status("No consolidated synth JSON found. Run 'socratic-cli synth' to generate it first.")
        return
    
    data = ensure_ids(data)
    units = data.get("knowledge_units", [])
    target_id = args.delete_concept
    
    if not isinstance(target_id, int) or target_id < 1 or target_id > len(units):
        print_status(f"Invalid ID: {target_id}. Use --list to see valid IDs.")
        return
    
    # Remove by position (ID is 1-based index)
    removed = units.pop(target_id - 1)
    data = ensure_ids(data)
    save_consolidated(project_dir, data)
    print_status(f"Deleted knowledge unit ID {target_id}: '{removed.get('heading', '')}'.")

def run_synth(args: argparse.Namespace) -> None:
    # Check for required OPENAI_API_KEY environment variable
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required but not defined in the environment. Currenlty only OpenAI models are supported.")

    # Validate project directory under projects/
    project_dir = Path("projects") / args.project
    if not project_dir.exists() or not project_dir.is_dir():
        raise SystemExit(
            f"Project '{args.project}' not found under projects/. Please create 'projects/{args.project}' and try again."
        )

    # CRUD mode: if any of the CRUD flags are present, skip ingest/synthesis flow.
    if getattr(args, "list_concepts", False) or args.delete_concept is not None or args.add_concept or args.modify_concept:
        if args.add_concept:
            if not args.input_dir:
                raise SystemExit("--input_dir is required when using --add_concept.")
            add_concept(args, project_dir)
            return
        if args.modify_concept:
            modify_concept(args, project_dir)
            return
        if getattr(args, "list_concepts", False):
            list_concepts(project_dir)
            return
        if args.delete_concept is not None:
            delete_concept(args, project_dir)
            return

        # If we reached here, no actionable CRUD flag was provided
        print_status("No CRUD action provided. Use --list_concepts, --delete_concept, --add_concept, or --modify_concept.")
        return


    directory = Path(args.input_dir)
    print(f"[INFO] Working directory: {directory}")

    # Run ingest first to generate concepts.txt
    print(f"[INFO] Running ingest stage to generate key concepts...")
    run_ingest(args)
    
    # Automatically load concepts.txt from project directory
    key_concepts_path = project_dir / "concepts.txt"
    print(f"[INFO] ### Loading key concepts from: {key_concepts_path}")
    try:
        text = key_concepts_path.read_text(encoding="utf-8", errors="replace")
    except Exception as error:
        raise ValueError(
            f"Failed to read concepts file: {key_concepts_path}"
        ) from error
    key_concepts = [line.strip() for line in text.splitlines() if line.strip()]
    print(f"[INFO] ### Loaded {len(key_concepts)} key concepts from file.")

    token_usage_list = [
        {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
        for _ in key_concepts
    ]
    workers = max(1, args.workers)

    def run_design(
        index_and_concept: tuple[int, str]
    ) -> tuple[int, str, tuple[str, str], dict]:
        idx, concept = index_and_concept
        print_status(f"Synthesizing design for concept {idx}: {concept[:50]}…")
        research_result, _, token_usage = research_concept_design(
            concept, args.model, directory
        )
        # Preview first 800 chars to avoid flooding the terminal
        preview = research_result[:800]
        if len(research_result) > 800:
            preview += "\n… (truncated)"
        print_agent_block(preview, title=f"Concept {idx} Result Preview")
        print_status(f"Done synthesizing design for concept {idx}")
        return idx, concept, research_result, token_usage

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(run_design, (idx, concept)): idx
            for idx, concept in enumerate(key_concepts)
        }
        for future in as_completed(futures):
            idx, concept, research_result, token_usage = future.result()
            token_usage_list[idx] = token_usage
            print(f"[INFO] Token usage: {token_usage_list[idx]}")
            text_path = project_dir / f"concept{idx}-synth.txt"
            save_as(
                "# Concept: " + concept + " design insights:\n\n" + research_result,
                text_path,
            )

            # convert the research_result to JSON. structured knowledge units are easier to manage later.
            json_result = convert_synth_output_to_json(research_result)
            output_obj = {
                    "header": concept,
                    "knowledge_units": json_result.get("knowledge_units", []),
            }
            json_path = project_dir / f"concept{idx}-synth.json"
            save_as(
                json.dumps(output_obj, indent=2, ensure_ascii=False),
                json_path,
            )
            print_status(
                f"Saved results for concept {idx}: text → {text_path.name}, json → {json_path.name}"
            )

    # After all workers are done, consolidate per-concept JSON files
    print_status("Consolidating per-concept synth JSON files into a single JSON…")
    consolidate(project_dir, model="gpt-5-mini")


__all__ = [
    "build_synth_parser",
    "research_concept_design",
    "consolidate",
    "add_concept",
    "modify_concept",
    "list_concepts",
    "delete_concept",
    "run_synth",
]

