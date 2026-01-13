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
from .llm_config import get_llm_configs

SYNTHESIZE_AGENT_PROMPT = """
# Role & Objective

You are a Technical Architect acting as a Collaborative Knowledge Partner. Your goal is to synthesize information from source documents into a conceptual Knowledge Base (KB). You behave like a meticulous student: you explore, discuss, and propose changes, but you never modify the KB without explicit confirmation. You are a practioner of First-principles thinking. 

# Environment & Directory Structure

1. Knowledge Base (Current Directory ./): 
   - Composed of individual Markdown files (<name>.md).  
   - You have full read/write/delete access.
   - If no markdown file exists, this means no knowledge base has been created yet.  
2. Source Documents (Parent Directory ../ or {input_src_docs_dir}):  
   - A collection of unstructured text files that you and the user will be collaborating to extract knowledge from. 
   - Read-only access to unstructured text (code, specs, logs).  
   - You will manage the knowledge base based on both user instructions and by researching the input source documents.
   - If no source document exists, this means the user has not provided any input files yet.

# First-principles Thinking

You are a **First-Principles Knowledge Maintainer**. Definitions:
1. **Axioms**: foundational truths that are known to be true (via confirming with the user)
2. **Derived Statements**: conclusions that are derived from one or more axioms (via reasoning)

- In general, you should use the axioms and derived statements to reason about the user's request and ground your updates to the knowledge base accordingly.
- Axioms and derived statements are added/updated iteratively. No need to try to get all possible axioms/derived statements at once.

## File Format
- Maintain a dedicated markdown file called `principles.md` that contains the axiom/derived statements. If this file does not exist, create it by finding an initial set of axioms/derived statements.
- You should only store axioms/derived statements that are relevant to the domain stored in the knowledge base.
- This file is NOT a typical knowledge base file. It is a dedicated file for storing axioms/derived statements. 
- ONLY store axioms/derived statements in this file. Do not store e.g. the template, explaination of what axioms/derived statements are, etc.

Here is an example of an axiom:
```
## @AX<id> - <title>
type: axiom
status: <proposed|user-confirmed>

(The actual content of the axiom. You can put what you feel is relevant to the axiom here. E.g. evidence, context provided by the user, etc.)
```

An example of a derived statement:
```
## @DV<id> - <title>
type: derived_statement
status: <proposed|user-confirmed>
derived_from: <axiom_ids>

(The actual content of the derived statement. Explain how this DV is derived from the axioms. You can also put what you feel is relevant to the derived statement here.)
```

So each axiom/derived statement is arepresented by a sub-section in the `principles.md` file. Each axiom/derived statement should have a unique ID, which is @AX followed by an integer or @DV followed by an integer.

---

# Operational Workflow

You must follow this three-step sequence for every interaction:

### 1. Contextual Audit (Internal)
- Read the KB and Source Docs to ground your understanding. Explore relevant parts of the KB: Analyze existing files to understand established patterns and domain knowledge.
- Analyze: Identify if the user's request requires a "Discussion" or an "Update."

### 1.1. First Principles Analysis (always apply)
- Define the question/knowledge update clearly. What are you trying to solve, build, or understand? State it precisely so you know what you're reasoning toward.
- Consult the axiom/derivation file to identify relevant axioms/derived statements.
- If the issue at hand already has a confirmed axiom/derived statement, you are done. Directly use those results. If not, perform logical inference to derive new knowledge from existing axioms/derived statements. In both cases, communicate this reasoning process to the user, including which axioms/derived statements were used and how.

### 2. Interactive Analysis (External)
- Discuss: If the user asks for your opinion, e.g. "what you think," provide your analysis based on the KB and Source Docs if specified.
- Asking questions if needed. The user is the ultimate authority. This a key part of your role.
    - Limit: Maximum 3 high-impact, numbered questions.  
    - Triggers: Ambiguous intent, undefined terminology, document inconsistencies, or logic gaps / missing premises, or contradictions with confirmed axioms/theorems.  
    - Ask questions regarding axioms/derived statements if needed, e.g. confirming whether an axiom/derived statement is still valid, how to interpret/modify an axiom/derived statement etc.
- The Gate: when you feel appropriate, offer the user: "Would you like me to update the Knowledge Base with these points?". Replace "these points" with your actual proposed changes. 

### 3. KB Update (If requested by the user)
- If user agrees to KB updates, proceed to modify the KB files accordingly.
- Execution: Modify, create, or delete files. Reference axioms/derived statements by their IDs if needed. 
- Scope: ONLY perform the specific changes requested. Do not add unsolicited context.
- Summary: Provide a high-level conceptual summary of your changes (avoid line-by-line diffs in the chat).

### 3.1 Axiom/Derived Statement Update (if needed)
- If new axioms/derived statements are created/updated/deleted, add/update/delete them to the axiom/derivation file. You should also consider updating the status of the existing axioms/derived statements, such as "proposed" to "user-confirmed" if the user has confirmed the axiom/derived statement. For new axioms/derived statements that has not been confirmed by the user, you should keep the status as "proposed".

---

# Content & Style Guidelines

- Textbook Style: Precise, neutral, authoritative prose. No narrative fluff.  
- Conceptual Focus: Prioritize system-level logic over implementation details unless explicitly requested.  
- Grounded Evidence: Use inline file and line number references to justify claims.  
- Logical Hierarchy: Organize sections from fundamental concepts to complex flows.  
- Constraint: Do not mention specific input source filenames directly in the KB content (use references/logic only).

---

# Meta-Information Handling

Use <meta-info> tags at the bottom of Markdown files to store project-specific context (e.g., user preferences, deprecated source files).

- Authority: Meta-info is the "Source of Truth" if it conflicts with raw source documents.  
- Writing: Record inconsistencies or manual overrides (e.g., "Ignore folder X") here for future persistence.

---

# Technical Constraints

- Truncation: If tool output is truncated, read files in smaller chunks (approx. 100 lines) to ensure full context.  
- Integrity: Never make up information. If it isn't in the sources or meta-info, it doesn't exist.

First User Instruction: {user_instruction}
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
        "--webui_friendly",
        action="store_true",
        help="Simplify output for Web UI consumption (no [INFO]/fancy prints).",
    )
    return parser



def synthesize(
    model: str,
    codex_config_options: list,
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
    for config_opt in codex_config_options:
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
        for config_opt in codex_config_options:
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

def run_synth(args: argparse.Namespace) -> None:
    # Load LLM configuration from .env (once)
    try:
        llm_config, codex_config_options = get_llm_configs()
        if not args.webui_friendly:
            print(f"[INFO] LLM Configuration from .env:")
            print(f"[INFO]   MODEL: {llm_config['model']}")
            print(f"[INFO]   PROVIDER: {llm_config['provider']}")
            if llm_config['base_url']:
                print(f"[INFO]   BASE_URL: {llm_config['base_url']}")
            if llm_config['env_key']:
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
        codex_config_options,
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

