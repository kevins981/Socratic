from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
from openai import OpenAI
import os

from .constants import MAX_KEY_CONCEPTS_PER_FILE, MAX_KEY_CONCEPTS_TOTAL
from .io_utils import save_as, print_status, print_agent_block, prompt_input

INGEST_PLANNER_PROMPT = """Your purpose is to help the user collaboratively decide what broad topics to research — not to do deep research yourself. You act as an intelligent planning assistant that interprets the user’s intent, lightly inspects the provided materials, and proposes a structured list of high-level research themes (called "concepts") for the next stage (Knowledge Synthesis).

## Goals
1. Translate the user’s high-level directions into a concrete, actionable *research plan*.  
2. Ensure the plan reflects both **user priorities** and **document realities**.  
3. Keep your output high-level and concise. Your goal is to define broad research themes, not to list specific rules or granular details. 
4. Generate a numbered list of these broad concepts and ask the user for feedback.


## Core Behaviors
You must:
- Ask clarifying questions until you fully understand what the user wants to explore.  
- Skim input files efficiently (titles, headers, function/class names, variable definitions, metadata, or summaries).  
- Synthesize and group your findings. Do not output a flat list of every detail you find.
- Generate a concise list of **concepts** worth researching.  
- Do not make up or infer any information. Only derive from the provided documents.

## Interaction Loop Guidelines
You are part of an iterative agent-human planning loop. Follow this protocol:

### Initialization
At the start, you will be given an initial input from the user. Use this to generate a preliminary list of concepts to research.

### Surface Scanning
Efficiently scan the provided documents to identify recurring terms, mechanisms, or patterns related to the user’s interests.
Avoid deep reading; prioritize section titles, variable names, or summaries.

### Draft Generation
Produce a preliminary research plan. Instructions for Draft Generation:
- Constraint: The initial research plan you generate should be proportional to the intial input from the user. For each concept provided by the user, generate 1 or 2 concepts. For example, if the user provided two concepts, you should generate 2 to 4 concepts.
- Your main task is to group and synthesize. If you find lots of specific concepts, you must cluster them logically under 2-4 high-level headings

### User Feedback Loop
Every time after you generate a list of concepts to research, ask the user for feedback of the current list of concepts to research. For example: "Would you like me to include policy X, which is related to Y?", "Would you like me to include concept Z, which is related to A?"
The user will either approve the list of concepts to research, or provide additional input to update the list of concepts to research.
If the user does not approve the list of concepts to research, you will need to update the list of concepts to research and ask the user for feedback again, until the user approves the list of concepts to research.

### Finalization
When the user approves, output the final approved list of concepts to research. Do not continue generating further refinements after finalization.

## Output Format
Format your output like this:

"Here is a list of concepts I discovered based on your description:
1. Concept A. Context behind concept A so that the downstream researchers to conduct research on this concept.
2. Concept B. Some context.
...

Would you like me to..."


## The Concept/topic to research: 
{initial_user_input}

"""

def build_ingest_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="socratic-cli ingest",
        description="Identify key concepts for the current directory.",
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
    return parser

def plan_concepts_to_research(initial_user_input: str, model: str, directory: Path) -> str:
    """
    Collaborate with user to determine a list of concepts to research.
    The user will provide initial input and the ingest planner will use that to generate an initial list of concepts to research.
    This initial list of concepts to research will be returned to the user for review.
    If the user is not satisfied, user can provide additional input and the ingest planner will update the list of concepts to research.
    Repeat this process until the user is satisfied with the list of concepts to research.
    Return the final list of concepts to research.
    """

    env = os.environ.copy()
    env["CODEX_API_KEY"] = os.environ["OPENAI_API_KEY"]

    instruction = INGEST_PLANNER_PROMPT.format(initial_user_input=initial_user_input)

    command = [
        "codex",
        "exec",
        "--cd",
        str(directory.resolve()),
        "--model",
        model,
        "--json",
        instruction
    ]

    print_status("Planning concepts based on your input…")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )

    codex_traj: list[str] = []
    assert process.stdout is not None
    for raw_line in process.stdout:
        codex_traj.append(raw_line)

    return_code = process.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, command)

    if len(codex_traj) < 2:
        raise ValueError("Unexpected Codex output: fewer than two lines returned.")

    second_last_line = codex_traj[-2] # the 2nd last line is the agent's output of the current step.
    resource_usage = codex_traj[-1]
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


    # At this point, the agent generated the first draft of the list of concepts, and is waiting for user feedback.
    print_agent_block(text, title="Agent Draft")

    # grab the codex session id (thread_id) from the codex trajectory.
    # the first line of the codex trajectory contains the thread_id.
    thread_start_line = codex_traj[0]
    thread_start_obj = json.loads(thread_start_line)
    if isinstance(thread_start_obj, dict) and thread_start_obj.get("type") == "thread.started" and "thread_id" in thread_start_obj:
        thread_id = thread_start_obj.get("thread_id")
    else:
        raise ValueError(f"Unexpected Codex output: thread_id not found in the first line: {thread_start_line}")



    # ask for user feedback.
    user_feedback = prompt_input("")
    
    # resume codex session with the user feedback.
    # currently hardcoded to only allow 1 round of feedback.
    resume_command = [
        "codex",
        "exec",
        "--cd",
        str(directory.resolve()),
        "--model",
        model,
        "--json",
        "resume",
        thread_id,
        user_feedback+".\nThis is the final feedback from the user. Only output the final list of concepts to research and do not generate any more questions asking for more feedback. ONLY print the final list of concepts to research and do not print anything else, such as 'Here is a list of...' or 'Would you like me to...'. In this final list, do not number the concepts. Just list the concepts one after another.\n Remember to use the format:\nConcept A. Context: ...\nConcept B. Context...\n..."
    ]

    print_status("Applying your feedback and finalizing…")
    process2 = subprocess.Popen(
        resume_command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )

    # TODO this is ugly
    assert process2.stdout is not None
    for raw_line in process2.stdout:
        codex_traj.append(raw_line)

    return_code = process2.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, resume_command)

    second_last_line2 = codex_traj[-2] 

    try:
        payload2 = json.loads(second_last_line2)
    except json.JSONDecodeError as error:
        raise ValueError("Failed to parse Codex output as JSON.") from error

    item2 = payload2.get("item")
    if not isinstance(item2, dict):
        raise ValueError("Codex output missing item field.")

    text2 = item2.get("text")
    if not isinstance(text2, str):
        raise ValueError("Codex output missing item.text field.")

    print_agent_block(text2, title="Final Concepts")

    return text2, "".join(codex_traj)    


def run_ingest(args: argparse.Namespace) -> None:
    # Check for required OPENAI_API_KEY environment variable
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required but not defined in the environment. Currenlty only OpenAI models are supported.")

    directory = Path(args.input_dir)
    print(f"[INFO] Working directory: {directory}")
    if getattr(args, "specific_instructions", None):
        print(f"[INFO] Specific instructions: {args.specific_instructions}")

    # Validate project directory under projects/
    project_dir = Path("projects") / args.project
    if not project_dir.exists() or not project_dir.is_dir():
        raise SystemExit(
            f"Project '{args.project}' not found under projects/. Please create 'projects/{args.project}' and try again."
        )

    # Prompt the user for initial input and capture it
    initial_user_input = prompt_input(
        "What should I research? Share a few high-level pointers."
    )
    # print(f"[INFO] Initial user input: {initial_user_input}")

    key_concepts, codex_traj = plan_concepts_to_research(initial_user_input, args.model, directory)

    save_as(key_concepts, project_dir / "concepts.txt")
    save_as(codex_traj, project_dir / "concepts_traj.jsonl")
    print(f"[INFO] Done identifying key concepts. Saved results to {project_dir / 'concepts.txt'}.")

