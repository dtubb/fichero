# Tuesday click-list — build `2026.08.02`

Sit in front of the app and work down. Grouped by **surface**, not by issue.

Every item is something changed on 2026-08-02 that **no human has clicked**. The tests pass; that is not the same thing. Where a step fails, the "if it fails" line tells you what to reopen so a red step is never just a dead end.

Budget: **A and B are the regression checks — do them first.** If either fails, stop and report; everything below is built on the same shared code.

---

## A. Regressions first — the shared code that everything else sits on

Today changed `Document`'s fields, the library sort path, the claim write path, and the build-tier resolver. Any of those could break something unrelated to the feature it was for.

| # | Do this | Expect | If it fails |
|---|---|---|---|
| A1 | Open an existing library | Opens normally, documents listed | `Document` gained `child_count` as a **transient** field (`db/__init__.py`, `transient_field_names`). If the library will not open or rows are empty, that is the DB layer writing a column that does not exist — reopen #3355 |
| A2 | Look at a folder that has children, **before** clicking it | Disclosure triangle already showing | #3355. No triangle = `child_count` is not arriving |
| A3 | Click a folder's triangle, expand it | Children appear | as above |
| A4 | Drag a document into a folder **in the sidebar** | It **moves** — one copy, in the new place | The whole #4401 class. A duplicate appearing = a copy; see §C |
| A5 | Click a row, then shift-click another | Selection extends normally | Selection/sort share `filteredDocuments`. Broken order or selection = the #3322 grouping changed the array under the selection code — reopen #3322 |
| A6 | Sort by **Name**, then by **Type** | Instant, no visible reload | Those are client sorts and must **not** round-trip. A spinner here means the refetch policy is firing for every sort — reopen #3322, decision (a) |

---

## B. First run — this should now be *absent*

| # | Do this | Expect | If it fails |
|---|---|---|---|
| B1 | Launch with your normal library | **No "which library?" prompt.** It opens straight into the library | #4017 |
| B2 | Launch again | Same — no prompt | #4017 |
| B3 | *(optional, only if you have one)* Launch pointing at a genuinely empty library | The first-run prompt **does** appear | #4017b. The prompt is gated on a **verified-empty** library, not on "we have not loaded yet" — if it appears over a full library, that gate is reading an unloaded state as empty |

---

## C. Drag and drop — the ten paths

Full reasoning in `2026-08-02-drop-path-table.md`. Three payload types are in play, and **which one is implicated tells you where to look**: `SidebarDragID` (sidebar-internal), `LibraryItemDrag` (library pane), plain file URLs (Finder).

| # | Drag this | To here | Expect | If it fails |
|---|---|---|---|---|
| C1 | A document in the sidebar | Onto a sidebar **folder row** | Moves | `SidebarDragID` · #4401 |
| C2 | A document in the sidebar | **Between** two rows | Moves, lands at that position | `SidebarDragID` |
| C3 | Same, holding **⌥** | Copies | `SidebarDragID` |
| C4 | Same, holding **⌘⌥** | Makes an alias | `SidebarDragID` |
| C5 | A document | Onto the **library section header** ("move to root") | Moves to root — **not** a copy, and no re-import | The one fixed here: the header had **two** drop modifiers and a document drag satisfied the *import* one. A duplicate = the old behaviour |
| C6 | A **PDF from Finder** | Onto the **content pane** (the big middle area) | Imports | The content pane accepted nothing at all before — it had an AppKit bridge that was unreachable. Nothing happening = that path is dead again |
| C7 | A document **in the library pane** | Onto a **sidebar folder** | Moves | `LibraryItemDrag` — this was *refused* before. If nothing happens, the sidebar is not recognising the library pane's payload |
| C8 | A document in the library pane | Onto a **folder cell** in the library pane | Moves | `LibraryItemDrag` |
| C9 | A **PDF from Finder** | Onto a sidebar folder | Imports into that folder | file URL path |
| C10 | A document | Onto the **chat** pane | Attaches to the transcript | text path |

**The general failure signature:** an internal move that produces a *second copy* means a destination matched the file-URL import handler instead of the typed move handler. That is the #4123 side effect and it is the same bug wherever it appears.

---

## D. Historical dates — end to end (#3322)

This is the paleography chain and the reason for the release. Do it in order.

| # | Do this | Expect | If it fails |
|---|---|---|---|
| D1 | Run date extraction on some documents (a workflow with the histdate tool) | Completes | #3322 core |
| D2 | Show the **Date** column (right-click a column header → Date) | Column appears beside Created | #3322 / #4482 — the column list was capped by a builder limit |
| D3 | Read the Date cells | Four different readings are possible and they must differ: an actual date; **"Undated in source"**; **"No date found"**; **"Date not examined"** | If everything undated reads the same, the four states have collapsed — that is the whole point of the feature. Reopen #3322 |
| D4 | Find a **year-precision** document | Reads **`1791`** — *not* `1 January 1791` | The client must never re-format; precision lives server-side. A day-precision rendering means someone added a second formatter |
| D5 | **Click the Date column header** | Sorts by document date. Brief load is expected here (it round-trips to the engine, by design) | #3322 step 5. A crash on click = the #4282 sort-descriptor bridge — that is the risk I flagged |
| D6 | Look at the bottom of the sorted list | Undated documents are **grouped at the end**, under a **"No date"** heading | #3322 step 6. Interleaved undated rows = the grouping is not applied |
| D7 | Check the dated rows above that heading | In date order — and a day-precision date sorts **before** the year that contains it | The engine's precision tie-break. Wrong order = the client re-sorted on top of the server's order, which is the trap this was built around |
| D8 | Click the Date header **again** (descending) | Reverses, still grouped | Another expected round-trip |
| D9 | Switch to **Name**, then back to **Date** | Both work; only the Date switches show a load | decision (a) |
| D10 | Switch to **List** view and **Table** view with Date sort active | The "No date" heading appears in both | It is one predicate feeding three renderers. Present in one and not the other = they have diverged |

> **Highest build risk in the release.** D5–D10 exercise `Section` inside the outline `Table`'s row builder next to `DisclosureTableRow`. It compiles; the runtime behaviour of that combination — selection and disclosure state across sections — is the thing I could not verify. If something is going to be wrong today, it is most likely here.

---

## E. Reader — hit targets (#4479)

| # | Do this | Expect | If it fails |
|---|---|---|---|
| E1 | Open a document in the Reader | Toolbar visible | — |
| E2 | Click the **edge** of a toolbar icon — deliberately a few points off the glyph, not its centre | It activates | Before today the clickable area was the glyph's drawn pixels, ~13pt against a 28pt policy. If you must hit the centre, the target is missing on that button — reopen #4479 with which button |
| E3 | Try several icons across the toolbar and the page controls | All the same | 24 buttons across 6 files were changed; a miss would be one file |

---

## F. VoiceOver (#4484)

| # | Do this | Expect | If it fails |
|---|---|---|---|
| F1 | Turn on VoiceOver (⌘F5) | — | — |
| F2 | Tab through the **library** toolbar and controls | Every control is **named**. Nothing says just "button" | 17 labels added here |
| F3 | Tab through **Settings** → AI Providers and MCP | Named. Per-row remove buttons say **which item** ("Remove extension .pdf", not a bare "Remove") | — |
| F4 | Tab through a **workflow** and the **chat** input | Named | — |
| F5 | In the research task list, focus a **task status** button | Announces the current status *and* what activating it will do | It is a state-carrying control; a fixed label would hide the point |
| F6 | With Date sort on, navigate to the **"No date"** heading | Reachable as a heading | It carries `.isHeader` so you do not have to arrow through every dated row |
| F7 | In Settings → AI Providers → Add Provider | There is **no "?" help button** | It was deleted, not labelled — it did nothing when clicked. If a "?" is there and does nothing, the deletion did not land |

---

## G. Sidebar (#4097, #4095, #4371, #4099)

| # | Do this | Expect | If it fails |
|---|---|---|---|
| G1 | Move the pointer over sidebar rows **without clicking** | A soft wash follows the pointer | #4097 |
| G2 | Watch the row text while hovering | **Nothing moves or re-truncates** — the wash is a fill only | Every Frame Perfect. Any shift = hover is changing metrics |
| G3 | Select a row | Subtle system fill, **normal black text**, icon keeps its colour — no white-on-accent | #4371 |
| G4 | Hover a **selected** row | Wash does **not** stack on the selection | #4097 |
| G5 | Look at a library header's item count | A system badge, right-aligned | #4095 |
| G6 | Type in the sidebar filter until the selected row would be excluded | The selected row stays visible | #4099 |
| G7 | Compare a library row's height to its item rows | Item rows are ~2pt shorter | **Known and undecided** — see `2026-08-02-sidebar-row-height-decision.md`, which needs your answer, not a bug report |

---

## H. Inspector — Related list (#4483)

| # | Do this | Expect | If it fails |
|---|---|---|---|
| H1 | Open the inspector's **Related** tab | Rows listed | #4483 |
| H2 | **Click a row first**, then press ↓ / ↑ | Selection moves. *The list needs a click before the keys reach it* | #4483 |
| H3 | Look for the focus ring | Present when focused | #4483 |
| H4 | Right-click a row | Context menu | #4483 |

---

## I. Claims — routing (#1848)

Only worth doing if you use these surfaces; everything here is refresh behaviour.

| # | Do this | Expect | If it fails |
|---|---|---|---|
| I1 | Change a claim's curation state in the **review queue** sheet | The list behind it reflects it | Was a direct service call that refreshed nothing |
| I2 | **Detached window on a second library** → change a curation state | It applies to **that** library | **The most serious bug fixed today.** It previously wrote to the *global* library regardless of window — evidence filed in the wrong archive, silently. If this misbehaves, stop and report it |
| I3 | Bulk-curate or merge claims in the inspector | Other claim surfaces update | store routing |

---

## What I could not verify

Blunt list. Everything here needed a GUI, a keypress, a real drag, or eyes — none of which I have.

1. **Nothing in this document has been clicked.** I never ran the app. Tests pass and lint is clean; that is all.
2. **`Section` inside the outline `Table`** (D5–D10) is the single construct I am least sure of. It compiles. Selection and disclosure behaviour across sections is unverified — this is the one I would test first after A and B.
3. **Every drag in §C.** Which of two drop modifiers on one view wins is not answerable from source — that ambiguity *was* the bug in C5, and I fixed it by removing the ambiguity, not by observing the outcome.
4. **Hover, selection weight, badge, row heights** (§G) — all pixels. The row-height *difference* is arithmetic from the code, not a screenshot.
5. **Hit targets** (§E) — the frame is applied; whether it feels right is yours.
6. **VoiceOver** (§F) — I verified every control *has* a label and that the scanner examined 1185 buttons. I have never heard one spoken.
7. **The four date states** (D3) — unit-tested as distinct values. Whether the wording reads correctly to a historian is your call, especially "Undated in source" versus "Date not examined".
8. **First run** (§B) — the launch logic is deterministic and tested, but launch is exactly where a race that unit tests cannot see would live.
9. **The build tier** now fails closed to `.release` if unresolvable. Every configuration defines it, so this should be invisible — but if features are mysteriously *missing*, check Console for `FeatureTier` and the message about an unresolvable tier.
