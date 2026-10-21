#!/usr/bin/env python3
"""NAME
    pdlc config - read-only: print the configuration in effect for the current directory

USAGE
    - to list every setting:
        pdlc config
    - to read one setting:
        pdlc config NAME

DESCRIPTION
    Prints the configuration values that apply to the current directory, after
    every layer is merged: the home file and its matching repository section,
    the repository's `.pdlc/config.toml`, and any global CLI flags.

    NAME is a setting's `table.key` path (`code.github.ignored_checks`) or its
    bare field name (`ignored_checks`). With NAME it prints the value alone: a
    list one item per line, a boolean as `true` or `false`, and nothing at all
    when the setting is unset or the list is empty. Without NAME it prints one
    `table.key = value` line per setting, with `(unset)` for an unset one.

    An unknown NAME exits 1 and names the valid settings. The command writes
    nothing and needs no tracker access; `pdlc doctor` additionally reports
    which file supplied each value and validates the whole configuration.

EXAMPLES
    pdlc config
    pdlc config ignored_checks
    pdlc config code.github.repository
"""

from __future__ import annotations

import json
import sys

from pdlc.config import CONFIG_FIELDS, FIELD_LOCATIONS, get_config
from pdlc.internal.inputs import print_help


def _field(name: str) -> str | None:
    if name in FIELD_LOCATIONS:
        return name
    table, _, key = name.rpartition(".")
    return CONFIG_FIELDS.get((table, key))


def _value_lines(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bool):
        return ["true" if value else "false"]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def _listing(value: object) -> str:
    if value is None:
        return "(unset)"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value))
    return json.dumps(value) if isinstance(value, str) else str(value)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    # Bare `pdlc config` lists every setting, so only an explicit flag asks for help.
    if any(argument in ("-h", "--help") for argument in args):
        print_help(__doc__)
        return 0
    if len(args) > 1:
        print("usage: pdlc config [NAME]", file=sys.stderr)
        return 1
    config = get_config()
    if not args:
        for field, location in FIELD_LOCATIONS.items():
            print(f"{location} = {_listing(getattr(config, field))}")
        return 0
    field = _field(args[0])
    if field is None:
        print(f"pdlc: unknown setting {args[0]!r}; valid settings: {', '.join(FIELD_LOCATIONS.values())}", file=sys.stderr)
        return 1
    for line in _value_lines(getattr(config, field)):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
