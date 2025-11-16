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
Using Socratic to build knowledge base to understand Socratic itself (3-min):
https://youtu.be/R4YpbqQZlpU

Using Socratic to build knowledge base for Google Analytics SQL agent:
https://youtu.be/L20vOB3whMs

## Install 
From Pypi:
```bash
pip install socratic-cli
```

From Source:
```bash
git clone https://github.com/kevins981/Socratic.git
cd socratic

# optional
conda create -n socratic python=3.10 -y
conda activate socratic

# install
pip install -e .
```

Install OpenAI Codex:
```bash
# might need sudo
npm install -g @openai/codex
```

For Web-UI:
```bash
# if npm is not installed
sudo apt install nodejs npm
cd web
npm install
```

## Running
Assume that the project name is `airline_demo` and relevant source files are located in `examples/repos/tau_airline`.

Web UI (recommended):
```bash
# 0. Create project
socratic-cli create --name airline_demo --input_dir examples/repos/tau_airline 

# 1. Launch web UI
cd web
npm run dev:project -- --project airline_demo
```

Command line interface:
```bash
# 0. Create project
socratic-cli create --name airline_demo --input_dir examples/repos/tau_airline 

# 1. Synthesis
# Source documents are stored in examples/repos/tau_airline
socratic-cli synth --project airline_demo

# Add a concept
socratic-cli synth --project airline_demo --add_concept

# Modify a concept
socratic-cli synth --project airline_demo --modify_concept --concept_id 1

# Delete a concept
socratic-cli synth --project airline_demo --delete_concept 1

# 2. Compose agent knowledge prompt
socratic-cli compose --project airline_demo
```

## Supported Models

Socratic works with any LLM that exposes an OpenAI-compatible API, including locally hosted models.

To configure your model, create a `.env` file at the project root (see `.env.example`).

The `.env` file must include:
- `MODEL`
- `BASE_URL`
- `ENV_KEY`
- `PROVIDER`

### Model Quality Notes

Some models do not work well with Codex due to tool-calling issues. In practice:

- **Most stable:** `gpt-5`, `gpt-5.1`
- **Works well:** `glm-4.6`, `grok-4`

In some cases, the model may encouter tool calling problems and therefore fail unexpectedly. E.g., `gpt-oss-120` is known to be unstable. In general, smaller models tend to be more unstable.
Socratic relies on multi-step reasoning and tool operations, so the model must be sufficiently capable to run the full pipeline reliably.


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

## Privacy & Security
- **Local storage:** All files and outputs are stored entirely on your own machine. Socratic does not upload, transfer, index, or store your data anywhere else.
- **Local processing:** All analysis and processing happen locally, **except** when data is sent to an external LLM provider (e.g., OpenAI) using your own API key.
- **Sandboxed terminal agent:** Socratic uses [Codex](https://github.com/openai/codex) as its terminal agent to read and analyze source documents. Socratic runs Codex in read-only mode, preventing the agent from editing files or running commands that require network access. See the [Codex](https://github.com/openai/codex/blob/main/docs/exec.md#non-interactive-mode) [sandbox](https://github.com/openai/codex/blob/main/docs/sandbox.md) documentations for more details.


