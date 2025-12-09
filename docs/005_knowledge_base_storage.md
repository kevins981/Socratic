# Knowledge Base Storage Model

This knowledge base is represented as a collection of markdown files, each capturing a single, coherent knowledge unit. The storage model is intentionally simple so that the knowledge base remains easy to inspect, version, and evolve alongside the source repository.

## File Layout and Naming

All knowledge units are stored directly in a single directory dedicated to the knowledge base. Each unit is a standalone markdown file whose filename encodes both its order and its subject.

- Filenames follow the pattern `00X_<name>.md`, where `X` is a zero-padded integer starting at `1`.
- The numeric prefix imposes a stable, human-chosen ordering over units, independent of filesystem sort order.
- The `<name>` segment is a short, descriptive identifier that reflects the primary topic of the unit rather than its exact wording.
- The file extension is always `.md`, indicating that content is written in markdown.

This convention makes it straightforward to navigate the knowledge base using standard filesystem tools while preserving a logical reading order.

## Knowledge Unit Granularity

Each file is intended to represent one conceptual knowledge unit: a chapter- or section-sized explanation focused on a single theme. Units should be internally cohesive and externally decoupled:

- Internally cohesive: a unit should fully explain its topic at the appropriate level of abstraction, including necessary definitions and context.
- Externally decoupled: cross-references to other units are allowed, but units should not rely on implicit, undocumented behavior from other files.

This granularity supports incremental evolution: new concepts are typically added as new files, while substantial re-interpretations of an existing concept result in edits to the corresponding file.

## Versioning and Evolution

The knowledge base is stored alongside the rest of the repository and is managed with the same version control mechanisms. Changes to the knowledge base are made as explicit edits to markdown files:

- New knowledge is introduced by creating new files that adhere to the naming convention.
- Existing knowledge is refined by editing the corresponding file in place.
- Obsolete or superseded knowledge units may be removed entirely, with their historical versions retained by version control.

This approach ensures that the evolution of the knowledge base is auditable and can be correlated with changes in the surrounding code and documentation.

