# Socratic: KnowledgeOps for Expert-Level Domain Agents

Socratic is a KnowledgeOps platform that helps teams build expert-level knowledge base for vertical, domain-specific agents.
You point Socratic at your existing domain docs, and Socratic collaborates with you to build a curated and reliable knowledge base that you actually trust.

Socratic is a **KnowledgeOps platform** that helps teams build *expert-level*, trustworthy knowledge bases for vertical, domain-specific agents.  
Point Socratic at your existing docs, and collaborate with Socratic to synthesize a **curated, reliable, auditable knowledge base**.

![GitHub commit activity](https://img.shields.io/github/commit-activity/m/kevins981/Socratic)
![GitHub License](https://img.shields.io/github/license/kevins981/Socratic)
![Static Badge](https://img.shields.io/badge/model%20support-openai,openrouter,local-orange)
![GitHub Repo stars](https://img.shields.io/github/stars/kevins981/Socratic)




## Overview
High-quality domain knowledge is *critical* for building high-value agents.  

Today, most teams rely on "document dump" workflows (e.g., RAG): give the agent all the files and hope it interprets them correctly.  
But this fails for the same reason it would with a human - you wouldn't onboard a new hire by handing them a folder of docs and saying "good luck."

| Traditional Document Dumps (e.g., RAG)       | Socratic (KnowledgeOps)                     |
|-----------------------------------------|----------------------------------------------|
| ❌ "Hope-based" knowledge retrieval       | ✅ Expert-controlled curation                |
| ❌ Agent misinterprets raw docs          | ✅ Guided, human-in-the-loop knowledge distillation      |
| ❌ Opaque, “black box” knowledge         | ✅ Clear, auditable knowledge base           |
| ❌ Hard to detect contradictions         | ✅ Surfaces ambiguities and inconsistencies  |


Socratic rethinks how expert knowledge should be distilled. It treats knowledge building like teaching a human expert: capturing tacit rules, resolving ambiguities, surfacing edge cases, and clarifying domain intuitions.

Socratic does this by combining:
- **Interactive collaboration with the human expert**  
  Socratic asks high-quality questions, identifies ambiguities, and requests clarification.
- **Grounded research over your actual domain documents**  
  It reads your code, specs, and docs to extract accurate conceptual models.
- **Knowledge as a first-class artifact**  
  It generates clean, modular, plain-text knowledge units - fully auditable and directly usable by downstream agents.
- **Human-in-the-loop curation**  
  Every proposed change can be inspected, diffed, refined, and explicitly approved.

The result is a **structured, trustworthy knowledge base**, not an opaque embedding index  giving you control over what your agent *actually knows*.


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
# Create project
socratic-cli create --name airline_demo --input_dir examples/repos/tau_airline

# Start working on your knowledge base!
socratic-cli synth --project airline_demo

# Digest model to look deeper into your existing knowledge base
socratic-cli digest --project airline_demo
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

## Privacy & Security
- **Local storage:** All files and outputs are stored entirely on your own machine. Socratic does not upload, transfer, index, or store your data anywhere else.
- **Local processing:** All analysis and processing happen locally, **except** when data is sent to an external LLM provider (e.g., OpenAI) using your own API key.
- **Sandboxed terminal agent:** Socratic uses [Codex](https://github.com/openai/codex) as its terminal agent to read and analyze source documents. Socratic runs Codex in read-only mode, preventing the agent from editing files or running commands that require network access. See the [Codex](https://github.com/openai/codex/blob/main/docs/exec.md#non-interactive-mode) [sandbox](https://github.com/openai/codex/blob/main/docs/sandbox.md) documentations for more details.


