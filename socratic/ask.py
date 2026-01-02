from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import List, Dict, Any

import litellm

from .constants import *
from .io_utils import save_as, print_status, print_agent_block, prompt_input, load_project_config, extract_agent_message_from_output
from .llm_config import get_llm_configs

ASK_AGENT_PROMPT = """Your task is to answer user questions using the knowledge base and source documents available to you. This is a READ-ONLY mode — you will NOT modify the knowledge base. Your job is to provide accurate, well-grounded answers based on the existing knowledge.


# Knowledge Base
Your current working directory contains the knowledge base.
- Knowledge base format: the knowledge base is organized into knowledge units, which are conceptually individual pieces of information that are related. Think about it as a chapter/section in a text book. Each knowledge unit is stored as a single markdown file. The knowledge base is thus the collection of all markdown files in the current directory.
- You have READ-ONLY access to the knowledge base. You should read the knowledge base files to understand the domain and answer user questions.
- DO NOT attempt to modify, add, or delete any files.

# Input source documents
The input source documents contain a collection of unstructured text files that provide additional context.
- For example, the input source documents may contain code files, documentation files, configuration files, specifications, and other text-based artifacts.
- You can use both the knowledge base and the input source documents to answer user questions.
- The input source documents are stored in the previous directory (../). You can also access the input source documents directory using the absolute path {input_src_docs_dir}.

# Your Task
You will be engaging in a multi-turn conversation with the user. You must follow this sequence:

1) **Read the KB first**
- IMPORTANT: Before answering any questions, you MUST read the existing knowledge base. This is critical as the KB contains essential knowledge about the domain.
- The KB represents curated, validated knowledge and should be your primary source of truth.

2) **Ask clarifying questions** (if needed)
- If the user's question is ambiguous or unclear, ask for clarification before answering.
- Use numbered list when asking questions to the user to make it easier for the user to answer and reference the questions.

3) **Answer the question**
- Provide a clear, accurate answer based on the knowledge base and source documents.
- Ground your answers in evidence from the KB and source documents.
- If the answer is not in the KB or source documents, say so clearly rather than making things up.
- Use inline file and line number references to ground your explanations when appropriate.

# Core Philosophy
- Do not make up or infer any information. Only derive from the knowledge base and source documents.
- Conceptual Focus, Implementation-Aware: Explain why and how at a systems level. Your explanations must be conceptual, but grounded in real evidence.
- Be honest when you don't know something or when the information is not available.

# Understanding `<meta-info>` Tags
When you read a Knowledge Unit, look for sections wrapped in `<meta-info>...</meta-info>`.
* **Authority:** Treat these notes as **authoritative instructions**.
* **Conflict Resolution:** If a raw source document conflicts with a `<meta-info>` note (e.g., the note says "File X is deprecated"), you must trust the note and ignore the source file.

# Other
- The terminal tools you control has a limit on the total number of bytes you can read with a single command. If the tool output is too long, the output will be truncated. This is NOT GOOD as you may miss important information. 
- When truncation occurs, you will see "X chars truncated" somewhere in the middle of the text output.
- To avoid this, it is HIGHLY recommended to 1) read files in smaller chunks, especially for files with long lines. Reading at most 100 lines at a time is a good rule of thumb. 2) when you see truncation, try to get the missing information that are truncated.


First user question: {user_instruction}
"""


def build_ask_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="socratic-cli ask",
        description=(
            "Ask questions about the knowledge base. Read-only mode that uses the KB to answer questions."
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



def ask_agent(
    model: str,
    codex_config_options: list,
    input_src_docs_dir: Path,
    project_dir: Path,
    webui_friendly: bool = False,
):
    """
    Use the knowledge base to answer user questions in a read-only mode.
    The agent has read access to both the KB and source documents but cannot modify anything.
    """
    
    env = os.environ.copy()

    # Prompt user for their question
    if webui_friendly:
        print("What would you like to know?")
        user_instruction = input()
        print("Agent in progress...")
    else:
        user_instruction = prompt_input("What would you like to know?")
        print_status("Agent in progress...")

    # directory that contains the knowledge base files
    project_dir_kb_dir = project_dir / "knowledge_base"

    instruction = ASK_AGENT_PROMPT.format(input_src_docs_dir=input_src_docs_dir, user_instruction=user_instruction)

    command = [
        "codex",
        "exec",
        "--cd",
        str(project_dir_kb_dir.resolve()),
        "--sandbox",
        "read-only",
        "--model",
        model,
    ]
    
    # Add all config options
    for config_opt in codex_config_options:
        command.extend(["--config", config_opt])
    
    # Only add reasoning effort for OpenAI reasoning models
    if "gpt-5" in model or "gpt-5.1" in model:
        command.extend(["--config", f"model_reasoning_effort='{ASK_CODEX_REASONING_EFFORT}'"])
    
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
        print_agent_block(text, title="Agent Response")
    last_text = text

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

    # Interactive loop: send user follow-up questions (exits on Ctrl-C)
    while True:
        if webui_friendly:
            user_feedback = input()
        else:
            user_feedback = prompt_input("")

        resume_command = [
            "codex",
            "exec",
            "--cd",
            str(project_dir_kb_dir.resolve()),
            "--sandbox",
            "read-only",
            "--model",
            model,
        ]
        
        # Add all config options
        for config_opt in codex_config_options:
            resume_command.extend(["--config", config_opt])
        
        # Only add reasoning effort for OpenAI reasoning models
        if "gpt-5" in model or "gpt-5.1" in model:
            resume_command.extend(["--config", f"model_reasoning_effort='{ASK_CODEX_REASONING_EFFORT}'"])
        
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
            print_agent_block(text2, title="Agent Response")


def run_ask(args: argparse.Namespace) -> None:
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

    ask_agent(
        model,
        codex_config_options,
        input_src_docs_dir,
        project_dir,
        webui_friendly=args.webui_friendly,
    )


__all__ = [
    "build_ask_parser",
    "ask_agent",
    "run_ask",
]

