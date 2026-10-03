#Requires -Version 5.1
# Machine installation for Windows; run from this checkout's root.
[CmdletBinding()]
param(
    [Alias('y')][switch]$Yes,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($Help) {
    Write-Host 'Usage: .\setup.ps1 [-Yes]'
    Write-Host 'Run from the repository root. -Yes (or -y) approves all installation and replacement prompts.'
    exit 0
}

function Confirm-Setup([string]$Question) {
    if ($Yes) {
        Write-Host "$Question [yes: -Yes]"
        return $true
    }
    Write-Host "`n"
    $answer = Read-Host "$Question [y/N]"
    return $answer -match '^(y|yes)$'
}

function Write-Step([int]$Number, [string]$Title) {
    Write-Host "`n[$Number] $Title" -ForegroundColor Yellow
}

# Windows PowerShell does not turn native nonzero exits into terminating errors.
function Invoke-Tool([string]$Command, [string[]]$Arguments) {
    $ErrorActionPreference = 'Continue'
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command $($Arguments -join ' ') failed (exit $LASTEXITCODE)."
    }
}

function Test-Tool([string]$Command, [string[]]$Arguments) {
    $ErrorActionPreference = 'Continue'
    & $Command @Arguments *> $null
    return $LASTEXITCODE -eq 0
}

function Test-CommandAvailable([string]$Name) {
    return $null -ne (Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue)
}

function Assert-Checkout {
    $gitRoot = [string](Invoke-Tool git @('rev-parse', '--show-toplevel'))
    if ((Resolve-Path -LiteralPath $gitRoot).ProviderPath -ne $repoRoot) {
        throw 'Setup cancelled: this folder is not the Git repository root.'
    }
    foreach ($path in @('pyproject.toml', 'src/pdlc/__init__.py', 'src/pdlc/cli.py')) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Setup cancelled: required PDLC package file $path is missing."
        }
    }
    $metadata = Get-Content -LiteralPath 'pyproject.toml' -Raw
    if ($metadata -notmatch '(?m)^name\s*=\s*"pdlc"\s*$') {
        throw 'Setup cancelled: this is not the PDLC repository.'
    }
    foreach ($directory in @('agent/skills', 'agent/sub-agents/claude', 'agent/sub-agents/codex', 'agent/sub-agents/copilot')) {
        if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
            throw "Setup cancelled: required directory $directory is missing."
        }
        $entries = @(Get-ChildItem -LiteralPath $directory)
        if ($entries.Count -eq 0) {
            throw "Setup cancelled: required directory $directory is empty."
        }
        foreach ($entry in $entries) {
            if ($directory -eq 'agent/skills') {
                if (-not (Test-Path -LiteralPath (Join-Path $entry.FullName 'SKILL.md') -PathType Leaf)) {
                    throw "Setup cancelled: required skill file $($entry.FullName)/SKILL.md is missing."
                }
            } elseif ($entry.PSIsContainer) {
                throw "Setup cancelled: expected a sub-agent file at $($entry.FullName)."
            }
        }
    }
}

function Install-Entries([string]$Mode, [string]$SourceDirectory, [string]$DestinationDirectory) {
    if (-not (Confirm-Setup "Install $Mode entries from $SourceDirectory into $DestinationDirectory (replace matching entries)?")) {
        Write-Host "Skipping $DestinationDirectory."
        return
    }
    [System.IO.Directory]::CreateDirectory($DestinationDirectory) | Out-Null
    foreach ($source in Get-ChildItem -LiteralPath $SourceDirectory) {
        $destination = Join-Path $DestinationDirectory $source.Name
        # Enumerate the parent to include dangling links; never traverse link targets.
        $existing = Get-ChildItem -LiteralPath $DestinationDirectory -Force |
            Where-Object { $_.Name -eq $source.Name } | Select-Object -First 1
        if ($null -ne $existing) {
            $isLink = ($existing.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
            if ($existing.PSIsContainer -and -not $isLink) {
                throw "Setup cancelled: cannot replace directory $destination; move it aside and rerun."
            }
        }
        $temporary = $null
        try {
            if ($Mode -eq 'copy') {
                $temporary = Join-Path $DestinationDirectory ('.pdlc-copy.' + [guid]::NewGuid().ToString('N'))
                Copy-Item -LiteralPath $source.FullName -Destination $temporary
            }
            if ($null -ne $existing) {
                if ($existing.PSIsContainer) {
                    [System.IO.Directory]::Delete($destination)
                } else {
                    [System.IO.File]::Delete($destination)
                }
            }
            if ($Mode -eq 'symlink') {
                try {
                    New-Item -ItemType SymbolicLink -Path $destination -Target $source.FullName | Out-Null
                } catch {
                    throw "Cannot create symbolic link $destination. Enable Windows Developer Mode or run PowerShell as administrator, then rerun setup. $($_.Exception.Message)"
                }
            } else {
                Move-Item -LiteralPath $temporary -Destination $destination
            }
            Write-Host "Installed ${Mode}: $($source.FullName) -> $destination"
        } finally {
            if ($null -ne $temporary -and (Test-Path -LiteralPath $temporary)) {
                Remove-Item -LiteralPath $temporary -Force
            }
        }
    }
}

try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'Setup cancelled: use setup.sh on macOS, Linux, or WSL.'
    }
    $repoRoot = (Resolve-Path -LiteralPath $PSScriptRoot).ProviderPath
    if ((Get-Location).Provider.Name -ne 'FileSystem' -or (Get-Location).ProviderPath -ne $repoRoot) {
        throw 'Setup cancelled: run .\setup.ps1 from the repository root.'
    }
    Assert-Checkout
    Write-Host @'
 ____  ____  _     ____
|  _ \|  _ \| |   / ___|
| |_) | | | | |  | |
|  __/| |_| | |__| |___
|_|   |____/|_____\____|

Let's set up PDLC!
'@

    Write-Step 0 'Pulling the latest repository changes...'
    Invoke-Tool git @('pull', '--ff-only')
    Assert-Checkout
    Write-Host 'Repository is up to date.'

    Write-Step 1 'Checking uv...'
    if (-not (Test-CommandAvailable uv)) {
        throw 'Setup cancelled: install uv from https://docs.astral.sh/uv/getting-started/installation/ and rerun.'
    }
    Write-Host 'uv is available.'

    Write-Step 2 'Checking Python...'
    $metadata = Get-Content -LiteralPath 'pyproject.toml' -Raw
    if ($metadata -notmatch '(?m)^requires-python\s*=\s*"(>=([0-9]+\.[0-9]+(?:\.[0-9]+)?))"\s*$') {
        throw 'Setup cancelled: unsupported requires-python in pyproject.toml.'
    }
    $pythonRequirement = $Matches[1]
    $pythonMinimum = $Matches[2]
    $findArguments = @('python', 'find', '--system', '--no-project', '--no-python-downloads', $pythonRequirement)
    if (-not (Test-Tool uv $findArguments)) {
        if (-not (Confirm-Setup "PDLC needs Python $pythonRequirement to run. Install Python $pythonMinimum with uv now?")) {
            throw 'Setup cancelled: Python installation declined.'
        }
        Invoke-Tool uv @('python', 'install', $pythonMinimum)
        Write-Host "Python $pythonMinimum installed."
    }
    $pythonPath = ([string](Invoke-Tool uv $findArguments)).Trim()
    Write-Host "Compatible Python is available: $pythonPath"

    Write-Step 3 'Checking GitHub CLI...'
    if (-not (Test-CommandAvailable gh)) {
        throw 'Setup cancelled: install GitHub CLI from https://cli.github.com/ and rerun.'
    }
    Write-Host 'GitHub CLI is present.'

    Write-Step 4 'Checking gh stack...'
    if (-not (Test-Tool gh @('stack', '--help'))) {
        if (-not (Confirm-Setup 'Install the gh stack extension with GitHub CLI now?')) {
            throw 'Setup cancelled: gh stack installation declined.'
        }
        Invoke-Tool gh @('extension', 'install', 'github/gh-stack')
        Write-Host 'gh stack extension installed.'
    } else {
        Write-Host 'gh stack extension is available.'
    }

    Write-Step 5 'Checking optional Azure tooling...'
    Write-Host 'Azure CLI and azure-devops are only needed for Azure DevOps work item management. PDLC also supports GitHub Issues and Projects via gh.'
    if (Test-CommandAvailable az) {
        Write-Host 'Azure CLI is present.'
        if (Test-Tool az @('extension', 'show', '--name', 'azure-devops')) {
            Write-Host 'azure-devops extension is already installed.'
        } elseif (Confirm-Setup 'Install the optional azure-devops extension with Azure CLI now?') {
            try {
                Invoke-Tool az @('extension', 'add', '--name', 'azure-devops')
                Write-Host 'azure-devops extension installed.'
            } catch {
                Write-Warning "Optional azure-devops installation failed; continuing. Rerun setup to retry. $($_.Exception.Message)"
            }
        } else {
            Write-Host 'Skipping optional azure-devops extension.'
        }
    } else {
        Write-Host 'Azure CLI not found. Install it if using Azure DevOps: https://learn.microsoft.com/cli/azure/install-azure-cli'
    }

    Write-Step 6 'Configuring PDLC on this machine...'
    Write-Host 'Required prerequisites are ready.'
    Write-Step 7 'Installing skills...'
    Install-Entries symlink (Join-Path $repoRoot 'agent/skills') (Join-Path $HOME '.agents/skills')
    if (Test-Path -LiteralPath (Join-Path $HOME '.claude') -PathType Container) {
        Install-Entries symlink (Join-Path $repoRoot 'agent/skills') (Join-Path $HOME '.claude/skills')
    }

    Write-Step 8 'Installing sub-agents for available harnesses...'
    if (Test-Path -LiteralPath (Join-Path $HOME '.claude') -PathType Container) {
        Install-Entries symlink (Join-Path $repoRoot 'agent/sub-agents/claude') (Join-Path $HOME '.claude/agents')
    }
    if (Test-Path -LiteralPath (Join-Path $HOME '.codex') -PathType Container) {
        Install-Entries copy (Join-Path $repoRoot 'agent/sub-agents/codex') (Join-Path $HOME '.codex/agents')
    }
    if (Test-Path -LiteralPath (Join-Path $HOME '.copilot') -PathType Container) {
        Install-Entries symlink (Join-Path $repoRoot 'agent/sub-agents/copilot') (Join-Path $HOME '.copilot/agents')
    }
    Write-Host 'Sub-agent setup finished.'

    Write-Step 9 'Installing or updating the CLI from this checkout...'
    Invoke-Tool uv @('tool', 'install', '--force', '--reinstall', '--python', $pythonPath, '--no-python-downloads', $repoRoot)
    Write-Host 'PDLC CLI installed or updated from this checkout.'
    Write-Host "`nPDLC setup complete! If pdlc is not on PATH, run: uv tool update-shell"
    Write-Host 'Configure work item management with: pdlc setup'
} catch {
    Write-Error "$($_.Exception.Message) Fix the reported error and rerun .\setup.ps1." -ErrorAction Continue
    exit 1
}
