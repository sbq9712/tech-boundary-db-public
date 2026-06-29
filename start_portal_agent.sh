#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ROOT/.env.local"

if [[ ! -f "$ENV_FILE" ]]; then
  cat >&2 <<'MSG'
Missing .env.local.
Required keys:
  TECHDB_AGENT_API_KEY=...
  TECHDB_AGENT_BASE_URL=https://.../v1
  TECHDB_AGENT_MODEL=...
MSG
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

cd "$ROOT/backend"
exec python3 portal_agent_server.py
