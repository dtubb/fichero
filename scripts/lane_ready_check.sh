#!/usr/bin/env bash
# The machine check a lane runs before it says READY; the conductor runs it again before review.
# A model's own report is not evidence: this is (spec harness/deterministic-conductor.md, conductor.ready-check).
#
# usage: scripts/lane_ready_check.sh [<rev>]       # default HEAD; compares against origin/integration
#        scripts/lane_ready_check.sh --self-test   # proves each check can fail
# exit 0 = READY, 1 = not ready (each failing check is printed)
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"

check() {  # check <rev> -> prints FAIL lines, returns count
  local rev=$1 base fails=0 n
  base=$(git merge-base origin/integration "$rev")
  n=$(git rev-list --count "$base..$rev")
  # 1. on current integration history: a branch from the pre-rewrite history is thousands ahead
  # ponytail: 60 is a guess at the largest honest lane; raise it if a real lane trips it
  [ "$n" -le 60 ] || { echo "FAIL: $n commits ahead of origin/integration; rebase onto it"; fails=$((fails+1)); }
  [ "$n" -gt 0 ] || { echo "FAIL: nothing to check: no commits ahead of origin/integration"; fails=$((fails+1)); }
  # 2. no private manuscripts in the tree
  if git ls-tree -r --name-only "$rev" -- "docs/user_manual/002 documents" "docs/user_manual/010 Prototypes" | grep -q .; then
    echo "FAIL: private docs/user_manual folders are tracked"; fails=$((fails+1)); fi
  # 3. every commit authored by the agent and citing an issue
  while IFS=$'\t' read -r sha email subj; do
    [ "$email" = "noreply@anthropic.com" ] || { echo "FAIL: $sha author is $email, not the agent"; fails=$((fails+1)); }
    git log -1 --format=%B "$sha" | grep -qE '#[0-9]{3,5}' || { echo "FAIL: $sha cites no issue: $subj"; fails=$((fails+1)); }
  done < <(git log --format=$'%h\t%ae\t%s' "$base..$rev")
  # 4. lint the changed files
  local py sw
  py=$(git diff --name-only --diff-filter=AM "$base" "$rev" -- '*.py')
  sw=$(git diff --name-only --diff-filter=AM "$base" "$rev" -- '*.swift')
  # the findings are printed (first 40 lines): a coder told only "ruff failed" fixed the wrong thing twice (2026-10-25)
  local out
  if [ -n "$py" ] && [ "$rev" = HEAD ]; then
    out=$(echo "$py" | tr '\n' '\0' | xargs -0 ruff check --output-format concise 2>&1) || { echo "FAIL: ruff on the changed Python"; echo "$out" | head -40; fails=$((fails+1)); }; fi
  if [ -n "$sw" ] && [ "$rev" = HEAD ] && command -v swiftlint >/dev/null; then
    out=$(echo "$sw" | tr '\n' '\0' | xargs -0 swiftlint lint --quiet --strict 2>&1) || { echo "FAIL: swiftlint on the changed Swift"; echo "$out" | head -40; fails=$((fails+1)); }; fi
  # 5. a source change comes with a test change
  local src tst
  src=$(git diff --name-only "$base" "$rev" -- 'fichero-server/src/*.py' 'fichero/fichero/*.swift' | head -1)
  tst=$(git diff --name-only "$base" "$rev" -- '*test*' '*Tests*' | head -1)
  [ -z "$src" ] || [ -n "$tst" ] || { echo "FAIL: source changed with no test change"; fails=$((fails+1)); }
  return $fails
}

if [ "${1:-}" = "--self-test" ]; then
  # each case must FAIL: no commits ahead, and (on a scratch commit) a missing issue + wrong author + no test
  out=$(check origin/integration) && { echo "self-test FAIL: an empty range passed"; exit 1; }
  echo "$out" | grep -q "nothing to check" || { echo "self-test FAIL: empty range not reported"; exit 1; }
  tmp=$(echo "no issue here" | GIT_AUTHOR_EMAIL=someone@example.com GIT_COMMITTER_EMAIL=someone@example.com \
        git commit-tree "$(git rev-parse origin/integration^{tree})" -p origin/integration)
  out=$(check "$tmp")
  for want in "not the agent" "cites no issue"; do
    echo "$out" | grep -q "$want" || { echo "self-test FAIL: '$want' not caught"; exit 1; }; done
  echo "self-test OK"; exit 0
fi

rev=${1:-HEAD}
if out=$(check "$rev"); then echo "READY: $(git rev-parse --short "$rev")"; exit 0; fi
echo "$out"; echo "NOT READY"; exit 1
