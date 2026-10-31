#!/bin/bash
# Owner set-up for the dev harness's second macOS user (dev-workflows spec section 0).
# Run as the OWNER:
#   scripts/harness_setup.sh --dry-run   prints every command and the read-only findings; changes nothing, asks nothing
#   scripts/harness_setup.sh             does it (sudo asks for your password; one yes before ~ is closed)
#   scripts/harness_setup.sh --probe     only the probe (re-run it after the worker's tools are installed)
#   scripts/harness_setup.sh --undo      chmod ~ back to the recorded mode, remove the sudoers line; says how to delete the user
# Safe to re-run: every step skips what is already done. The worker user is NOT admin and NOT in staff.
set -euo pipefail
cd /   # sudo -u keeps the cwd; after chmod 700 ~ the worker cannot read one inside it (git: "Unable to read current working directory")

MODE="do"
case "${1:-}" in --dry-run) MODE=dry ;; --undo) MODE=undo ;; --probe) MODE=probe ;; "") ;; *) echo "usage: $0 [--dry-run|--probe|--undo]"; exit 2 ;; esac
DRY=0; [ "$MODE" = dry ] && DRY=1
OWNER="$(id -un)"
WUSER="${FICHERO_WORKER_USER:-fichero-worker}"
WGID="${FICHERO_WORKER_GID:-599}"          # a group of its own (staff is 20)
WORKROOT="${FICHERO_WORKROOT:-/Users/Shared/fichero-worker}"
REPO_URL="${FICHERO_REPO_URL:-https://github.com/dtubb/fichero.git}"   # public: anonymous clone; never ~/code/fichero
REPO_SLUG="${FICHERO_REPO_SLUG:-dtubb/fichero}"
SUDOERS="/etc/sudoers.d/$WUSER"
STATE="$HOME/.fichero-harness-setup-state"  # the previous mode of ~, for --undo

[ "$(id -u)" != 0 ] || { echo "run as the owner, not root"; exit 1; }
run() { if [ "$DRY" = 1 ]; then printf 'DRY-RUN: %s\n' "$*"; else printf '+ %s\n' "$*"; "$@"; fi; }
as_worker() { run sudo -n -u "$WUSER" -H "$@"; }
say() { printf '\n== %s\n' "$*"; }
user_exists() { id "$WUSER" >/dev/null 2>&1; }

# ---------------------------------------------------------------- probe (as the worker user; each line must be DENIED)
# A denial counts only if the thing being proved was really attempted: a missing tool (127) or a failure that is not an
# authorisation failure is UNPROVEN, never "denied". UNPROVEN does not pass the wall silently: it is listed and the run says so.
LEAK=0; UNPROVEN=0
# /usr/bin/git is an xcrun shim: the new user's first call runs xcodebuild -find git (minutes under load; NOT a hang).
GITBIN=git; for g in /Library/Developer/CommandLineTools/usr/bin/git /Applications/Xcode.app/Contents/Developer/usr/bin/git /opt/homebrew/bin/git; do [ -x "$g" ] && { GITBIN="$g"; break; }; done
[ "$GITBIN" != git ] || echo "note: no real git found; the first git call as $WUSER goes through the xcrun shim and may take minutes (not a hang)"
as_w() { sudo -n -u "$WUSER" -H "$@"; }
probe_read() {   # path the worker must NOT be able to read; skipped (said) if it does not exist for the owner
  local p="$1"
  [ -e "$p" ] || { echo "skip (absent for the owner): $p"; return; }
  if as_w /bin/sh -c 'test -r "$1"' sh "$p" >/dev/null 2>&1; then echo "LEAK: $WUSER can read $p"; LEAK=1; else echo "ok (denied): read $p"; fi
}
probe_net() {    # label, then a command; denied only if it failed AND the error is an authorisation failure
  local label="$1"; shift
  local out rc=0
  out="$(as_w env GIT_TERMINAL_PROMPT=0 "$@" 2>&1)" || rc=$?
  if [ "$rc" = 0 ]; then echo "LEAK: $label SUCCEEDED as $WUSER"; LEAK=1
  elif [ "$rc" = 127 ] || echo "$out" | grep -qiE "command not found|no such file"; then echo "UNPROVEN: $label (tool missing for $WUSER; re-run --probe once installed)"; UNPROVEN=1
  elif echo "$out" | grep -qiE "could not read Username|terminal prompts disabled|Authentication failed|403|401|HTTP 4|gh auth login|not logged in|Permission denied|requires authentication"; then echo "ok (denied): $label"
  else echo "UNPROVEN: $label failed, but not with an authorisation error: $(echo "$out" | tail -1 | cut -c1-120)"; UNPROVEN=1; fi
}
run_probe() {
  say "the probe, as $WUSER: every line must be denied"
  if ! user_exists; then echo "(dry-run: $WUSER not created yet; the probe would run these)"; fi
  local libs=("$HOME" "$HOME/Fichero Projects" "$HOME/Library/Keychains/login.keychain-db")
  local g; for g in "$HOME"/Library/Application\ Support/Fichero* "$HOME"/Library/Containers/*ichero* "$HOME"/Library/Group\ Containers/*ichero*; do [ -e "$g" ] && libs+=("$g"); done
  if [ "$DRY" = 1 ] || ! user_exists; then
    local p; for p in "${libs[@]}"; do echo "DRY-RUN: as $WUSER, test -r '$p'  (expect: denied)"; done
    echo "DRY-RUN: as $WUSER, git push --dry-run $REPO_URL HEAD:refs/heads/probe  (expect: authorisation failure)"
    echo "DRY-RUN: as $WUSER, gh api -X POST repos/$REPO_SLUG/issues -f title=probe  (expect: authorisation failure)"
    return
  fi
  local p; for p in "${libs[@]}"; do probe_read "$p"; done
    probe_net "git push by URL" "$GITBIN" -C "$WORKROOT/clone" push --dry-run "$REPO_URL" HEAD:refs/heads/probe
  probe_net "gh api write" gh api -X POST "repos/$REPO_SLUG/issues" -f title=probe
  [ "$LEAK" = 0 ] || { echo "THE WALL LEAKS; do not use the harness (scripts/harness_setup.sh --undo to back out)"; exit 1; }
  [ "$UNPROVEN" = 0 ] || echo "probe: no leak found, but some lines are UNPROVEN above: the wall is not yet proved"
}

if [ "$MODE" = probe ]; then user_exists || { echo "$WUSER does not exist"; exit 1; }; run_probe; exit 0; fi

# ---------------------------------------------------------------- undo
if [ "$MODE" = undo ]; then
  [ -f "$STATE" ] || { echo "no recorded mode in $STATE: nothing to undo"; exit 1; }
  run chmod "$(cat "$STATE")" "$HOME"
  run sudo rm -f "$SUDOERS"
  rm -f "$STATE"
  cat <<MSG
undone: ~ is back to $(stat -f %Sp "$HOME"), the sudoers line is gone. The user and the workroot remain. To delete them:
  sudo sysadminctl -deleteUser $WUSER        (removes the account and its home)
  ls -la $WORKROOT                           (look first, then: sudo rm -rf $WORKROOT)
  sudo dseditgroup -o delete $WUSER          (the group)
MSG
  exit 0
fi

say "checks (read-only)"
df -h / | tail -1 | awk '{print "disk free: "$4" ("$5" used)"}'
if user_exists; then echo "user $WUSER exists (primary group $(id -gn "$WUSER"))"; else echo "user $WUSER does not exist yet"; fi

say "1. a group of its own and the user (not admin, not staff)"
if dscl . -read "/Groups/$WUSER" >/dev/null 2>&1; then echo "group $WUSER exists"; else run sudo dseditgroup -o create -i "$WGID" "$WUSER"; fi
if user_exists; then echo "user $WUSER exists: skipped"; else run sudo sysadminctl -addUser "$WUSER" -fullName "Fichero worker" -GID "$WGID" -password -; fi
# the home directory must exist (sysadminctl sometimes leaves it out)
if [ "$DRY" = 1 ]; then echo "DRY-RUN: if /Users/$WUSER is missing: sudo createhomedir -c -u $WUSER"
elif [ ! -d "/Users/$WUSER" ]; then run sudo createhomedir -c -u "$WUSER" || true; [ -d "/Users/$WUSER" ] || { echo "no home for $WUSER; stopping"; exit 1; }; fi
# not a member of staff, or stop
if [ "$DRY" = 1 ] && ! user_exists; then echo "DRY-RUN: dsmemberutil checkmembership -U $WUSER -G staff  (must say: not a member; else stop)"
else
  m="$(dsmemberutil checkmembership -U "$WUSER" -G staff 2>&1 || true)"
  echo "staff check: $m"
  echo "$m" | grep -qi "not a member" || { echo "$WUSER is in staff (or the check failed): staff can read the owner's home. Stopping."; exit 1; }
fi

say "2. the owner's home closed to everyone else"
CUR="$(stat -f %Lp "$HOME")"
echo "current mode of $HOME: $CUR ($(stat -f %Sp "$HOME"), owner $(stat -f %Su "$HOME"), group $(stat -f %Sg "$HOME"))"
echo "who can read it today through the group ($(stat -f %Sg "$HOME")) and will LOSE that read at 700:"
gid="$(stat -f %g "$HOME")"
dscl . -list /Users PrimaryGroupID | awk -v g="$gid" -v me="$OWNER" '$2==g && $1!=me {print "   user " $1 " (primary group)"}'
dscl . -read "/Groups/$(stat -f %Sg "$HOME")" GroupMembership 2>/dev/null | sed 's/GroupMembership: //' | tr ' ' '\n' | awk -v me="$OWNER" 'NF && $1!="root" && $1!=me {print "   member " $1}' || true
for u in $(dscl . -list /Users UniqueID | awk '$2>=500 && $2<1000 {print $1}'); do [ "$u" = "$OWNER" ] || [ "$u" = "$WUSER" ] || echo "   other local user (uid>=500): $u (admin: $(dsmemberutil checkmembership -U "$u" -G admin 2>&1 | grep -qi 'is a member' && echo yes || echo no))"; done
echo "other users' processes now running (they may need the home):"; ps -axo user= | awk -v me="$OWNER" '$1!="root" && $1!=me && $1!="nobody" && $1!="daemon" && $1 !~ /^_/ {print "   " $1}' | sort -u || true
echo "system launchd jobs that run as a named user:"; grep -l "<key>UserName</key>" /Library/LaunchDaemons/*.plist 2>/dev/null | head -10 | sed 's/^/   /' || true
echo "(file sharing: System Settings > General > Sharing; a shared folder under $HOME stops working for others at 700)"
if [ "$DRY" = 1 ]; then echo "DRY-RUN: would ask 'close $HOME to mode 700? [y/N]', record $CUR in $STATE, then chmod 700 $HOME"
else
  if [ "$CUR" = 700 ]; then echo "already 700"
  else
    read -r -p "close $HOME to mode 700 (was $CUR)? [y/N] " yn
    [ "$yn" = y ] || { echo "not closed: the wall would leak; stopping"; exit 1; }
    [ -f "$STATE" ] || echo "$CUR" > "$STATE"
    run chmod 700 "$HOME"
  fi
fi

say "3. the workroot: public data only, writable by both users"
run sudo install -d -m 1777 "$WORKROOT"

say "4. one narrow sudoers line: the owner may run commands AS the worker user, nothing else"
TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT
echo "$OWNER ALL=($WUSER) NOPASSWD: ALL" > "$TMP"
if [ "$DRY" = 1 ]; then echo "DRY-RUN: visudo -cf <file containing: $(cat "$TMP")>"; else sudo visudo -cf "$TMP"; fi
run sudo install -m 440 -o root -g wheel "$TMP" "$SUDOERS"
[ "$DRY" = 1 ] || sudo visudo -cf "$SUDOERS"

say "5. the worker's git identity and trust of trees under the workroot"
as_worker "$GITBIN" config --global user.name Claude
as_worker "$GITBIN" config --global user.email noreply@anthropic.com
if [ "$DRY" = 0 ] && sudo -n -u "$WUSER" -H "$GITBIN" config --global --get-all safe.directory 2>/dev/null | grep -Fxq "$WORKROOT/*"; then echo "safe.directory already set: skipped"
else as_worker "$GITBIN" config --global --add safe.directory "$WORKROOT/*"; fi

say "6. the worker's clone, anonymous over https (no credential exists for this user)"
if [ "$DRY" = 0 ] && sudo -n -u "$WUSER" -H test -d "$WORKROOT/clone/.git"; then echo "clone exists: skipped"
else as_worker "$GITBIN" clone "$REPO_URL" "$WORKROOT/clone"; fi

run_probe

cat <<MSG

== left for you, as the worker (sudo -iu $WUSER), each once:
  - install claude, uv, ruff and gh? (gh is optional; without it the gh probe line stays UNPROVEN) for that user: they live in
    your home otherwise, which it cannot read. Create a venv under $WORKROOT and put its python in harness.toml [check] python
  - sign claude in as $WUSER (claude /login, or claude setup-token if the Keychain is locked); keep the token out of $WORKROOT
  - then: scripts/harness_setup.sh --probe, and the smoke test (one claude turn, one ladder on a throwaway commit)
MSG
