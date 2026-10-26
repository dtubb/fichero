#!/bin/bash
# The worker wrapper (pipeline.key-per-lane, jailed-agent): the runner starts this with an allow-listed
# environment and never holds a key. The wrapper reads the key file into the one variable the provider's Pi
# expects, then execs the worker. usage: run-worker.sh <ENV_VAR|-> <key-file|-> <command...>
set -u
var=$1; file=$2; shift 2
if [ "$var" != "-" ] && [ "$file" != "-" ]; then
  export "$var"="$(cat "$file")"
fi
exec "$@"
