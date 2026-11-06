# Serves this folder locally so presentation.html and notes.html share an origin and can sync.
# Usage: powershell -ExecutionPolicy Bypass -File run.ps1 [-Port 8000]
# Needs uv on PATH; uv supplies Python, downloading one the first time if none is installed.
param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error 'uv was not found on PATH. Install it from https://docs.astral.sh/uv/ or open a new terminal after installing.'
}

$base = "http://127.0.0.1:$Port"
Write-Host "Deck:  $base/presentation.html  (share this window)"
Write-Host "Notes: $base/notes.html  (open in a separate window of the same browser)"
Write-Host 'Press Ctrl+C to stop.'

uv run --no-project python -m http.server $Port --bind 127.0.0.1 --directory $PSScriptRoot
