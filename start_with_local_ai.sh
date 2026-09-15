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

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to prepare breadth runtime data." >&2
  exit 1
fi

echo "Preparing pinned breadth runtime data before the Docker build..."
python3 "$ROOT/scripts/hydrate_breadth_runtime.py"

cd "$ROOT"
echo "Building current API and web images..."
docker compose --env-file "$ENV_FILE" build api readonly-agent web

echo "Preparing verified Docling models before accepting document uploads..."
docker compose --env-file "$ENV_FILE" run --rm --no-deps api \
  python -m app.document_ingestion.models

echo "Starting local services..."
docker compose --env-file "$ENV_FILE" up -d api readonly-agent web

