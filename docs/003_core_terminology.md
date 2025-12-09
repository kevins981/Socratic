# Core Terminology

## Input Source Documents

Input source documents are the raw artifacts that describe a system or domain. They typically include code, documentation, configuration files, and other text-based materials. Conceptually:

- They are treated as the immutable source of truth about how the system actually behaves.
- They are read by the agent as evidence during synthesis.
- They are not modified by synthesis; all persistent changes are made to the knowledge base instead.

## Knowledge Base

The knowledge base is the curated representation of understanding derived from the input source documents and user guidance. It:

- Lives inside the project directory under a `knowledge_base/` subdirectory.
- Consists entirely of markdown files, each representing a single knowledge unit.
- Is intended to be version-controlled and reviewed like source code.

There are two distinct roles the knowledge base can play during a synthesis session:

- **User knowledge base**: the copy under the project directory that represents the current, user-approved state.
- **Agent knowledge base**: a temporary working copy made under the input source documents directory that the agent edits directly during an active session.

The user knowledge base is the long-lived, user-facing view. The agent knowledge base is an internal scratch space used to propose and apply changes safely during a single synthesis run.

## Knowledge Units

A knowledge unit is a single markdown file in the knowledge base that captures a coherent, related set of ideas. Each unit:

- Focuses on a specific concept, subsystem, workflow, or design concern.
- Uses structured headings and concise prose suitable for deep reading.
- Is written to be self-contained, though it may implicitly rely on context from other units.

File naming follows a stable convention:

- Each file is named `00X_<name>.md`, where:
  - `00X` is a zero-padded integer that orders units.
  - `<name>` is a short, descriptive identifier.

This scheme makes it easy to scan and reorder units while keeping filenames stable for version control.
