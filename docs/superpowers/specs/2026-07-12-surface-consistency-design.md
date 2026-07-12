# App Surface Consistency — shared chrome across modes (2026-07-12)

Status: plan (Daniel 2026-07-12, "you're in charge"). Extends the shipped
Inspector (10→4) and Reader (3-tab) patterns to every sidebar-level mode.

## Goal

The Inspector and Reader now share a **native chrome**: top-level icon tabs +
bottom filter mini-toolbar + optional sub-tabs, native SwiftUI, cross-platform,
OpenAPI-only, @Observable stores. Apply that SAME pattern to the other modes so
the whole app reads as one system. **Reuse, don't re-implement** — extract the
chrome as shared components (the Inspector design already called for this) and
adopt them everywhere. Cheapest path wins: fold overlapping surfaces rather
than build new ones.

## Sidebar-level modes today (`SidebarMode` / `AppViewMode`)

Library · Search · Chat · Workflows · Automation · Activity · Research ·
Knowledge Graph — plus **Comparison** (currently its own `ModelComparison`
surface, categorized under chat).

Reference (already pattern-compliant): **Reader** (Page/Knowledge/Notes) and
**Document Inspector** (Source/Artifacts/Knowledge/Notes).

## The shared chrome (extract as reusable components)

1. **Top tab bar** — icon row (compact-width adaptive), 3–5 facets per surface.
2. **Bottom mini-toolbar** — count · filter · refresh · selection actions
   (reuse `MiniToolbar.swift`).
3. **Optional sub-tabs / sub-mode switcher** inside a tab (like Reader Knowledge's
   graph/timeline/map).
4. Shared contracts: native `List`/`Table`/OutlineView per fit; full-row
   selection; source-navigation where data has a source; action-history/undo;
   OpenAPI-only; @Observable stores; cross-platform Mac/iPad/iPhone; the entity
   **Lozenge** where entities appear.

Extraction: promote the Reader/Inspector chrome (`ReaderTabBar`, the tab-switcher
+ mini-toolbar pattern) into a reusable `SurfaceChrome` component set that
Workflow/Chat/Research/Search adopt. WorkflowInspector already has a nascent
tab enum (Built-in/MCP/Agents) — migrate it to the shared chrome.

## Per-mode adoption plan (best-guess, refine per review)

### Workflow (tools + chains + editor)
- **WorkflowInspector** adopts the shared chrome. Tabs: **Tools** (Built-in /
  MCP / Agents as sub-tabs — the existing palette), **Chain** (the workflow's
  chain of steps), **Run/Activity** (this workflow's runs). Every node is an
  editable tool (#2441). Chains live here.
- The workflow editor canvas keeps its graph; the inspector is the tabbed detail.

### Chat / Research / Agent (the THINK/agent layer)
- These are variations of one thing: an **agent conversation over documents**.
  Give them the document-inspector chrome: top tabs + bottom mini-toolbar.
- Proposed tabs: **Conversation** (messages), **Sources** (scoped documents —
  ChatInspector already has this), **Knowledge** (entities/claims the agent
  surfaced), **Compare** (see below). Research = the same chrome with a
  project/workspace wrapper.
- The in-app **Agent** (#2067) is the model acting as a user via audited tools —
  same chrome, so chat/research/agent are one consistent surface.

### Comparison → fold into Chat/Agent (cheapest)
- **Roll ModelComparison into Chat/Research/Agent as a "Compare" facet** —
  compare agents/models side-by-side within the conversation surface rather
  than a separate top-level mode. Retire the standalone ModelComparison mode
  once its capability is a Compare tab. (Decision: cheapest = one surface.)

### Search
- Sidebar-level Search adopts the chrome: results list + a bottom mini-toolbar
  for filters/scope (SearchFiltersPanel folds into the mini-toolbar), optional
  tabs for result kinds (documents / entities / claims).

### Knowledge Graph (OntologyBrowser)
- Already tab-like; align its chrome (bottom mini-toolbar + tabs) with the
  Inspector Knowledge tab it mirrors. Low effort — mostly consistency.

## Related node-model needs (Daniel flagged)

- **Image STACK / grouping** (inverse of the reversible split #1595): combine
  two+ images into one GROUP/stack node (e.g. two pages of one letter). Children
  reference a parent group; reversible; each still workable. Ties the node model
  + #1595 reversible split.

## What this is NOT
- Not a rewrite. Adopt the shared chrome on existing surfaces; fold overlaps.
- Canvas/Spatial stay Library view modes (out of scope, per prior decision).

## Milestones (to create)
- **Surface Chrome — Shared Components** (extract the reusable tab+mini-toolbar chrome)
- **Workflow View** (WorkflowInspector → shared chrome; chains; tools)
- **Chat / Agent View** (shared chrome; Comparison folded in as Compare)
- **Research View** (shared chrome over the project workspace)
- **Search View** (shared chrome; filters → mini-toolbar)

## Build order
1. **Extract shared chrome components** (SurfaceChrome: tab bar + mini-toolbar +
   sub-tabs) from the Reader/Inspector implementations — the foundation.
2. **Workflow** adoption (highest overlap with the inspector pattern; tools/chains).
3. **Chat/Agent** adoption + **Comparison fold**.
4. **Research** adoption.
5. **Search** adoption; **Knowledge Graph** alignment.
6. Node-model: image stack/group (#1595 sibling).

Dispatch after the in-flight #3318 (folder+library reconciliation) lands and a
worker frees (2-worker cap). This is planning + issues now; a design/brainstorm
pass with Daniel refines the per-mode tab sets before implementation.
