import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
import re
from typing import List, Dict, Any

import litellm

from .synth import load_consolidated, save_consolidated, ensure_ids, llm_generate_title, add_knowledge_unit, delete_knowledge_unit, modify_knowledge_unit
from .constants import GLOBAL_CODEX_REASONING_EFFORT
from .io_utils import print_status, print_agent_block, prompt_input, load_project_config
from .llm_config import get_codex_config_options, load_llm_config

UPDATE_CODEX_AGENT_PROMPT = """You are an expert Senior Staff Engineer and technical architect. Your primary skill is the ability to analyze complex systems — including code, documentation, configuration files, specifications, and other text-based artifacts—and rapidly synthesize a deep, conceptual understanding of their structure, intent, and logic.

Your task is to collaborate with the user to build and maintain a knowledge base given a set of source documenets. Your job is to take a user's natural-language instruction and produce a global patch to the existing knowledge base.


# Existing Knowledge Base
There is an existing knowledge base of concepts stored in .socratic/synth-consolidated.json. You should thoroughly review the existing knowledge base as a part of your research process. This is critical to your success, because the knowledge base may contain important information that is not present in the source documents, such as user directives, clarifications, and other important information from previous conversations with the user.
- Within the knowledge base, the special symbol "[USER DIRECTIVE]" indicates a user directive. You should pay close attention to these user directives. User directives override information in the source documents and should take precedence, since the user is the ultimate source of truth.
- If an user directive contradicts information in the rest of the knowledge base, you should raise this up with the user for clarification and guidance.

IMPORTANT: strategy to read the knowledge base.
- In the knowledge base JSON file, each knowledge unit is stored in a single line. So the knowledge base file can be large and contains long lines. It is NOT a good idea to try to read the entire file all at once (e.g. cat or sed a large number of lines). When you try to read too much contents, the output will be truncated ("[... output truncated to fit X bytes"]"). If you see this, do not assume that the knowledge base is incomplete. Do NOT read more than 10 lines of the knowledge base at a time. Its better to make multiple small reads instead of one large read.
- The best way to explore the knowledge base is to first search for relevant keywords and retrieve their line numbers. Then, use bash tools such as 'sed' to read only specific few lines of the knowledge base to fully understand the knowledge base.



# Your Tasks
1. Understand the User's Intent
Interpret the user instruction. Based on your understanding of the user's intent, the existing knowledge base, and the source documents, decide which action(s) are required.
You are allowed to modify any information in the existing knowledge base. To do this, there are three types of actions you can take:
- ADD new knowledge unit(s)
- MODIFY existing knowledge unit(s). To modify an existing knowledge unit, you need to provide the ID of the knowledge unit you want to modify. Your output will overwrite this existing knowledge unit with the new one.
- DELETE outdated or superseded content. To delete a knowledge unit, you need to provide the ID of the knowledge unit you want to delete.

# Output Options
You will be engaging in a multi-turn conversation with the user. Every time you response to the user, you have two options:
Option 1: Ask the user for clarification and guidance. This is useful when you are uncertain about the user's intent, something in the existing knowledge base, or the source documents.
Option 2: Show the user your proposed patch to the existing knowledge base (add/modify/delete). You can use the following format. Note that you dont need to use all three options. You can propose any number of add/modify/delete operations. The format:

Based on your request, I plan to make the following updates:
- ADD new knowledge unit:
(The new knowledge unit you want to add)
Reason: (A concise explanation of why you are adding this knowledge unit)

- MODIFY existing knowledge unit with ID: (the ID of the knowledge unit you want to modify)
(The new knowledge unit you want to modify)
Reason: (A concise explanation of why you are modifying this knowledge unit)

- DELETE knowledge unit with ID: (the ID of the knowledge unit you want to delete)
Reason: (A concise explanation of why you are deleting this knowledge unit)

When you are proposing changes to knowledge base, you must be COMPLETE. I.e. do NOT say "do the following modification for all knowledge units with IDs > 1". You should explictly list all the knowledge units you want to modify, add, or delete, even if the content of modification is the same for multiple knowledge units.


# Core Philosophy
- Do not make up or infer any information. Only derive from the provided documents.
- Concise, logical, and to the point.
- Conceptual Focus, Implementation-Aware: Explain why and how at a systems level. Your explanations must be conceptual, but grounded in real evidence: code, documents, or configuration files. Use inline file and line number references to ground your explanations.
- Define Before Use: Avoid vague terminology. Introduce new terms only after defining them precisely.

IMPORTANT:
- ONLY do what the user asked you to do. DO NOT add any additional information or context that is not asked for. For instance, if the user asks you to modify/move/delete a specific bullet point, only modify/move/delete that bullet point. DO NOT do anything that is not asked for.


User update request: {user_update_request}

"""

def build_update_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="socratic-cli update",
        description="Update the project using a Codex agent.",
    )
    parser.add_argument(
        "--project",
        required=True,
        help="Project name; must match a folder under projects/",
    )
    return parser


def parse_updater_output(raw_text):
    """
    Parses raw text from LLM updater output containing XML-style function calls.
    Not doing standard function calls because not all models support parallel function calls. 
    
    Supported Schema:
    1. Add:    <cmd type="add">TEXT</cmd>
    2. Modify: <cmd type="modify" id="123">TEXT</cmd>
    3. Delete: <cmd type="delete" id="123" />
    
    Args:
        raw_text (str): The raw string output from the LLM.
        
    Returns:
        list: A list of dictionaries representing the function calls.
    """
    
    # Define the Regex Pattern
    # Group 1-3: Matches <cmd type="...">CONTENT</cmd>
    # Group 4-5: Matches <cmd type="..." /> (Self-closing)
    pattern = re.compile(
        r'<cmd\s+type="(add|modify|delete)"(?:\s+id="(\d+)")?>(.*?)</cmd>'  # Pattern A: Block
        r'|'                                                                  # OR
        r'<cmd\s+type="(delete)"(?:\s+id="(\d+)")?\s*/>',                    # Pattern B: Self-closing
        re.DOTALL | re.IGNORECASE
    )

    parsed_commands = []

    # finditer returns an iterator yielding match objects over all non-overlapping matches
    for match in pattern.finditer(raw_text):
        cmd_data = {}
        
        # check which side of the OR (|) matched
        if match.group(1): 
            # It matched Pattern A (Block with content)
            action = match.group(1).lower()
            id_str = match.group(2)
            content = match.group(3)
        else:
            # It matched Pattern B (Self-closing)
            action = match.group(4).lower()
            id_str = match.group(5)
            content = None

        # 1. Process Function Name
        cmd_data['function'] = action

        # 2. Process ID (Convert to int if it exists)
        if id_str:
            try:
                cmd_data['id'] = int(id_str)
            except ValueError:
                cmd_data['id'] = None # Handle edge case of malformed ID

        # 3. Process Text (strip outer whitespace, preserve internal newlines)
        if content is not None:
            # We strip() to remove the newline immediately after <cmd> 
            # and the newline immediately before </cmd>
            cmd_data['text'] = content.strip()

        parsed_commands.append(cmd_data)

    return parsed_commands

def get_knowledge_units_to_modify(text: str) -> List[int]:
    """
    Gets the IDs of the knowledge units that need to be modified. Input is the natural language KB update requests produced by the codex agent.
    """
    llm_config = load_llm_config()
    model = llm_config['model']
    api_base = llm_config['base_url']
    provider = llm_config['provider']


    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": "You are given a piece of text. Your task is to extract the IDs of the knowledge units that need to be modified (only modified, not added or deleted). Only return the IDs in as a comma-separated list of integers. E.g. 1,2,4. Do not return any other text or comments."},
        {"role": "user", "content": text}
    ]

    response = litellm.completion(
        model=model,
        custom_llm_provider=provider,
        messages=messages,
        api_base=api_base
    )

    # Print token usage
    if hasattr(response, 'usage') and response.usage:
        usage = response.usage
        print(f"[INFO] apply_update_to_kb token usage: {usage}")


    llm_output = response.choices[0].message.content
    print(f"[DEBUG] get_knowledge_units_to_modify LLM output: {llm_output}")
    knowledge_units_to_modify = []
    for item in llm_output.strip().split(','):
        item = item.strip()
        if not item:
            continue
        try:
            num = int(item)
            knowledge_units_to_modify.append(num)
        except ValueError:
            # Optionally print a warning or log
            print(f"[WARN] Skipping invalid ID in LLM output: '{item}'")
    return knowledge_units_to_modify


UPDATER_LLM_PROMPT = """
You are an assistant that manages a knowledge base. 
To perform actions, you must output commands in a specific XML format. 
You can execute multiple commands in a single response.

### Commands
1. ADD: Use <cmd type="add">TEXT</cmd>
2. MODIFY: Use <cmd type="modify" id="1">TEXT</cmd>
3. DELETE: Use <cmd type="delete" id="2" />

### Rules
- "id" must be an integer.
- "text" can be multi-line and contain quotes.
- Do not escape quotes inside the text area.
- You may output multiple <cmd> blocks in sequence.

### Example output
<cmd type="add">
This is the text of the knowledge unit to add.
</cmd>

<cmd type="modify" id="4">
This is the updated text for to replace the existing knowledge unit with ID 4.

The text can be multi-line and contain spaces.
</cmd>

<cmd type="delete" id="9" />

You are given 1) the natural language knowledge base update requests produced by an upstream codex agent, and 2) the existing knowledge units in the knowledge base that need to be modified. If there are no knowledge units to modify, there will be no existing knowledge units provided.
Your task is to produce commands based on the knowledge base update requests and the existing knowledge units.

### Input
1) The natural language knowledge base update requests produced by an upstream codex agent:
{kb_update_request}

2) The existing knowledge units in the knowledge base that need to be modified:
{existing_knowledge_units}
"""

def apply_update_to_kb(text: str, project_dir: Path) -> str:
    """
    Applies the update to the knowledge base.
    """

    # first, we perform a LLM call to convert the natural language KB update requests produced by the codex agent into a series of function calls.

    # Load LLM config to get model, api_base, and provider
    llm_config = load_llm_config()
    model = llm_config['model']
    api_base = llm_config['base_url']
    provider = llm_config['provider']
    

    # The input to the updater LLM is 1) the natural language KB update requests produced by the codex agent, and 2) the existing knowledge units in the knowledge base.
    # for example, the codex agent may want to modify an existing knowledge unit: "Replace backticked `EVENTS_` with `EVENT2_` ". So the updater LLM must know the existing knowledge unit, in order to produce the correct modification. 

    # To do that, we first pass it to an LLM to get the IDs of the knowledge units that need to be modified.
    # We then use that list to retrieve the knowledge units from the knowledge base.
    # Those knowledge units are then passed to the updater LLM to produce the final update.
    knowledge_unit_ids_to_modify = get_knowledge_units_to_modify(text)
    print(f"[DEBUG] knowledge_unit_ids_to_modify: {knowledge_unit_ids_to_modify}")

    # next, we retrieve the knowledge units from the knowledge base.
    knowledge_units = load_consolidated(project_dir)
    knowledge_units = knowledge_units.get("knowledge_units", [])
    knowledge_units_to_modify = [knowledge_units[i] for i in knowledge_unit_ids_to_modify]
    print(f"[DEBUG] knowledge_units_to_modify: {knowledge_units_to_modify}")

    knowledge_units_to_modify_text = str(knowledge_units_to_modify)
    print(f"[DEBUG] knowledge_units_to_modify_text: {knowledge_units_to_modify_text}")

    instruction = UPDATER_LLM_PROMPT.format(kb_update_request=text, existing_knowledge_units=knowledge_units_to_modify_text)

    print(f"[DEBUG] updater LLM instruction: {instruction}")

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": instruction},
        {"role": "user", "content": " "}
    ]

    response = litellm.completion(
        model=model,
        custom_llm_provider=provider,
        messages=messages,
        api_base=api_base
    )

    # Print token usage
    if hasattr(response, 'usage') and response.usage:
        usage = response.usage
        print(f"[INFO] apply_update_to_kb token usage: {usage}")


    # The LLM output is expected to follow this format:
    # <cmd type="add">
    # Welcome to the "Future" of AI.
    # This text spans multiple lines.
    # </cmd>
    
    # <cmd type="modify" id="45">
    # This is the updated text for ID 45.
    # It contains 'single quotes' and "double quotes" without escaping.
    # </cmd>
    
    # <cmd type="delete" id="99" />

    updater_llm_output = response.choices[0].message.content
    print(f"[DEBUG] updater_llm_output: {updater_llm_output}")
    # output is a list of dictionaries, each dictionary containing the function name, id, and text.
    updater_llm_output_commands = parse_updater_output(updater_llm_output)

    # Separate commands by type to avoid index shifting issues
    modify_commands = []
    delete_commands = []
    add_commands = []
    
    for cmd in updater_llm_output_commands:
        if cmd['function'] == 'modify':
            modify_commands.append(cmd)
        elif cmd['function'] == 'delete':
            delete_commands.append(cmd)
        elif cmd['function'] == 'add':
            add_commands.append(cmd)
    
    # Sort delete commands by ID in descending order to prevent index shifting.
    # E.g. if we first delete ID 3, then the original ID 4 will become ID 3, and so on. So later deletes are incorrect.
    delete_commands.sort(key=lambda x: x.get('id', -1), reverse=True)
    
    # Process modifies first (they use original indices)
    for cmd in modify_commands:
        if 'id' in cmd:
            print(f"[DEBUG] Modifying knowledge unit {cmd['id']}: {cmd['text'][:100]}...")
            new_knowledge_unit_title = llm_generate_title(cmd['text'])
            new_knowledge_unit = {
                "heading": new_knowledge_unit_title,
                "body": cmd['text']
            }
            modify_knowledge_unit(project_dir, cmd['id'], new_knowledge_unit)
            print(f"[INFO] Modified knowledge unit {cmd['id']}: {new_knowledge_unit_title}")
    
    # Process deletes in descending order (highest index first)
    for cmd in delete_commands:
        if 'id' in cmd:
            print(f"[DEBUG] Deleting knowledge unit {cmd['id']}")
            delete_knowledge_unit(project_dir, cmd['id'])
    
    # Process adds last (they append to the end)
    for cmd in add_commands:
        print(f"[DEBUG] Adding knowledge unit: {cmd['text'][:100]}...")
        new_knowledge_unit_title = llm_generate_title(cmd['text'])
        new_knowledge_unit = {
            "heading": new_knowledge_unit_title,
            "body": cmd['text']
        }
        add_knowledge_unit(project_dir, new_knowledge_unit)
        print(f"[INFO] Added new knowledge unit: {new_knowledge_unit_title}")
    
    return response.choices[0].message.content


def run_update(args: argparse.Namespace) -> None:
    # Load and print LLM configuration from .env
    try:
        llm_config = load_llm_config()
        print(f"[INFO] LLM Configuration from .env:")
        print(f"[INFO]   MODEL: {llm_config['model']}")
        print(f"[INFO]   BASE_URL: {llm_config['base_url']}")
        print(f"[INFO]   ENV_KEY: {llm_config['env_key']}")
    except SystemExit:
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
    input_dir = Path(input_dir_str)
    
    print(f"[INFO] Working directory: {input_dir}")

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

    # Prompt user for update request
    user_update_request = prompt_input("What would you like to update?")

    print_status(f"Agent in progress...")

    # Launch codex agent
    config_options, env_key = get_codex_config_options()
    
    env = os.environ.copy()
    
    instruction = UPDATE_CODEX_AGENT_PROMPT.format(user_update_request=user_update_request)
    
    command = [
        "codex",
        "exec",
        "--cd",
        str(input_dir.resolve()),
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
    print_agent_block(text, title="Agent Draft")
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

    # Interactive loop: send user feedback until DONE
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

    print_status("Update session completed. Performing the actual updates to the knowledge base...")
    apply_update_to_kb(last_text, project_dir)

    # Clean up temporary file in source file directory
    if dest_file.exists():
        dest_file.unlink()
        # print_status(f"Cleaned up temporary file: {dest_file}")

