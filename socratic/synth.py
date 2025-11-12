from __future__ import annotations

import argparse
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openai import OpenAI

from .constants import MAX_KEY_PROCESSES_PER_PLAYBOOK
from .io_utils import save_as, print_status, print_agent_block
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


RESEARCH_AGENT_PROMPT = """You are an expert Senior Staff Engineer and technical architect. Your primary skill is the ability to analyze complex, multi-modal systems—including code, documentation, configuration files, specifications, and other text-based artifacts—and rapidly synthesize a deep, conceptual understanding of their structure, intent, and logic.

Your task is to analyze a provided system to investigate a specific "Concept". Your output will be consumed by another AI coding agent to perform tasks, so clarity, precision, and verifiability are paramount. The downstream agent has no room for ambiguity.

The Concept/topic to research: {concept}

# Knowledge Unit Types
When synthesizing knowledge from source documents, identify the most suitable **knowledge unit type** for each distinct piece of knowledge. Choose based on the nature of the information — whether it describes a concept, process, policy, or data relationship.

Each knowledge unit should be self-contained.

Below are some examples of types of knowledge units you can use:

## 1. Concept
Purpose: General descriptive or explanatory knowledge that doesn’t fit better as a process, policy/rule, or data.
You are generating a **Concept Knowledge Unit**. Summarize the key idea and its purpose in the system. Explain what it is, why it matters, and how it connects to other system elements.

## 2. Procedure
Purpose: Describes a dynamic process, workflow, or algorithm. Defines how something happens, step-by-step.
You are generating a Procedure Knowledge Unit. Describe the process in terms of triggers, inputs/outputs, and logical flow.

## 3. Policy/Rule
Purpose: Defines constraints, business rules, or conditional logic — what can or cannot happen.
You are generating a Policy or Rule Knowledge Unit. Define the rule, its conditions, and consequences for violations.

## 4. Data
Purpose: Defines data entities, their attributes, and relationships — what data exists and how it fits into the system.
You are generating a Data Knowledge Unit. Describe a data entity and its relationships to others.


When analyzing a document, you may find multiple knowledge unit types describing related aspects of one concept. 
In such cases, each knowledge unit captures a distinct aspect of system knowledge, and all can coexist within one synthesized knowledge base.

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
        required=True,
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

    out_path = project_dir / "synth-consolidated.json"
    save_as(json.dumps(output_json, indent=2, ensure_ascii=False), out_path)
    print_status(f"Saved consolidated synth JSON → {out_path.name}")
    return out_path

def run_synth(args: argparse.Namespace) -> None:
    # Check for required OPENAI_API_KEY environment variable
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required but not defined in the environment. Currenlty only OpenAI models are supported.")

    directory = Path(args.input_dir)
    print(f"[INFO] Working directory: {directory}")

    # Validate project directory under projects/
    project_dir = Path("projects") / args.project
    if not project_dir.exists() or not project_dir.is_dir():
        raise SystemExit(
            f"Project '{args.project}' not found under projects/. Please create 'projects/{args.project}' and try again."
        )
    
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
    "run_synth",
]

