# Node editor fabel review — 2026-08-02

Question held throughout, per the manager: **does the editor render the graph
the engine will actually execute, or its own idea of it?** Answer: **its own
idea, in three places.** And the #4473 question — could a test pass over a
path that does nothing? — **yes: the editor's entire legality model has zero
tests.**

## Finding 1 (the headline): two connection-legality tables, six-sevenths divergent

- Client: `WorkflowCanvasView+EdgeConnection.swift::canConnect` — allows
  same-type, `any`, plus five conversions: `json→text`, `array→json`,
  `array→text`, `file→files`, `image→file`, `image→files`.
- Engine: `workflows/validation.py::validate_port_connection` — allows
  same-type, `ANY`, and exactly ONE conversion: `FILES→FILE`. (Its
  `ARRAY→ANY` entry is dead code — `ANY` is already accepted earlier.)

Proven pair by pair against the live validator:

```
  json -> text   server=REJECT  client=ALLOW
 array -> json   server=REJECT  client=ALLOW
 array -> text   server=REJECT  client=ALLOW
  file -> files  server=REJECT  client=ALLOW
 files -> file   server=ALLOW   client=ALLOW
 image -> file   server=REJECT  client=ALLOW
 image -> files  server=REJECT  client=ALLOW
```

Consequence: the canvas lets you draw the edge, the workflow saves without
complaint (create/update do NOT run connection validation), and the failure
surfaces only at RUN time — `_validate_workflow_for_execution` refuses with
"Invalid connection from …". A user builds something the editor calls legal
and the engine calls illegal, and finds out last. That is "the node editor is
not working" in one sentence: **it enforces a contract the engine does not
have.**

All 39 shipped presets pass the engine validator — so this bites only
canvas-BUILT workflows, which is why testing presets never surfaced it.

## Finding 2: the client carries hardcoded port tables — a second copy of the tool contract

`WorkflowPortView.swift:302` and `NodePopover.swift:342` fabricate a
`files` input port as a fallback when a node has no port data. The engine's
port truth is the tool registry (`enrich_node_with_ports`). A client-side
fabricated port is the editor's own idea of a tool's interface; when the
registry and the fallback disagree, the editor draws ports that don't exist
or misses ones that do — same class as Finding 1.

## Finding 3: nothing tests the editor's legality model

`canConnect` has **zero** references in `fichero/fichero-tests/`. The engine
validator IS tested — but no test anywhere asserts the two agree, so they
drifted apart with both sides green. This is #4473's shape again: the tests
that exist (server-side) are correct but are not evidence about what the
editor permits.

## What the fix should be (program, not patch)

`impossible > checked > documented`: **one table, owned by the engine,
consumed by the client.**

1. Engine exports its compatibility rule (and per-tool port defs) through
   OpenAPI — either a generated constants schema or on the existing
   `/api/workflows/tools` payload, which already carries port data.
2. `canConnect` reads the served rule; the hardcoded `conversions` dict and
   the fabricated fallback ports are deleted.
3. Save-time validation: `POST/PUT /api/workflows` runs
   `validate_workflow_connections` and returns the errors, so an illegal
   graph is refused when the user can still see why — not at run time.
4. One cross-stack test: the client table (until deleted) must equal the
   served table — the tables cannot silently diverge again.

Interim question for the workflow lane (deliberately NOT decided here): which
table is semantically right? The tools themselves are permissive
(`files_tool` accepts a bare string; text inputs take JSON strings), so the
engine's one-conversion table is probably too strict and the client's five
were someone's observation of what actually works. Whoever fixes this should
decide per-pair from tool behaviour, then encode it ONCE, engine-side.

## Side findings

- `WorkflowDef.version` is `str` but shipped preset JSON carries `version: 1`
  (int) — `WorkflowDef.model_validate(preset)` on raw preset dicts throws.
  Current consumers coerce through the DB row so nothing breaks today, but
  any new code validating presets directly (as `resolve_sub_workflow_ref`'s
  JSON fallback does via model_validate!) inherits a trap. Worth one
  `field_validator` coercion or fixing the JSONs.
- Save paths keep edges and `input_mappings` in sync on detach
  (`detachAndRedrag` removes both) — reviewed, coherent.
- The run-status half of the editor was already hardened by #4457 (stream
  death settles to truth); not re-reviewed.

Filed: see issue "Node editor enforces a connection contract the engine does
not have" (this review is its body).
