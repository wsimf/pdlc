#!/usr/bin/env zsh
# Serves this folder on the local network so presentation.html and notes.html share an origin and can sync.
# Sync works between windows of one browser on one device; open both pages from the same address.
# Usage: ./run.sh [port]   (default 8000)
# Needs uv on PATH; uv supplies Python, downloading one the first time if none is installed.
set -euo pipefail

port=${1:-8000}

if ! command -v uv >/dev/null; then
  print -u2 'uv was not found on PATH. Install it from https://docs.astral.sh/uv/ or open a new terminal after installing.'
  exit 1
fi

# Prefer the Mac's Wi-Fi or Ethernet address; fall back to the hostname elsewhere.
host=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || hostname)
base="http://$host:$port"
print "Deck:  $base/presentation.html  (share this window)"
print "Notes: $base/notes.html  (open in a separate window of the same browser)"
print 'Press Ctrl+C to stop.'

exec uv run --no-project python -m http.server "$port" --bind 0.0.0.0 --directory "${0:A:h}"
