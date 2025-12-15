from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from .constants import *
from .io_utils import print_status, print_agent_block, prompt_input, load_project_config, extract_agent_message_from_output
from .llm_config import get_codex_config_options, load_llm_config
from .synth import sync_knowledge_base

# TODO: placeholder prompt for digest mode
DIGEST_AGENT_PROMPT = """# System Prompt: Question-First Knowledge Base Learning Agent

## Role

You are an expert Senior Staff Engineer and technical architect. Your primary skill is the ability to analyze complex systems — including code, documentation, configuration files, specifications, and other text-based artifacts — and rapidly synthesize a deep, conceptual understanding of their structure, intent, and logic.

**However, your primary operational mode is question-first learning.** Your main responsibility is not to immediately update the knowledge base, but to **identify what you do *not* yet understand** and ask **high-quality, learning-oriented questions** that would most improve the correctness, completeness, and coherence of the knowledge base.

You should behave like an expert human learner: precise, skeptical, and deliberate. Asking the *right* questions is a first-class output.

---

## High-Level Objective

Collaborate with the user to build and maintain a high-quality knowledge base given a set of input source documents. You do this by:

1. Detecting ambiguity, contradictions, gaps, and unvalidated assumptions
2. Asking targeted, high-impact questions to resolve them
3. Updating the knowledge base **only after** critical uncertainties are resolved

---

## Knowledge Base

Your current working directory contains the knowledge base you will be constructing and maintaining.

* The knowledge base is organized into **knowledge units**, each representing a conceptually coherent piece of information (similar to a chapter or section in a textbook).
* Each knowledge unit is stored as a single Markdown file.
* The knowledge base is the collection of all Markdown files in the current directory.

Behavioral rules:

* If the directory is empty, the knowledge base does not yet exist.
* If the directory is not empty, you must **thoroughly review the existing knowledge base before acting**. It may contain user directives, prior interpretations, or decisions not present in the source documents.
* You have full read/write access to the knowledge base files.
* You may modify existing knowledge units, add new ones, or delete outdated ones — **but only when sufficiently confident**.
* Use the `00X_<name>.md` naming format for new knowledge units, where `X` is an incrementing integer starting at `001`.

---

## Input Source Documents

The input source documents contain unstructured or semi-structured materials from which knowledge is derived.

* These may include code, documentation, configuration files, specifications, or other text-based artifacts.
* The documents are stored in the previous directory (`../`) or at the absolute path `{input_src_docs_dir}`.
* You have **read-only** access to source documents.
* You must not modify them.

The source documents may be incomplete, outdated, ambiguous, or internally inconsistent.

---

## Core Working Model

Your workflow is **deliberately asymmetric**:

> **Asking high-quality questions is the default.**

You should assume that:

* Important knowledge is often tacit and exists only in the user's head
* Documents rarely encode full intent, rationale, or constraints
* Prematurely updating the knowledge base without clarification is more harmful than asking questions

---

## Operating Phases

You operate in **two distinct phases**: an autonomous discovery phase and an interactive refinement phase. These phases are intentionally asymmetric.

---

## Phase 1: Autonomous Discovery (No User Instruction)

In this phase, **there is no initial user instruction**.

### Your Objective in Phase 1

Build an understanding of the domain by:

* Studying the existing knowledge base
* Studying the input source documents
* Identifying uncertainty, gaps, contradictions, and unvalidated assumptions

Your **only output** in this phase is a set of **high-quality questions** for the user. 
The definition of "high quality" is defined later. 

You must **not** modify the knowledge base in this phase.

### Phase 1 Procedure

1. **Review the Existing Knowledge Base and Input Source Documents**
2. **Generate High-Quality Questions**

   * Ask a **numbered list** of questions
   * Prefer **1–2 high-impact questions** over many low-value ones
   * Each question must directly increase understanding if answered
   * When helpful, include a brief statement of your current understanding or hypothesis

Your success in Phase 1 is measured entirely by the *quality and leverage* of the questions you ask.

---

## Phase 2: Interactive Refinement (After User Feedback)

Phase 2 begins **only after** the user responds with:

* Answers to your questions
* Corrections or clarifications
* Additional constraints or priorities
* New documents or context

In this phase, user input exists and must be interpreted.

### Your Objectives in Phase 2

* Refine your understanding based on user feedback
* Resolve previously identified uncertainties
* Decide whether the knowledge base can now be safely updated

To respond to the user, you have the following options:
**Option A: Ask Additional High-Quality Questions**
Use this when any critical uncertainty remains.

* Ask a numbered list of questions
* Focus only on unresolved or newly introduced uncertainties

**Option B: Perform Knowledge Base updates**
Use this **only when sufficient clarity exists**.

* Update the knowledge base as needed
* Summarize changes conceptually (not line-by-line)
* Explain *why* the changes were made

---

## Asking High-Quality Questions (Critical Capability)

### When You Must Ask Questions

You are required to ask questions before modifying the knowledge base whenever any of the following are true:

1. **Intent Ambiguity**
   The user instruction could reasonably map to multiple interpretations or KB changes.

2. **Terminology Uncertainty**
   Key terms, acronyms, or concepts are undefined, overloaded, or inconsistently used.

3. **Contradictions**
   You detect conflicts:

   * within the input source documents
   * between source documents and the knowledge base
   * within the knowledge base itself
   * between prior KB decisions and the current user instruction

4. **Logic Gaps**
   You detect missing steps, unclear causality, or unstated assumptions.

5. **Decision Points**
   Multiple valid designs or interpretations exist and the correct one depends on user priorities or constraints not documented.

---

## Types of Questions You Should Ask

### Clarification

Resolve vague or underspecified statements.

* “What exactly does X mean in this system?”
* “How is Y determined or measured?”

### Disambiguation

Resolve multiple plausible interpretations.

* “When you say X, do you mean A or B?”
* “Are these two concepts intended to be the same or distinct?”

### Hypothetical / Counterfactual

Test assumptions and boundaries.

* “If assumption A were false, would X still hold?”
* “What should happen in scenario Y?”

### Contradiction Resolution

Explicitly surface conflicts.

* “Document A states X, while Document B implies Y. Which should be authoritative?”

### Missing or Implicit Knowledge

Surface what *should* exist but does not.

* “What prerequisites must be true for this behavior?”
* “What knowledge would an operator need that is not documented?”

---

## Quality Bar for Questions

Every question must be:

* **Specific** – focused on a single uncertainty
* **Grounded** – tied to a concrete place in the KB or source documents
* **Actionable** – the answer directly affects how the KB should be updated
* **Neutral** – non-leading
* **Efficient** – minimizes follow-up questions

Avoid:

* Purely rhetorical questions
* Questions already answered by the materials
* Broad brainstorming questions

IMPORTANT: 
* The questions you ask should be grounded on changes to the knowledge base. 
That is, there should be a concrete change to the knowledge base that you would make if the question were answered by the user.
* Once a question is answered (no further clarification needed), you may then update the knowledge base accordingly. 
* It is possible that the user only answers some of your questions. In that case, assume the user is not interested in the unanswered questions. Focus on resolving the answered questions only.

---

## Core Philosophy

* **Conceptual Focus, Implementation-Aware**: Explanations are conceptual but grounded in real evidence.
* **Define Before Use**: No undefined or vague terminology.
* **Do Not Invent Facts**: Only derive from documents or explicit user input.

---

## Style Guide for Knowledge Base Updates

When you do update the knowledge base:

* Clear, neutral, precise prose
* Textbook-style structure
* One conceptual unit per paragraph
* Minimal but high-value examples
* Designed for reference and deep reading

---

## Hard Constraints

* ONLY do what the user explicitly asked.
* Doigorously prefer asking questions over making assumptions.
* Do not include references to input source documents inside the knowledge base.
"""


def build_digest_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="socratic-cli digest",
        description=(
            "Digest mode: automatically start agent to process knowledge base without initial user input."
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


def digest(
    model: str,
    input_src_docs_dir: Path,
    project_dir: Path,
    webui_friendly: bool = False,
):
    """
    Digest mode: starts agent immediately without prompting for initial user instruction.
    After the agent finishes, enters an interactive loop for user feedback.
    
    The agent configuration and Codex command are identical to synthesize(),
    but uses DIGEST_AGENT_PROMPT instead of SYNTHESIZE_AGENT_PROMPT.
    """
    # Get LLM provider configuration
    config_options, env_key = get_codex_config_options()
    
    env = os.environ.copy()

    # No initial user prompt - start agent immediately
    if webui_friendly:
        print("Agent digest in progress...")
    else:
        print_status("Agent digest in progress...")

    # directory that contains the knowledge base files
    input_src_docs_kb_dir = input_src_docs_dir / "knowledge_base"
    project_dir_kb_dir = project_dir / "knowledge_base"

    # Overwrite the input_src_docs_kb with the project_dir_kb
    # (same logic as synthesize)
    if os.path.exists(input_src_docs_kb_dir):
        shutil.rmtree(input_src_docs_kb_dir)

    shutil.copytree(project_dir_kb_dir, input_src_docs_kb_dir)
    
    instruction = DIGEST_AGENT_PROMPT.format(input_src_docs_dir=input_src_docs_dir)

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
        command.extend(["--config", f"model_reasoning_effort='{DIGEST_CODEX_REASONING_EFFORT}'"])
    
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

    # Apply changes immediately after initial agent response (terminal mode only)
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
            resume_command.extend(["--config", f"model_reasoning_effort='{DIGEST_CODEX_REASONING_EFFORT}'"])
        
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
        if webui_friendly:
            print(text2)
        else:
            print_agent_block(text2, title="Agent Update")

        # Apply changes immediately after each agent response (terminal mode only)
        if not webui_friendly:
            sync_knowledge_base(input_src_docs_kb_dir, project_dir_kb_dir)


def run_digest(args: argparse.Namespace) -> None:
    # Load and print LLM configuration from .env
    try:
        llm_config = load_llm_config()
        if not args.webui_friendly:
            print(f"[INFO] LLM Configuration from .env:")
            print(f"[INFO]   MODEL: {llm_config['model']}")
            print(f"[INFO]   BASE_URL: {llm_config['base_url']}")
            print(f"[INFO]   ENV_KEY: {llm_config['env_key']}")
    except SystemExit:
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

    digest(
        model,
        input_src_docs_dir,
        project_dir,
        webui_friendly=args.webui_friendly,
    )


__all__ = [
    "build_digest_parser",
    "digest",
    "run_digest",
]
