# Build notes: the Preview today, and where the segment editor goes in it (slice 13 prep)

For the wireframes the maintainer reviews **before any slice-13 code** (ruled 2026-09-27; see
`segment-editor.md`, "The plan for slices 13 and 13b"). This file is an inventory and a
*proposal*: every placement below is a recommendation for the wireframes, not a decision. Read
on disk 2026-09-27 on `spec/page-model`.

## 1. What the Preview has today

**The pane head** (`PaneHead/PreviewHeadControls.swift`, `PreviewLens.swift`)
- Kind/lens selector: **Preview ∨ / Edit**. *Edit* is IMAGE editing (the edit chain), a different
  content, not segment editing.
- Up to the parent image (↰), previous / next page ‹ › with *n/N*.
- Renditions: previous / next rendition, and a menu naming which rendition is showing.
- Zoom-controls toggle (⌘⌥E).
- ~~**Pencil toggle**: slides the markup row out under the head.~~ **Corrected 2026-09-27:** wrong
  when written. The markup row left the pane head on 2026-08-30 for the WINDOW's annotation bar,
  and its pencil is the window toolbar's split button (`ContentView+Toolbar.annotationBarToggle`),
  not a head control. So Q3's "in the head beside the pencil" was built as a switch in the head's
  controls (`PreviewHeadLensControls`), first in the row; the pencil is in the toolbar above it.

**The markup row** (`PaneHead/PreviewMarkupToolsRow.swift`), in its ruled order:
- Selecting: **Select Text** (⌘⌥U), **Select** (⌘⌥V, the default), **Select Words** (⌘⌥W).
- **Draw Region**: draws EPHEMERAL marquees (run scopes), promoted to regions by naming them.
- Marking: **Line**, **Highlight** (split button: five colours, underline, strikethrough),
  **Text Note**, **Star**, **Check** (✓ / ✓✓ / ✓✓✓).
- Edit verbs, shown with a selection and **only in Edit Segments mode**: **Delete**, **Combine**
  (⌘⌥C).

**The quiet bottom bar**: the **What to show** menu (`ReaderToolbar.whatToShowMenu`): Show
Annotations, Show Word Bounding Boxes, Show Regions, Show Text Inline, and **Edit Segments** (the
mode, #5114).

**The zoom cluster** (bottom right, `PreviewZoomMapCluster`): zoom − / + / 100% / fit, mini-map,
loupe and magnifier toggles; their sizes and locks are settings, not visible switches.

**On the page**: click / ⇧-click / band select; drag a selected box to move it (mode only);
double-click to open a region; ⌫ (a marquee always; regions in the mode only); Esc clears.
**Context menu**: Add Region…, New Region from Selection…, Clear Selections, Combine N Regions,
New Region from Words, Delete Region(s) — the writing verbs only in the mode.
**⌘Z / ⇧⌘Z** for move, delete and combine (#4941).

**The Inspector** (`ArtifactPanel+Regions.swift`): an artifact's line regions as rows; clicking
selects on the page (the shared `RegionSelection`); **Combine** (ruled to stay, #5115) with ⌘Z.

**Switches counted** for `source.editor.two-switches`: eleven stored settings
(magnifier/loupe enabled, sizes, locks; annotations, regions, inline text) plus the markup row.

## 2. Where each behaviour would live

**Proposed shape, in one paragraph.** Keep ONE surface. *Edit Segments* stays the mode (#5114).
The pencil's markup row becomes two groups: **Mark** (line, highlight, note, star, check —
reading tools, always there) and **Segments** (select, draw, reshape, cut, join, link — present only
in the mode, replacing Draw Region's current place). The What-to-show menu keeps reading options,
and gains the editor's **two** switches (Show Order, Show Links) inside an *Editing* section that
appears with the mode. Level of detail replaces "Show Word Bounding Boxes" and "Show Regions".
The zoom cluster is the image viewer's, not the editor's.

| Behaviour | State | Where in the existing Preview | Merge / move / remove |
|---|---|---|---|
| `segment-focus` | PARTIAL | Edit Segments in What-to-show (built); proposed **also** as the pencil's Segments group appearing | Consider moving the switch to the head beside the pencil; the menu entry stays |
| `two-switches` | GAP | Show Order + Show Links in an *Editing* section of What-to-show, visible in the mode | **Remove** Show Regions / Word Bounding Boxes (level of detail decides); loupe & magnifier stay in the zoom cluster as viewer aids, not editor switches |
| `level-of-detail` | GAP | Automatic by zoom: regions → lines → words → characters | Replaces two What-to-show switches |
| `draw-shapes` | GAP | Segments group: box, polygon, point, line, baseline (one tool with a shape picker) | **Merge** with Draw Region: in the mode it draws a segment; out of it, a marquee (as today) |
| `reshape` | GAP | On the page, in the mode: drag corners/sides, double-click an edge to add a point | — |
| `cut` | GAP | Segments group: scissors tool | — |
| `join-group` | PARTIAL | Segments group: Join (today's Combine), Group, Ungroup | **Rename** Combine → Join; Inspector keeps Join (#5115) |
| `propose-shape` | GAP | Segments group: click-to-propose, then adjust | — |
| `draw-link` | GAP | Segments group: drag from one segment to another, pick the type | Needs Show Links on |
| `match-across-passes` | GAP | Context menu on a segment when two passes are open side by side | — |
| `control-points` | GAP | Slice 15 (maps): a GCP tool in the Segments group, georeferencing only | Parked until 15 |
| `marks` | GAP | The Mark group, applied to the SELECTED segments (not only to a drawn area) | **Merge** marks and segment selection: a highlight on a selection marks those segments |
| `set-kind` / `set-direction` / `set-language-script` / `set-hand-campaign` | PARTIAL / GAP | A **Segment** menu (menu bar + context menu) acting on the selection | New menu; the Inspector shows the facts and may offer the same verbs (#5115) |
| `reorder` | PARTIAL | With Show Order on: numbers on the page; drag in the list (the Reader or Inspector) | The order list's home is a wireframe question |
| `selection-shared` | PARTIAL | Already shared Source ↔ Inspector; Reader to join | — |
| `shapes-in-source-view` | PARTIAL | As ruled: shapes here, readings in the Reader, Inspector offers verbs | — |
| `transcribe-by-line` | GAP | The Reader beside the Source view: line picture above its reading, Return → next line | Reader, not this pane |
| `system-undo` / `redo-works` / `edits-are-actions` | PARTIAL | Built through the audited actions; extends to every new verb | — |
| `one-overlay` / `one-input-seam` | PARTIAL / GAP | Engineering: one overlay draws and edits; one pointer seam | No UI of its own |
| `keyboard-complete` | GAP | Every Segments tool and Segment-menu verb gets a menu-bar entry and a shortcut | The menu-bar entry for the mode itself is still owed (scene-graph hazard noted on `segment-focus`) |
| `pencil-draws` / `pencil-traces-strokes` | GAP | iPad: the Segments group's tools take the Pencil; tracing is a separate tool | iPad wireframes |
| `library-lists-segments` | GAP | The Segments pane (approved 2026-09-27) — a list/strip/grid beside, not inside, this pane | Separate wireframe |
| `smooth-when-dense` | GAP | Slice 12's gate: engine side measured and inside budget; frames still to measure on devices | — |
| `voiceover` | GAP | Each visible segment an accessibility element | — |
| `agent-parity` | PARTIAL | Every verb is an action, so MCP and CLI follow | — |
| `source.textedit.*` (11) | PARTIAL / GAP | **13b, the Reader**: typing is a new reading, Return splits, Backspace joins, runs of keys are one action, lines move in the order | Recommended home is the Reader (spec); a sixth pane kind is the alternative the maintainer rules on |

## 3. Questions for the maintainer, in the wireframes

1. **Draw Region**: merge into the Segments group's shape tool (a segment in the mode, a marquee
   outside it), or keep marquees as their own tool?
2. **Two switches**: do "Show Regions" and "Show Word Bounding Boxes" go, with level of detail
   deciding what is drawn?
3. **Where the mode's switch sits**: What-to-show only (as built), or also in the head beside the
   pencil?
4. **Combine → Join**: rename, so the page, the Inspector and the menu use one word.
5. **The order list**: in the Reader, the Inspector, or the Segments pane?
6. **Marks on a selection**: may a highlight apply to selected segments, not only a drawn area?

## 4. Ruled 2026-09-27

The maintainer ruled on all six questions; the rulings are recorded in `segment-editor.md` ("The plan
for slices 13 and 13b"). In short: Q1 **merge** Draw Region into the one Shape tool; Q2 **keep** the
display switches, rethought as **layers** (image on or off, overlays on or off, workspace defaults),
which overrides section 2's proposal to remove Show Regions and Word Bounding Boxes; Q3 the Edit
Segments switch goes in the **head beside the pencil and** stays in What to show; Q4 **Combine → Join**
everywhere; Q5 reorder in **all three places**, drag and keyboard, **one** implementation; Q6 marks
apply to the **selection** or attach to what is drawn over, **Apple Preview's PDF annotations** are the
target (read PDFKit's annotation types first), and marks export as real PDF annotations.
