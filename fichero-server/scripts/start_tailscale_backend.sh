#!/bin/bash
set -euo pipefail

# Run the loopback-only engine behind Tailscale Serve with its public cert pin.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON_BIN="${FICHERO_PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"
[[ -x "$PYTHON_BIN" ]] || PYTHON_BIN=python3
command -v tailscale >/dev/null || { echo "Tailscale is required." >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required." >&2; exit 1; }

DOMAIN="${FICHERO_TAILSCALE_DOMAIN:-$(tailscale status --json | jq -r '.Self.DNSName // empty' | sed 's/\.$//')}"
[[ -n "$DOMAIN" ]] || { echo "Could not determine the Tailscale DNS name." >&2; exit 1; }
TAILSCALE_DIR="$HOME/Library/Application Support/Fichero/Tailscale"
mkdir -p "$TAILSCALE_DIR"
chmod 700 "$TAILSCALE_DIR"
TAIL_CERT="$TAILSCALE_DIR/$DOMAIN.crt"
TAIL_KEY="$TAILSCALE_DIR/$DOMAIN.key"
tailscale cert --cert-file "$TAIL_CERT" --key-file "$TAIL_KEY" "$DOMAIN"
TAIL_PIN="$(openssl x509 -in "$TAIL_CERT" -pubkey -noout | openssl pkey -pubin -outform DER | openssl dgst -sha256 -binary | openssl base64 -A)"

LOCAL_ACCESS="$(PYTHONPATH="$REPO_ROOT/fichero-server/src" "$PYTHON_BIN" "$SCRIPT_DIR/start_backend.py" --prepare-local-access)"
LOCAL_CERT="$(printf '%s' "$LOCAL_ACCESS" | jq -r '.certificate_path')"
LOCAL_KEY="$(printf '%s' "$LOCAL_ACCESS" | jq -r '.key_path')"
TOKEN_FILE="$HOME/Library/Application Support/Fichero/.api-key"
[[ -r "$TOKEN_FILE" ]] || { echo "Missing $TOKEN_FILE; start Fichero once first." >&2; exit 1; }

tailscale serve --bg --https=443 https+insecure://127.0.0.1:8765
export FICHERO_BOOTSTRAP_TOKEN="$(<"$TOKEN_FILE")"
export FICHERO_TLS_CERTFILE="$LOCAL_CERT"
export FICHERO_TLS_KEYFILE="$LOCAL_KEY"
export FICHERO_TLS_SPKI_HASH="$TAIL_PIN"
export FICHERO_PUBLIC_BASE_URL="https://$DOMAIN"
export FICHERO_TAILNET_URL="https://$DOMAIN"
exec "$SCRIPT_DIR/start_backend.sh" "$@"
