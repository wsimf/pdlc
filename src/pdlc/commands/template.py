"""NAME
    pdlc template - print a bundled evidence template

USAGE
    pdlc template NAME

DESCRIPTION
    Print the named template as Markdown to stdout: the outline a body must
    follow and the rules for filling it in.

    A `post` command that takes a templated body checks it against the same
    template before changing anything, and refuses one that is missing a
    required section, leaves a section empty, or keeps an unfilled
    `- <placeholder>` bullet; its error lists every problem and prints the
    template again. Each `### ` heading in the template is a required section
    unless it is marked `<!-- optional -->`; headings the template does not
    declare are allowed.

    This command is local and read-only; it does not load project
    configuration or contact a backend. `pdlc template --help` lists the
    available templates.

EXAMPLES
    pdlc template implementation-summary
"""

from __future__ import annotations

import sys

from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help
from pdlc.templates.template import load_template, template_names


def _help() -> str:
    names = "\n".join(f"  {name}" for name in template_names())
    return f"{__doc__.strip()}\n\nAVAILABLE TEMPLATES\n{names}"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if any(argument in ("-h", "--help") for argument in args):
        print_help(_help())
        return 0
    if len(args) != 1:
        print("usage: pdlc template NAME", file=sys.stderr)
        return 1
    try:
        sys.stdout.write(load_template(args[0]))
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
