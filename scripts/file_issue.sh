#!/usr/bin/env bash
# file_issue.sh — the ONE safe way to file a GitHub issue on dtubb/fichero.
#
# Enforces the board organizer's rules so the manager can self-serve the clear
# cases without re-introducing duplicate/mis-placed milestones:
#   - milestone MUST exist and be OPEN (closed ones print their live successor)
#   - only the 15 canonical labels (lane + type [+ priority] [+ needs-design])
#   - --milestone auto keyword-routes the common themes; ambiguous -> you specify
#
# ponytail: a bash gh-wrapper, not a service. Keyword router covers high-traffic
# routes only; everything else requires an explicit --milestone (honest, not magic).
#
# Usage:
#   scripts/file_issue.sh --title "..." --type bug|feature|task \
#     --lane backend|client:swiftui|docs [--milestone "Name"|auto] \
#     [--priority P0|P1|P2|P3] [--needs-design] [--body "..."|--body-file F] [--dry-run]
#   scripts/file_issue.sh --self-test
set -euo pipefail
REPO="dtubb/fichero"

TITLE="" TYPE="" LANE="" MILESTONE="auto" PRIORITY="" NEEDS_DESIGN="" BODY="" BODYFILE="" DRY=""
while [ $# -gt 0 ]; do case "$1" in
  --title) TITLE="$2"; shift 2;;
  --type) TYPE="$2"; shift 2;;
  --lane) LANE="$2"; shift 2;;
  --milestone) MILESTONE="$2"; shift 2;;
  --priority) PRIORITY="$2"; shift 2;;
  --needs-design) NEEDS_DESIGN=1; shift;;
  --body) BODY="$2"; shift 2;;
  --body-file) BODYFILE="$2"; shift 2;;
  --dry-run) DRY=1; shift;;
  --self-test) SELFTEST=1; shift;;
  -h|--help) sed -n '2,20p' "$0"; exit 0;;
  *) echo "unknown arg: $1" >&2; exit 2;;
esac; done

# --- keyword router: title+body -> canonical milestone (first match wins) ---
route() {
  local t; t="$(printf '%s %s' "${1:-}" "${2:-}" | tr '[:upper:]' '[:lower:]')"
  case "$t" in
    *auth*|*authz*|*acl*|*token*|*csrf*|*tls*|*ssl*|*cert*|*pinning*|*malicious*|*symlink*|*"path travers"*|*sanitiz*|*scrypt*|*password*|*vulnerab*|*exploit*|*privacy*) echo "Security";;
    *notariz*|*codesign*|*"code sign"*|*sparkle*|*"self-updat"*|*"dmg"*|*"release notes"*) echo "Release & Distribution";;
    *guardrail*|*invariant*|*"known_violations"*) echo "Programmatic Guardrails";;
    *xcodebuild*|*testflight*|*"build harness"*|*"ci "*|*nightly*) echo "Dev & Build Harness";;
    *"fichero cli"*|*" cli "*|*"cli:"*|*completion*) echo "Developer Experience";;
    *embedding*|*mlx*|*"model use"*|*"model-use"*|*"provider reliab"*|*"ai infra"*|*"ai-infra"*|*batch*) echo "AI Backend Hardening";;
    *corpus*|*"source archive"*|*dataset*|*"demo data"*|*catalogue*) echo "Source Archives";;
    *"knowledge graph"*|*" kg "*|*entity*|*claim*|*hermeneut*) echo "KG & Hermeneutics";;
    *search*|*retrieval*|*rerank*) echo "Search";;
    *workflow*|*"node editor"*|*langgraph*) echo "Workflows";;
    *"mcp"*) echo "MCP";;
    *pairing*|*discovery*|*bonjour*|*"qr "*) echo "Device Pairing & Discovery";;
    *toolbar*|*"window chrome"*) echo "Window Chrome & Toolbars";;
    *inspector*|*annotation*) echo "UI Reform — Inspector & Annotation";;
    *font*|*"sf symbol"*|*emoji*) echo "Mac Polish — Fonts, SF Symbols, No Emoji";;
    *reading*|*"pdf"*|*"multi-page"*|*"library view"*) echo "Library & Reading Surface";;
    *) echo "";;
  esac
}

# closed milestone -> live successor (do not re-create the closed one)
successor() { case "$1" in
  "CLI") echo "Developer Experience";;
  "AI Infrastructure") echo "AI Backend Hardening";;
  "Test Coverage") echo "Developer Experience";;
  "Networking — OpenAPI-only (kill hand-rolled URLSession)") echo "Programmatic Guardrails";;
  "Docs Review") echo "Documentation";;
  "Native SwiftUI Controls") echo "Mac Polish — Fonts, SF Symbols, No Emoji";;
  "Infrastructure") echo "(historical — pick a specific successor)";;
  Source\ Archive\ -\ *) echo "Source Archives";;
  *) echo "";;
esac; }

if [ "${SELFTEST:-}" = 1 ]; then
  fail=0
  chk(){ local got; got="$(route "$1" "$2")"; [ "$got" = "$3" ] || { echo "FAIL route('$1')='$got' want '$3'"; fail=1; }; }
  chk "harden QR pairing transport with SPKI + keychain tokens" "" "Security"
  chk "notarize the macOS build and wire Sparkle" "" "Release & Distribution"
  chk "CLI: add login command" "" "Developer Experience"
  chk "re-embed with bge-m3 embedding provider" "" "AI Backend Hardening"
  chk "import the Sergio corpus dataset" "" "Source Archives"
  chk "add a guardrail for raw DB access" "" "Programmatic Guardrails"
  chk "totally unrelated widget color" "" ""
  [ "$(successor CLI)" = "Developer Experience" ] || { echo "FAIL successor(CLI)"; fail=1; }
  [ $fail = 0 ] && echo "file_issue self-test passed" || exit 1
  exit 0
fi

# --- validate ---
[ -n "$TITLE" ] || { echo "error: --title required" >&2; exit 2; }
case "$TYPE" in feature|bug|task) ;; *) echo "error: --type must be feature|bug|task" >&2; exit 2;; esac
case "$LANE" in backend|client:swiftui|docs) ;; *) echo "error: --lane must be backend|client:swiftui|docs" >&2; exit 2;; esac
[ -z "$PRIORITY" ] || case "$PRIORITY" in P0|P1|P2|P3) ;; *) echo "error: --priority must be P0..P3" >&2; exit 2;; esac

# --- resolve + validate milestone (must be OPEN) ---
if [ "$MILESTONE" = "auto" ]; then
  MILESTONE="$(route "$TITLE" "$BODY")"
  [ -n "$MILESTONE" ] || { echo "error: could not auto-route. Re-run with --milestone \"Name\" (see agent-work/2026-07-03-milestone-consolidation-plan.md §5)." >&2; exit 3; }
  echo "auto-routed to milestone: $MILESTONE" >&2
fi
state="$(gh api "repos/$REPO/milestones?state=all&per_page=100" --paginate -q ".[] | select(.title==\"$MILESTONE\") | .state" 2>/dev/null || true)"
if [ -z "$state" ]; then
  echo "error: milestone '$MILESTONE' does not exist. Do NOT create it here — ask the board organizer." >&2; exit 3
elif [ "$state" = "closed" ]; then
  s="$(successor "$MILESTONE")"
  echo "error: milestone '$MILESTONE' is CLOSED (historical). File into its successor: ${s:-ask the board organizer}." >&2; exit 3
fi

# --- labels (canonical only) + create ---
LABELS="$LANE,type:$TYPE"
[ -n "$PRIORITY" ] && LABELS="$LABELS,priority:$PRIORITY"
[ -n "$NEEDS_DESIGN" ] && LABELS="$LABELS,needs-design"
set -- --repo "$REPO" --title "$TITLE" --milestone "$MILESTONE" --label "$LABELS"
if [ -n "$BODYFILE" ]; then set -- "$@" --body-file "$BODYFILE"; else set -- "$@" --body "${BODY:-$TITLE}"; fi

if [ -n "$DRY" ]; then echo "DRY-RUN: gh issue create $*"; exit 0; fi
gh issue create "$@"
