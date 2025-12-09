# Synth Subcommand: Purpose and Execution Model

## Role of `socratic-cli synth`

The `synth` subcommand is the primary entry point for running a synthesis session on a project-specific knowledge base. Conceptually, it:

- Treats a project as a pairing of input source documents and an associated knowledge base.
- Spawns an expert “knowledge base maintainer” agent whose job is to update markdown knowledge units under user guidance.
- Runs an interactive loop where the user issues natural-language instructions and the agent proposes and applies global patches to the knowledge base.

From the user’s perspective, `synth` is the command that turns a repository of raw artifacts into a curated, evolving knowledge base.

## Knowledge Base Organization

Each project has a single authoritative knowledge base:

- The knowledge base lives under `projects/<name>/knowledge_base/`.
- It consists exclusively of markdown files, each representing a single knowledge unit (for example, a conceptual area, subsystem, or major concern).
- File names follow the pattern `00X_<name>.md`, where:
  - `00X` is a zero-padded, monotonically increasing integer that orders units.
  - `<name>` is a short, descriptive, hyphen- or underscore-separated identifier.

Within a file:

- The content is written in textbook-style prose with clear headings.
- Each unit is self-contained enough to be read on its own, but may implicitly reference other units.

From the perspective of `synth`, the knowledge base is simply “all markdown files in the `knowledge_base/` directory.” There are no additional indexing or metadata structures; ordering and structure are encoded directly in filenames and headings.

## Project and Directory Layout

Each synthesis session is scoped to a named project:

- The user invokes `socratic-cli synth --project <name>`.
- The project directory is resolved as `projects/<name>`, and must already exist as a directory.
- Project-level configuration is loaded to locate the input source documents directory. That directory is treated as the immutable source of truth for raw artifacts.
- Within the project directory, a `knowledge_base/` subdirectory contains the authoritative markdown knowledge units for that project.

The synthesis workflow distinguishes:

- **Input source documents directory**: the read-only collection of code, documentation, and other artifacts to study.
- **Project knowledge base directory**: the version-controlled markdown representation of synthesized understanding.

## Knowledge Base Duplication and Change Tracking

To enable safe editing and diff-based review, `synth` works with two copies of the knowledge base during a session:

- **Project copy (`project_dir/knowledge_base`)**: the authoritative state before and after synthesis.
- **Working copy (`input_src_docs_dir/knowledge_base`)**: a temporary copy the agent directly edits.

At the start of a session:

1. Any existing working copy is deleted.
2. The project copy is recursively copied into the working location.

During the session, only the working copy is mutated by the agent. The project copy remains unchanged until the tool synchronizes changes back.

After each agent response in terminal mode, the tool:

1. Compares the working and project copies directory-by-directory.
2. Derives added, deleted, and modified files via content comparison.
3. Prints a human-readable, colorized summary and unified diffs for modified knowledge units.
4. Applies the working copy back onto the project copy so that the project directory reflects the latest accepted state.

This design treats the project directory as the stable, user-visible knowledge base, while using the working copy as an internal scratch space for the agent.

## Interactive Session Flow

At a high level, a synthesis session proceeds as follows:

1. **Initial instruction.** When `synth` starts, it prompts the user with “What should we work on?” and reads a free-form natural-language instruction.
2. **Agent invocation.** It invokes the Codex execution environment in the working knowledge base directory, passing the synthesized agent prompt plus the user’s instruction as the initial JSON payload.
3. **First response and sync.** It parses the agent’s initial response, displays it as an “Agent Draft” in terminal mode, and immediately synchronizes the working knowledge base back into the project knowledge base with a detailed diff.
4. **Threaded interaction.** It extracts a thread identifier from the Codex output and enters an interactive loop:
   - The user types follow-up feedback or new instructions.
   - `synth` resumes the same agent thread with the new user message.
   - The agent returns an updated response that may further edit knowledge units.
   - The tool prints the response (“Agent Update”) and re-runs synchronization and diffing.
5. **Session termination.** The loop continues until the user exits (for example, via end-of-input or interrupt). The final state of the project knowledge base remains on disk for later review and version control.

This loop allows users to incrementally refine the knowledge base, treating each agent turn as an opportunity to inspect and correct both the narrative output and the underlying markdown files.

## CLI and Web UI Modes

The `synth` subcommand supports two interaction modes:

- **Terminal mode** (default):
  - The agent works directly in the knowledge base directory under the input source documents tree.
  - After each agent turn, `synth` automatically synchronizes changes back into the project’s `knowledge_base/` directory and prints a recursive diff summary.
  - This mode assumes the user will use standard tools (for example, `git diff`) to further review and manage changes.

- **Web UI–friendly mode**:
  - The agent is still run against the working copy of the knowledge base, but automatic synchronization into the project directory is skipped.
  - The web UI is responsible for presenting per-file changes and managing user approval, writing accepted changes into the project knowledge base.

Functionally, both modes share the same agent behavior and knowledge base manipulation model. They differ only in how and when proposed changes are propagated back to the project directory and surfaced to the user for approval.
