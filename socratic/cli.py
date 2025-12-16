import argparse
import sys
from .synth import build_synth_parser, run_synth
from .create import build_create_parser, run_create
from .digest import build_digest_parser, run_digest
from .export import build_export_parser, run_export

def build_root_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="socratic-cli",
        description="Socratic CLI with simple subcommands",
    )
    parser.add_argument(
        "command",
        choices=["synth", "create", "digest", "export"],
        help="Subcommand to run",
    )
    return parser


def main() -> None:
    if len(sys.argv) < 2:
        build_root_parser().print_help()
        sys.exit(1)

    root_parser = build_root_parser()
    # Parse only the first positional command
    root_args, _ = root_parser.parse_known_args(sys.argv[1:2])

    command = root_args.command

    if command == "synth":
        sub_parser = build_synth_parser()
        sub_args = sub_parser.parse_args(sys.argv[2:])
        run_synth(sub_args)
        return

    if command == "create":
        sub_parser = build_create_parser()
        sub_args = sub_parser.parse_args(sys.argv[2:])
        run_create(sub_args)
        return

    if command == "digest":
        sub_parser = build_digest_parser()
        sub_args = sub_parser.parse_args(sys.argv[2:])
        run_digest(sub_args)
        return

    if command == "export":
        sub_parser = build_export_parser()
        sub_args = sub_parser.parse_args(sys.argv[2:])
        run_export(sub_args)
        return

    root_parser.error(f"Unknown command: {command}")


if __name__ == "__main__":
    main()


