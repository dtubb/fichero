# Every external-drop surface, what it declares, and what it can accept (#2386)

**Why this exists:** Daniel reported *"drag and drop of a pdf doesn't work from
some locations."* #3390, #702 and #570 are all closed drag-drop-PDF issues and
he still reports drops failing. So a closed issue was not evidence the path
worked — each fix was real and closed **one surface** while others stayed
broken.

This is the enumeration that explains the phrase. It was produced by reading
every drop declaration, not by reproducing one failure.

---

## The table

| # | Surface | Declares | Extraction | Reaches the shared loader? |
|---|---|---|---|---|
| 1 | **Whole window** — `ContentViewModifiers` (`DropTargetModifiers`, applied to the entire `NavigationSplitView`) | was `.dropDestination(for: URL.self)` | SwiftUI `Transferable` URL | **NO** ← the defect |
| 2 | Detail column — `ContentView+RootLayout` | `.onDrop(of: [.item])` | `ExternalFileDropLoader` | yes |
| 3 | Sidebar row — `SidebarItemRow+Presentation+Body` (×3 row shapes) | `.onDrop(of: SidebarItemRow.dropTypes)` | `ExternalFileDropLoader` | yes |
| 4 | Library folder cell — `LibraryView+CellDrop` | `.onDrop(of: SidebarItemRow.dropTypes)` | `ExternalFileDropLoader` | yes |
| 5 | Library section header — `SidebarSectionHeader` | `.onDrop(of: SidebarItemRow.dropTypes)` | shared classifier | yes |

`MainContentModifiers` also carries a `handleFileDrop` parameter, but only to
forward it into `DropTargetModifiers` — it is a pass-through, not a sixth
surface.

## Why surface 1 produced "from some locations"

A `dropDestination(for: URL.self)` is only ever **offered** droppables that can
vend a `URL`. Three shapes arrive at a drop:

1. a real `file-url` — Finder;
2. a **promised file** that must be materialised — many apps, in-progress
   downloads;
3. **`public.pdf` data with no URL at all** — Preview, Mail, some browsers.

Shapes 2 and 3 were not mishandled by surface 1. They were **never handed to
it**. Meanwhile surfaces 2–5, which take `[NSItemProvider]`, would have
accepted all three: `ExternalFileDropLoader` tries a direct URL, then per-UTI
`loadFileRepresentation`, then copies the result to stable storage.

**And surface 1 covers the whole window, so it sits above the others.** Whether
a drop was accepted therefore depended on which surface caught it. Same PDF:
works from Finder, does nothing from Preview.

That is the entire symptom, and it is not "a broken drop path" — it is **two
paths accepting different things with nothing forcing them to agree**, which is
the defect class this codebase keeps producing.

It is also #4458, filed as a *scoping* problem ("scope the content-pane drop to
`detailColumn`, not the whole `NavigationSplitView`"). Scope and extraction were
the same defect: what surface 1 could accept is precisely what made its
shadowing matter.

## The second half: a link is not a file

Separately, and unrelated to the above: there was **no scheme check anywhere in
the import path**. `classifyDroppedURLs` had two buckets — Fichero library
packages, and "everything else, import it" — so dragging a link from a browser
handed `https://example.org/paper.pdf` to the importer **as a file path**. It
failed on a file that does not exist, and the user saw a drop that did nothing.

Half of #2386 was never a bug. It was a feature nobody had built.

## What was fixed, and what was not

**Fixed** (`6a11a9fc2`): all five surfaces take `[NSItemProvider]` and reach
`ExternalFileDropLoader`. Remote URLs are bucketed by `isFileURL == false` —
not a scheme allowlist, so an unanticipated scheme cannot fall through — and
reported to the user instead of being passed off as a path.

**Not built:** downloading a linked PDF. Redirects, auth walls, content-type
sniffing and partial files on a dropped connection are a real feature with a
real failure surface. What exists now is honesty: the drop explains itself
rather than silently doing nothing.

**Not proven:** delivery. The tests cover *classification* — which bucket each
URL shape lands in. They do **not** prove a document exists afterwards with
content in the right parent, because that needs a running app, a real drag
session and a live engine.

Explicitly untested, and named rather than implied:

- a real Finder `file-url` drop
- a promised file
- a data-only provider (`public.pdf`, no URL)
- the loader's per-UTI `loadFileRepresentation` fallback

Those are exactly the shapes #4473 asks about. **Classification-only is what
let #3390, #702 and #570 all close while the bug stayed alive**, so the gap is
recorded here rather than left to be inferred from a green suite.

## Also found

**#3276 is stale.** It says the frontend forces `extractText`/`autoEmbed=false`
on every drag-drop import, making partial failures invisible. No view passes
either flag any more — both default to `nil`, i.e. the engine's own defaults.
The issue wants closing or rewriting.
