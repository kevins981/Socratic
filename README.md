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

## Installation

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

# 1. Ingest source files
# Source documents are stored in examples/repos/tau_airline
socratic-cli ingest --model gpt-5-mini --input_dir examples/repos/tau_airline/ --project airline_demo

# 2. Run synthesis
# gpt-5 recommended for better quality
# Be careful: if there are many concepts in concept.txt and the size of source documents
# is large, this step may consume non-trivial amount of API tokens. Recommend starting small 
# to get a sense of the cost first.
socratic-cli synth --model gpt-5 \
  --input_dir examples/repos/tau_airline \
  --project airline_demo \
  --key_concepts projects/airline_demo/concepts.txt \
  -n 4

# 3. Compose agent knowledge prompt
socratic-cli compose --project airline_demo --model gpt-5
```
