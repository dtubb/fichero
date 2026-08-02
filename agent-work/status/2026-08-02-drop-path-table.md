# Drag-and-drop: every path, what it accepts, and what it does

**Lane:** lane-crash2 · **Date:** 2026-08-02 · **For:** lane-plan's fabel review
**Commits:** `ad44d5432` (header + content pane), `<this commit>` (library pane → sidebar)

Daniel, testing the live app: *"drag and drop pdf doesn't work, move in sidebars
copies, etc. review then fix. then test. take time."* Both had been closed as
fixed. This is the review he asked for, written down so the next person does not
have to rediscover it.

Read it as ground truth about the code as of this commit. Where something is
unverified, it says so.

---

## The one-line diagnosis

**The destination infers what a drag MEANS from the UTIs it can see, instead of
the source declaring its intent.** Every defect below is a consequence.

#4123 taught document drags to export a real file so dragging OUT to Finder
would deposit something useful. That capability, added for one direction,
silently changed the meaning of the other: a destination asking "can this load a
URL?" started answering *yes* for internal moves and re-importing them.

#4401 fixed that — in one of the places it happens.

---

## The table

| # | Path | Source payload | Destination | Accepts | Internal doc drag | Finder drag | Status |
|---|---|---|---|---|---|---|---|
| 1 | Sidebar row (folder / leaf / disclosure) | `SidebarDragID` | `handleRowDrop` → shared classifier | `.utf8PlainText, .item, .fileURL, .data` | **move** | import | fixed #4401 |
| 2 | Sidebar row insertion (between rows) | `SidebarDragID` | `.dropDestination(for: SidebarDragID.self)` | typed | **move** (⌥ copy, ⌘⌥ alias) | n/a — never offered | OK |
| 3 | Sidebar unified-rows root insertion | `SidebarDragID` | `.dropDestination(for: SidebarDragID.self)` | typed | **move** (⌥ copy, ⌘⌥ alias) | n/a | OK |
| 4 | **Library section header** ("move to root") | `SidebarDragID` | was `.onDrop([.fileURL])` **＋** `.dropDestination` | both | **was: hollow COPY** | import | **fixed here** |
| 5 | **Content pane** | external only | was `ContentDropTargetView` (AppKit) | `.item`, but unreachable | n/a | **received nothing** | **fixed here** |
| 6 | Library folder cell (list / icons / columns / table) | `LibraryItemDrag` | `.dropDestination(for: LibraryItemDrag.self)` | typed | **move**, always | n/a | OK, see gap B |
| 7 | **Library pane → sidebar folder** | `LibraryItemDrag` | `handleRowDrop` → shared classifier | `.item` matches | **was: refused** | n/a | **fixed here** |
| 8 | Chat / Chat inspector | any | `.onDrop([.text, .plainText])` | text | attaches transcript | n/a | OK — see constraint |

---

## What was actually wrong

### 4 — the library header re-imported internal drags

Two drop modifiers on one view:

```swift
.onDrop(of: [UTType.fileURL]) { ...importFiles... }        // matched, because
.dropDestination(for: SidebarDragID.self) { ...move... }   // #4123 vends a file
```

An internal document drag satisfies the import handler's
`canLoadObject(ofClass: URL.self)` filter. Which of two drop modifiers on the
same view wins is **not answerable from source**, and it decided whether a move
became a copy.

**The confirmation, and the reason I am confident this is the same mechanism as
#4401 rather than a new one: folders moved correctly all along.** `SidebarDragID`
only populates `documentId` for non-folders, so a folder row exports no file and
never matched the import handler. Any explanation that does not account for
"folders were fine" is the wrong one.

Fixed by merging into one handler that calls the *actual shared*
`classifySidebarDropPayload` — not a copy of its logic. Plus `onDropError`,
because the header accepts the drop synchronously and a refusal it cannot report
is an item that appears to vanish.

### 5 — the content-pane bridge could never have received a drop

`ContentDropTargetView` (#4458) was merged with a full green test file. Two
defects, **both provable from the API contract**, neither needing the live drag
its author said was required:

1. `readObjects(forClasses: [NSItemProvider.self])` — `readObjects` requires
   every class to conform to `NSPasteboardReading`. `NSItemProvider` does not
   (it is `NSSecureCoding`/`NSCopying`). The conforming set is `NSString`,
   `NSAttributedString`, `NSURL`, `NSColor`, `NSImage`, `NSSound`,
   `NSPasteboardItem`, `NSFilePromiseReceiver`. It always returned empty.
2. `hitTest(_:) -> nil` was the *safety* argument. It is also how AppKit's
   **drag-destination** search fails to find a view — that search walks the same
   `hitTest`. The file's own doc comment predicted this branch.

**What its tests pinned:** one asserted `hitTest` is nil at five points, actually
instantiating the view; the other asserted the *source order* of a `guard` above
a callback. Both passed, over a path that delivered nothing. This is the
guardrail-against-an-empty-tree shape in a new costume — the test could not
distinguish "delivers drops" from "delivers nothing".

Deleted (−85 lines), replaced with `.onDrop(of: [.item])` at the **same**
`detailColumn` scope. Scope was the *only* reason #4184's original `.onDrop` was
reverted — it had been applied to the whole `NavigationSplitView`, where its
effect on nested sidebar rows could not be ruled out. On `detailColumn` the
sidebar is not inside the modified view at all.

`.item` rather than `.fileURL` is #4184's actual finding: Mail, Safari and
in-progress downloads advertise a content UTI and no file promise, and a
`.fileURL`-only destination discarded them silently.

### 7 — two drag types for one concept

Found while completing the review; not in any issue.

- Sidebar rows vend `SidebarDragID`, id = `doc:<uuid>`.
- Library rows, tiles, columns and table cells vend `LibraryItemDrag`, id = the
  **bare** document id, first string representation = JSON.

So dragging a document **out of the library pane onto a sidebar folder** — from
the pane where the documents actually are, which is the ordinary way to file
something — produced no `doc:` id. The #4401 classifier then did exactly the
right thing for the wrong input: it refused to re-import something that started
inside the app, and said *"Couldn't read what was dragged."*

Correct refusal, no data loss, feature entirely unusable.

**Fixed on the RECEIVING side only, deliberately.** Teaching `LibraryItemDrag` to
vend a `doc:`-prefixed string first would fix this and break path 8: `ChatView`
and `ChatInspector` accept `.text`/`.plainText` and read the *first* string,
which is how a dragged document attaches its transcript. Changing a drag source
to satisfy one destination is precisely how #4123 caused #4401. Not doing it
again.

---

## Gaps found and NOT fixed — for the fabel review to decide

**A. Sidebar row → library folder cell does nothing.** Path 6 accepts only
`LibraryItemDrag`; the sidebar vends `SidebarDragID`. No match, no feedback, no
error. The mirror image of gap 7, and the same root cause: two payload types for
one concept. The symmetric receiver-side fix would be teaching path 6 to
recognise a `doc:`-prefixed string. I did not do it because path 6 is typed
(`.dropDestination(for: LibraryItemDrag.self)`) and widening it means switching
it to the untyped provider API — a larger change than this brief warranted, and
one worth deciding rather than assuming.

**B. Two modifier grammars for the same gesture.** The sidebar implements
Finder's grammar (plain = move, ⌥ = copy, ⌘⌥ = alias). The library folder cell
(`moveDraggedItems`) **always moves** — ⌥ does nothing. Same gesture, same
conceptual objects, two rules. Not a data-loss bug; is an inconsistency a user
will hit.

**C. `sidebarDropOperation`'s modifiers are sampled at different moments.**
`handleDropIntoFolder` samples once at the drop; the insertion paths call
`.current()` inside the handler. Both look correct today. Worth one deliberate
rule rather than two places that happen to agree.

**D. The whole family has no test that a drop DELIVERS anything.** Every test
here, including mine, is either a pure-classifier test or a source assertion.
That is honest about what a worker can verify without a GUI — but it is exactly
the gap that let #4458 ship green. If XCUITest can drive a real drag, that is
worth more than any of these.

---

## Tuesday's click-list

Nothing below is verified. Not claiming otherwise — that is what went wrong the
last two times these were closed.

**Sidebar move (#4401)**
1. Drag a **transcribed** document from inside a folder onto the **library name
   row**. Expect: moves to root. Fail: a second hollow copy.
2. Same with a **folder**. Expect: moves. Regression check — this worked before.
3. Drag a PDF **from Finder** onto the library name row. Expect: imports.
4. Drag a document **row onto another folder row**. Regression check for the
   shared classifier.
5. **New:** drag a document from the **library pane** (icons or list) onto a
   sidebar folder. Expect: moves. Before this commit: "Couldn't read what was
   dragged."

**Content pane (#4184 / #4458)**
6. Drag a PDF from **Finder** onto the content pane. Expect: imports.
7. Drag a PDF attachment from **Mail**. This is #4184's real case and has never
   worked.
8. Drag a link or image from **Safari**.
9. Click a library row, then a folder cell, immediately after. Regression check
   for the hit-testing worry that caused the revert.
10. Drag onto a **folder cell** specifically — its own `.dropDestination` must
    still win over the pane-level one.

If 1 still copies, the next suspect is path 3
(`SidebarView+UnifiedRows`). I have read it and believe it is safe because it is
typed on `SidebarDragID` and never sees a file — but that belief is the same kind
of source-only reasoning that produced the last closure, so treat it as
unverified.
