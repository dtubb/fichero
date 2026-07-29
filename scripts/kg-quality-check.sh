#!/bin/bash
# KG quality probe — measure entity recall + SVO/claim coverage on a library.
# Run after a workflow has populated the KG (NER per-page or Catalogue).
#
# Usage:
#   ./scripts/kg-quality-check.sh ~/Documents/fichero-loop-test.fichero [doc_id]
#
# Without doc_id: probes every doc in the library.
# With doc_id: detailed per-entity breakdown for that doc.

set -euo pipefail

LIB="${1:-$HOME/Documents/fichero-loop-test.fichero}"
DOC_ID="${2:-}"

CLI="PYTHONPATH=fichero-server/src .venv/bin/python -m fichero --json --library $LIB"

if [[ -n "$DOC_ID" ]]; then
  echo "=== Entities for $DOC_ID ==="
  eval "$CLI kg entities $DOC_ID" \
    | python3 -c '
import sys, json
d = json.load(sys.stdin)
ents = d.get("entities", d) if isinstance(d, dict) else d
for e in (ents if isinstance(ents, list) else []):
    name = e.get("canonical_name") or e.get("name") or "?"
    kind = e.get("entity_type") or "?"
    eid = e.get("id", "?")[:8]
    print(f"  {kind:14}  {name:40}  id={eid}")
print(f"--- {len(ents) if isinstance(ents, list) else 0} entities ---")'

  echo
  echo "=== Claims for $DOC_ID ==="
  eval "$CLI kg claims $DOC_ID" \
    | python3 -c '
import sys, json
d = json.load(sys.stdin)
claims = d.get("claims", d) if isinstance(d, dict) else d
for c in (claims if isinstance(claims, list) else []):
    text = (c.get("text") or "").replace("\n", " ")[:90]
    nents = len(c.get("entity_ids") or [])
    cid = c.get("id", "?")[:8]
    print(f"  [{nents} ents] {text}  id={cid}")
print(f"--- {len(claims) if isinstance(claims, list) else 0} claims ---")'
else
  echo "=== Library-wide KG counts ==="
  eval "$CLI kg search ''" 2>/dev/null \
    | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    counts = d.get("counts", {})
    for k in ("entity", "claim", "note", "annotation"):
        print(f"  {k}: {counts.get(k, 0)}")
except Exception as e:
    print(f"(could not parse: {e})")'

  echo
  echo "=== Per-doc entity / claim counts ==="
  for did in $(eval "$CLI docs list" | python3 -c 'import sys,json; [print(d["id"]) for d in json.load(sys.stdin)]'); do
    ents=$(eval "$CLI kg entities $did" 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); l=d.get("entities", d) if isinstance(d, dict) else d; print(len(l) if isinstance(l, list) else 0)')
    claims=$(eval "$CLI kg claims $did" 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); l=d.get("claims", d) if isinstance(d, dict) else d; print(len(l) if isinstance(l, list) else 0)')
    printf "  %s  ents=%-3s  claims=%-3s\n" "${did:0:8}" "$ents" "$claims"
  done
fi
