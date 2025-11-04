from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from .io_utils import save_as


def build_create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="socratic-cli create",
        description="Create a new project scaffold under projects/{name}.",
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Project name. Creates projects/{name} with default structure.",
    )
    return parser


def run_create(args: argparse.Namespace) -> None:
    name = args.name.strip()
    if not name:
        raise ValueError("--name must be a non-empty string")

    base_dir = Path("projects") / name

    # Create base project directory and subdirectories
    base_dir.mkdir(parents=True, exist_ok=True)
    # (base_dir / "ingest").mkdir(parents=True, exist_ok=True)
    # (base_dir / "synth").mkdir(parents=True, exist_ok=True)

    # Create project.yaml with minimal metadata
    created_at = datetime.now().isoformat(timespec="seconds")
    yaml_content = f"project_name: {name}\ncreated_at: {created_at}\n"
    save_as(yaml_content, base_dir / "project.yaml")

    print(f"[INFO] Created project at {base_dir.resolve()}")


__all__ = [
    "build_create_parser",
    "run_create",
]


