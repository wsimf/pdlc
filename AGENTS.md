# PDLC

This repository contains the installable `pdlc` CLI and its GitHub-native product-development workflow. Keep both surfaces simple, typed, and behaviorally aligned.

## Work sequence

1. Read `git status --short` first and preserve unrelated staged, unstaged, and untracked work.
2. Trace the concrete caller, backend seam, and tests before changing behavior; use `rg` and direct file reads rather than guessing from names.
3. Make the smallest scoped change. Keep domain policy pure, keep host I/O behind the host ports, and keep CLI parsing at the command boundary.
4. Run the focused tests, then the full `tests/` suite and packaging checks when their surfaces changed.
5. Re-read the diff, run `git diff --check`, and report exactly what was validated; separate static, test, build, GitHub, and runtime evidence.

Done means every modified behavior has a caller, a regression check or an explicit reason it cannot have one, and clean diff/check output.

## Repository map

- `src/pdlc/cli.py` dispatches `inspect`, `next`, and `post` commands; `exec` is a compatibility alias and global CLI options become `Config` overrides layered over `.pdlc/config.toml` for that run. `prepare` and `cleanup` are human-only worktree commands, intentionally absent from `--help` and the agent workflow: `prepare` is backend-free scaffolding except `--after`, which resolves the predecessor work item and records it in the worktree's Git config for `inspect implement` to stack on, `cleanup` resolves the work item to confirm it is Complete before tearing down its worktree and `gh stack` branches.
- `src/pdlc/commands/` owns command orchestration and user-facing argument/error handling.
- `src/pdlc/domain/` owns pure lifecycle, evidence, model, and completion policy.
- `src/pdlc/hosts/*_provider.py` exposes concrete providers; `hosts/lib/{azure,github,file,none}/` owns their implementations, and `workitem_host/`, `code_host/`, and `attachment_host/` retain neutral ports and selection.
- `src/pdlc/internal/` owns shared facades and implementation helpers; callers should use these seams instead of reaching into a backend.
- `tests/` contains package-level Python tests.
- `agent/skills/` contains the agent-facing PDLC skills and their references; they drive the workflow through the installed `pdlc` CLI, which is expected on `PATH`.
- `agent/sub-agents/` contains Claude and Codex specialist declarations.

When changing a lifecycle command or its evidence contract, inspect the matching package command under `src/pdlc/commands/` and the skills that call it, then update their tests/docs together when both surfaces are affected.

Skill and sub-agent instructions describe the CLI as a contract, never as an implementation. State only as much of the command's expected outcome as the step needs to verify — the state it leaves behind, the fields it reads back, what a failure does or does not touch. Do not narrate the steps the script runs internally to get there; those are free to change without touching a single skill.

Do not repeat in a skill or sub-agent anything the command's `--help` already documents — flags, input forms, output fields, refusal reasons, sample output. Name the command the step uses and let the agent run `pdlc <command> --help` for the rest; a duplicated copy drifts from the CLI.

Do not explain PDLC itself to the agent running a skill or sub-agent — what the lifecycle is, how gates, markers, or evidence work, or why a rule exists. Tell it only what it can use PDLC for in its own task: which command gets it the information or transition it needs, and what to do with the result. The `pdlc` entry skill is the one exception: it gives a short model of work items, workflows, gates, and human boundaries without naming any workflow's stages, and links `pdlc guide contract` for the rest.

Skills, sub-agents, and `src/pdlc/guides/` pass command input as a file path or `text:<body>`, never as `-` for stdin, so every documented invocation works the same across shells and platforms. The CLI still accepts `-` as a convenience for humans, and command `--help` keeps documenting it.

## PDLC workflow

The lifecycle is data-driven: a work item's type selects its workflow, and the workflow definition supplies the stages, gates, transitions, and owners. The Feature pipeline is the only workflow today, and more will follow, so never assume a stage order up front. Stage skills belong to the stages they own, but the `pdlc` and `pdlc-loop` skills, the guides, and routing code must not name a workflow's stages or predict the next stage from the current one; they follow `# Due Next`. Gate state controls whether work is pending, under review, awaiting approval, blocked on CI, stale, or complete.

For lifecycle behavior, read `pdlc guide contract` first. For a work-item orientation, use the read-only `agent/skills/pdlc/SKILL.md`; for queue execution, use `agent/skills/pdlc-loop/SKILL.md`; for a stage, use that stage's `SKILL.md` and only its triggered references.

Use the controller and owning skill for routing. Work-item state, evidence markers, task identity, PR linkage, and completion readiness are machine-checked; do not infer them from prose, branch names, checkboxes, or recent files.

Treat `pdlc inspect*` commands as read-only. Treat `pdlc post *` commands as state-mutating workflow operations and run them only when the task explicitly authorizes that transition. Human approval, skip, decision resolution, and completion remain explicit driver actions.

## Development

The package requires Python `>=3.12` and uses `uv`; project metadata in `pyproject.toml` is the source of truth for packaging and entry points.

```bash
XDG_CACHE_HOME=/tmp/pdlc-uv-cache uv run ruff check src tests
XDG_CACHE_HOME=/tmp/pdlc-uv-cache uv run mypy
XDG_CACHE_HOME=/tmp/pdlc-uv-cache uv run python -m unittest discover -s tests -p 'test_*.py'
XDG_CACHE_HOME=/tmp/pdlc-uv-cache uv build
git diff --check
```

For local workflow scenarios set `[backend] name = "file"` in `.pdlc/config.toml` and point `PDLC_HOME` at a temporary directory. The default work-item backend is GitHub; the file backend persists records under `.pdlc` unless `PDLC_HOME` overrides it. Code-host selection follows `[code_host] name`, and attachments follow `[attachment_host] name`. Only `PDLC_HOME`, `PDLC_REPOSITORY`, and `PDLC_DEBUG` are read from the environment; every other setting is a config-file key.

The skills name no project-specific tool. A consuming repo routes each seam to its own specialist skill or sub-agent through the `[agents]` and `[skills]` tables of `.pdlc/config.toml`, read back by `pdlc inspect capability`; an unset slot falls back to `general-purpose` or an inline seam. The slot contract lives in `pdlc guide capabilities`.

For Python syntax validation in this environment, use `PYTHONPYCACHEPREFIX=/tmp/pdlc-pycache python3 -m compileall -q src`; this proves compilation only, not GitHub, build, simulator, or runtime behavior.

## Writing command help

Every command's printed `--help` (its module docstring under `src/pdlc/commands/`) and the
top-level `pdlc --help` (`_usage()` in `src/pdlc/cli.py`) follow the same section convention,
adapted from `gh`'s help layout to pdlc's own read-only/mutating split:

- The top-level `pdlc --help` is the only "parent with children" surface in the CLI — every
  other command is a leaf with no sub-commands of its own. Its sections are `USAGE`,
  `READ-ONLY COMMANDS` (setup, inspect*, next), `MUTATING COMMANDS` (post*), `FLAGS` (the
  global `--repo`/`--project-number`/`--project-owner`/`--backend`/`--home` overrides),
  `ARGUMENTS`, `EXAMPLES`, and `LEARN MORE`.
- A leaf command's docstring never lists sub-commands: it has no `COMMANDS` section, only
  whatever subset of `NAME`, `USAGE`, `DESCRIPTION`, `FLAGS`, and `EXAMPLES` applies. `NAME` is
  one line, `pdlc <command> - <one-line summary>`. `USAGE` holds the invocation synopsis
  line(s) that were previously embedded mid-paragraph. When a command has more than one
  invocation form and the right one depends on state (e.g. creating a new record vs.
  updating an existing one, or which stage/mode a flag selects), spell out the condition
  inline rather than listing bare alternatives — `- if <condition>:` followed by the
  indented invocation — so an agent can tell which form applies without reading the whole
  `DESCRIPTION`. `DESCRIPTION` carries the full
  behavioral prose — evidence formats, JSON shapes, gate semantics, sample output — moved
  under the heading verbatim, never trimmed or summarized — except its opening paragraph,
  which states only what the command does: no internal mechanics ("how"), no naming other
  pdlc commands/stages, no assuming familiarity with the wider PDLC lifecycle. Mechanics,
  rationale, and cross-references belong in the paragraphs after it. `FLAGS` lists every flag the
  command accepts — positional arguments stay in `USAGE` only — one line per flag naming its
  input type (`TEXT`, `FILE|-`, a fixed set of literals, `action="store_true"`, repeatable)
  and what it does; this holds even for `--attachment`/`--attachment-description`, which are
  otherwise documented once in the top-level help. `USAGE` stays the synopsis; it is never
  trimmed to compensate for `FLAGS` spelling things out.
- A command's docstring is its behavioral contract, not decorative help text (see "Skill and
  sub-agent instructions" above) — restructuring it into sections must never delete or
  paraphrase the contract prose, only relocate it.
- Keep the top-level `_usage()` one-liner for a command in sync with that command's own
  docstring whenever a flag or argument changes; a change to one without the other is a bug.

## Change hygiene

Use `apply_patch` for edits. Keep Markdown sentences on one source line. Add comments only where they explain a contract, ownership boundary, or non-obvious constraint, and keep them current.

Do not broaden a change into workflow redesign, backend migration, publishing, or destructive cleanup without explicit scope. Stage only named paths, and report any pre-existing or unrelated dirty state separately.
