#!/bin/zsh
# Run compute_bench.py once per config line (stdin: "<stage> <args...>"), one at a time, on a scratch base.
# Each row: the bench's JSON, /usr/bin/time -l's peak RSS of the parent, the exit code, swap used before and after,
# free memory before. A config is skipped when free+inactive memory is under $MIN_FREE_GB. A crash keeps its
# faulthandler stack in crash-<n>.txt. Usage: compute_bench_run.sh OUT.jsonl < configs.txt
setopt pipefail
OUT=${1:?out.jsonl}; PY=${PY:-~/code/fichero/.venv/bin/python}; MIN_FREE_GB=${MIN_FREE_GB:-3}
HERE=${0:A:h}
export FICHERO_BASE_PATH=$(mktemp -d) PYTHONFAULTHANDLER=1
swap() { sysctl -n vm.swapusage | awk '{print $6}' }
free_gb() { vm_stat | awk '/page size of/{ps=$8} /Pages free|Pages inactive|Pages speculative|Pages purgeable/{gsub(/\./,"",$NF); s+=$NF} END{printf "%.1f", s*ps/1024^3}' }
i=0
while read -r line; do
  [[ -z $line || $line == \#* ]] && continue
  i=$((i+1)); f=$(free_gb); s0=$(swap); line=${line//@DB/$FICHERO_BASE_PATH/b$i.duckdb}  # a new scratch file a run
  # N processes each hold a model and a page: a blla process peaked at 7 GB on a 6944x4934 page (M4, 2026-10-27), and a
  # 4-process row took the M4 off the network. Ask for N x PER_PROC_GB free, not the flat minimum.
  need=$MIN_FREE_GB; [[ $line == *"--kind proc"* ]] && need=$(( ${${line##*--n }%% *} * ${PER_PROC_GB:-7} ))
  if (( f < need )); then echo "{\"config\":\"$line\",\"skipped\":\"free ${f} GB < ${need}\"}" | tee -a $OUT; continue; fi
  /usr/bin/time -l $PY $HERE/compute_bench.py ${=line} > run.out 2> run.err; rc=$?
  maxrss=$(awk '/maximum resident set size/{printf "%.2f", $1/1024^3}' run.err)
  (( rc != 0 )) && cp run.err crash-$i.txt
  echo "{\"config\":\"$line\",\"rc\":$rc,\"time_l_parent_rss_gb\":${maxrss:-null},\"free_gb_before\":$f,\"swap_before\":\"$s0\",\"swap_after\":\"$(swap)\",\"therm\":\"$(pmset -g therm | grep -c Speed_Limit)\",\"result\":$(tail -1 run.out | grep '^{' || echo null)}" | tee -a $OUT
done
rm -rf $FICHERO_BASE_PATH run.out run.err
