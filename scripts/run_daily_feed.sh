#!/usr/bin/env bash
# Online publisher only. Company offline servers import the resulting ZIP.
set -euo pipefail
BOUNDARY="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$BOUNDARY/runtime"
# Wait for a concurrent pipeline so the feed sees a completed data generation.
exec flock "$BOUNDARY/pipeline/.pipeline.lock" \
  "$BOUNDARY/pipeline/.venv/bin/python" "$BOUNDARY/scripts/build_feed_package.py" \
  --since-last --daily "$@" >> "$BOUNDARY/runtime/daily-feed.log" 2>&1
