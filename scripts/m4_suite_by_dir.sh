#!/bin/zsh
# Engine unit suite, one pytest per top-level test directory, so a silent death loses one
# directory and the log names it. Built for the second Mac ("the M4", ssh m4); works anywhere.
#
#   mkdir -p ~/fichero-overnight/bydir-<sha>
#   caffeinate -i zsh scripts/m4_suite_by_dir.sh ~/fichero-overnight/bydir-<sha> [<checkout> [<python>]]
#
# Wait for a line "DONE" in <out>/SUMMARY.txt; each line is "<dir> exit=<n> <pytest summary>".
# <checkout> defaults to ~/code/fichero-worktrees/check; <python> to ~/code/fichero/.venv/bin/python.
# Node must be on PATH or the reader tests skip (they never skip here: /opt/homebrew/bin is added).
export PATH=/opt/homebrew/bin:$PATH
out=${1:?usage: m4_suite_by_dir.sh <out-dir> [<checkout> [<python>]]}
repo=${2:-$HOME/code/fichero-worktrees/check}
py=${3:-$HOME/code/fichero/.venv/bin/python}
mkdir -p "$out"; cd "$repo" || exit 2
for d in fichero-server/tests/unit/*(/) ; do
  n=${d:t}
  PYTHONPATH=$PWD/fichero-server/src $py -m pytest -q -rfE --timeout=300 -p no:cacheprovider $d > $out/$n.log 2>&1
  echo "$n exit=$? $(tail -1 $out/$n.log | cut -c1-120)" >> $out/SUMMARY.txt
done
PYTHONPATH=$PWD/fichero-server/src $py -m pytest -q -rfE --timeout=300 -p no:cacheprovider fichero-server/tests/unit/*.py > $out/_toplevel.log 2>&1
echo "_toplevel exit=$? $(tail -1 $out/_toplevel.log | cut -c1-120)" >> $out/SUMMARY.txt
echo DONE >> $out/SUMMARY.txt
