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

- `src/pdlc/cli.py` dispatches `inspect`, `next`, and `post` commands; `exec` is a compatibility alias and CLI options become `PDLC_*` environment variables.
- `src/pdlc/commands/` owns command orchestration and user-facing argument/error handling.
- `src/pdlc/domain/` owns pure lifecycle, evidence, model, and completion policy.
- `src/pdlc/hosts/` owns GitHub, file, and no-op adapters for work items, code hosts, and attachments.
- `src/pdlc/internal/` owns shared facades and implementation helpers; callers should use these seams instead of reaching into a backend.
- `tests/` contains package-level Python tests.
- `agent/skills/` contains the agent-facing PDLC skills and their references; they drive the workflow through the installed `pdlc` CLI, which is expected on `PATH`.
- `agent/sub-agents/` contains Claude and Codex specialist declarations.

When changing a lifecycle command or its evidence contract, inspect the matching package command under `src/pdlc/commands/` and the skills that call it, then update their tests/docs together when both surfaces are affected.

## PDLC workflow

The fixed lifecycle is `Product → UI → Tasks → Technical Plan → Implementation → Testing → Verification → Complete`. Gate state controls whether work is pending, under review, awaiting approval, blocked on CI, stale, or complete.

For lifecycle behavior, read `agent/skills/pdlc/references/pdlc-contract.md` and `agent/skills/pdlc/references/parity-contract.md` first. For a work-item orientation, use the read-only `agent/skills/pdlc/SKILL.md`; for queue execution, use `agent/skills/pdlc-loop/SKILL.md`; for a stage, use that stage's `SKILL.md` and only its triggered references.

Use the controller and owning skill for routing. Work-item state, evidence markers, task identity, PR linkage, and completion readiness are machine-checked; do not infer them from prose, branch names, checkboxes, or recent files.

Treat `pdlc inspect*` commands as read-only. Treat `pdlc post *` commands as state-mutating workflow operations and run them only when the task explicitly authorizes that transition. Human approval, skip, decision resolution, and completion remain explicit driver actions.

## Development

The package requires Python `>=3.12` and uses `uv`; project metadata in `pyproject.toml` is the source of truth for packaging and entry points.

```bash
XDG_CACHE_HOME=/tmp/pdlc-uv-cache uv run python -m unittest discover -s tests -p 'test_*.py'
XDG_CACHE_HOME=/tmp/pdlc-uv-cache uv build
git diff --check
```

Use `PDLC_BACKEND=file` with a temporary `PDLC_HOME` for local workflow scenarios. The default work-item backend is GitHub; the file backend persists records under `.pdlc` unless `PDLC_HOME` overrides it. Code-host selection follows `PDLC_CODE_HOST`, and attachments follow `PDLC_ATTACHMENT_HOST`.

For Python syntax validation in this environment, use `PYTHONPYCACHEPREFIX=/tmp/pdlc-pycache python3 -m compileall -q src`; this proves compilation only, not GitHub, build, simulator, or runtime behavior.

## Change hygiene

Use `apply_patch` for edits. Keep Markdown sentences on one source line. Add comments only where they explain a contract, ownership boundary, or non-obvious constraint, and keep them current.

Do not broaden a change into workflow redesign, backend migration, publishing, or destructive cleanup without explicit scope. Stage only named paths, and report any pre-existing or unrelated dirty state separately.
