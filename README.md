# Socratic: Automated Knowledge Synthesis for Vertical LLM Agents

_Transform unstructured domain data into structured, agent-ready knowledge - automatically._


## Overview

Socratic is a tool that automates **knowledge synthesis for vertical LLM agents** - agents specialized in specific domains.

Socratic ingests sparse, unstructured source documents (docs, code, logs, etc.) and synthesizes them into **compact, structured knowledge bases** ready to plug into agents.

##  Why Socratic?

Building effective domain agents requires high-quality, domain-specific knowledge. Today, this knowledge is:

* Manually curated by experts 🧠
* Costly to maintain 💸
* Quickly outdated as source documents change ⚠️

The goal of Socratic is to automate this process, enabling accurate and cost effective domain knowledge management.

## Demo
https://youtu.be/BQv81sjv8Yo?si=r8xKQeFc8oL0QooV

## How It Works

Socratic uses a combination of LLM and LLM agents. Socratic contains 3 stages: ingest, synthesis, and compose. 

### 1. **Ingest**

Given a directory containing documents relevant to the vertical task, Socratic extracts a list of candidate **concepts to research**. This is done collaboratively between the user and a terminal agent. 

* User provides high-level research directions.
* A terminal agent (codex) quickly scans the source documents to gain context and proposes concepts to research.
* User further refines and finalizes the list of concepts.

The ingest stage generates the final set of concepts to research (`concepts.txt`).

### 2. **Synthesis**

For each concept to research generated in the ingest stage, Socratic launches a terminal agent (codex) that explores the source documents to synthesize knowledge related to the specific concept. 

For each concept, the synthesis stores the synthesized knowledge in both plain text (`concept{i}-synth.txt`) and JSON format (`concept{i}-synth.json`). 

### 3. **Compose**

Convert synthesized knowledge into prompts that are ready to be dropped directly into your LLM agent’s context.

## Install from Pypi
```bash
pip install socratic-cli
```

## Install from Source

```bash
git clone https://github.com/kevins981/Socratic.git
cd socratic

# optional
conda create -n socratic python=3.10 -y
conda activate socratic

# install
pip install -e .
```

## OpenAI API
Currently only OpenAI models are supported, and an OpenAI API key is required.
```bash
export OPENAI_API_KEY="your_api_key_here"
```

## Example Workflow

```bash
# 0. Create project
socratic-cli create --name airline_demo

# 1. Synthesis
# Source documents are stored in examples/repos/tau_airline
socratic-cli synth --model gpt-5 \
  --input_dir examples/repos/tau_airline \
  --project airline_demo \
  -n 4

# Add 
socratic-cli synth --model gpt-5-mini --project airline_demo --add_concept  "modification policy" --input_dir examples/repos/tau_airline/

# 2. Compose agent knowledge prompt
socratic-cli compose --project airline_demo --model gpt-5
```

Web UI:
```bash
cd web
npm run dev:project -- --project google_analytics
```

## Privacy & Security
- **Local storage:** All files and outputs are stored entirely on your own machine. Socratic does not upload, transfer, index, or store your data anywhere else.
- **Local processing:** All analysis and processing happen locally, **except** when data is sent to an external LLM provider (e.g., OpenAI) using your own API key.
- **Sandboxed terminal agent:** Socratic uses [Codex](https://github.com/openai/codex) as its terminal agent to read and analyze source documents. Socratic runs Codex in read-only mode, preventing the agent from editing files or running commands that require network access. See the [Codex](https://github.com/openai/codex/blob/main/docs/exec.md#non-interactive-mode) [sandbox](https://github.com/openai/codex/blob/main/docs/sandbox.md) documentations for more details.


