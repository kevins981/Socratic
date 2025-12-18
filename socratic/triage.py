from __future__ import annotations

import argparse
import difflib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any

import litellm

from .constants import *
from .io_utils import save_as, print_status, print_agent_block, prompt_input, load_project_config, extract_agent_message_from_output
from .llm_config import get_codex_config_options, load_llm_config

TRIAGE_AGENT_PROMPT = """You are **Socratic Triage**, an assistant whose job is to (1) **localize failures in target-agent trajectories** and (2) **learn triage knowledge from the user** into a persistent knowledge base (KB).

## Terms
- **Target agent**: the agent being debugged.
- **Triage agent (you)**: the agent analyzing the target agent.
- **Trajectory / trace**: the recorded steps, tool calls, messages, outputs, errors, and intermediate artifacts from the target agent’s run.

---

## Core responsibilities
You must handle two kinds of user tasks:

### Task type A — Triage a trajectory
Goal: identify the **most likely root cause** of failure for a given target-agent trajectory.

You must follow this sequence:

1) **Read the KB first**
- IMPORTANT: Before analyzing the trace, you MUST read the existing triage KB. This is critical as the KB contains essential knowledge about how to correctly perform the triage task.
- If the KB is missing something needed to interpret the trace format, proceed but note the gap.

2) **Read the provided trajectory carefully**
- Extract key evidence: where the run diverges, error messages, tool misuse, invalid assumptions, missing context, retrieval issues, schema mismatches, etc.
- Do not invent steps that are not in the trace.

3) **Propose a root cause and ask for confirmation**
- Provide your best diagnosis as a **testable claim** with supporting evidence from the trace.
- Ask the user for confirmation (e.g., "this is my diagnosis..."). If you are not sure about something, you can ask the user for clarification.
- If multiple plausible causes exist, provide a ranked short list and ask a discriminating question.

4) **Update KB only after confirmation**
- Only after the user confirms (or corrects) the diagnosis, you can (optionally) update the KB with any new knowledge learned from this triage session. For example:
  - add/adjust failure mode definitions
  - add a “signature” (symptoms → likely cause)
  - add a minimal example reference
  - add a recommended fix/checklist item
- Only add to the KB if the existing KB does not already cover the new knowledge and you believe it will help future triage tasks.

If the user does **not** confirm, do **not** update the KB. Revise your hypothesis first.

### Task type B — Learn triage knowledge from the user
Goal: capture user-provided expertise about traces and failures.

When the user is teaching you (formats, failure modes, heuristics, interpretation rules, fix strategies):
- Ask **classification questions** that make the knowledge precise and reusable:
  - “Is this failure mode about planning, tool use, retrieval, or environment?”
  - “What symptoms reliably distinguish it?”
  - “What’s the minimal example or canonical snippet?”
  - “What’s the recommended fix?”
- Summarize the learned knowledge in a compact, structured form.
- Propose a KB update and ask for approval before writing it.

---

## Knowledge Base

The current working directory **is the knowledge base (KB)**.

- The KB consists of **knowledge units**, each stored as a single Markdown file. Each unit represents one coherent concept, rule, pattern, or clarification (similar to a section in a textbook).
- If the directory is **empty**, the KB does not yet exist and you should create it.
- If the directory is **not empty**, an existing KB is present. You must **thoroughly read it before proceeding**, as it may contain critical user directives, clarifications, or prior conclusions not found elsewhere.
- You have **full read/write access** to the KB. Your responsibilities include:
  - modifying existing knowledge units
  - adding new knowledge units
  - deleting outdated or incorrect knowledge units
- New knowledge units must follow the naming format: `00X_<short_descriptive_name>.md`, where `X` starts at `001` and increments.

In general, its a good idea to keep the following concepts in the KB:
- How to read/interpret target-agent trajectories, since the trace format may vary.
- How to find the golden/expected behavior for a target agent for a given task. This is known as the "correctness condition". Different target agents may have different correctness conditions.
- Information about common failure modes, their symptoms, root causes.
---

## Input source documents
The input source documents contains a collection of unstructured text files that you and the user will be collaborating to extract knowledge from. 

- The input source documents are stored in the previous directory (../). You have read-only access to the input source documents. You are not allowed to modify the input source documents (any attempts will be blocked). You can also access the input source documents directory using the absolute path {input_src_docs_dir}.

- In general, there are two types of input source documents:
    1) Agent trajectories that need to be triaged.
    1) Documents provided by the user that contain relevant information about the target agent, its environment, and the task it is trying to accomplish. These are meant to give you more context.

- The idea is that, you will manage the knowledge base based on both user instructions and by researching the input source documents.

---

## Style Guide
In general, use textbook-style writing for the knowledge base.
- Clear, Neutral, Precise Prose: Writing is objective and unambiguous. Sentences are concise but complete; verbosity is avoided, but abruptness is avoided too. Tone is authoritative and matter-of-fact—neither conversational nor casual.

---

First user instruction: {user_instruction}
"""


def sync_knowledge_base(source_kb_dir: Path, target_kb_dir: Path) -> None:
    """
    Synchronize knowledge base by copying source to target.
    Deletes target directory if it exists, then copies source to target.
    
    Args:
        source_kb_dir: The source knowledge base directory (what the agent produced)
        target_kb_dir: The target knowledge base directory (to be overwritten)
    """
    if os.path.exists(target_kb_dir):
        shutil.rmtree(target_kb_dir)
    shutil.copytree(source_kb_dir, target_kb_dir)


def build_triage_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="socratic-cli triage",
        description=(
            "Synthesize design notes for key concepts in the provided input directory."
        ),
    )
    parser.add_argument(
        "--project",
        required=True,
        help="Project name; must match a folder under projects/",
    )
    parser.add_argument(
        "--webui_friendly",
        action="store_true",
        help="Simplify output for Web UI consumption (no [INFO]/fancy prints).",
    )
    return parser



def triage(
    model: str,
    input_src_docs_dir: Path,
    project_dir: Path,
    webui_friendly: bool = False,
):
    """
    Research all concepts at once using a single Codex agent call.
    Returns the consolidated result for all concepts.
    input_dir: the directory containing the source files to synthesize.
               the knowledge base files are stored in input_dir/knowledge_base/.
               We set the codex agent working directory to input_dir/knowledge_base/ 
               and grant full write access within that directory so the agent can modify the knowledge base files.
               We tell the agent in the prompt that the source input files are stored in ../. This is how we ensure the agent has read-only access to the source input files but write access to the knowledge base files.
    """
    # Get LLM provider configuration
    config_options, env_key = get_codex_config_options()
    
    env = os.environ.copy()

    # Prompt user for synthesis request
    if webui_friendly:
        print("What should we work on?")
        user_instruction = input()
        print("Agent in progress...")
    else:
        user_instruction = prompt_input("What should we work on?")
        print_status("Agent in progress...")

    # directory that contains the knowledge base files
    input_src_docs_kb_dir = input_src_docs_dir / "knowledge_base"
    project_dir_kb_dir = project_dir / "knowledge_base"

    # first delete the input_src_docs_kb if it exists
    if os.path.exists(input_src_docs_kb_dir):
        shutil.rmtree(input_src_docs_kb_dir)

    shutil.copytree(project_dir_kb_dir, input_src_docs_kb_dir)
    
    instruction = TRIAGE_AGENT_PROMPT.format(input_src_docs_dir=input_src_docs_dir, user_instruction=user_instruction)

    command = [
        "codex",
        "exec",
        "--cd",
        str(input_src_docs_kb_dir.resolve()),
        "--sandbox",
        "workspace-write",
        "--model",
        model,
    ]
    
    # Add all config options
    for config_opt in config_options:
        command.extend(["--config", config_opt])
    
    # Only add reasoning effort for OpenAI reasoning models
    if "gpt-5" in model or "gpt-5.1" in model:
        command.extend(["--config", f"model_reasoning_effort='{GLOBAL_CODEX_REASONING_EFFORT}'"])
    
    command.extend([
        "--json",
        instruction,
    ])

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
    
    # Parse and display the initial agent message
    text = extract_agent_message_from_output(collected_output)
    if webui_friendly:
        print(text)
    else:
        print_agent_block(text, title="Agent Draft")
    last_text = text

    # Apply changes immediately after initial agent response (terminal mode only)
    # In webui_friendly mode, we skip auto-sync and let the web UI handle per-file approval
    if not webui_friendly:
        sync_knowledge_base(input_src_docs_kb_dir, project_dir_kb_dir)

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

    # Interactive loop: send user feedback (exits on Ctrl-C)
    while True:
        if webui_friendly:
            # print("Type feedback")
            user_feedback = input()
        else:
            user_feedback = prompt_input("")

        resume_command = [
            "codex",
            "exec",
            "--cd",
            str(input_src_docs_kb_dir.resolve()),
            "--sandbox",
            "workspace-write",
            "--model",
            model,
        ]
        
        # Add all config options
        for config_opt in config_options:
            resume_command.extend(["--config", config_opt])
        
        # Only add reasoning effort for OpenAI reasoning models
        if "gpt-5" in model or "gpt-5.1" in model:
            resume_command.extend(["--config", f"model_reasoning_effort='{GLOBAL_CODEX_REASONING_EFFORT}'"])
        
        resume_command.extend([
            "--json",
            "resume",
            thread_id,
            user_feedback,
        ])

        if webui_friendly:
            print("Continuing agent with your input…")
        else:
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
        
        # Parse and display the resumed agent message
        text2 = extract_agent_message_from_output(resume_output)
        last_text = text2
        if webui_friendly:
            print(text2)
        else:
            print_agent_block(text2, title="Agent Update")

        # Apply changes immediately after each agent response (terminal mode only)
        # In webui_friendly mode, we skip auto-sync and let the web UI handle per-file approval
        if not webui_friendly:
            sync_knowledge_base(input_src_docs_kb_dir, project_dir_kb_dir)


def print_directory_diff(source_dir: Path, target_dir: Path) -> None:
    """
    Show a colorized recursive diff between two directories.
    source_dir: the updated directory (what the agent produced)
    target_dir: the original directory (what we had before)
    """
    # ANSI color codes
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    print(f"\n{BOLD}=== Knowledge Base Changes ==={RESET}\n")
    
    # Get all files recursively from both directories
    source_files = set()
    target_files = set()
    
    if source_dir.exists():
        for file_path in source_dir.rglob('*'):
            if file_path.is_file():
                rel_path = file_path.relative_to(source_dir)
                source_files.add(rel_path)
    
    if target_dir.exists():
        for file_path in target_dir.rglob('*'):
            if file_path.is_file():
                rel_path = file_path.relative_to(target_dir)
                target_files.add(rel_path)
    
    # Find added, deleted, and potentially modified files
    added_files = sorted(source_files - target_files)
    deleted_files = sorted(target_files - source_files)
    common_files = sorted(source_files & target_files)
    
    modified_files = []
    for rel_path in common_files:
        source_file = source_dir / rel_path
        target_file = target_dir / rel_path
        
        source_content = source_file.read_text(encoding='utf-8', errors='replace')
        target_content = target_file.read_text(encoding='utf-8', errors='replace')
        
        if source_content != target_content:
            modified_files.append(rel_path)
    
    # Print summary
    has_changes = added_files or deleted_files or modified_files
    
    if not has_changes:
        print(f"{BLUE}No changes detected.{RESET}\n")
        return
    
    # Print added files
    if added_files:
        print(f"{GREEN}{BOLD}Added files:{RESET}")
        for file_path in added_files:
            print(f"{GREEN}  + {file_path}{RESET}")
        print()
    
    # Print deleted files
    if deleted_files:
        print(f"{RED}{BOLD}Deleted files:{RESET}")
        for file_path in deleted_files:
            print(f"{RED}  - {file_path}{RESET}")
        print()
    
    # Print modified files with diffs
    if modified_files:
        print(f"{YELLOW}{BOLD}Modified files:{RESET}")
        for file_path in modified_files:
            print(f"{YELLOW}  ~ {file_path}{RESET}")
        print()
        
        # Show detailed diffs for modified files
        for rel_path in modified_files:
            source_file = source_dir / rel_path
            target_file = target_dir / rel_path
            
            source_lines = source_file.read_text(encoding='utf-8', errors='replace').splitlines(keepends=True)
            target_lines = target_file.read_text(encoding='utf-8', errors='replace').splitlines(keepends=True)
            
            print(f"{BOLD}--- {rel_path} (before){RESET}")
            print(f"{BOLD}+++ {rel_path} (after){RESET}")
            
            # Generate unified diff with 2 lines of context
            diff_lines = difflib.unified_diff(
                target_lines,
                source_lines,
                fromfile=str(rel_path),
                tofile=str(rel_path),
                lineterm='',
                n=2  # Show only 2 context lines before and after changes
            )
            
            # Skip the first two lines (file headers) since we already printed them
            diff_list = list(diff_lines)
            for line in diff_list[2:]:
                if line.startswith('+'):
                    print(f"{GREEN}{line}{RESET}")
                elif line.startswith('-'):
                    print(f"{RED}{line}{RESET}")
                elif line.startswith('@@'):
                    print(f"{BLUE}{line}{RESET}")
                else:
                    print(line)
            print()
    
    # Print summary at the end
    print(f"{BOLD}Summary: {GREEN}{len(added_files)} added{RESET}, "
          f"{RED}{len(deleted_files)} deleted{RESET}, "
          f"{YELLOW}{len(modified_files)} modified{RESET}\n")

def run_triage(args: argparse.Namespace) -> None:
    # Load and print LLM configuration from .env
    try:
        llm_config = load_llm_config()
        if not args.webui_friendly:
            print(f"[INFO] LLM Configuration from .env:")
            print(f"[INFO]   MODEL: {llm_config['model']}")
            print(f"[INFO]   BASE_URL: {llm_config['base_url']}")
            print(f"[INFO]   ENV_KEY: {llm_config['env_key']}")
    except SystemExit as e:
        # If .env loading fails, it will exit with appropriate error message
        raise
    
    # Extract model from config
    model = llm_config['model']

    # Validate project directory under projects/
    project_dir = Path("projects") / args.project
    if not project_dir.exists() or not project_dir.is_dir():
        raise SystemExit(
            f"Project '{args.project}' not found under projects/. Please create 'projects/{args.project}' and try again."
        )

    # Load project configuration to get input_dir
    config = load_project_config(args.project)
    input_dir_str = config.get("input_dir")
    if not input_dir_str:
        raise SystemExit(
            f"input_dir not found in project configuration for '{args.project}'. "
            "The project may be corrupted or was created with an older version."
        )
    input_src_docs_dir = Path(input_dir_str)

    if not args.webui_friendly:
        print(f"[INFO] Input source files directory: {input_src_docs_dir}")

    triage(
        model,
        input_src_docs_dir,
        project_dir,
        webui_friendly=args.webui_friendly,
    )
    # print(f"[INFO] Token usage: {token_usage}")

    

__all__ = [
    "build_triage_parser",
    "triage",
    "run_triage",
]
