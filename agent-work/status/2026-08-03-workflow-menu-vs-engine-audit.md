# Workflows: the menu vs what actually runs (#3804)

Audit of every workflow the UI offers against every workflow the engine can
actually run. Verified against the code in this tree at `ba553cfd0`, not
against the issue text — #3804 was filed 2026-07-14 and the tree has moved.

## What the Run Workflow menu actually is

The menu is **not** a hand-written list. `RunWorkflowSubmenuItems.swift` renders
whatever `GET /api/workflows` returns, grouped by `folder_path`, filtered by
`direct_runnable`, each entry expanded to `Default` + the available providers
(+ their models). There is **no hardcoded workflow name anywhere in Swift** —
grep for preset names returns only unrelated labels.

That has one good consequence and one bad one:

- **Good:** no menu entry can name a workflow that does not exist. The classic
  dead-control shape (a menu item pointing at a missing recipe) does not occur
  here. Every tool referenced by every shipped preset resolves in the registry
  (39 presets, 119 nodes, 42 distinct tools — 0 missing, 0 non-executable).
- **Bad:** every rule about *what may be offered* now lives in the list
  response, and the engine does not re-check any of it at run time. The menu is
  the only enforcement point. Any other caller — CLI, MCP, Shortcuts, a direct
  POST — walks straight past it.

So the dead controls in this codebase are not missing workflows. They are
**controls the menu offers that the engine silently ignores**, and **rules the
menu enforces that the engine does not**.

## Population

39 shipped presets in `resources/default_workflows/`, in 10 folders:
Books (1), Catalogue (8), Clean Up (1), Convert (5), Describe (1), Export (1),
Image Editing (8), Organize (1), Transcribe (10), Translate (3).

---

## Findings, worst first

### 1. DEAD CONTROL — `config.internal` is enforced only by the Swift menu

`_workflow_direct_runnable()` (`api/routes/workflow/workflows.py:170`) is the
**only** reader of `config.internal` / `config.input_contract` in the entire
server. It feeds one field on the list response, which one SwiftUI view uses to
filter the menu. The execute route never checks it.

`_validate_workflow_for_execution()` runs connection validation, preflight, and
graph build — none of which know what an internal component is.

Consequence: `POST /api/workflows/execute` with the id of
**"Spanish Script v2 Child Passes (19th-20th C.)"** — a sub-workflow component
that requires contract inputs, not a document selection — is accepted. The CLI
and MCP surfaces list and run workflows without ever reading `direct_runnable`,
so they can and will offer it. The Swift menu hides it correctly; the engine
does not agree with the menu.

This is the #4467 shape: a run that cannot honestly do the thing it was asked
to do should refuse, not proceed.

**Ranked first** because it is a real divergence between menu and engine, on the
side where the engine is more permissive than the UI — which is exactly the side
that lets other clients do the wrong thing.

### 2. DEAD CONTROL — provider/model overrides that provably change nothing

The menu offers `Default` + every available provider + model for **every**
workflow, unconditionally. The engine applies a run-level override only to
top-level nodes whose tool has `uses_llm` (`execution/runner.py:954-966`).

**14 of the 39 shipped presets have zero `uses_llm` nodes at top level.** For
these, picking any provider or model from the menu is a complete no-op: the run
proceeds identically to `Default`, reports success, and nothing tells the user
their choice was discarded.

| Preset | Why the override does nothing |
| --- | --- |
| Enhance Images | pure image op, no LLM node |
| Fuzzy Clean Images | " |
| Prepare Images for OCR | " |
| Recombine Segments | " |
| Remove Background Images | " |
| Rotate / Auto-Orient Images | " |
| Segment Images | " |
| Split Images | " |
| Split Chapters | deterministic split |
| Export to Desktop (MD + DOCX + XLSX) | file export |
| 1 · Import → Artifacts | bookkeeping stage |
| 4 · Merge / Dedup | " |
| 5 · KG Persist / Finalize | " |
| **Transcribe Spanish Script (19th-20th C.)** | **all LLM work is inside a `sub_workflow` child — see 3** |

Thirteen of these are merely meaningless. The fourteenth is actively wrong.

### 3. The `sub_workflow` blind spot — three rules all stop at the parent

"Transcribe Spanish Script (19th-20th C.)" is two nodes: `files` →
`sub_workflow`. The child, "Spanish Script v2 Child Passes", carries the real
work: one `transcribe` and two `transcribe_review` nodes, **all
`category="vision"`**.

Three separate mechanisms scan only `workflow.nodes` and never descend into the
child:

| Mechanism | Where | What it concludes for this preset | Truth |
| --- | --- | --- | --- |
| Run-level override | `execution/runner.py:958` | no LLM nodes → apply nothing | 3 LLM nodes exist |
| LLM/vision preflight | `workflows/validation.py:372` | no LLM nodes → validate nothing | 3 vision nodes exist |
| Menu vision filter | `SidebarSearchTypes.swift:171` | `hasVisionNodes == false` | it is a vision workflow |

Composed, the user experience is: the menu offers **only text-only models** for
a vision-only workflow, the engine accepts the pick without validating it, and
then discards it. Every layer is individually defensible and the composition is
wrong in all three directions at once.

The Swift comment at `SidebarSearchTypes.swift:113-115` says the filter "fails
open ... the engine still rejects a genuinely bad pick". **That claim is false
for any workflow whose LLM work is inside a sub-workflow.** The engine rejects
nothing, because it never looks.

### 4. `(Untested)` is on 38 of 39 presets, so it says nothing

`_workflow_untested()` flags any `is_system` preset whose config lacks
`"tested": true`. Exactly one preset opts in — **Transcribe HTR**. The UI
appends "(Untested)" to a name when the flag is set
(`SidebarSearchTypes.swift:184`), so 38 of 39 menu entries read
"Something (Untested)".

A warning that fires on 97% of the population is not a warning; it is a suffix.
Either the presets get validated and the flag starts meaning something, or the
signal should be inverted (mark the small tested set) — but the current state
tells the user nothing, which is why Daniel cannot tell what a menu item will do.

### 5. Naming and grouping inconsistencies (cosmetic, ranked last)

Each of these is a case where the name does not describe what runs:

- **"Transcribe"** is the display name of `transcribe_cloud.json` — the generic
  no-prompt variant. It reads as the category, sits in the `/Transcribe` folder
  next to four siblings, and is the one entry whose name gives no hint that the
  others are more specific. Its description says so; the name does not.
- **"6 · Catalogue"** (stage) vs **"Catalogue"** (the full 12-node preset), both
  in `/Catalogue`. Two menu entries one word apart doing very different amounts
  of work.
- **"Describe (visual)"** — lowercase parenthetical, unlike every other
  parenthetical in the set (`(Auto-Detect)`, `(DeepL)`, `(Ensemble + Deep
  Review)`, `(local)`, `(19th-20th C.)`). No single convention.
- **"NER per-page (local)"** lives in `/Catalogue`, is the only preset named
  after an acronym, and is the only one whose name states its execution locality.
- Two registry tools, **`translate`** and **`text_translate`**, both translate
  text. "Translate" uses `text_translate`; "Translate (DeepL)" uses `translate`.
  The names carry no hint which is which.
- `config.variant_group` / `config.variant` exist on only 2 of 10 Transcribe
  presets (HTR, Paleography), so the variant vocabulary is half-applied.

These are real, but they are naming. They rank below a control that does nothing.

---

## What the engine can run that the menu never offers

Nothing is hidden by accident. The one preset the menu withholds
("Spanish Script v2 Child Passes") is correctly withheld — it needs contract
inputs, not a selection. The gap is that the engine does not agree (finding 1).

The registry holds 136 tools, 120 executable; 42 are used by shipped presets.
The unused remainder is reachable through the node editor, which is the point of
a node editor, and is not a menu inconsistency.

---

## Fixes in this lane (engine/Python only)

1. **Refuse to execute a non-direct-runnable component.** Move the
   `internal` / `input_contract` rule out of the list-response formatter into a
   function the *execute* path also calls, and 400 with a message that names the
   component and says it must be invoked by a parent `sub_workflow` node. Every
   client inherits the rule; no client can bypass it.
2. **Refuse a run-level override that no node would accept.** If
   `provider_override` / `model_override` is set and the workflow has zero nodes
   that would take it, 400 rather than silently discarding it — and say which of
   the two reasons applies (no LLM nodes at all, vs. all LLM work delegated to
   sub-workflow *X*).
3. **Publish the same answer to the UI** as `accepts_model_override` on the
   workflow response, computed by the *same* function that does the refusing, so
   the menu can stop offering the dead submenu and the two can never drift.

Both refusals follow #4467: raise loudly, never substitute.

## Handed to the Swift lane (not touched here)

- **S1 — hide the dead override submenu.** Consume `accepts_model_override`
  from the workflow response; when false, render `Menu(workflow.name)` as a
  plain `Button` that runs `Default`. Removes 13 meaningless submenus and the
  one actively misleading one. (`RunWorkflowSubmenuItems.swift:38-57`)
- **S2 — the vision filter is a second copy of an engine rule.**
  `WorkflowSidebarItem.requiresVisionModel` re-implements
  `validate_workflow_llm_preflight` client-side from the node list, which is why
  it gets the sub-workflow case wrong. It should read a server-computed field.
  The engine half (descending into sub-workflow children for vision detection)
  is a follow-up here; the Swift half is deleting the local computation.
  (`SidebarSearchTypes.swift:166-180`, `WorkflowStore+Loading.swift:54`)
- **S3 — decide what `(Untested)` means.** Product decision, then either
  validate the presets or invert the flag. Not a code fix until decided.
- **S4 — naming pass** on finding 5. Wants Daniel's eye, not an agent's.

## Follow-up in the engine (not this commit)

- Descend into `sub_workflow` children in `validate_workflow_llm_preflight` so a
  genuinely bad model pick is caught for delegating parents, and so a
  server-computed `requires_vision` can back S2. Needs child resolution inside
  validation, which touches the resolver — worth its own change.
- CLI/MCP list surfaces do not read `direct_runnable`; once fix 1 lands they
  cannot *run* a component, but they will still *list* it. Cosmetic once the
  engine refuses, but worth closing.
