(AI generated. Not reviewed.)

# Mac UI Shape — Holistic Design Proposal (EPIC #2030)

> Status: **DRAFT for Daniel's review** (2026-06-11). The structural keystone
> (#2031) ships first as a focused fold; this doc is the target the rest of the
> reform (toolbar #2032, Liquid Glass #2041, chrome/styling #2033–#2040) builds
> toward. Nothing here is implemented beyond #2031 until approved.

## 1. North star — what the Mac app's *shape* should be

Fichero is a **Finder-grade archival workspace**, not a stack of unrelated
screens. One window, one coherent spatial model the user never loses their place
in. Every "mode" is a different **lens on the same library**, not a different app.

The shape that delivers that is a **single persistent three-column shell** —
`sidebar | content | inspector` — that **never tears down**. Switching lens swaps
**only the content column** (and the inspector's *content*); the navigation rail
and the inspector frame are constant. This is the Xcode/Mail/Finder model, and
it's what makes the app feel native rather than web-in-a-window.

## 2. The persistent shell (the spine) — #2031

```
┌──────────────┬───────────────────────────────┬──────────────┐
│  SIDEBAR     │          CONTENT              │  INSPECTOR   │
│  (rail)      │   (the active lens)           │  (detail)    │
│              │                               │              │
│  ◦ Library   │   library → docs/folders      │  per-lens    │
│  ◦ Search    │   search  → results           │  detail:     │
│  ◦ Chat      │   chat    → conversation      │  • doc info  │
│  ◦ Workflows │   workflows→ node editor      │  • KG detail │
│  ◦ Automation│   activity → run browser      │  • run info  │
│  ◦ Activity  │   mindPalace→ spatial canvas  │  • node info │
│  ◦ MindPalace│   research → chat+browser     │  • tasks     │
│  ◦ Research  │   knowledge→ entity list      │  • entity    │
│  ◦ Knowledge │                               │              │
└──────────────┴───────────────────────────────┴──────────────┘
        ▲                    ▲                        ▲
   never replaced     only this swaps        one shared inspector,
                      on lens change         content routes per lens
```

**Confirmed by audit:** the `NavigationSplitView` shell already persists; the bug
is that three lenses (research, mindPalace, knowledgeGraph) smuggle their **own
private inspector pane** into the content column, and the real window inspector is
blind to the active lens. #2031 fixes exactly that (see issue comment for the
per-mode fold). After #2031 the spine is true: **one inspector, content-routed.**

## 3. Information architecture — grouping the 9 lenses

Nine flat sidebar items is a lot. Proposal: **group the rail into bands** (Finder
sidebar style — labelled sections, not a flat list), ordered by how an archivist
works:

- **MATERIAL** — Library, Search  *(the documents themselves)*
- **KNOWLEDGE** — Knowledge Graph, Mind Palace  *(what's *in* the documents)*
- **WORK** — Workflows, Automation, Activity  *(processing the documents)*
- **THINK** — Research, Chat  *(reasoning over the documents → becomes the Agent, EPIC #2067)*

Open question for Daniel: are these the right four bands, and the right names?
(This is the IA decision that most shapes "the feel.")

## 4. The shared inspector — one frame, per-lens content (+ tabs within a lens)

- **One** window-level inspector frame, toggled by one control, visibility
  persisted per-window (`@SceneStorage`).
- Its **content routes on the active lens** (the `inspectorView` switch *is* the
  router). Within a lens, sub-tabs stay internal (e.g. document inspector's
  Info / KG / Annotations tabs).
- Selected tab **persists across lens switches** (`@SceneStorage("inspector.selectedTab")`).
- Rogue private panes (SpatialNodeInspector, ResearchTasksPane, KG detail pane)
  become the shared inspector's content for their lens. *(#2031)*

## 5. Toolbar — zoned, lens-aware — #2032

One **zoned toolbar** spanning the window, not per-pane button soup:

```
[ sidebar toggle ] [ ‹ lens-local nav › ] ····· [ lens actions ] ····· [ view: ◫ ☰ ▦ ] [ inspector toggle ]
   leading              content-leading            content-center           content-trailing      trailing
```

- **Leading/trailing** zones (sidebar + inspector toggles, global) are **constant**.
- **Content zones** are **lens-aware**: the middle changes with the lens (library
  shows import/new-folder + layout picker; KG shows graph/list/timeline; workflows
  shows run/stop). Same *zones*, different *contents* — mirrors the shell's "frame
  constant, content swaps" rule.
- Every action here must also exist in the **menu bar + context menu + a keyboard
  shortcut** (the Mac-assed completeness matrix, EPIC #1925).

## 6. Materials / Liquid Glass — where glass belongs — #2041

Tahoe Liquid Glass is a **structural accent, not a coat of paint**. Proposal:

- **Glass:** the sidebar rail, the toolbar, inspector chrome, floating overlays
  (loupe, command palette) — the *navigation surfaces*.
- **NOT glass:** the content column's working surface (document text, page images,
  tables, the node canvas) — **content stays opaque and legible**; reading
  archival material through frosted glass is wrong.
- Respect reduce-transparency / increase-contrast; never trade legibility for sparkle.

## 7. Cross-cutting Finder-grade behaviors (the "assed" in Mac-assed)

These make it feel native; they cut across every lens (track per existing EPICs):

- **Tabs + multiple windows** on the same library; ⌘N = new library, ⌘T = new tab,
  open-in-new-window from context menu. *(File-New = #2042 ✅)*
- **Show ALL items, no caps**; List/Table/Icons/Map per fit (#1969 semantic fonts,
  Finder-selection EPIC #1962).
- **Multi-select everywhere** + rich **context menus** mirroring the toolbar.
- **Keyboard navigation**: ⌘1–9 to switch lens, arrow/⌘↑↓ to move, space = Quick Look.
- **Nothing renders from a local path** — always the storage endpoint (remote-safe).
- **State persists per window** via `@SceneStorage` (lens, column widths, inspector tab).

## 8. Phasing (so the reform ships without a big-bang rewrite)

1. **#2031 — shell keystone (NOW):** true persistent spine + shared inspector. *(focused fold; approved)*
2. **#2032 — zoned toolbar:** the lens-aware toolbar zones.
3. **IA banding:** group the 9 lenses into the 4 bands (§3) — small, high-impact.
4. **#2041 — Liquid Glass:** apply glass to navigation surfaces only (§6).
5. **#2033–#2040 — chrome/styling polish** against the now-stable shape.
6. Continuous: the **completeness matrices** (#1925) keep menu/context/toolbar/keyboard in sync.

## 9. Open questions for Daniel (the taste calls)

1. **IA bands (§3):** right grouping + names (MATERIAL / KNOWLEDGE / WORK / THINK)?
2. **Inspector default:** open or closed by default per lens? (Library: open; Mind Palace: ?)
3. **Chat/Research/Chat → Agent:** §3 puts Research+Chat in one band; EPIC #2067 says they
   converge into the Agent. Should the rail show "Agent" as one lens now, or keep
   Research + Chat separate until #2067 lands?
4. **Tabs:** do you want document tabs *within* the content column (Safari-style) or
   only window-level? (Affects the toolbar's leading zone.)
5. **Liquid Glass aggressiveness:** subtle (rail + toolbar only) or also inspector
   panels + sheets?

---
## 0. Product spine — the three layers (READ → THINK → WRITE)
The UI shape exists to serve the research lifecycle, as three source-grounded layers:
- **Hermeneutic (READ)** — decompose sources → claims/SVO/entities/citations, bbox-anchored.
- **Interpretative (THINK)** — notes/annotations on a reading (human + AI), tied to sources.
- **Synthesis (WRITE)** — Zettelkasten + outliner + Scrivener-like composition → citation-aware export (EPIC #2108).
A **workspace** is the synthesis container; the **Agent** (#2067) works across all three and writes in the same space as the human. See memory `three-layer-product-spine`.
