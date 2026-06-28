#!/usr/bin/env bash
# Tail Fichero's unified log, hiding known-benign WKWebView sandbox/XPC noise.
set -euo pipefail

PREDICATE='process == "Fichero" OR process == "com.apple.WebKit.WebContent"'
RAW=false
SELF_CHECK=false

usage() {
  cat <<'EOF'
Usage:
  scripts/tail-fichero-logs.sh
  scripts/tail-fichero-logs.sh --raw
  scripts/tail-fichero-logs.sh --self-check

Default mode filters benign WKWebView sandbox/XPC chatter so real app logs stay readable.
Use --raw when debugging WebKit itself.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --raw) RAW=true ;;
    --self-check) SELF_CHECK=true ;;
    --help|-h) usage; exit 0 ;;
    *) echo "error: unknown argument '$arg'" >&2; usage; exit 2 ;;
  esac
done

NOISE_REGEX='CFPasteboard|Connection invalid|launchservicesd|coreservicesd|AudioComponentRegistrar|networkd|intents-framework|Sandbox: .*deny|XPC.*(interrupted|invalid)'

if $SELF_CHECK; then
  echo "predicate: $PREDICATE"
  echo "noise regex: $NOISE_REGEX"
  exit 0
fi

if $RAW; then
  exec log stream --style compact --level debug --predicate "$PREDICATE"
fi

exec log stream --style compact --level debug --predicate "$PREDICATE" \
  | grep --line-buffered -Ev "$NOISE_REGEX"
