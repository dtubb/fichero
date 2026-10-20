#!/usr/bin/env zsh
# REAL end-to-end recipe run of one commit on the test Mac (a dev tool, not shipped): 4-5 dev-corpus pages,
# Find Regions -> Find Lines -> Read (Kraken), started as a person's Start, bounded to 15 minutes.
#
#   scripts/realrun_seeded.sh <sha>      (run on the M4; checks the sha out in ~/code/fichero-worktrees/check)
#
# THE SEED: a fresh state dir has no Kraken reader, so Start downloads one first, and that one-time download was 228 s of a
# 268 s run (2026-10-20). This script copies the reader in before the engine starts, so the wall time measures reading
# (43 s, same pages). The seed is the reader the run uses, PP-OCRv6 (medium), Zenodo record 10.5281/zenodo.21788410, 61 MB:
# ~/Fichero Dev Test/reader-seed/kraken-models, a copy of the state/kraken-models of any finished run (the engine downloaded
# it once through its normal path). The pages are ~/Fichero Dev Test/reader-seed/src (dev-corpus photographs, no owner data).
# To re-seed, copy a finished run's state/kraken-models into reader-seed/. Everything it writes is under ~/Fichero Dev Test.
# The engine's bootstrap token is read from the app's key file and never printed.
SHA="${1:?usage: realrun_seeded.sh <sha>}"; D="$HOME/Fichero Dev Test/realrun-$SHA"; O="$D/out"; SOCK=/tmp/rr14f3.sock
mkdir -p "$O" "$D/state"; rm -rf "$D/state" "$D/rr.fichero"; mkdir -p "$D/state"; rm -f $SOCK
# The Kraken reader (PP-OCRv6 medium) is copied in, so the wall time measures reading, not the one-time download
# (a fresh state dir spent 228 s of 268 on it, 2026-10-20). To re-seed: copy a finished run's state/kraken-models to reader-seed/.
cp -R "$HOME/Fichero Dev Test/reader-seed/kraken-models" "$D/state/"
cd ~/code/fichero-worktrees/check && git fetch -q ~/code/fichero-test.git "+refs/heads/*:refs/remotes/t/*" && git checkout -qf --detach $SHA || { echo CHECKOUT-FAILED > $O/verdict; exit 4; }
echo "code $(git rev-parse --short=9 HEAD)" > $O/status
source ~/code/fichero/.venv/bin/activate; export PATH=/opt/homebrew/bin:$PATH HF_HUB_OFFLINE=1
export PYTHONPATH=$PWD/fichero-server/src:$PWD/fichero-server:$PWD/fichero-cli/src:$PWD/fichero-mcp/src
FICHERO_FEATURE_TIER=beta FICHERO_BASE_PATH="$D/state" FICHERO_UDS_PATH=$SOCK FICHERO_LIBRARY_ALLOWED_ROOTS="$D" FICHERO_BOOTSTRAP_TOKEN="$(cat $HOME/Library/Application\ Support/Fichero/.api-key)" nohup caffeinate -dis python -m fichero_server > "$O/engine.log" 2>&1 &
EP=$!
for i in $(seq 1 90); do [ -S $SOCK ] && break; sleep 1; done
R() { FICHERO_UDS=$SOCK python -m fichero_cli --library "$D/rr.fichero" "$@"; }
R library create "$D/rr.fichero" > $O/create.txt 2>&1
R import "$HOME/Fichero Dev Test/reader-seed/src" > $O/import.txt 2>&1
R --json recipes assemble --purposes transcribe --languages es --scripts Latn --materials handwriting --no-cloud-allowed --pages 5 --jobs find-regions,find-lines,read-a-line > "$O/recipe.json" 2>&1
python3 -c "
import json,sys
d=json.load(open('$O/recipe.json'))
ids=[a.get('id') for a in d.get('automatic',[])]+[b.get('job') for b in d.get('left_off',[])]+[c.get('id') for c in d.get('by_hand',[])]
print('AUTOMATIC', [a.get('id') for a in d.get('automatic',[])])
print('LEFT_OFF', [(b.get('job'), b.get('sentence')) for b in d.get('left_off',[])])
print('BY_HAND', d.get('by_hand'))
print('GAPS', d.get('gaps'))
" > "$O/assembled.txt" 2>&1
cat "$O/assembled.txt"
if ! python3 -c "import json,sys; d=json.load(open('$O/recipe.json')); sys.exit(0 if any(s.get('id')=='find-regions' for s in d.get('steps',[])) else 1)"; then echo 'NO-FIND-REGIONS-STEP' > "$O/status"; exit 7; fi
A='{"purposes":["transcribe"],"languages":["es"],"scripts":["Latn"],"materials":["handwriting"],"directions":{"Latn":"ltr"}}'
R recipes save-project-setup --answers "$A" --recipe "$(cat $O/recipe.json)" > $O/save.txt 2>&1
date +%s > $O/t_go
R --json recipes start-project > "$O/start.json" 2>&1
J=$(python3 -c "import json;print(json.load(open('$O/start.json'))['started']['job_id'])" 2>/dev/null)
echo "job $J" >> $O/status
end=$(( $(date +%s) + 900 )); s=none
while [ $(date +%s) -lt $end ]; do
  R --json recipes run-status $J > "$O/rs.json" 2>&1; s=$(python3 -c "import json;print(json.load(open('$O/rs.json')).get('state'))" 2>/dev/null)
  case "$s" in running|queued|waiting|pending) sleep 10;; *) break;; esac
done
date +%s > $O/t_end
echo "state $s" >> $O/status
R --json recipes run-summary $J > "$O/summary.json" 2>&1
R --json documents list > "$O/docs.json" 2>&1
python3 - "$O" > "$O/steps.txt" 2>&1 <<'PY'
import json,sys
out=sys.argv[1]
rs=json.load(open(f"{out}/rs.json"))
for s in rs.get("steps",[]): print("STEP", s.get("job"), s.get("state"), s.get("why"), "waiting_for=", rs.get("waiting_for"))
print("reason", rs.get("reason"))
PY
for n in 001 002 003 004 007; do :; done
R --json segments list-document "$(python3 -c "
import json
d=json.load(open('$O/docs.json'))
ids=[]
def w(x):
    if isinstance(x,dict):
        if isinstance(x.get('name'),str) and x['name'].endswith('.jpg') and 'id' in x: ids.append((x['name'],x['id']))
        for v in x.values(): w(v)
    elif isinstance(x,list):
        for v in x: w(v)
w(d)
print(' '.join(i for n,i in sorted(set(ids))[:1]))
" )" > /dev/null 2>&1
kill $EP 2>/dev/null; sleep 4; kill -9 $EP 2>/dev/null
grep -cE "ERROR|did not become a pass|Traceback" $O/engine.log > $O/errors-count.txt
grep -E "ERROR|did not become a pass|Traceback" $O/engine.log | head -20 | cut -c1-220 > $O/errors.txt
tail -40 $O/engine.log > $O/engine-tail.txt
echo DONE >> $O/status
