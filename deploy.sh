#!/usr/bin/env bash
# Build the image, load it into podman, and replace the running avecmoi
# container. Run from a checkout of this repo on spacedock:
#
#   ./deploy.sh                      # prompts for the /admin password
#   ADMIN_PASSWORD=... ./deploy.sh
#
# Overrides: NAME (container, default avecmoi), PORT (host port, default 8081),
# VOLUME (podman volume or host dir for questions, default avecmoi-data).
set -euo pipefail

NAME="${NAME:-avecmoi}"
PORT="${PORT:-8081}"
VOLUME="${VOLUME:-avecmoi-data}"

if [ -z "${ADMIN_PASSWORD:-}" ]; then
  read -rsp "Admin password for /admin: " ADMIN_PASSWORD; echo
fi

cd "$(dirname "$0")"
nix build
podman load -i result

# Remove the old container by name, plus anything else still holding the port.
podman rm -f "$NAME" 2>/dev/null || true
for id in $(podman ps -aq --filter "publish=$PORT"); do podman rm -f "$id"; done

podman run -d --name "$NAME" --restart=unless-stopped \
  -p "$PORT:8080" \
  -v "$VOLUME:/data" \
  -e ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  avecmoi:latest

sleep 1
curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null && echo "avecmoi is up on port $PORT"
