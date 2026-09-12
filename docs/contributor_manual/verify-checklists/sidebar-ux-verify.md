# Sidebar/UX verify-and-close checklist

Seven issues whose fixes are already in the build (base `c3da13c81`). Run top to
bottom — the sections follow one pass through the UI: sidebar → library view →
workflow runs. Each check: what to click, what you should SEE, and what the old
broken behaviour looked like. If a check fails, the issue stays open — note what
you saw.

## A. Sidebar

### 1. #4520 — drag a folder or image onto the sidebar

- Drag `~/Documents/Fichero Demo Files/Demo/EAP1740/items/EAP1740_NP_T19_1700_002`
  onto Inbox, then a bare image onto a folder row.
- **Fixed:** the drop imports — spinner, activity updates, files appear.
- **Broken was:** drop accepted, then popped back; nothing imported; console
  logged `Reentrant message: kDragIPCCompleted`.

### 2. #4522 — importing one file updates one row

- With a large folder expanded and the sidebar scrolled mid-way, import a single
  file via the import menu.
- **Fixed:** one new row appears in place; disclosure state, selection, and
  scroll position all survive; no visible flash of the whole tree (and not twice).
- **Broken was:** whole sidebar redrew twice — rows flickered, selection jumped,
  scroll reset.

### 3. #4186 — workflow presets live under the locked container, once

- Fresh app launch (the heal runs at startup). Look at the workflow area of the
  tree.
- **Fixed:** Books/Catalogue/Clean Up/Convert/… sit INSIDE the locked Default
  Workflows container; nothing duplicated; clicking a preset folder behaves like
  a folder, not the custom-workflow editor.
- **Broken was:** those ten folders sat at tree ROOT beside the container,
  unlocked, and clicking one opened the custom workflow library view; workflows
  also rendered twice (virtual-hierarchy duplicate).

### 4. #4516 — workflow nodes carry an icon (sidebar half)

- Find any workflow node in the sidebar.
- **Fixed:** it has a distinct SF Symbol glyph — clearly not a document, not a
  folder.
- **Broken was:** no icon at all; the row read as malformed.

## B. Library view

### 5. #4516 — same glyph in the library (library half)

- Open the parent of that workflow node in the library view (list and grid).
- **Fixed:** the workflow node shows the SAME glyph as the sidebar.
- **Broken was:** empty thumbnail well / no icon; sidebar and library disagreed.

### 6. #4514 — default workflow folders are visually protected everywhere

- View the Default Workflows folders in the library view.
- **Fixed:** purple with a lock icon (matching the sidebar); rename/edit
  affordances absent; dragging anything onto one is refused up front, not
  accepted-then-failed.
- **Broken was:** they rendered as ordinary folders in library views and
  accepted drops.

## C. Workflow runs

### 7. #4523 (dup of #4552) — a run touches exactly the selection

- Select ONE PDF in a folder that contains several files. Right-click → Run
  Workflow → any cheap/deterministic preset. Watch the activity list.
- **Fixed:** exactly one item is processed — the clicked PDF, nothing else.
- **Broken was:** the run fanned out to every file in the folder (#4523) or
  every item in the sidebar (#4552) while the toolbar claimed "Running 1
  workflow…".
- If this holds, close BOTH #4523 and #4552's remaining doubt in one go.

### 8. #4503 — a preset's cost is known before it runs (partial)

- Open a preset that contains an LLM/vision node but pins no provider. Check its
  cost/provider preview (app surface, or `fichero workflow preview-cost`).
- **In scope for this check:** the preview names the REAL provider/model it
  would call (resolved from app-DB defaults), and a providerless or delegating
  preset is NOT reported as free.
- **Broken was:** providerless nodes silently fell back to app-DB defaults
  (OpenRouter) and the safeguard reported them free — two unauthorised paid runs.
- **Knowingly still open:** presets still do not pin providers, and the
  `(Untested)` labels on the ~25 LLM presets are #4501's separate
  validation pass. Do not fail this check for either.

---

Out of scope here: #4525 (pane stability) is knowingly PARTIAL — the
PaneContentPlan matrix landed, but the per-node-type audit and the unreachable
workflow node editor remain open; it is not part of this verify pass.
