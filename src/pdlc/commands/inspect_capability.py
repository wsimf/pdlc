#!/usr/bin/env python3
"""NAME
    pdlc inspect capability - read-only: resolve the project's PDLC capability routing

USAGE
    pdlc inspect capability                 # dump every slot and its resolution
    pdlc inspect capability build-run       # one line, ready to paste
    pdlc inspect capability build-run --name   # the configured name, or nothing

DESCRIPTION
    Resolve the project's PDLC capability routing so a calling skill can paste
    the result straight into a sub-agent brief.

    A project declares which specialist skill or sub-agent handles each PDLC seam
    in the ``[agents]`` and ``[skills]`` tables of ``.pdlc/config.toml``. The
    skills never hardcode a tool name; they ask here and inject the answer.

    For an ``agents`` slot the output is just the sub-agent name to dispatch to
    (``general-purpose`` when the slot is unset). For a ``skills`` slot the output
    is an instruction: invoke the configured skill first, or — when the slot is
    unset — the fallback that tells the agent to handle that seam inline.

    ``--name`` answers the narrower question "did the project configure this
    slot at all?". It prints the configured name alone, with no surrounding
    instruction, and prints nothing when the slot is unset — including for an
    ``agents`` slot, where the ``general-purpose`` default is suppressed. A
    calling skill uses it to drop a whole section of a brief when the project
    has no specialist for that seam, rather than pasting a fallback sentence.

FLAGS
    --name    action="store_true": print only the configured skill or sub-agent
              name for SLOT, or nothing when the slot is unset. Requires SLOT.

EXAMPLES
    # Paste-ready routing line for a sub-agent brief.
    pdlc inspect capability build-run

    # Include a verification section only when the project configures build-run.
    pdlc inspect capability build-run --name
"""

from __future__ import annotations

import sys

from pdlc.config import CAPABILITY_SLOTS, get_capabilities
from pdlc.internal.inputs import print_help

# What an agent slot's sub-agent is expected to do, shown only in the dump.
_AGENT_SLOT_NOTE = {
    "core-implementer": "implements [CORE] delivery tasks",
    "ui-implementer": "implements [UI] delivery tasks",
}

# The instruction emitted for a skills slot when the project leaves it unset.
# Each seam still runs; the calling agent does the work itself.
_SKILL_FALLBACK = {
    "build-run": (
        "No build-run skill is configured for this project. Build and run the "
        "app using the workflow documented in AGENTS.md; if you cannot, say so "
        "and exit."
    ),
    "ux-design": (
        "No ux-design skill is configured for this project. Resolve interaction "
        "and visual design from the design references named in AGENTS.md and the "
        "platform's own conventions."
    ),
    "cumulative-review": (
        "No cumulative-review skill is configured for this project. Perform the "
        "cumulative review yourself over the change scope described below."
    ),
    "test-authoring": (
        "No test-authoring skill is configured for this project. Follow the "
        "framework, layout, and house style of the existing test suite."
    ),
    "test-framework": "",
}


def _skill_line(slot: str, name: str | None) -> str:
    if name:
        return (
            f"You must invoke the `{name}` skill before continuing. "
            "If it is not available, say so and exit."
        )
    return _SKILL_FALLBACK.get(slot, "")


def _known(slot: str) -> str:
    """The table a slot belongs to, or a ValueError naming every known slot."""
    for section in ("agents", "skills"):
        if slot in CAPABILITY_SLOTS[section]:
            return section
    known = ", ".join(CAPABILITY_SLOTS["agents"] + CAPABILITY_SLOTS["skills"])
    raise ValueError(f"unknown capability slot {slot!r}. Known slots: {known}")


def _one(slot: str) -> str:
    caps = get_capabilities()
    if _known(slot) == "agents":
        return caps.agent(slot)
    return _skill_line(slot, caps.skill(slot))


def _name(slot: str) -> str:
    """The configured name for a slot, or empty when the project left it unset.
    Callers use the empty answer to omit a section, so no default is applied."""
    caps = get_capabilities()
    table = caps.agents if _known(slot) == "agents" else caps.skills
    return table.get(slot) or ""


def _dump() -> str:
    caps = get_capabilities()
    lines = ["# PDLC capabilities", "", "## Agents", ""]
    for slot in CAPABILITY_SLOTS["agents"]:
        configured = caps.agents.get(slot)
        shown = configured or "general-purpose (default)"
        lines.append(f"- {slot}: {shown} — {_AGENT_SLOT_NOTE[slot]}")
    lines += ["", "## Skills", ""]
    for slot in CAPABILITY_SLOTS["skills"]:
        configured = caps.skills.get(slot)
        shown = configured or "(unset — seam runs inline)"
        lines.append(f"- {slot}: {shown}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    args = command_args
    if any(a in ("-h", "--help") for a in args):
        print_help(__doc__)
        return 0
    name_only = "--name" in args
    args = [a for a in args if a != "--name"]
    if len(args) > 1 or (name_only and not args):
        print("usage: pdlc inspect capability [SLOT] [--name]", file=sys.stderr)
        return 1

    try:
        if not args:
            output = _dump()
        elif name_only:
            output = _name(args[0]) + "\n"
        else:
            output = _one(args[0]) + "\n"
    except ValueError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
