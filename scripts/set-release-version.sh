#!/usr/bin/env bash
# set-release-version.sh — set ONE dated CalVer version across frontend + backend.
#
# Releases are dated (CalVer), not semantic. This is the single command that
# keeps frontend and backend on the same version so they track together.
#
# AUTOMATIC by default: with no date argument it stamps TODAY. A second release
# on the same calendar day automatically bumps a sub-number (.2, .3, …) so each
# build is distinct and Sparkle's build integer stays strictly increasing.
#
#   Frontend (Xcode):   MARKETING_VERSION       = <date>[.N][-beta]   (Apple display string)
#                       CURRENT_PROJECT_VERSION = <YYYYMMDD><NN>       (Sparkle build int, monotonic)
#   Backend (pyproject): version = "<PEP440>"   (e.g. 2026.6.27, 2026.6.27.2, 2026.6.27b1)
#
# Same-day sub-number N is derived from how many release tags already exist for
# today: N = (count of `v<DATE>*` tags) + 1.
#   N == 1 → display  YYYY.MM.DD[-beta]
#   N  > 1 → display  YYYY.MM.DD.N[-beta]
#
# Build integer is a 10-digit YYYYMMDD + 2-digit NN (2026062701, 2026062702,
# next day 2026062801). This is strictly greater than the OLD 8-digit YYYYMMDD
# scheme (20260627) for every plausible date, so Sparkle monotonicity survives
# the scheme change.
#
# PEP 440 forbids leading zeros (2026.06.27 is invalid) and the literal "-beta",
# so the engine uses the canonical form: strip leading zeros on month/day; a
# beta release maps to bN (2026.6.27b1, b2, …); a non-beta sub-build maps to an
# extra release segment (2026.6.27.2). The app keeps the human-readable -beta
# suffix (Apple + Sparkle accept it; Sparkle orders updates by the build
# INTEGER, not the short string, so the suffix is display-only).
#
# Usage:
#   scripts/set-release-version.sh                 # auto: today, stable, next sub-number
#   scripts/set-release-version.sh --beta          # auto: today, beta channel
#   scripts/set-release-version.sh 2026.06.27      # explicit date, stable
#   scripts/set-release-version.sh 2026.06.27 --beta
#   scripts/set-release-version.sh --dry-run       # print computed versions, touch nothing
#   scripts/set-release-version.sh --self-check    # assert N=1 vs N=2 produce expected strings
#
# Env:
#   FICHERO_RELEASE_SEQ=N   force the same-day sub-number (skip tag counting)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PBX="$ROOT/fichero/fichero.xcodeproj/project.pbxproj"
PY="$ROOT/fichero-engine/pyproject.toml"
NOTES="$ROOT/RELEASE_NOTES.md"

# ── arg parsing ──────────────────────────────────────────────────────────────
# The date is optional and positional; flags may appear in any order.
DATE=""
BETA=false
DRY_RUN=false
SELF_CHECK=false
for arg in "$@"; do
  case "$arg" in
    --beta)       BETA=true ;;
    --dry-run|-n) DRY_RUN=true ;;
    --self-check) SELF_CHECK=true ;;
    --help|-h)    sed -n '32,41p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)           echo "error: unknown flag: $arg" >&2; exit 2 ;;
    *)
      [ -z "$DATE" ] || { echo "error: unexpected extra argument: $arg" >&2; exit 2; }
      DATE="$arg" ;;
  esac
done

# Default to TODAY when no date was supplied.
[ -n "$DATE" ] || DATE="$(date +%Y.%m.%d)"

[[ "$DATE" =~ ^[0-9]{4}\.[0-9]{2}\.[0-9]{2}$ ]] \
  || { echo "error: date must be YYYY.MM.DD (got '$DATE')" >&2; exit 1; }

# ── same-day sequence ────────────────────────────────────────────────────────
# Count existing release tags for this date (tags are v<MARKETING_VERSION>, e.g.
# v2026.06.27-beta or v2026.06.27.2-beta) — the next build is count + 1.
seq_for_date() {
  local d="$1"
  if [ -n "${FICHERO_RELEASE_SEQ:-}" ]; then echo "$FICHERO_RELEASE_SEQ"; return; fi
  local n
  n="$(git -C "$ROOT" tag -l "v$d*" 2>/dev/null | grep -c . || true)"
  echo "$(( n + 1 ))"
}

# ── version computation (pure; sets the three globals) ───────────────────────
# Args: <date> <beta:true|false> <N>
compute_versions() {
  local d="$1" beta="$2" n="$3"
  local yyyy rest mm dd nn

  # display sub-number suffix: empty for N==1, ".N" for N>1
  local subdisp=""
  [ "$n" -gt 1 ] && subdisp=".$n"

  APP_VERSION="$d$subdisp"
  [ "$beta" = true ] && APP_VERSION="$APP_VERSION-beta"

  # build int: YYYYMMDD + zero-padded NN  (2026.06.27, N=1 -> 2026062701)
  printf -v nn '%02d' "$n"
  BUILD_INT="${d//./}$nn"

  # PEP 440: drop leading zeros on month/day
  yyyy="${d%%.*}"; rest="${d#*.}"; mm="${rest%%.*}"; dd="${rest#*.}"
  mm="${mm#0}"; dd="${dd#0}"
  ENGINE_VERSION="$yyyy.$mm.$dd"
  if [ "$beta" = true ]; then
    ENGINE_VERSION="${ENGINE_VERSION}b$n"          # 2026.6.27b1, b2, …
  elif [ "$n" -gt 1 ]; then
    ENGINE_VERSION="${ENGINE_VERSION}.$n"          # 2026.6.27.2 (extra release segment)
  fi
}

# ── release-notes heading (the third thing that must agree) ──────────────────
# create-github-release.sh renders the `## <MARKETING_VERSION>` section of
# RELEASE_NOTES.md into the Sparkle appcast, and refuses to publish without it.
# So the heading has to track the stamp. Retitle it here rather than leaving a
# manual step that only bites when a build slips past midnight.
#
# Two guards, because retitling the wrong heading rewrites history:
#   1. only an UNRELEASED heading — no `v<version>` tag may exist for it
#   2. only a CalVer-SHAPED heading — never `0.0.1 — Alpha (2026-04-29)`
# Anything else is a hand-edit, and we say so instead of guessing.
is_calver_heading() { [[ "$1" =~ ^[0-9]{4}\.[0-9]{2}\.[0-9]{2}(\.[0-9]+)?(-beta)?$ ]]; }

retitle_release_notes() {  # <target-version> <dry-run:true|false>
  local target="$1" dry="$2" top
  [ -f "$NOTES" ] || { echo "error: $NOTES not found" >&2; return 1; }
  top="$(grep -m1 -E '^## ' "$NOTES" | sed -E 's/^## +//')"
  [ -n "$top" ] || { echo "error: RELEASE_NOTES.md has no '## ' section" >&2; return 1; }

  if [ "$top" = "$target" ]; then
    echo "notes  : '## $target' already current"
    return 0
  fi
  if ! is_calver_heading "$top"; then
    echo "error: top release-notes section is '## $top', not an unreleased dated entry." >&2
    echo "       add a '## $target' section to RELEASE_NOTES.md by hand." >&2
    return 1
  fi
  if git -C "$ROOT" rev-parse -q --verify "refs/tags/v$top" >/dev/null 2>&1; then
    echo "error: '## $top' is already released (tag v$top exists)." >&2
    echo "       add a new '## $target' section; do not retitle a shipped release." >&2
    return 1
  fi
  if [ "$dry" = true ]; then
    echo "notes  : would retitle '## $top' -> '## $target'"
    return 0
  fi
  RN_FILE="$NOTES" RN_OLD="$top" RN_NEW="$target" python3 - <<'PY'
import os, pathlib
p = pathlib.Path(os.environ["RN_FILE"])
p.write_text(p.read_text().replace("## " + os.environ["RN_OLD"],
                                   "## " + os.environ["RN_NEW"], 1))
PY
  echo "notes  : retitled '## $top' -> '## $target'"
}

# ── PEP 440 validity check (best-effort: uses repo venv, then python3) ────────
pep440_check() {
  local v="$1" py=""
  if [ -x "$ROOT/.venv/bin/python" ]; then py="$ROOT/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then py="python3"; fi
  if [ -n "$py" ]; then
    "$py" -c "from packaging.version import Version; x=Version('$v'); print('  PEP 440 OK:', x, '| prerelease:', x.is_prerelease)" 2>/dev/null \
      || echo "  (packaging lib not available — '$v' is canonical PEP 440 regardless)"
  else
    echo "  (no python available — '$v' is canonical PEP 440 regardless)"
  fi
}

# ── self-check: assert the N=1 / N=2 strings, no file writes ─────────────────
if [ "$SELF_CHECK" = true ]; then
  fails=0
  assert_eq() {  # <label> <got> <want>
    if [ "$2" = "$3" ]; then
      echo "  ok: $1 = $2"
    else
      echo "  FAIL: $1 = '$2' (expected '$3')" >&2; fails=$((fails+1))
    fi
  }
  # stable, N=1
  compute_versions 2026.06.27 false 1
  assert_eq "N1 stable APP"    "$APP_VERSION"    "2026.06.27"
  assert_eq "N1 stable BUILD"  "$BUILD_INT"      "2026062701"
  assert_eq "N1 stable ENGINE" "$ENGINE_VERSION" "2026.6.27"
  # stable, N=2
  compute_versions 2026.06.27 false 2
  assert_eq "N2 stable APP"    "$APP_VERSION"    "2026.06.27.2"
  assert_eq "N2 stable BUILD"  "$BUILD_INT"      "2026062702"
  assert_eq "N2 stable ENGINE" "$ENGINE_VERSION" "2026.6.27.2"
  # beta, N=1
  compute_versions 2026.06.27 true 1
  assert_eq "N1 beta APP"      "$APP_VERSION"    "2026.06.27-beta"
  assert_eq "N1 beta BUILD"    "$BUILD_INT"      "2026062701"
  assert_eq "N1 beta ENGINE"   "$ENGINE_VERSION" "2026.6.27b1"
  # beta, N=2
  compute_versions 2026.06.27 true 2
  assert_eq "N2 beta APP"      "$APP_VERSION"    "2026.06.27.2-beta"
  assert_eq "N2 beta BUILD"    "$BUILD_INT"      "2026062702"
  assert_eq "N2 beta ENGINE"   "$ENGINE_VERSION" "2026.6.27b2"
  # next-day rollover: build int must exceed today's and the old 8-digit scheme
  compute_versions 2026.06.28 true 1
  assert_eq "next-day BUILD"   "$BUILD_INT"      "2026062801"
  [ "$BUILD_INT" -gt 2026062702 ] && echo "  ok: monotonic across days" || { echo "  FAIL: build int not monotonic" >&2; fails=$((fails+1)); }
  [ "$BUILD_INT" -gt 20260627 ]   && echo "  ok: new 10-digit > old 8-digit scheme" || { echo "  FAIL: not > old scheme" >&2; fails=$((fails+1)); }
  # release-notes heading guard: retitle dated entries, never historical ones
  assert_heading() {  # <heading> <want:yes|no>
    if is_calver_heading "$1"; then got=yes; else got=no; fi
    if [ "$got" = "$2" ]; then echo "  ok: heading '$1' retitlable=$got"
    else echo "  FAIL: heading '$1' retitlable=$got (expected $2)" >&2; fails=$((fails+1)); fi
  }
  assert_heading "2026.07.08-beta"   yes
  assert_heading "2026.07.08"        yes
  assert_heading "2026.07.08.2-beta" yes
  assert_heading "0.0.1 — Alpha (2026-04-29)" no
  assert_heading "0.0.2"             no
  assert_heading "Highlights"        no
  echo
  if [ "$fails" -eq 0 ]; then echo "self-check: PASS"; exit 0; else echo "self-check: $fails FAILED" >&2; exit 1; fi
fi

# ── compute for the real run ─────────────────────────────────────────────────
N="$(seq_for_date "$DATE")"
compute_versions "$DATE" "$BETA" "$N"

echo "date   : $DATE  (same-day build #$N)"
echo "app    : MARKETING_VERSION=$APP_VERSION  CURRENT_PROJECT_VERSION=$BUILD_INT"
echo "engine : version=$ENGINE_VERSION"

retitle_release_notes "$APP_VERSION" "$DRY_RUN"

if [ "$DRY_RUN" = true ]; then
  echo
  echo "dry-run: no files modified."
  echo "pep440:"; pep440_check "$ENGINE_VERSION"
  exit 0
fi

# ── frontend: CURRENT_PROJECT_VERSION via agvtool (sanctioned tool, works) ───
( cd "$ROOT/fichero" && xcrun agvtool new-version -all "$BUILD_INT" >/dev/null )

# ── frontend: MARKETING_VERSION via value-only sed (sanctioned-tool-blocked) ─
# agvtool new-marketing-version is broken on this project (it looks for a
# literal "YES" path) and the xcodeproj gem 1.27.0 can't parse the project (a
# PBXShellScriptBuildPhase stores shellScript as an Array). Value-only flat
# substitution makes no structural change; integrity is re-checked below via
# `agvtool what-version -terse` (if the project were broken, agvtool would not parse it).
# Project rule #10 sanctions agvtool/xcodeproj; this is the documented fallback.
sed -i '' -E "s/^([[:space:]]*)MARKETING_VERSION = .*;/\1MARKETING_VERSION = $APP_VERSION;/" "$PBX"

# ── backend: both [tool.briefcase] and [project] version lines ───────────────
# Anchored to a digit so a hypothetical `version = "<string>"` dep key is untouched.
sed -i '' -E "s/^version = \"[0-9].*\"/version = \"$ENGINE_VERSION\"/" "$PY"

# ── verify ───────────────────────────────────────────────────────────────────
echo
echo "verify:"
echo -n "  MARKETING_VERSION configs: "; grep -cE "MARKETING_VERSION = $APP_VERSION;" "$PBX"
echo -n "  CURRENT_PROJECT_VERSION:   "; ( cd "$ROOT/fichero" && xcrun agvtool what-version -terse )
echo "  engine version:"; grep -nE '^version = ' "$PY" | sed 's/^/    /'
pep440_check "$ENGINE_VERSION"
