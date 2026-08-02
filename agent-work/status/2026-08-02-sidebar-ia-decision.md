# Sidebar information architecture — one decision, seven issue numbers

**For:** Daniel · **From:** lane-crash2 · **2026-08-02**
**Do not implement any of this without a decision. Nothing here has been built.**

---

## The decision, stated once

> **Entities, research projects, workspaces and workflows stop being bespoke
> sidebar MODES and become node kinds in the library tree.**

That is the whole of #1686, #1738, #1793, #2446, #2447, #4102 and #4335. Seven
issues filed over eight weeks, in three milestones, all describing the same
change from different angles. A triage lane already identified the cluster and
named **#4102 canonical**; this document adds the part nobody had written down —
**what is actually built** — and turns it into something answerable in one pass.

---

## Are the older five superseded?

**Partly, and not in the way that lets you close them.** I tested the hypothesis
rather than assuming it.

| # | Filed | Claim | Superseded by | Built? |
|---|---|---|---|---|
| #1686 | Jun 6 | entities browse like a library (grid/list/table, multi-select) | #2447 restates it structurally | **no** |
| #1738 | Jun 7 | research/workspaces are movable library items | #2446 | **no** |
| #1793 | Jun 8 | entities/research keep the sidebar visible instead of replacing content | #2446 + #2447 | **no** |
| #2446 | Jun 20 | remove Research/Workspace modes; add them as node kinds | #4102 (canonical) | **no** |
| #2447 | Jun 20 | remove Entities mode; entities are folder-like nodes | #4102 (canonical) | **no** |
| #4102 | Jul 26 | retire the bottom sections; libraries listed separately | — canonical | **half** |
| #4335 | Jul 30 | every created node kind appears in the tree | stage of #4102 | **partly** |

**Recommendation: close #1686, #1738, #1793, #2446 and #2447 as duplicates of
#4102**, carrying their specifics into it as acceptance criteria. Not because
the work is done — it mostly is not — but because five stale designs in a
milestone read as five separate jobs, and the next lane to pick one up will
re-derive this whole analysis. One issue with seven acceptance criteria is
answerable; seven issues describing one change is not.

The trade-off: #1686 carries a detail the others lose — entities should reuse
**LibraryView's own view-mode machinery** (grid/list/table/map, multi-select),
not merely appear in the tree. That is a real requirement and must survive the
merge, or the entity surface becomes a list where a library used to be offered.

---

## What is actually built, as of `integration` today

**Retired already** — the pinned bottom navigation rows. `SidebarView+PinnedNavigationRows.swift`
now says so in source: *"The pinned bottom navigation rows (workflows browser,
scoped chat, research, saved workspaces, entities) are retired (#4102)."* Only an
automation load-error row remains. So **#4102's removal half is done.**

**Still fully present** — the modes themselves. `ViewSettings.swift:188`:

```swift
enum SidebarMode: String, CaseIterable {
    case library, chat, workflows, automation, activity
    case research        // 8: Research projects + workspace
    case knowledgeGraph  // 9: Entity / ontology browser
}
```

and `SidebarModeIcon` renders `SidebarMode.allCases`, so **every mode still has a
button**. #2446 and #2447 are untouched.

**Partly built** — the tree's node vocabulary. `SidebarItem.ItemType` already
holds twelve kinds including `savedSearch`, `conversation`, `workflow`, `chain`,
`comparison`, `schedule`, `trigger`. It has **no** case for a workspace, a
research project or an entity. So the tree can already express most of what
#4335 asks for, and specifically cannot express the three things this decision
is about.

**The honest summary:** the bottom sections were removed, which took away the
*duplicate* entry points, but the modes they duplicated are still there. The IA
is currently half-migrated — which is worse than either end state, because a
user can reach research and entities only through a mode bar that the rest of
the design has moved away from.

---

## What you are actually deciding

Three questions. Recommendations given, because you are deciding, not designing.

### 1. Do entities become library nodes at all?

**Recommend: yes.** It is the direction every issue in the cluster points, it
matches the #2081 node model, and it removes a whole content-replacing mode.

**The trade-off you should know before saying yes:** an entity is not a
container in the same sense a folder is. A folder holds documents; an entity is
*referenced by* documents. Making it "a folder you drill into" means its
children are a **query result** (documents mentioning this person), not a stored
membership list. That is fine — saved searches already work that way — but it
means dragging a document "into" a person cannot mean the same thing as dragging
it into a folder. #1686 explicitly wants "add photos to a person", so this needs
an answer: does dropping on an entity create a claim/annotation linking them?

### 2. Do research projects and workspaces become library nodes?

**Recommend: yes, and this one is cheaper than it looks.** A workspace is
already a `Document` with `is_workspace` set — it is *already* a node in the
tree's data model, it simply has no `ItemType` case and no renderer. This is
closer to wiring than to redesign.

### 3. What happens to the mode bar?

**Recommend: keep `library`, `chat`, `workflows`, `automation`, `activity`;
remove `research` and `knowledgeGraph`.** Those two become node kinds. The rest
are genuinely app-level surfaces rather than per-library containers.

**The trade-off:** removing `knowledgeGraph` removes the only route to the
ontology/graph browser, which is a real view with no per-entity equivalent.
Either it moves to the View menu (⌘-number, as #4102's own note suggests) or the
graph becomes a *view mode* of the library the way Canvas did. The second is
more coherent and more work.

---

## Suggested sequencing, if you say yes

Cheapest first, each independently shippable:

1. **Workspace + research as `ItemType` cases and renderers.** Data already
   exists; this is the wiring half of #4335 and the positive half of #2446.
2. **Remove the `research` mode** once (1) makes it redundant.
3. **Entity nodes** — needs the answer to question 1 first.
4. **Remove the `knowledgeGraph` mode** — needs the answer to question 3.
5. **#1686's entity-library view modes**, reusing LibraryView's machinery.

Steps 1 and 2 are unblocked by anything in this document and are the ones I
would hand to a lane on Tuesday.

---

## What I did not do

No code. No issue closures. The recommendation to close five as duplicates is a
recommendation; I have not closed them, because collapsing seven issues into one
is itself an IA decision and it is yours.
