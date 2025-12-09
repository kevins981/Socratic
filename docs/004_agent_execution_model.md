# Agent Execution Model

Socratic delegates most of the synthesis behavior to an agent running inside a Codex execution environment. The execution model is defined along three axes: working directory, access rights, and responsibilities.

### Working Directory and Access Boundaries

During a synthesis session:

- The agent’s working directory is set to the working knowledge base under the input source documents directory.
- Within this directory, the agent has full read and write access and is expected to add, edit, or delete markdown files representing knowledge units. This directory is the agent’s mutable copy of its current understanding, independent from the input source materials.
- The parent directory contains the input source documents. The agent can read from this location but is not allowed to modify anything there, ensuring that the original evidence remains stable across synthesis runs.

This structure enforces a clear separation:

- **Mutable layer**: the working knowledge base directory, where the agent encodes its evolving understanding.
- **Immutable evidence layer**: the input source documents directory, which remains unchanged and can be re-read at any time.

### Example Directory Layout

Consider a project whose input source documents live under `examples/repos/airline_demo`:

- `examples/repos/airline_demo/` — input source documents (code, specs, and other raw artifacts).
- `examples/repos/airline_demo/knowledge_base/` — working knowledge base directory that the agent treats as its mutable copy of domain understanding.

During synthesis, the Codex agent’s working directory is set to `examples/repos/airline_demo/knowledge_base/`. From the agent’s perspective:

- Paths under `.` refer to knowledge base files that it may freely read and modify.
- Paths under `../` refer to input source documents that it may read but must not attempt to modify.

### Codex Agent Sandbox Configuration

The Codex agent is launched with a sandbox configuration that enforces this separation of responsibilities:

- The working directory (`--cd`) is set to the knowledge base directory under the input source documents tree.
- The sandbox mode is set to allow read/write access only within this working directory, while treating parent directories as read-only.

At a high level, the execution is configured as follows:

- `--cd <input_src_docs_dir>/knowledge_base` ensures that all relative paths the agent writes to are scoped to the knowledge base.
- A workspace-scoped sandbox mode (for example, `workspace-write`) grants write permission inside the working directory but denies writes outside it.
- The system prompt explicitly tells the agent that:
  - the knowledge base lives in the current directory and is expected to be edited; and
  - the input source documents live in `../` and are available only for reading.

Together, this directory layout and sandbox configuration give the agent direct read/write control over its own knowledge base copy, while preserving the input source documents as immutable evidence. 
