#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.." || exit 2
exec scripts/verify_all.sh --fast "$@"
