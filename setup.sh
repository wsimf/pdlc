#!/usr/bin/env bash
# Machine installation; run from this checkout's root. Compatible with Bash 3.2+.
set -Eeuo pipefail

assume_yes=false
for arg in "$@"; do
    case "$arg" in
        -y) assume_yes=true ;;
        -h|--help)
            printf 'Usage: ./setup.sh [-y]\nRun from the repository root. -y approves all installation and replacement prompts.\n'
            exit 0 ;;
        *) printf 'Unknown argument: %s\n' "$arg" >&2; exit 1 ;;
    esac
done

die() { printf 'Setup cancelled: %s\n' "$*" >&2; exit 1; }
trap 'printf "Setup failed at line %s. Fix the reported error and rerun ./setup.sh.\n" "$LINENO" >&2' ERR

confirm() {
    local answer
    if "$assume_yes"; then
        printf '%s [yes: -y]\n' "$1"
        return 0
    fi
    printf '%s [y/N] ' "$1"
    if ! IFS= read -r answer; then
        printf '\n'
        return 1
    fi
    case "$answer" in y|Y|yes|YES|Yes) return 0 ;; *) return 1 ;; esac
}

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
[[ $(pwd -P) == "$repo_root" ]] || die 'run ./setup.sh from the repository root.'

validate_checkout() {
    local git_root directory entry found
    git_root=$(git rev-parse --show-toplevel) || die 'not in a Git checkout.'
    [[ $(cd "$git_root" && pwd -P) == "$repo_root" ]] || die 'this folder is not the Git repository root.'
    [[ -f pyproject.toml && -f src/pdlc/__init__.py && -f src/pdlc/cli.py ]] || die 'required PDLC package files are missing.'
    [[ $(sed -n 's/^name[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' pyproject.toml) == pdlc ]] || die 'this is not the PDLC repository.'
    for directory in agent/skills agent/sub-agents/claude agent/sub-agents/codex agent/sub-agents/copilot; do
        [[ -d "$directory" ]] || die "required directory $directory is missing."
        found=false
        for entry in "$directory"/*; do
            [[ -e "$entry" ]] || continue
            if [[ "$directory" == agent/skills ]]; then
                [[ -f "$entry/SKILL.md" ]] || die "required skill file $entry/SKILL.md is missing."
            else
                [[ -f "$entry" ]] || die "expected a sub-agent file at $entry."
            fi
            found=true
        done
        "$found" || die "required directory $directory is empty."
    done
}
validate_checkout

cat <<'ART'
 ____  ____  _     ____
|  _ \|  _ \| |   / ___|
| |_) | | | | |  | |
|  __/| |_| | |__| |___
|_|   |____/|_____\____|

Let's set up PDLC!
ART

printf '\n[0] Pulling the latest repository changes...\n'
git pull --ff-only
validate_checkout

printf '\n[1] Checking uv...\n'
command -v uv >/dev/null 2>&1 || die 'install uv from https://docs.astral.sh/uv/getting-started/installation/ and rerun.'

printf '\n[2] Checking Python...\n'
# Read the package requirement before Python itself is available to parse TOML.
python_requirement=$(sed -n 's/^requires-python[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' pyproject.toml)
[[ "$python_requirement" =~ ^\>=([0-9]+\.[0-9]+(\.[0-9]+)?)$ ]] || die 'unsupported requires-python in pyproject.toml.'
python_minimum=${BASH_REMATCH[1]}
if ! python_path=$(uv python find --system --no-project --no-python-downloads "$python_requirement" 2>/dev/null); then
    confirm "PDLC needs Python $python_requirement to run. Install Python $python_minimum with uv now?" || die 'Python installation declined.'
    uv python install "$python_minimum"
    python_path=$(uv python find --system --no-project --no-python-downloads "$python_requirement")
fi
printf 'Using Python: %s\n' "$python_path"

printf '\n[3] Checking GitHub CLI...\n'
command -v gh >/dev/null 2>&1 || die 'install GitHub CLI from https://cli.github.com/ and rerun.'

printf '\n[4] Checking gh stack...\n'
if ! gh stack --help >/dev/null 2>&1; then
    confirm 'Install the gh stack extension with GitHub CLI now?' || die 'gh stack installation declined.'
    gh extension install github/gh-stack
fi

printf '\n[5] Checking optional Azure tooling...\n'
printf 'Azure CLI and azure-devops are only needed for Azure DevOps work item management. PDLC also supports GitHub Issues and Projects via gh.\n'
if command -v az >/dev/null 2>&1; then
    if az extension show --name azure-devops >/dev/null 2>&1; then
        printf 'azure-devops extension is already installed.\n'
    elif confirm 'Install the optional azure-devops extension with Azure CLI now?'; then
        if ! az extension add --name azure-devops; then
            printf 'Optional azure-devops installation failed; continuing. Rerun setup to retry.\n' >&2
        fi
    else
        printf 'Skipping optional azure-devops extension.\n'
    fi
else
    printf 'Azure CLI not found. Install it if using Azure DevOps: https://learn.microsoft.com/cli/azure/install-azure-cli\n'
fi

# Replace only matching entries; never remove a real directory or unrelated files.
install_entries() {
    local mode=$1 source_dir=$2 destination_dir=$3 source destination temporary
    if ! confirm "Install $mode entries from $source_dir into $destination_dir (replace matching entries)?"; then
        printf 'Skipping %s.\n' "$destination_dir"
        return
    fi
    mkdir -p "$destination_dir"
    for source in "$source_dir"/*; do
        [[ -e "$source" ]] || continue
        destination="$destination_dir/$(basename "$source")"
        if [[ -d "$destination" && ! -L "$destination" ]]; then
            die "cannot replace directory $destination; move it aside and rerun."
        fi
        printf '%s: %s -> %s\n' "$mode" "$source" "$destination"
        if [[ "$mode" == symlink ]]; then
            rm -f "$destination"
            ln -s "$source" "$destination"
        else
            # Rename a fresh copy so existing symlinks are replaced, never followed.
            temporary=$(mktemp "$destination_dir/.pdlc-copy.XXXXXX")
            if [[ -L "$destination" ]]; then
                rm -f "$destination"
            fi
            if cp "$source" "$temporary" && mv -f "$temporary" "$destination"; then
                :
            else
                rm -f "$temporary"
                die "copy failed for $destination; rerun to retry."
            fi
        fi
    done
}

printf '\n[6] Prerequisites ready. Configuring PDLC on this machine...\n'
printf '\n[7] Installing skills...\n'
install_entries symlink "$repo_root/agent/skills" "$HOME/.agents/skills"
if [[ -d "$HOME/.claude" ]]; then
    install_entries symlink "$repo_root/agent/skills" "$HOME/.claude/skills"
fi

printf '\n[8] Installing sub-agents for available harnesses...\n'
if [[ -d "$HOME/.claude" ]]; then
    install_entries symlink "$repo_root/agent/sub-agents/claude" "$HOME/.claude/agents"
fi
if [[ -d "$HOME/.codex" ]]; then
    install_entries copy "$repo_root/agent/sub-agents/codex" "$HOME/.codex/agents"
fi
if [[ -d "$HOME/.copilot" ]]; then
    install_entries symlink "$repo_root/agent/sub-agents/copilot" "$HOME/.copilot/agents"
fi

printf '\n[9] Installing or updating the CLI from this checkout...\n'
uv tool install --force --reinstall --python "$python_path" --no-python-downloads "$repo_root"
printf '\nPDLC setup complete! If pdlc is not on PATH, run: uv tool update-shell\n'
printf 'Configure work item management with: pdlc setup\n'
