#!/usr/bin/env bash
# list_machos.sh DIR [--executables] — print every Mach-O file under DIR, one path per line, sorted.
# --executables: only MH_EXECUTE images (what the App Sandbox entitlement goes on).
#
# One `file -f LISTFILE` run, not `find -exec file {} +` (#6132, ITMS-90296): the 2026.10.24 archive's embed phase
# signed 8 of ~871 Mach-Os, so torch/bin/protoc shipped unsandboxed. The CAUSE IS UNCONFIRMED: an argument-list overflow
# under xcodebuild's environment was suspected but the old find listed 871/871 under a 1 MB environment. This is
# hardening: no argument limit, errors not swallowed, and a short list fails the sweep. LC_ALL=C: `file` echoes bytes that are not valid UTF-8 (see build-release-dmg.sh).
# (`file -f` pads the name column with spaces after the colon.) Fails when it lists fewer Mach-Os than the tree has
# .so/.dylib files (those are always Mach-O): a short list is a failed sweep, not a small engine.
set -euo pipefail
dir="${1:?usage: list_machos.sh DIR [--executables]}"
mode="${2:-}"
names="$(mktemp)"
trap 'rm -f "$names"' EXIT
find "$dir" -type f > "$names"
all="$(LC_ALL=C file -f "$names" | LC_ALL=C grep -v '(for architecture' | LC_ALL=C grep -E ':[[:space:]]+Mach-O' || true)"
expected="$(find "$dir" -type f \( -name '*.so' -o -name '*.dylib' \) | wc -l | tr -d ' ')"
found="$(printf '%s' "$all" | grep -c . || true)"
if [ "$found" -lt "$expected" ]; then
  echo "error: list_machos.sh found $found Mach-O files under $dir but it holds $expected .so/.dylib files" >&2
  exit 1
fi
if [ "$mode" = "--executables" ]; then
  all="$(printf '%s\n' "$all" | LC_ALL=C grep 'executable' || true)"
fi
printf '%s\n' "$all" | LC_ALL=C sed -En 's/:[[:space:]]+Mach-O.*//p' | LC_ALL=C sort -u
