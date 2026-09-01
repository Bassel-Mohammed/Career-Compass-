#!/usr/bin/env bash
#
# Keep PUBLIC_HOST in .env pointing at whatever URL ngrok currently holds.
#
# Why this exists
# ---------------
# A free ngrok account cannot reserve a domain, so every restart of the tunnel hands out a new
# random hostname. Two things in this stack are pinned to that hostname: the backend's
# CORS_ALLOWED_ORIGINS and the AI service's CC_OPENROUTER_SITE_URL, both interpolated from
# PUBLIC_HOST at container start. A stale PUBLIC_HOST does not break the site visibly — the
# pages load and the API calls fail — so it is exactly the kind of drift worth automating away.
#
# This watches ngrok's local API, and when the public hostname differs from what .env says, it
# rewrites .env and recreates only the three containers that read it. Nothing happens while the
# hostname is unchanged, so the steady state costs one loopback request every 15 seconds.
#
# Run it under systemd alongside the tunnel; see the header of ngrok-careercompass.service.

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$HOME/Desktop/career_compass}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
NGROK_API="${NGROK_API:-http://127.0.0.1:4040/api/tunnels}"
INTERVAL="${INTERVAL:-15}"

ENV_FILE="$PROJECT_DIR/.env"

log() { printf '%s ngrok-sync: %s\n' "$(date -Is)" "$*"; }

# The https tunnel's hostname, or empty if ngrok is not up yet. Parsed with python3 rather than
# jq, which is not installed by default on Ubuntu Server.
current_ngrok_host() {
    curl -sf --max-time 5 "$NGROK_API" 2>/dev/null | python3 -c '
import json, sys
from urllib.parse import urlparse
try:
    tunnels = json.load(sys.stdin).get("tunnels", [])
except Exception:
    sys.exit(0)
for t in tunnels:
    url = t.get("public_url", "")
    if url.startswith("https://"):
        print(urlparse(url).hostname or "")
        break
' 2>/dev/null || true
}

configured_host() {
    grep -E '^PUBLIC_HOST=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true
}

if [[ ! -f "$ENV_FILE" ]]; then
    log "no .env at $ENV_FILE — nothing to keep in sync"
    exit 1
fi

log "watching $NGROK_API, syncing PUBLIC_HOST in $ENV_FILE every ${INTERVAL}s"

while true; do
    host="$(current_ngrok_host)"

    if [[ -n "$host" && "$host" != "$(configured_host)" ]]; then
        log "public host changed to $host — updating .env"

        # A pipe delimiter keeps the slashes in hostnames and paths from ending the expression.
        if grep -qE '^PUBLIC_HOST=' "$ENV_FILE"; then
            sed -i "s|^PUBLIC_HOST=.*|PUBLIC_HOST=$host|" "$ENV_FILE"
        else
            printf 'PUBLIC_HOST=%s\n' "$host" >> "$ENV_FILE"
        fi

        # Only these three interpolate PUBLIC_HOST. Recreating the databases would be both
        # pointless and a good way to interrupt a demo mid-sentence.
        log "recreating backend, ai-service and caddy"
        if (cd "$PROJECT_DIR" && docker compose -f "$COMPOSE_FILE" up -d backend ai-service caddy); then
            log "now serving https://$host"
        else
            log "compose failed — .env is updated, containers are not; will retry on next change"
        fi
    fi

    sleep "$INTERVAL"
done
