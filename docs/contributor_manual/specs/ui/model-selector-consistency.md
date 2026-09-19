---
title: Model / Provider Selector — Consistency Spec
status: DRAFT
owner: creative director
tags: [model-picker, providers, ai, consistency, design-lead-testing]
related: [ai-settings-redesign-proposal, menus-and-commands]
---

# Model / Provider Selector — Consistency Spec

> Milestone: model-selector-consistency

> Manual: TBD — the user manual's AI section needs "Choosing a model": that the picker is the same
> control everywhere it appears (island, workflow bar, Settings), what local vs remote means for
> privacy and cost, and how to add a provider key.
>
> **DRAFT for review 2026-09-15.** CD brief: "The model/API-key node selector isn't consistent
> between the document island (top of window), the workflow bar, and the Settings window. The one in
> the document island looks best — be consistent with it. It's design-lead testing, so review it."
> This is a **review + proposal**, grounded in the code, not yet ratified.

Legend: **[OK]** matches intent · **[BROKEN]** diverges · **[GAP]** missing · **[PROPOSED]** this
spec's recommendation. The reference surface is the **document island** (`ModelChipToolbarItem`).

---

## Intent (the design)

Choosing which model runs is ONE decision the user makes in several places. Wherever it appears — the
window's model chip, the workflow bar's per-step picker, a chat toolbar, a comparison sheet — it must
look and behave the SAME: same rows, same family glyph, same cost display, same grouping, same
"configured tiers first," same vision/selection awareness. Settings is the one different job (it
MANAGES the catalog — add/remove/configure keys), but even it renders the same ROW so a model looks
identical whether you're picking it or configuring it. One picker component, one list policy, one row.

This is the same "one source, many surfaces" principle as [[menus-and-commands]] and the workspace
consolidation.

---

## Current architecture (grounded, 2026-09-15) — ~7 pickers, 3 list-builders

There is no shared picker. At least seven implementations render "choose a model":

| Surface | File | Shape | List logic |
|---|---|---|---|
| **Document island (REFERENCE)** | `Shell/Toolbar/ModelChipToolbarItem.swift` (`ModelChipToolbarItem` + `ModelFamilyMark` + `ModelPickerRow`) | compact chip → popover | selection-aware (vision vs text tier); loads its own provider cache on menu-open |
| Workflow bar (per step) | `Shell/Toolbar/WorkflowBarModelPicker.swift` (+ `WorkflowBarModelTier`) | Menu | configured tiers first, then provider-grouped, deduped on **provider+model**, vision flag + cost |
| Settings | `Settings/AI/AIProviders/AIModelSelectionView.swift` (+ `AIModelCatalog`, `ModelRowView`) | full filtered list | filter (capabilities/mode) + sort (cost/…) + search + add-model — a MANAGEMENT view |
| Chat toolbar | `Chat/ChatViewToolbar.swift` (`ChatModelPicker`) | Menu | its own |
| Comparison | `Chat/ModelComparison/ModelPickerSheet.swift` | sheet | its own |
| Workflow node | `Workflow/Nodes/ModelPicker.swift`, `NodeProviderModelSelector.swift` | inline | its own |

**Finding S1 — three different list-builders for the same list.** The island loads a provider cache
on open; the workflow bar has a pure tier-first/provider-grouped/deduped builder; Settings has a
filter+sort pipeline. They each claim to use "the same provider cache the Run Workflow menu uses,"
but assemble and order it differently — so the same account can show different models, in a different
order, at different (or no) cost, depending on where you look.

**Finding S2 — the ROW is drawn three ways.** The island's `ModelPickerRow` + `ModelFamilyMark`
(family glyph, tier, vision hint) is the nicest; the workflow bar draws its own menu rows; Settings'
`ModelRowView` draws its own with cost/capabilities. A model has three faces.

**Finding S3 — vision/selection awareness is island-only.** Only `ModelChipToolbarItem` narrows to
vision-capable models when a page is selected. The workflow bar carries a `visionFlag` but the chat
and node pickers don't consistently. Awareness should be a property of the shared component.

**Finding S4 — cost display is inconsistent.** Settings and the workflow bar show per-million cost;
the island shows tier/family; chat shows neither. Cost is a first-class decision input and should
render the same everywhere it's shown.

---

## Proposed design — one picker, one list policy, one row (build on the island)

### 1. Extract the island's row as the shared row — **[PROPOSED]**
`ModelFamilyMark` + `ModelPickerRow` (the reference's row: family glyph · name · tier · vision hint ·
cost) become a shared component every surface renders — the island, workflow bar, chat, comparison
node, AND Settings' management list (same row, plus its add/remove affordance). No surface hand-draws
a model row.

### 2. One pure list-builder — **[PROPOSED]**
Generalize `WorkflowBarModelPicker`'s already-pure builder (configured tiers first → provider-grouped
→ deduped on **provider+model** → vision flag → cost, with a tiers-only fallback when the cache is
empty) into the ONE model-list function. The island, workflow bar, chat and node pickers all call it;
Settings' management view filters/sorts ON TOP of the same base list. Selection/vision-awareness is a
parameter (the island passes "vision" when a page is selected), not a fork.

### 3. One picker component, two presentations — **[PROPOSED]**
A single `ModelPicker` view (the island's chip+popover as the canonical presentation) with a compact
mode (chip, for toolbar/workflow-bar/chat) and, where a sheet is warranted (comparison), the same
rows in a sheet. Settings keeps its management chrome but hosts the shared rows. One component, so
grouping, family marks, cost and vision awareness can't drift.

### 4. Provider/API-key affordance is consistent — **[PROPOSED]**
Adding/choosing a provider key surfaces the same way from every picker (a "Manage providers…" route
into Settings), so a picker that finds no configured model always offers the same next step, never a
dead empty menu (mirrors `SidebarContextMenuPolicyTests`' never-silently-empty rule).

---

## Behaviors (each → one pinning test)

- `models.one-list-policy` — **[PROPOSED]** every picker's base list comes from the ONE pure builder;
  same account → same models, same order, same dedupe (provider+model), everywhere. *Test:* pure
  unit tests over the builder (extend the existing `WorkflowBarModelPicker` list tests): tier-first
  order, provider+model dedupe, tiers-only fallback, vision filter narrows correctly.
- `models.one-row` — **[PROPOSED]** the island, workflow bar, chat and Settings render the SAME row
  component (family mark + name + tier + cost). *Test:* a source guardrail that no surface defines
  its own model-row struct once the shared one exists.
- `models.vision-awareness` — **[PROPOSED]** a page/vision selection narrows every picker to
  vision-capable models identically. *Test:* the builder's vision-filter unit test, plus the island's
  existing selection→tier resolution test.
- `models.cost-shown-consistently` — **[PROPOSED]** where cost is shown it is the same value and
  format across surfaces. *Test:* a formatter unit test + a render check.
- `models.never-empty-offers-providers` — **[PROPOSED]** a picker with no configured model always
  offers the Manage-providers route, never a silent empty menu. *Test:* pure policy test (the
  `SidebarContextMenuPolicyTests` fallback shape).

---

## Maintainer test, 2026-09-19 morning

Evidence for the "~7 pickers, 3 list-builders" finding above, plus a fourth captured picker and
a ruling.

- `models.four-pickers-today` — **[BROKEN]** (#4883) what each of four surfaces shows today, as
  observed live (workflow bar, centre island, Settings > AI > Defaults, and — newly
  captured, screenshot 9.40.17 — the workflow node's config popover):

  | Picker | Shows today |
  |---|---|
  | Workflow bar | flat text list, "Use the default (model)" first, each row a name + a loose tag mixing capability/size/provider ("Vision", "Text", "Large", "apple", "openrouter", "huggingface", "spacy", "kraken", "whisper"); no icons, no prices; unavailable models greyed |
  | Centre island | provider icon, name, price per million tokens in/out, an eye icon for vision-capable models, a tick on the current one, provider name at the right, "AI Settings..." link at the bottom |
  | Settings > AI > Defaults | grouped under provider headings (Apple Intelligence, Hugging Face, ...), full ids ("datalab-to/chandra-ocr-2"), descriptive names ("Apple Vision (OCR)"), a "None" row |
  | Workflow node config popover | lists ONLY the role defaults, each with a generic "?" icon and no provider icon: Default, $small, $large, $vision_small, $vision_medium, $vision_large; lists NO concrete models at all |

  Four different shapes, confirming Finding S1/S2 above with a fourth data point rather than
  the three already catalogued. Whether a row shows price, capability, provider, or all three
  remains an open DESIGN question (see "Open questions," item three, below) — not decided by this finding.
- `models.four-pickers-four-sources` — **[PARTIAL]** (#4883) cause, verified at each file at the
  time this behavior was written: four pickers, four different data sources, not just four
  different rows/layouts, with the workflow bar's `modelPinMenu` (hand-drawn `Button` rows, no
  `SharedModelRow`/`SharedModelChoice` use) the one outlier surface. **Updated 2026-09-19
  (705e65cf1)**: per that commit's own account, five of the six picker surfaces already shared
  `SharedModelListBuilder` before this fix — the "zero adoption" framing above is stale, corrected
  here. This commit closes the workflow bar's own remaining gap: its model control is now the
  same popover idiom the step inspector uses, rendering `SharedModelRow`, and its two hand-drawn
  menus (`modelMenu`, `modelPinMenu`) are deleted outright. **Which source is canonical is NOT an
  open question** — the node popover's own code already cites the ruling:
  `docs/contributor_manual/specs/ui/workflow-node-config.md`'s
  `nodeconfig.model.same-list-as-settings` (ruled 2026-09-08, `[OK]`, pinned
  `NodeModelListParityTests`) states pickers offer the user-CONFIGURED models, because the live
  catalog used to let a node pick a model its provider does not actually serve → a 404 at run.
  PARTIAL, not OK: **NOT SEEN ON SCREEN** (the fixing commit's own words — build passes, tests
  pass, "how the popover and its rows look on screen" is unverified); the island's own catalog
  source and Settings' own row are still open per the maintainer's own outstanding questions
  (below). Pinned: `SharedModelListBuilderTests` (17 cases), `NodeModelListParityTests`,
  `AISettingsSelectionTests`, `ModelRowSourceGuardrailTests` — all executed through Xcode per
  the commit, all passing.
- `models.role-defaults-always-offered` — **[PARTIAL, RULED]** (#4883) every model picker offers
  the ROLE DEFAULTS (small, large, vision small, and so on) as choices ALONGSIDE concrete models
  — in the workflow bar and the document island the maintainer must be able to choose "small",
  "large", "vision small", etc, not only a named model. The one shared picker (§"Proposed
  design" above) should have two groups: role defaults (resolved to whatever Settings > AI >
  Defaults currently names, and SAYING which model that is) and concrete models. At the time
  this behavior was written, only the workflow node popover offered role defaults, and it
  offered ONLY those, no concrete models — the opposite gap. **Updated 2026-09-19 (705e65cf1)**:
  role defaults now have ONE home, `SharedModelListBuilder.roleDefaultAliases(from:
  includeVision:)` — it builds `$small`/`$large`/the three vision aliases from `AIDefaults`,
  each naming the concrete model it resolves to today (or "not set"); no such resolver existed
  before. The node popover's own private `aliasOptions` is deleted and now takes the shared
  rows; the workflow bar's new popover offers every role default alongside the concrete models
  (picking a role default stores the ALIAS, not the resolved model, so a run-level override
  never silently freezes — a text alias chosen on a vision step raises, and the bar already
  marks that choice unsuitable). Still open, per the maintainer, and NOT decided here: how the
  ISLAND offers role defaults (it stores a CONCRETE (provider, model) pair only —
  `ModelChipToolbarItem.swift:259`, `select(_:)` — it is where a role default GETS its value, so
  it cannot hold a role alias today) and what SETTINGS' own row should show. **NOT SEEN ON
  SCREEN** — same disclaimer as `models.four-pickers-four-sources` above.
- `models.node-popover-vision-check-diverges` — **[BROKEN]** (#4694) the workflow node config
  popover says "No vision-capable providers available" in orange on a vision node
  (screenshot 9.40.17), while the other three pickers on the same machine show vision-capable
  models as available (apple-vision, claude-opus-5, and others with the eye icon) at the same
  time. **Cause: UNVERIFIED — two candidates, both consistent with the code, neither confirmed
  against what the maintainer's machine actually returned.** (a) Stale-capabilities path:
  `NodePopover+Comparison.swift:28-32` derives `supportsVision` from the SAVED rows'
  `capabilities`; the id-based heuristic (`idLooksVisionCapable`) runs only when `capabilities`
  is empty — so a saved row with a non-empty `capabilities` set that happens to lack "vision"
  is marked not-vision-capable even if the island's live catalog flags the same model as
  vision-capable. This is a catalog-content divergence, not a load race. (b) Empty-providers
  path: `loadProviders()` (`:8-23`) only appends a provider when `provider.enabled` is true and
  `listProviderModels` succeeds — the screenshot shows the popover listing NO concrete models
  at all, only role defaults, which equally fits zero enabled/configured providers returned, or
  an unhandled throw into the function's own `catch`. Both are named; neither is the confirmed
  cause. #4694 already names the same CLASS of bug ("Node picker filters providers on the
  provider-level vision flag") — evidence added there rather than duplicated as a new issue.
- `models.chat-picker-uses-the-shared-builder` — **[PARTIAL]** (#4900) the chat toolbar's model
  picker (`ChatViewToolbar.swift`, `ChatModelPicker`) renders the shared
  `SharedModelListBuilder`/`SharedModelRow` spine, not its own inline picker. Built: `21820e8d2`
  (82 insertions, 31 deletions). PARTIAL because nothing tests it — the commit's own message
  states outright: "No tests reference this surface." A high-traffic surface (every chat
  window's model picker) with zero coverage of the rewrite. The test shape that would catch a
  regression: drive the picker through the real shared builder and assert the rendered choice
  set, PLUS an explicit companion asserting the chat toolbar's production call site still
  routes through it rather than a re-inlined picker — the same pure-function-plus-
  call-site-routing pairing `AISettingsSelectionTests` uses for its own
  "productionCallSiteRoutesOnlyThroughThePureFunction" check.

## RATIFIED 2026-09-15 (evening, CD)

- **Adopt the shared spine.** One shared ROW (the island's `ModelFamilyMark` / `ModelPickerRow`) +
  one pure list-builder (generalize `WorkflowBarModelPicker`'s tier-first / provider-grouped /
  provider+model-deduped / vision+cost builder). Every surface — island, workflow bar, chat,
  comparison, nodes — renders both. The ~7 divergent pickers collapse to one spine. Land
  subtractively (shared row → shared builder → per-surface adoption), each step pinned by a pure
  list-builder test. Keep the builder PURE (the island fetches its own cache outside the
  `LibraryWorkspaceRoot` env, #4448) — don't bake an environment read into it.
- **Settings uses the SAME picker — direct, one-step selection.** In the Settings window you choose a
  model the SAME way as the island: the shared picker (chip → popover of the shared rows), picked
  directly — NOT "open a menu, then a submenu" to drill to a model. Settings keeps its management
  affordances (add/remove providers, keys, filters) around that picker, but the act of CHOOSING the
  active/default model is the one shared component, so it looks and behaves identically to the island.
  (This supersedes "Settings reuses the ROW only" — it reuses the whole picker for selection.)
- **Platform = iPad / Mac / iOS first-class** (matches [[menus-and-commands]]): the shared row +
  builder must render correctly on all three; test each.

## Open questions (still open)

1. **Chip vs menu vs sheet** — **ANSWERED 2026-09-19 (705e65cf1)**: the workflow bar's model
   control is now the same popover idiom the step inspector uses (not a `Menu`), rendering
   `SharedModelRow`; its `Choose Model` right-click menu item opens the same popover. Not seen
   on screen yet, per that commit's own disclaimer.
2. **Settings' scope** — Settings manages keys/catalog (a superset job). Confirm it reuses the shared
   ROW only, keeping its filter/sort/add chrome — not that it collapses into the picker.
3. **Cost everywhere?** — should the island show per-million cost too (it shows tier/family today), or
   is cost a workflow-bar/settings concern where budget matters most? **Candidate answer recorded,
   not decided here** (from the source-model spec work, branch `spec/page-model`, `specs/source/
   models-chains-and-projects.md` — not in this tree): a row could show what a "model card" knows
   — what it suits (languages/scripts/periods), whether it's local or cloud, and a licence class —
   alongside or instead of price/capability/provider. See `ai-settings.md`'s own Open Question 5
   for the model-card shape this candidate answer depends on.
4. **Node vs step pickers** — the workflow NODE pickers (`ModelPicker`, `NodeProviderModelSelector`)
   and the workflow BAR picker — one component for both, or do nodes need more (provider+model+params)?
5. **How does the island offer role defaults?** (`models.role-defaults-always-offered`) The island is
   verified to store only a resolved concrete `(provider, model)` pair — it IS where $medium/
   $visionMedium get their value, so it cannot itself hold a role-alias sentinel the way the node
   popover's `aliasOptions` do. Does picking "$medium" from the island mean "show me what $medium
   currently resolves to, then let me change that value" (the island stays the editor of the
   default), or does the shared picker need a genuinely separate role-alias affordance the island
   does not have today?

---

## Ponytail review (2026-09-15)

The lazy, correct move is to promote what already works, not add a new abstraction: the island's
`ModelFamilyMark`/`ModelPickerRow` is the nicest row — make it the shared one; the workflow bar
ALREADY has the pure list-builder with dedupe/tiers/vision/cost — make it THE one and delete the other
list logics. Net change is deletions plus a couple of extractions, not a new picker framework.

Watch-outs:
- **Settings is a different job** (management), not just a picker — reuse its ROW, don't force it into
  the chip. Collapsing them would lose the add/remove/key affordances.
- **Data source boundary** — the island fetches its own cache because a toolbar item lives OUTSIDE the
  `LibraryWorkspaceRoot` env tree (`ModelChipToolbarItem` documents this #4448 boundary). The shared
  list-builder must stay PURE (takes `[LLMProvider]` + tier defaults), so each host feeds it from
  wherever it legitimately gets the cache — don't bake an environment read into the shared component.
- **Don't over-unify presentation** — chip, menu and sheet are legitimately different containers for
  different contexts; share the rows and the list policy, not necessarily one container.
- Land it in increments (shared row first → shared list-builder → per-surface adoption), each pinned
  by an extended existing test, exactly like the menu and workspace programs.

**Verdict:** adopt the island's row + the workflow bar's pure list-builder as the shared spine;
Settings reuses the row; land subtractively. Ready for CD review, not yet code.
