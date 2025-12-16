from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from .io_utils import load_project_config, print_status


def build_export_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="socratic-cli export",
        description="Export knowledge base to a single markdown file.",
    )
    parser.add_argument(
        "--project",
        required=True,
        help="Project name; must match a folder under projects/",
    )
    parser.add_argument(
        "--format",
        choices=["agentmd"],
        default="agentmd",
        help="Export format (currently only 'agentmd' is supported)",
    )
    return parser


def export(
    project_name: str,
    project_dir: Path,
    export_format: str,
) -> None:
    """
    Export knowledge base files to a single concatenated markdown file.
    
    Args:
        project_name: Name of the project
        project_dir: Path to the project directory
        export_format: Export format (currently only 'agentmd')
    """
    # Knowledge base directory
    kb_dir = project_dir / "knowledge_base"
    
    # Validate knowledge base directory exists
    if not kb_dir.exists():
        raise SystemExit(
            f"Knowledge base directory not found: {kb_dir}\n"
            f"The project '{project_name}' may not have a knowledge base yet."
        )
    
    # Get all .md files and sort alphabetically
    md_files = sorted(kb_dir.glob("*.md"))
    
    if not md_files:
        raise SystemExit(
            f"No markdown files found in knowledge base directory: {kb_dir}\n"
            f"The knowledge base for project '{project_name}' appears to be empty."
        )
    
    print_status(f"Found {len(md_files)} markdown file(s) in knowledge base")
    
    # Build output filename with ISO 8601 timestamp
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    output_filename = f"{project_name}_{timestamp}.md"
    output_path = project_dir / output_filename
    
    # Concatenate files with newlines between them
    content_parts = []
    for md_file in md_files:
        print_status(f"Reading {md_file.name}")
        file_content = md_file.read_text(encoding="utf-8")
        content_parts.append(file_content)
    
    # Join with newline separator
    combined_content = "\n".join(content_parts)
    
    # Write output file
    output_path.write_text(combined_content, encoding="utf-8")
    
    print_status(f"Exported knowledge base to: {output_path}")
    print(f"\nExport completed successfully!")


def run_export(args: argparse.Namespace) -> None:
    """
    Entry point for the export subcommand.
    """
    # Validate project directory under projects/
    project_dir = Path("projects") / args.project
    if not project_dir.exists() or not project_dir.is_dir():
        raise SystemExit(
            f"Project '{args.project}' not found under projects/. "
            f"Please ensure 'projects/{args.project}' exists and try again."
        )
    
    # Load project configuration
    config = load_project_config(args.project)
    project_name = config.get("project_name", args.project)
    
    print(f"[INFO] Exporting knowledge base for project: {project_name}")
    print(f"[INFO] Format: {args.format}")
    
    # Call main export function
    export(
        project_name=project_name,
        project_dir=project_dir,
        export_format=args.format,
    )


__all__ = [
    "build_export_parser",
    "export",
    "run_export",
]
