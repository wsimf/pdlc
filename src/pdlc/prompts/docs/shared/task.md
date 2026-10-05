## Task

`{{TASK_TAG}}` (tag included) — `{{TASK_TITLE}}`

{{#IF REPOSITORY}}
This task belongs to the `{{REPOSITORY}}` repository, checked out at `{{REPOSITORY_PATH}}`. Work only in that folder: read, change, build, test, and commit there, following its own `AGENTS.md` / `CLAUDE.md` and its own build and test commands.

{{/IF}}
{{TASK_BODY}}
