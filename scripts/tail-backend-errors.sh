#!/bin/bash
# Tail /tmp/fichero-backend.log showing only anomalous statuses + Python errors.
# Drops 200/201/204 access lines and the noisy LangChainPendingDeprecation warning.
#
# Usage:
#   ./scripts/tail-backend-errors.sh                # default log path
#   ./scripts/tail-backend-errors.sh /path/to/log   # custom log path

set -euo pipefail

LOG="${1:-/tmp/fichero-backend.log}"

if [[ ! -f "$LOG" ]]; then
  echo "Log file not found: $LOG" >&2
  exit 1
fi

# `tail -F` survives uvicorn --reload truncation/rotation.
# `--line-buffered` makes grep flush per line so output is live, not chunked.
# Pattern matches:
#   - HTTP 202 (Accepted — workflow kickoffs that may never finish)
#   - HTTP 3xx, 4xx, 5xx (anything but the clean 2xx success codes)
#   - ERROR / Traceback (Python exceptions)
exec tail -F "$LOG" \
  | grep --line-buffered -E '" (202|3[0-9]{2}|4[0-9]{2}|5[0-9]{2}) |ERROR|Traceback'
