#!/bin/bash
# Wrapper: the script lives in the builder package (fichero-builder/fichero_builder/scripts/lane_ready_check.sh); this keeps the old path working. Same argv, stdin and exit code.
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/fichero-builder/fichero_builder/scripts/lane_ready_check.sh" "$@"
