# Where is the line between a default and a user workflow — and does storage respect it?

Requested by the manager before any storage change (Daniel: *"why can I run
workflow in one library but not the other … or maybe that makes sense,
workflows, but not for defaults"*). Answer first, fixes second. **No storage
change was needed or made.**

## The answer

**The line exists, is well-drawn, and is exactly the one Daniel asked for.**

- The line is **`is_system`**, and it is written by exactly one writer: the
  seeder (`seed_default_workflows`). Create, import, and duplicate never set
  it; **editing a preset demotes it** (`is_system=False`, #780) — so an edited
  default becomes a user workflow of the library where the edit happened,
  which is the correct semantics.
- **Defaults are stored once, as rows in the GLOBAL library** (#4102, #4450) —
  not seeded per-library (so they cannot diverge), and not raw JSON at
  runtime (so a user can still edit them, in the global library, and the edit
  is a row). The shipped JSON is only the install-time template.
- **User workflows are rows in the library that created them** and never
  resolve cross-library. A user workflow created while the global library was
  open is a global-library workflow — still not a default (`is_system` gate).
- **Read paths fall back** from the request's library to the global defaults:
  `list_workflows`, `get_workflow`, duplicate, workflow-runs join, the
  execute path (`workflow_execution/core.py`), and chains
  (`store.get(...) or resolve_default_workflow(...)`).
- **Mutating paths deliberately do NOT fall back** (update/patch/delete/
  reorder + their action-layer twins): a default is read-only outside the
  global library, and a user workflow from another library stays invisible.
  Correct, verified site by site (9 sites, all mutating).

So do NOT unify storage — the design already distinguishes exactly what
Daniel's second clause asks for. The bug he saw was the pre-#4450 world
(defaults seeded per-library); #4450 fixed the main paths, and Tuesday's
click-list item 3 verifies it in the app.

## What did NOT respect the line (found by sweeping every lookup site)

Three read paths missed the #4450 sweep — the "runs in one library but not
the other" class, still live in the tree:

1. **Model/workflow comparison** (`_workflow_from_request`,
   `_workflow_from_compare_request`): looked up only the request library's
   DB → comparing against a shipped default 404'd in every non-global
   library. FIXED: same `resolve_default_workflow` fallback the other read
   paths use.
2. **Sub-workflow child resolution** (`resolve_sub_workflow_ref`): chain was
   injected-state → library DB → **shipped JSON**, skipping the global
   library entirely. Consequence: a user's edit to a default *component*
   (e.g. tweaked prompts on the Spanish Script child passes) took effect
   when the parent ran in the global library and was silently ignored
   everywhere else — same workflow, different behaviour per library. FIXED:
   global-default resolution (id then name, `is_system` rows only) inserted
   before the JSON fallback. Seam ledger count bumped in the same commit.
3. **`compare-node/apply`** (persists a model choice onto a workflow node)
   correctly has NO fallback — it mutates, and defaults are read-only outside
   the global library. Left as is, noted so nobody "fixes" it.

Tests: `test_subworkflow_db_resolution.py` (global edit wins outside global,
by id and name; global *user* workflow does NOT leak) and
`test_model_comparison_default_workflows.py` (default resolves anywhere;
unknown id still 404s). All fail without the fixes.

## The cross-HOST half ("run a workflow on a host with local things")

Storage answer: each host's engine seeds defaults into its own global
library, so defaults exist on every host without sync. User workflows ride
inside the `.fichero` package, so they travel with a shared/moved library.
That part is coherent today. What Daniel is gesturing at beyond it — a
remote engine running host-local workflows over the paired-HTTPS transport —
is a capability/design question (which host's engine executes, whose
provider keys, whose models), not a storage bug; it belongs with the
connection/multi-user milestones, not this sweep.
