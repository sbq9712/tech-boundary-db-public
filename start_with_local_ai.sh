#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ROOT/.env.local"

if [[ ! -f "$ENV_FILE" ]]; then
  cat >&2 <<'MSG'
Missing .env.local.
Create it with:

TECHDB_AGENT_API_KEY=...
TECHDB_AGENT_BASE_URL=https://.../v1
TECHDB_AGENT_MODEL=...
TECHDB_AGENT_AI_TIMEOUT_SECONDS=120
HERMES_AGENT_TIMEOUT_SECONDS=150

Do not commit this file.
MSG
  exit 1
fi

cd "$ROOT"
docker compose --env-file "$ENV_FILE" up -d --build api readonly-agent web
