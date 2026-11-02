# Workflow source node: memory, measured (#4390)

Status: design note for Step 2.5 of `specs/ui/workflows.md`; the build is Step 2.6.

## The problem

The Files and Folder source nodes put every selected document's full dump, `page_content` included, into the run's
state (`state["documents"]` and the node's stored output). State is held for the whole run, checkpointed, and capped at
8 MB serialised (#5518), so a large folder either fails the cap or sits in memory from the first node to the last.

## Measured

`fichero-server/scripts/measure_source_node_memory.py` builds a temporary library (never the app database), runs the
Folder source over N pages of 40 KB of text each, and prints peak RSS.

| Pages | Page text held in state | JSON of the state documents | Peak RSS growth | Where |
|------:|------------------------:|----------------------------:|----------------:|-------|
| 50    | 2,048,000 B             | n/a                         | +3.4 MB         | Pro   |
| 500   | 20,480,000 B            | 21,154,500 B                | +44.7 MB        | M4 iMac (lane-sharing a55ee5d28c) |

Growth is linear in pages and is the page text carried in state; 500 pages already overshoot the 8 MB state cap, and
the 4,292-page Marshall Diaries would hold about 175 MB of text for the whole run.

## Decision

- The source emits references (`id, name, doc_type, parent_id, sequence, path`), the shape `document_ref` already
  produces for the Work Out Dates preset (#5518). References are the default; `documents_as: "full"` keeps the old dump.
- The node function hydrates references into full documents for the one tool call that needs them, from the library
  database, and drops them when the call returns. State and stored outputs carry ids only.
- A tool that loads pages itself (`date_extract`) is listed as reference-aware and receives the references untouched.

## Ceiling

Hydration is per node call, not per batch inside a tool: peak memory is one node's pages, not the whole run's.
A tool that wants a tighter bound can become reference-aware and load pages in its own batches.
