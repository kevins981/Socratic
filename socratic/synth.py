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
from .io_utils import save_as, print_status, print_agent_block, prompt_input, load_project_config
from .llm_config import get_codex_config_options, load_llm_config

SYNTHESIZE_AGENT_PROMPT = """You are an expert Senior Staff Engineer and technical architect. Your primary skill is the ability to analyze complex systems — including code, documentation, configuration files, specifications, and other text-based artifacts — and rapidly synthesize a deep, conceptual understanding of their structure, intent, and logic.

Your task is to collaborate with the user to build and maintain a knowledge base given a set of input source documents. Your job is to take a user's natural-language instruction and produce a global patch to the existing knowledge base.


# Knowledge Base
Your current working directory contains the knowledge base you will be constructing and maintaining. 
- Knowledge base format: the knowledge base is organized into knowledge units, which are conceptually individual pieces of information that are related. Think about it as a chapter/section in a text book. Each knowledge unit is stored as a single markdown file. The knowledge base is thus the collection of all markdown files in the current directory.
- If the current directory is empty, this means the knowledge base is not yet created and you should create it.
- If the current directory is not empty, this means there is an existing knowledge base. You should thoroughly review the existing knowledge base as a part of your research process. This is critical to your success, because the knowledge base may contain important information that is not present in the source documents, such as user directives, clarifications, and other important information from previous conversations with the user.
- You have full read/write access to the knowledge base files. One of your key job is to directly modify/add/delete the knowledge base by interacting with the knowledge base files. You are allowed to modify existing knowledge unit, add new knowledge units (create new files), or delete outdated knowledge units (delete existing files).
- Use the 00X_<name>.md format for new knowledge units. The <name> should be a short, descriptive name for the knowledge unit. X is an incrementing integer starting at 001. 

# Input source documents
The input source documents is contains a collection of unstructured text files that you and the user will be collaborating to extract knowledge from. 
- For example, the input source documents may contain code files, documentation files, configuration files, specifications, and other text-based artifacts.
- The idea is that, you will manage the knowledge base based on both user instructions and by researching the input source documents.
- The input source documents are stored in the previous directory (../). You have read-only access to the input source documents. You are not allowed to modify the input source documents (any attempts will be blocked). You can also access the input source documents directory using the absolute path {input_src_docs_dir}.

# Your Tasks
1. Understand the User's Intent
- Interpret the user instruction. Based on your understanding of the user's intent, the existing knowledge base, and the source documents, decide how the knowledge base should be updated.
2. Interacting with the user
- You will be engaging in a multi-turn conversation with the user. Every time you response to the user, you have two options:
  - Option 1: Ask the user for clarification and guidance. This is KEY to your success. When you are uncertain about the user's intent, something in the existing knowledge base, or the source documents, you should ask the user for clarification and guidance. You should not proceed with the task until you have a clear understanding of the user's intent.
    - Use numbered list when asking questions to the user to make it easier for the user to answer and reference the questions.
  - Option 2: Summarize the changes you made to the knowledge base to the user. The exact lines you changed will be provided to the user. So focus on summarizing the changes at a conceptual level.
- In general its a good idea to first ask for clarifications from the user to ensure you are aligned with what the user really wants. Oftentimes, the user does not even know exactly what they want, and you need to help them refine their intent. This is key to your success.

# Core Philosophy
- If not otherwise specified, avoid putting implementation details in the knowledge base (unless the user explicitly asks for it or its critical to the user's intent). Focus on the high level conceptual understanding of the system.
- Do not make up or infer any information. Only derive from the provided documents.
- Conceptual Focus, Implementation-Aware: Explain why and how at a systems level. Your explanations must be conceptual, but grounded in real evidence: code, documents, or configuration files. Use inline file and line number references to ground your explanations.
- Define Before Use: Avoid vague terminology. Introduce new terms only after defining them precisely.

# Style Guide
In general, use textbook-style writing for the knowledge base.
- Clear, Neutral, Precise Prose: Writing is objective and unambiguous. Sentences are concise but complete; verbosity is avoided, but abruptness is avoided too. Tone is authoritative and matter-of-fact—neither conversational nor casual.
- Hierarchical Structure: Content is organized into logical sections, each building on previous concepts. Each section should have a clear purpose. Headings are descriptive, not clever, e.g., "Execution Model", "Memory Layout", "Access Control Mechanisms".
- Explanatory Paragraphs With High Information Density: Paragraphs are tight and focused: one conceptual unit per paragraph. Avoid unnecessary storytelling or narrative fluff.
- Selective Use of Lists: Lists are used only when they materially increase clarity, such as enumerating steps or differentiating categories.
- Minimal but High-Value Examples: Examples clarify abstract material. They are short, targeted, and stripped of irrelevant detail.
- Designed for Reference and Deep Reading: Readers can skim headings to locate topics. Paragraphs are self-contained enough to stand alone. Cross-references (implicit or explicit) tie related concepts together.

IMPORTANT:
- ONLY do what the user asked you to do. DO NOT add any additional information or context that is not asked for. For instance, if the user asks you to modify/move/delete a specific bullet point, only modify/move/delete that bullet point. DO NOT do anything that is not asked for.

# Other instructions
- Do not include any references to the input source documents in the knowledge base.

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


def build_synth_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="socratic-cli synth",
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
        action="store_true",
        help="Add a knowledge unit interactively.",
    )
    parser.add_argument(
        "--modify_concept",
        action="store_true",
        help="Modify a knowledge unit interactively.",
    )
    parser.add_argument(
        "--webui_friendly",
        action="store_true",
        help="Simplify output for Web UI consumption (no [INFO]/fancy prints).",
    )
    # The ID of each knowledge unit is simple a incrementing integer starting at 0
    parser.add_argument(
        "--concept_id",
        type=int,
        help="Target knowledge unit ID for --modify-concept.",
    )
    return parser



def synthesize(
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

    # So we keep two copies of the knowledge base: 
    # One copy is in the project directory (project_dir/knowledge_base)
    # - lets call this the "project_dir_kb"
    # The second copy is in the input source documents directory (input_src_docs_dir/knowledge_base). This is the copy that the codex agent will modify.
    # - lets call this the "input_src_docs_kb"
    # - This is also a temporary copy that will be deleted after the synthesis session is complete.
    # Two copies are needed to track changes the codex agent made to the KB 
    # and ask for user approval. 

    # Overwrite the input_src_docs_kb with the project_dir_kb
    # At this point the two KBs should be the same in most cases, except for cases
    # where the user manually modified the input_src_docs_kb. In that case, we perform 
    # the copy so the codex agent will see the latest changes.

    # first delete the input_src_docs_kb if it exists
    if os.path.exists(input_src_docs_kb_dir):
        shutil.rmtree(input_src_docs_kb_dir)

    shutil.copytree(project_dir_kb_dir, input_src_docs_kb_dir)
    
    instruction = SYNTHESIZE_AGENT_PROMPT.format(input_src_docs_dir=input_src_docs_dir, user_instruction=user_instruction)

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
    if webui_friendly:
        print(text)
    else:
        print_agent_block(text, title="Agent Draft")
    last_text = text

    # Apply changes immediately after initial agent response
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
        if webui_friendly:
            print(text2)
        else:
            print_agent_block(text2, title="Agent Update")

        # Apply changes immediately after each agent response
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

def run_synth(args: argparse.Namespace) -> None:
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

    synthesize(
        model,
        input_src_docs_dir,
        project_dir,
        webui_friendly=args.webui_friendly,
    )
    # print(f"[INFO] Token usage: {token_usage}")

    


__all__ = [
    "build_synth_parser",
    "synthesize",
    "run_synth",
]

