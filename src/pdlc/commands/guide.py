"""NAME
    pdlc guide - print a bundled Markdown guide for PDLC agents

USAGE
    pdlc guide [SUBCOMMAND]

DESCRIPTION
    Print ``guides/SUBCOMMAND.md`` as Markdown to stdout, or ``guides/guide.md``
    when no subcommand is supplied. This command is
    local and read-only; it does not load project configuration or contact a
    backend. Use ``pdlc guide guide`` for the general agent guide.
"""

from __future__ import annotations

from importlib.resources import files
import sys

from pdlc.internal.inputs import print_help


def _guide_names() -> list[str]:
    return sorted(
        resource.name.removesuffix(".md")
        for resource in files("pdlc.guides").iterdir()
        if resource.name.endswith(".md")
    )


def _help() -> str:
    guides = "\n".join(f"  {name}" for name in _guide_names())
    return f"{__doc__.strip()}\n\nAVAILABLE GUIDES\n{guides}"


def _guide(subcommand: str) -> str:
    if not subcommand or subcommand in {".", ".."} or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        for character in subcommand
    ):
        raise FileNotFoundError(subcommand)
    return files("pdlc.guides").joinpath(f"{subcommand}.md").read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if any(argument in ("-h", "--help") for argument in args):
        print_help(_help())
        return 0
    if len(args) > 1:
        print("usage: pdlc guide [SUBCOMMAND]", file=sys.stderr)
        return 1
    subcommand = args[0] if args else "guide"
    try:
        sys.stdout.write(_guide(subcommand))
    except (FileNotFoundError, OSError, UnicodeError):
        print(f"No guide found for {subcommand}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
