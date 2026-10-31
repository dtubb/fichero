#!/bin/bash
# Owner set-up for the dev harness's second macOS user (dev-workflows spec section 0; review 3 B1-B3).
# Run as the OWNER, once:   scripts/harness_setup_owner.sh --dry-run    (prints every command, changes nothing)
#                           scripts/harness_setup_owner.sh              (does it; sudo asks for your password)
# The worker user is NOT admin and NOT in staff (staff can read the owner's home), and the owner's home gets chmod 700.
set -euo pipefail

DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
OWNER="$(id -un)"
WUSER="${FICHERO_WORKER_USER:-fichero-worker}"
WGID="${FICHERO_WORKER_GID:-599}"          # a group of its own (staff is 20)
WORKROOT="${FICHERO_WORKROOT:-/Users/Shared/fichero-worker}"
REPO_URL="${FICHERO_REPO_URL:-https://github.com/dtubb/fichero.git}"   # public: anonymous clone, no credential, never ~/code/fichero
SUDOERS="/etc/sudoers.d/$WUSER"

run() { if [ "$DRY" = 1 ]; then printf 'DRY-RUN: %s\n' "$*"; else printf '+ %s\n' "$*"; "$@"; fi; }
as_worker() { run sudo -n -u "$WUSER" -H "$@"; }
say() { printf '\n== %s\n' "$*"; }

say "checks (read-only)"
df -h / | tail -1 | awk '{print "disk free: "$4" ("$5" used)"}'
[ "$(id -u)" != 0 ] || { echo "run as the owner, not root"; exit 1; }
if id "$WUSER" >/dev/null 2>&1; then echo "user $WUSER exists: group $(id -gn "$WUSER") (must not be staff)"; EXISTS=1; else echo "user $WUSER does not exist yet"; EXISTS=0; fi
stat -f "home %N is %Sp (owner %Su, group %Sg)" "$HOME"

say "1. a group of its own and the user (not admin, not staff)"
if dscl . -read "/Groups/$WUSER" >/dev/null 2>&1; then echo "group $WUSER exists"; else run sudo dseditgroup -o create -i "$WGID" "$WUSER"; fi
if [ "$EXISTS" = 0 ]; then run sudo sysadminctl -addUser "$WUSER" -fullName "Fichero worker" -GID "$WGID" -password -; fi

say "2. the owner's home closed to everyone else (staff would otherwise read it)"
run chmod 700 "$HOME"

say "3. the workroot: public data only, writable by both users"
run sudo install -d -m 1777 "$WORKROOT"

say "4. one narrow sudoers line: the owner may run commands AS the worker user, nothing else"
TMP="$(mktemp)"; echo "$OWNER ALL=($WUSER) NOPASSWD: ALL" > "$TMP"
if [ "$DRY" = 1 ]; then echo "DRY-RUN: visudo -cf <file containing: $(cat "$TMP")>"; else sudo visudo -cf "$TMP"; fi
run sudo install -m 440 -o root -g wheel "$TMP" "$SUDOERS"; rm -f "$TMP"
[ "$DRY" = 1 ] || sudo visudo -cf "$SUDOERS"

say "5. the worker's git identity and trust of trees under the workroot"
as_worker git config --global user.name Claude
as_worker git config --global user.email noreply@anthropic.com
as_worker git config --global --add safe.directory "$WORKROOT/*"

say "6. the worker's clone, anonymous over https (no credential exists for this user)"
as_worker git clone "$REPO_URL" "$WORKROOT/clone"

say "7. the probe: every line below must FAIL as $WUSER"
for cmd in "test -r $HOME" "test -r '$HOME/Fichero Projects'" "gh auth status" \
           "env GIT_TERMINAL_PROMPT=0 git -C $WORKROOT/clone push --dry-run origin HEAD:refs/heads/probe"; do
  if [ "$DRY" = 1 ]; then echo "DRY-RUN: sudo -n -u $WUSER -H sh -c '$cmd'  (expect: fails)"
  elif sudo -n -u "$WUSER" -H sh -c "$cmd" >/dev/null 2>&1; then echo "LEAK: '$cmd' SUCCEEDED as $WUSER"; LEAK=1; else echo "ok (denied): $cmd"; fi
done
[ "${LEAK:-0}" = 0 ] || { echo "the wall leaks; fix before using the harness"; exit 1; }

cat <<MSG

== left for you, as the worker (sudo -iu $WUSER), each once:
  - install claude, uv and ruff for that user (they live in your home otherwise, which it cannot read);
    create a venv under $WORKROOT for the project and put its python in harness.toml [check] python
  - sign claude in as $WUSER (claude /login, or claude setup-token); keep the token out of $WORKROOT
  - then the smoke test (before anything more is built): one claude turn, one ladder on a throwaway commit, the probe
MSG
