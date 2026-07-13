#!/bin/bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <library-path-on-the-Mac>" >&2
  exit 2
fi

TOKEN_FILE="$HOME/Library/Application Support/Fichero/.api-key"
[[ -r "$TOKEN_FILE" ]] || { echo "Missing $TOKEN_FILE; start the engine first." >&2; exit 1; }
PAIR_JSON="$(curl -fsSk -H "Authorization: Bearer $(<"$TOKEN_FILE")" -X POST https://127.0.0.1:8765/api/pair/code)"
PAIR_JSON="$PAIR_JSON" FICHERO_PAIRING_LIBRARY_PATH="$1" python3 - <<'PY'
import base64
import json
import os
import urllib.parse

pair = json.loads(os.environ["PAIR_JSON"])
payload = {
    "v": 1,
    "api_url": pair["tailnet_url"],
    "pair_code": pair["code"],
    "expires_at": pair["expires_at"],
    "spki": pair["spki_pin"],
    "library_path": os.environ["FICHERO_PAIRING_LIBRARY_PATH"],
}
encoded = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
print(f"Expires: {pair['expires_at']}")
print("fichero://pair?payload=" + urllib.parse.quote(encoded, safe=""))
PY
