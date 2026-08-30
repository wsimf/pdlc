# PDLC

The PDLC command-line tool and its agent workflow instructions.

## Development

```bash
uv run pdlc --help
uv build
```

Install from the current branch with:

```bash
uv tool install 'git+ssh://git@github.com/ORG/pdlc.git@master'
```

Update a branch-based installation with:

```bash
uv tool upgrade pdlc --reinstall
```

## Environment variables

Values in `.pdlc/config.toml` override environment variables. CLI options override both.

All variables are optional unless a selected backend or workflow requires them.

| Variable | Default | Purpose |
|---|---|---|
| `PDLC_REPOSITORY` | unset; required for GitHub | GitHub repository in `OWNER/REPOSITORY` form. |
| `PDLC_PROJECT_NUMBER` | unset; required for GitHub | GitHub Projects number. |
| `PDLC_PROJECT_OWNER` | unset; required for GitHub | GitHub Projects owner. |
| `PDLC_BACKEND` | `github` | Work-item backend: `github` or `file`. |
| `PDLC_CODE_HOST` | Follows `PDLC_BACKEND` | Code/PR host: `github`, `file`, or `none`. |
| `PDLC_ATTACHMENT_HOST` | `file` | Attachment host: `file` or `none`. |
| `PDLC_HOME` | `.pdlc` | Local file-backend and attachment storage root. |
| `PDLC_ACTOR` | `local` | Actor name recorded by the file backend. |
| `PDLC_REF_LABEL` | `pdlc` | Label used for local inspector scratch files. |
| `PDLC_ITEMS_FILE` | unset | Fixture file used instead of live GitHub Project items. |
| `PDLC_SUBISSUES_FILE` | unset | Fixture file used instead of live GitHub subissues. |
| `PDLC_MAX_ATTEMPTS` | `5` | Maximum queue-loop polling attempts. |
| `PDLC_INITIAL_DELAY_SECONDS` | `60` | Initial queue-loop retry delay. |
| `PDLC_MAX_DELAY_SECONDS` | `900` | Queue-loop retry delay ceiling. |
| `PDLC_NO_SLEEP` | unset | Any non-empty value skips queue-loop retry sleeps. |
| `PDLC_AUTOAPPROVE_CHURN_CAP` | `3` | Maximum rework count eligible for automatic approval. Set to `0` to disable it. |

For GitHub, create `.pdlc/config.toml` with:

```toml
[backend]
name = "github"

[backend.github]
repository = "OWNER/REPOSITORY"
project_number = 123
project_owner = "OWNER"
```

Run `pdlc setup` to create this file interactively. It detects the GitHub repository from `remote.origin.url`, lists available GitHub Projects with `gh`, and lets you choose the project owner or enter another owner.
