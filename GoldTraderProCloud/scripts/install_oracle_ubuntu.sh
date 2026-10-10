#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BUNDLE_ROOT="$(cd -- "$APP_DIR/.." && pwd)"
if [[ ! -f "$APP_DIR/docker-compose.yml" || ! -f "$APP_DIR/Dockerfile" ]]; then
  echo "ERROR: Keep the deployment bundle folder structure intact." >&2; exit 2
fi
if ! command -v apt-get >/dev/null 2>&1; then echo "ERROR: Use Ubuntu/Debian on the Oracle VM." >&2; exit 2; fi
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "Installing Docker Engine and Docker Compose from Ubuntu repositories..."
  sudo apt-get update
  sudo apt-get install -y docker.io docker-compose-v2 ca-certificates openssl
  sudo systemctl enable --now docker
fi
sudo docker info >/dev/null 2>&1 || { echo "ERROR: Docker is not running."; exit 3; }
ENV_FILE="$APP_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" <<ENVVARS
GOLDTRADER_INGEST_TOKEN=$(openssl rand -hex 32)
GOLDTRADER_READ_TOKEN=$(openssl rand -hex 32)
CLOUDFLARE_TUNNEL_TOKEN=
GOLDTRADER_DATA_DIR=/data
GOLDTRADER_MAX_QUOTE_AGE_SECONDS=15
LOG_LEVEL=INFO
ENVVARS
  chmod 600 "$ENV_FILE"
  echo "Created .env with separate random API tokens."
fi
if grep -q 'replace_with_' "$ENV_FILE" || grep -q '^GOLDTRADER_INGEST_TOKEN=$' "$ENV_FILE" || grep -q '^GOLDTRADER_READ_TOKEN=$' "$ENV_FILE"; then
  echo "ERROR: Set real random ingest/read tokens in $ENV_FILE first." >&2; exit 4
fi
mkdir -p "$APP_DIR/data"; sudo chown -R 10001:10001 "$APP_DIR/data"; sudo chmod 700 "$APP_DIR/data"
echo "Building and starting API (no inbound API port is published)..."
sudo docker compose -f "$APP_DIR/docker-compose.yml" --project-directory "$APP_DIR" up -d --build api
sudo docker compose -f "$APP_DIR/docker-compose.yml" --project-directory "$APP_DIR" exec -T api \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read().decode())"
echo
echo "API process is live; this does not confirm market data is connected."
echo "Private secrets: $ENV_FILE"
echo "NEXT: configure a Cloudflare Tunnel public hostname to http://api:8000."
echo "Put its token in CLOUDFLARE_TUNNEL_TOKEN in .env, then run:"
echo "  cd '$APP_DIR' && sudo docker compose --profile cloudflare up -d cloudflared"
echo "Logs: sudo docker compose -f '$APP_DIR/docker-compose.yml' --project-directory '$APP_DIR' logs -f api"
