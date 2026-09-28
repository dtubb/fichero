# Build notes: UX wiring -- where the app reaches what the engine does (audit, 2026-09-27)

## What to test in the morning (2026-09-28)

Built overnight on `spec/page-model`; the lead merges, syncs the contract and builds. Use the
acceptance library's imported Syriac page, or any page imported from PAGE / ALTO with File ▸ Import
Page From…. Every edit below should undo with ⌘Z and redo with ⇧⌘Z.

1. **Imported boxes show** (#5146). Open an imported page: the Source view draws its regions and
   lines. *Should:* boxes on the image, not only text.
2. **Select a box on an imported page** (#5152). Click a line. *Should:* it highlights; the Inspector's
   Source section shows the path **Page › Region › Line**, then **Text**, **Language & Script**,
   **Hands**, **Certainty and Damage**, and **Order**. Click a crumb to inspect that level.
3. **Edit an imported page** (#5152). Turn on Edit Segments (head, beside the pencil). Drag a line's
   box; select two lines and right-click ▸ **Join 2 Regions**; select one and press Delete. *Should:*
   each happens, and ⌘Z puts it back.
4. **How the page was made** (#5149). Inspector ▸ Source ▸ **Info**, or click **Page** in the path.
   *Should:* "Imported from ‹file› · PAGE XML · 12 lines, 4 regions" and **Show Original**, which opens
   the file read-only, exactly as imported.
5. **The working pass** (#5156). On a page with two passes, the Making section says which is
   "Working" and why; the other offers **Make Working**. *Should:* the Source view redraws from the
   chosen pass; ⌘Z goes back (a first choice goes back to the rule).
6. **Which reading counts** (#5153, #5175). Select a line and type a correction of it. *Should:* Text
   lists both; the correction counts, marked "A person's correction, over the reading it corrects";
   the file's reading offers **Make This Count**, and choosing it marks it "Chosen by a person"; ⌘Z.
7. **Language & script** (#5158, #5176). Select a line. *Should:* language, script, direction, encoding,
   each saying where it came from. On the Syriac page: script **Syrc · detected**, direction **Right
   to Left · from the script**, language **Not determined** (nothing states it; never an English
   fallback).
8. **The Segment menu** (#5157). With lines selected: Inspector path head ▸ **Segment** ▸ Direction ▸
   Right to Left, or Language… (type `syc`); also right-click in Edit Segments. *Should:* all the
   selected lines change in one step; one ⌘Z undoes it.
9. **Hands** (#5161). Select a line ▸ Hands ▸ **Attribute** ▸ New Hand… ("hand B"). *Should:* "hand B"
   on one line, "judged by ‹you›" on the next; **Withdraw** removes it from view (kept in the record);
   ⌘Z.
10. **Marks on a selection** (Q6). Select two lines and press Highlight. *Should:* one highlight per
    line, each attached to its own line (so moving a line takes its highlight).
11. **Reading order** (Q5, 3c). Inspector ▸ Source ▸ **Order**: drag a region, or click the list and
    press ⌥⌘↑ / ⌥⌘↓ / ⌥⌘⇞ / ⌥⌘⇟. Click a line crumb: Order lists its **words**, which move the same way.
    *Should:* the Reader's text follows the new order; ⌘Z restores it byte for byte. In the Reader,
    put the caret in a line and press ⌥⌘↑ (with the Order list NOT focused): the line moves.
12. **One selection** (#5155). Pick a row in the Order list. *Should:* that segment lights on the
    image and the Inspector follows it. In the Reader, put the caret on a line: that line lights on
    the image; select boxes: their lines are tinted in the Reader.
13. **Certainty and damage** (5.5). Select a line ▸ Certainty and Damage ▸ **Mark** ▸ Unclear.
    *Should:* the section shows the line with an under-dot on every letter (drawn, not typed: Text
    still shows the plain reading) and "Unclear · letters 1–N · by ‹you›"; **Withdraw** takes it out
    of view; ⌘Z. Once #5179 lands, the Syriac page's own file marks six lines unclear on import.
14. **Typing in the Reader** (#5154, both halves). Put the caret in a derived page's line and type,
    then move off the line. *Should:* a new reading, correcting the old (see 6); Return mid-line splits
    the line and its box (the engine records the box cut as an estimate); Backspace at a line's start joins it
    to the line before; each one ⌘Z.
16. **Signs** (5.6). On the MUFI page (Clm 13027), declare U+F1AC as a sign (command line or MCP:
    `sign.declare`), then select a line that uses it. *Should:* Signs names the sign, "U+F1AC · MUFI
    F1AC · 1 here · 50 in the project". A character segment with a described letterform shows
    "ܐ › Estrangela alaph › hand B" and its features.
17. **Links** (5.7, #5164). Select two lines (first, then second) ▸ Links ▸ **Link** ▸ Continues.
    Then inspect the first line. *Should:* "Is continued by Line · ‹the second line's words›"; the
    second line reads "Continues Line · ‹the first›". **Withdraw**; ⌘Z. **Copy Reference** puts
    `fichero:segment/…` on the clipboard. Paste that link into Safari's address bar (or `open
    'fichero:segment/…'` in Terminal): *Should:* Fichero opens the page with that line selected; a line
    since joined into another opens the one that absorbed it (#5164, macOS only).
18. **Rights** (5.8). Select a line ▸ Rights ▸ **Set** ▸ Local Models Only; then Add Label…
    ("TK Attribution"). *Should:* "Models: Local models only", "Labels: TK Attribution", and a record
    "On this segment"; at Page level the page's own records; **Withdraw**; ⌘Z. Records only tighten: a
    page rule of "No Models" wins over a line's "Local or Cloud". **Not built:** restricting to named
    readers from the app (it cannot list accounts yet). **Enforced (4f2ad2ec9):** in a multi-user
    library, a restriction naming only other accounts hides the line from you (owner included), and
    setting one that does not name you is refused with a sentence saying why.
19. **Said about this** (5.7). On a page with claims, anchor one to a line (`claim.patch` with a
    `source_anchor` naming the line's `segment_id`, from MCP or the command line), then select that line. *Should:* "Said About This" lists the
    claim ("anchored here", its excerpt) and the entities mentioned on the line; clicking one opens it
    in the knowledge views. Hidden on a line nothing is said about.
20. **The Segments pane** (#4942). Click any pane's kind icon ▸ **Segments**, beside a Preview, with
    an imported page selected. *Should:* the page's regions, in its order, each "Region · ‹words›";
    the chevron opens a region to its lines, and the path at the top goes back up. Pick a row: its box
    lights in the Preview and the Inspector follows. Drag a row, or ⌥⌘↑ / ⌥⌘↓ with the list focused:
    the order changes; ⌘Z. **Gathered sets:** in the Inspector, Hands ▸ **Everything in This Hand**, or
    Signs ▸ **Every Instance**. *Should:* the pane lists them across pages (the crumb "Page" goes
    back); a row opens its page with that segment selected; pages you may not read are counted
    beneath ("2 more on pages you may not read"), never silently missing. **Strip and Grid:** the head's view menu ▸ Strip / Grid. *Should:* each
    segment's picture cut from the page, its words beneath, in the page's order; a click selects, a
    double click opens a region. A click in the pane focuses it: ⊞ Split splits the Segments pane.
15. **A georeference beside a transcription** (#5122). On a page with an imported transcription AND an
    imported IIIF georeference: *Should:* the Source view draws the transcription's lines, never the
    control points; Making lists the georeference under **Georeferencing**.

21. **A segment's history, picture and baseline** (#5163). Select a line, move its box, set its language,
    then look at Inspector ▸ **Making**. *Should:* the line's picture; "Curved baseline, N points" (or
    Straight); "Version 3, now", then Version 2 "then language unset → syc" and Version 1 "then moved or
    reshaped". **Restore** on Version 1 puts it back; ⌘Z, and ⌘Z again after two edits (both undo now).
22. **Shapes drawn as themselves** (#5163 residue). Open the Syriac page. *Should:* each line is drawn as
    its outline (not a rectangle) with its baseline as a heavier line under the ink; a selected line is
    outlined in the accent colour, Finder-style dim when the window is not in front.
23. **Reshape** (Edit Segments on, ONE line selected). *Should:* a square handle on every point of the
    outline and the baseline, a small round one on each side. Drag a square: the point moves. Press a
    round one and drag: a point is added there. ⌥-click a square: the point is removed (never below 3
    for an outline, 2 for a baseline). Click a square without dragging, then the arrow keys: the point
    moves one pixel, ten with ⇧ (without a selected point the arrows page as before). Each is one ⌘Z.
24. **Draw a polygon or a baseline** (Edit Segments on). The chevron beside **Shape** ▸ Polygon: click
    points, then click the first one (or double-click) to close. ▸ Baseline: click points, double-click to
    finish. **Escape** while drawing abandons just the drawing. *Should:* a new region (polygon) or line
    (baseline) on the page, drawn as itself; ⌘Z removes it. ▸ Box drags a box as before.
25. **Table cells** (#5168). Import a Transkribus table page (`transkribus_abp_table_0019.page.xml`) and
    select a cell. *Should:* the path reads **Page › Table › Cell, Rows 3–4, Column 1** (counted from 1);
    the Segments pane's rows name cells the same way.
26. **Proposed matches** (#5165). With matches proposed on a page (`segment.match_propose` from MCP or the
    command line), the Segments pane head shows **N Proposed Matches**. *Should:* each row the newer
    line, "was ‹the older› · proposed by ‹who› · sure N%"; **Accept** / **Reject**; ⌘Z.
27. **Reading orders and flows** (#5160). Inspector ▸ Order (or the Segments pane) head: the order
    picker. **New Order…** makes a copy to rearrange; **New Flow…** a flow. Select a line and use
    ▲ ▼ (Previous / Next in Order). On the NEXT page of the same source: picker ▸ **Continue a Flow Here**
    ▸ the flow. *Should:* this page's lines join the flow's end, in the page's order (one ⌘Z); from the
    first page, Next off its last line opens this page with its first line selected.
28. **Export choices** (#5162). Page level ▸ Making ▸ a pass's **Export** menu. *Should:* As Edited ▸ PAGE
    XML, ALTO, TEI, hOCR, YOLO for a text pass (IIIF Georeference and QGIS Points for a georeferencing
    pass), saved as `‹page›.page.hocr` etc. with the report; **As Imported…** saves the original file byte
    for byte.
29. **Typing in the Reader, continued** (13b). Type a run of words and pause two seconds: one reading,
    one ⌘Z. Have someone (or MCP) correct the same line while you type, then move off it. *Should:* your
    words stay on the line, marked, with **Keep Mine / Take Theirs / Compare**; Keep Mine lands.
30. **Out of reach** (13b). Type in the Reader, then stop the engine (quit a Dev Local engine, or turn off
    the network to a remote one) and keep typing. *Should:* one line at the top says the engine is out of
    reach, the text goes read-only, and nothing typed is lost. Start the engine again: within a few
    seconds editing comes back and the held words are saved (a line someone changed meanwhile comes back
    with Keep Mine / Take Theirs / Compare).
31. **No reading** (13b). Edit Segments ▸ Shape ▸ Baseline: draw a line. *Should:* it is drawn hollow and
    dashed, a click picks it, the Segments pane lists it "Line N · No reading", and the Inspector's Text
    says "No reading" with **Type a Reading…**; type one and the mark goes (⌘Z brings it back). A line
    you emptied in the Reader is NOT marked: it has an empty reading.
32. **Shapes on a PDF page.** Import a PAGE or ALTO file onto a PDF page (File ▸ Import Page From…).
    *Should:* each line is drawn as its outline with its baseline under the ink, as on an image page, at
    any zoom; a line with no reading is dashed.
33. **A drawn line lands in its region.** Edit Segments ▸ Shape ▸ Baseline: draw a line inside a region,
    just under its last line. *Should:* the Inspector's path reads **Page › Region › Line**, and the Order
    list shows it as that region's last line (one drawn between two lines goes between them); ONE ⌘Z
    removes it from both, and ⇧⌘Z puts it back in the same place. Draw one on blank margin
    outside every region: the path reads **Page › Line**, and it is not put in any region.
34. **A direction reaches the Reader at once** (#5171). With the Reader open beside the Source view,
    select a line and use the Segment menu (or the Inspector) to set **Right to Left**. *Should:* the
    Reader's page lays that line out right to left straight away; ⌘Z puts it back, ⇧⌘Z sets it again,
    each showing at once, with the scroll and caret kept.
35. **Direction on a whole source** (#5171). In the Library, right-click a document or folder ▸
    **Direction ▸ Top to Bottom** (or Right to Left). *Should:* its pages in the Reader lay out that way
    at once; the Inspector's Language section's **Direction** row shows Top to Bottom and
    where it came from; ⌘Z puts it back, ⇧⌘Z again. **Not Stated** clears it, and the script's own
    direction answers again.
36. **Reshape on a PDF page.** On that PDF page, turn on Edit Segments (head) and click a line. *Should:*
    its points show square handles and its sides round ones; drag a baseline point and the line follows
    (dashed while dragging), then lands; ⌥-click an outline point removes it; ⌘Z puts each back. The
    Inspector shows the line picked; put the Reader's caret on another line and the PDF page outlines
    that one. While editing, the head shows no Polygon/Baseline menu, Delete or Join on a PDF page.

**Not built:** the menu-bar Segment menu, comparing two passes side by side, attribute edits
on a page still read from an artifact (it is converted on first edit, #4924).

Asked for by the maintainer after his try-out of 2026-09-27: everything built must be hooked into the
UX, systematically. `SegmentDisplay` was the pattern that prompted it -- a seam tested twenty ways that
seemed never to reach the screen (#5146; it did reach the screen, and the defect was the ranking
inside it). This file records, for EVERY `source.*` behaviour a spec tags **[OK]** or **[PARTIAL]**,
where the app reaches it, whether it is on screen, and its end-to-end test. Read on disk on
`spec/page-model` at `6dc912235`, from code; nothing was built or run. A behaviour's spec tag is
about the ENGINE; this file is about the person.

**The rule from now on** (2026-09-27): a slice is not done until one end-to-end test goes through the
exact call the screen makes, on a real imported file.

## Wired overnight (2026-09-27/28) -- pending the lead's build and test run

None of this is tagged [OK] in a spec: the Swift is typechecked, not compiled into the app, and its
end-to-end tests have not run. Each row names the end-to-end test through the screen's own call on a
real imported file (the recorded Syriac PAGE import, `fichero/Tests/Fixtures/segments/`, re-checked
against the engine on every Python run). When the lead's run is green, the rows' behaviours move.

| Gap issue | Behaviours | Commit(s) | End-to-end test (`ImportedPageDrawsItsBoxesTests`) |
|---|---|---|---|
| #5146 | `source.app.overlays-draw-from-the-seam` (imported pages) | 6dc912235 | `…DrawsTheFilesRegionsAndLines` |
| #5152 | `source.editor.shapes-in-source-view`, `selection-shared` (imported) | ba9557474, 0e149018f, 431248e41 | `…ALineClicked…`, `…JoiningTwoImportedLines…` |
| #5149 | `source.making.in-inspector` (page level, imported file) | c254941e6, c59ef6007, e91a3c4eb | `…SaysHowItWasMadeAndShowsItsOriginal` |
| #5153 | `source.reading.chosen-is-worked-out`, `corrections-are-new` (seen) | 61ba0e9e4, fd9793f60 | `…ChoosingTheFilesReadingOverACorrection…` |
| #5155 | `source.editor.selection-shared` (Order list, Reader app half) | f5f580761 | `…ALineNamedByTheReader…` |
| #5156 | `source.pass.working`, `named-authored` (shown, chosen) | a1d41dcdb, 2196a3ec2 | `…MakeWorkingSendsPassChooseWorking…` |
| #5157 | `source.editor.set-kind`, `set-direction`, `set-language-script` | 71a3fbac1 | `…SegmentMenuSetsDirection…` |
| #5158 | `source.lang.three-facts`, `says-where-from`, `unknown-is-not-unexamined` | afad2c57e | `…LanguageSectionShows…` |
| #5161 | `source.hand.attributed`, `not-provenance`, `record` | a98f4db80 | `…HandsSectionShows…` |
| Q6 | `source.editor.marks` (on the selection) | 81ba748a1 | `…AHighlightOnTwoSelectedLines…` |
| #5154 | `source.textedit.typing-is-a-new-reading`, `return-splits-the-line`, `backspace-joins-in-reading-order` (app half; page half bugs2 6857c8ae6, ba90038e6) | 02cd36aa2, fd9793f60 | `…ReadersEditSplitAndJoinMessagesBecomeTheirActions` |
| #5001 | slice 13b: `source.textedit.a-run-of-keys-is-one-action`, `deleting-words-keeps-ink` (app half, 52fa144b9), `stale-keeps-your-words` (engine 24c16562b: `expected_counting_id` → 409; app: token sent, 409 → `lineCommitted` stale with mine/theirs, no refresh). Token decided 2026-09-28 by the lead as a default; the maintainer may revisit. Page half (coalescing, `line-empty`, `line-stale` with Keep Mine / Take Theirs / Compare, `commitPending()`): bugs2. The app calls `commitPending()` before a page swap (`loadIfNeeded`) and when the pane goes (`dismantleNSView`, best effort). There is no File ▸ Save command, so the page's own ⌘S is the save key | 52fa144b9, 24c16562b, the stale app commit | `…ARunOfTypingIsOneReadingOneAuditOneUndo`, `…DeletingWordsIsANewReading…`, `…ATypedLineAgainstAReadingThatNoLongerCounts…`; `test_stale_keeps_your_words.py` |
| 5.5 | `source.sure.editorial-facts`, `brackets-are-drawn` (shown, marked, withdrawn) | b75cac9ef, abe343ae9, fd3e57f96 | `…CertaintyAndDamageSectionShowsTheFactsDrawn…` |
| 5.6 | `source.sign.declared`, `list-authority`, `gather-instances` (a count); `source.letterform.chain`, `features` (read-only, inside Signs) | 46cf7efa1 | `…SignsSectionNamesTheMUFISign…` (real MUFI page), `…SignsSectionReadsACharactersLetterform…` |
| #5164 | `source.link.typed`, `both-ways` (read from each end), `source.segment.citable` (Copy Reference) | 13494cbb7 | `…LinksSectionReadsALinkFromThisEnd…` |
| 5.8 | `source.rights.record`, `tighten-only` (shown in words, records placed), `who-acts` (the engine's refusal said) | b01d0cdf4 | `…RightsSectionSaysWhatApplies…` |
| 5.7 | `source.statement.on-segment`, `both-ways` (from the segment: claims and mentions whose anchor names it, each opening its claim or entity) | f95b6e43a, 0f0d01e37 | `…WhatIsSaidAboutALineListsItsClaimAndMention…` |
| #4942 | `source.segments-pane.exists`, `selection-shared`, `reorders` (first slice: the list) | 9b7e783fd (spec), e252d3967 | `…SegmentsPaneListsOpensReordersAndSelects…` |
| #4942 | `source.segments-pane.views` (list, strip, grid of the engine's segment pictures; one order store) | d1f312d68 | `…AStripCellsPictureIsTheEnginesCutOfTheLine` |
| #4942 | `source.segments-pane.gathers` (everything in a hand, every instance of a sign; what may not be read is counted and said, #5180) | 2036f6d2f, 73e31c287 (pane focus) | `…EverythingInHandBIsGathered…`, `…EveryInstanceOfTheMUFISignIsGathered` |
| #5122 | a georeferencing pass is never drawn as the page's boxes; Making lists it apart | 8b9e51c37 | unit only: `SegmentDisplayTests.aGeoreferenceIsNotDrawnAsThePagesBoxes` (no real georef+transcription page recorded yet) |

Engine defects found on the way, filed: #5176 (the Syriac page resolved to "English, left to right"
by fallback; fixed by bugs2, 844b6d3bc); #5179 (a file's own editorial marks are dropped on import).
Fixed in-lane: a page's first working-pass choice could not be undone (a1d41dcdb); a mid-line lost
stretch could not be placed (abe343ae9).

**Engine only, no screen yet:** campaigns (`source.campaign.*`, de90ff63f); their actions are reachable
from MCP and the command line. Letterforms are SHOWN, read-only, inside the Signs section (see the
table), and cannot yet be described from the app.

**Question for the maintainer:** letterforms: inside Signs, or their own section?

## The headline

Of **144** behaviours: **26** wired and visible, **18** reachable in part, **39** not reachable
(31 with no Swift caller at all), **60** engine-internal (no screen of their own), 1 unsure. Of the
source-model routes, **8** have an app caller. Two Swift types have no caller: `SegmentSelection`
(its `shared` instance is never written) and `SegmentEditCommand`.

The most urgent gap is not a spec row: **a box on an imported page draws but cannot be selected or
edited** (#5152) -- so on an imported page the Inspector's segment level, Edit Segments and undo are
unreachable. It comes first.

## The build order: one issue per gap, ranked by what the maintainer reaches for first

The 49 gaps below (section "GAPS") are grouped into 18 issues, one per SURFACE a person would reach
for, because a gap list split finer than the surface that closes it gets built piecemeal:

1. **#5152** a box on an imported page cannot be selected or edited -- source.editor.shapes-in-source-view, source.editor.selection-shared (imported pages)
2. **#5153** choose which reading counts, and see a reading's full record, in the Inspector's Text section -- source.reading.chosen-is-worked-out, source.reading.chosen-follows-project-rule, source.reading.written-read-pair, source.reading.corrections-are-new, source.reading.level-recorded, source.reading.read-from, source.reading.char-confidence-on-line
3. **#5154** type a correction in the Reader as a new reading; Return splits a line, Backspace joins -- source.reading.set, source.textedit.typing-is-a-new-reading, source.textedit.reader-shows-segments, source.textedit.return-splits-the-line, source.textedit.backspace-joins-in-reading-order
4. **#5155** one selection across the Source view, the Reader and the Inspector -- source.editor.selection-shared
5. **#5156** show, hide and compare a page's passes, and choose the working pass -- source.pass.named-authored, source.pass.working
6. **#5157** set kind, direction and language/script on the selection (the Segment menu) -- source.editor.set-kind, source.editor.set-direction, source.editor.set-language-script, source.lang.many-per-page, source.dir.per-segment
7. **#5158** the Inspector's Language & script section -- the three facts and where each came from -- source.lang.three-facts, source.lang.says-where-from, source.lang.reading-overrides, source.lang.cascade, source.lang.project-declared
8. **#5159** join selected segments by id; group lines into a region and ungroup -- source.editor.join-group
9. **#5160** pick, create and step through named reading orders and flows -- source.order.named-multiple, source.order.next-previous, source.segment.flow, source.editor.reorder
10. **#5161** hands in the Inspector -- browse and create hands, attribute a segment, ink vs record -- source.hand.record, source.hand.attributed, source.hand.not-provenance
11. **#5162** choose what to export, export hOCR and YOLO from the menu, and import/export a page on iOS -- source.format.export-choices, source.format.first-four, source.format.everywhere
12. **#5163** a segment's history, its picture and its baseline -- source.segment.versioned-alone, source.segment.picture-by-shape, source.segment.curved-baseline, source.segment.shape-kinds
13. **#5164** typed links between segments, a segment's links, copy its reference, open a fichero:segment link -- source.link.typed, source.link.both-ways, source.form.label-and-answer, source.segment.citable
14. **#5165** review proposed segment matches and carry readings/marks across -- source.segment.match-record, source.segment.carry-across-a-match
15. **#5166** signs -- declare a sign, look it up, the project list, variants, gather instances -- source.sign.declared, source.sign.list-authority, source.sign.project-list, source.sign.in-readings, source.sign.variants, source.sign.gather-instances
16. **#5167** attach a rights or consent record and see the effective rights -- source.rights.record
17. **#5168** tables -- a cell's row and column, draw a table or its cells -- source.segment.table-cells, source.table.is-a-segment
18. **#5169** georeferencing -- export a georeferencing pass, import one into the library, choose gazetteer candidates -- source.geo.iiif-georef-out, source.geo.iiif-georef-in, source.geo.gazetteer-candidates

## What is wired today

- Boxes over the image and the PDF page come from the segment seam (`OCRGeometryOverlay.loadOCRGeometry`,
  `PDFPageView+OCRBoxes`), imported pages included since #5146.
- Inspector › Source: with a box selected, the path head, the Text section (readings, maker, which
  counts and why, sic/corr pairs) and the Order section (children, drag and ⌥⌘ keys, ⌘Z).
- The Reader's ⌥⌘ keys move the caret's line in the order (`ReaderLineMove`).
- File › Export › Export Page As (PAGE XML, ALTO, TEI) and Import Page From…, macOS only.
- Edit Segments: move, delete, combine, with undo and redo, on artifact-backed pages.


Method: every generated operation (openapi.json operationId → camelCase Swift name) was grepped across `fichero/fichero/**/*.swift`. Of the source-model routes, **only 8 have an app caller**:
`listDocumentSegments…`, `getSegment…`, `listSegmentReadings…` (SegmentService); `listDocumentOrders…`, `listOrderEntries…`, `placeInReadingOrder…` (ReadingOrderService); `exportDocumentPage…`, `importDocumentPage…` (DocumentService+PageIO). The preview's box edits go through the older `PUT /api/artifacts/{id}/regions` (ArtifactService+RegionCuration), which the engine now routes into `segment.convert_and_edit`. The app's generic `ActionsService.invokeAction(name:)` is called only with document/claim/entity/artifact action names (the only language one is `document.set_language`); it is never called with a segment, reading, hand, sign, rights, link or order action.
**Uncalled source routes** (0 app callers): all segment writes (`POST/PUT/PATCH /api/segments…`, merge, split, delete, undelete, carry, matches, passes, restore-version, versions, picture, reference), `POST …/readings/choice`, `GET /api/segments/document/{id}/text`, `GET /api/reading-orders/{id}/neighbours`, `POST /api/reading-orders`, `GET /api/formats`, all `/api/links`, `/api/signs`, `/api/rights`, `/api/hands`, `/api/content-representations`, `GET /api/source-settings/resolve`, and the authority `refresh` and `link` routes.

Short names used in the table:
- **SS** = `fichero/fichero/Services/SegmentService.swift`; **STORE** = `Models/SegmentStore.swift` (`SegmentStore.shared(for:)`, owned by `LibraryManager`)
- **OVL** = `Views/Preview/ImageViewer/OCRGeometryOverlay.swift:loadOCRGeometry` → `SegmentDisplay.selected(for:store:)`; **PDFBOX** = `Views/Preview/PDFViewer/PDFPageView+OCRBoxes.swift`
- **INSP** = `Views/Inspector/Source/SourceSectionView.swift` (mounted by `DocumentInspector+Sections.swift:contentTab`) → `SegmentInspectorView` (path head, **Text** section = `InspectorTextSection`, **Order** section = `ReadingOrderList`). It is shown only when the focused preview's `RegionSelection` resolves to segment ids.
- **ORDER** = `Services/ReadingOrderService.swift` → `Models/ReadingOrderStore.swift` → `Views/Components/ReadingOrderList.swift` (Inspector ▸ Source ▸ **Order** tab, and the Order section at a selected level). **RLM** = `Views/Reader/Knowledge/ReaderLineMove.swift` ← `DocumentKGWebPaneCoordinatorMacOS.moveLine` (⌥⌘↑/↓/⇞/⇟ on the Reader caret line; the engine's `document_view.html` posts `lineMove`).
- **PIO** = `Services/DocumentService+PageIO.swift` `exportPage`/`importPage` ← `App/Menus/PageExportRunner.swift` / `PageImportRunner.swift` ← `App/Menus/ReaderExportCommands.swift:ReaderExportMenuItems`. That menu is **File ▸ Export ▸ "Export Page As ▸ PAGE XML/ALTO/TEI"** and **"Import Page From…"**, also in the reader head menu (`ReadingPaneView.swift:529`). It is macOS only (`#else EmptyView`) and needs a single document.
- **RGN** = `Services/ArtifactService+RegionCuration.swift` (PUT `/api/artifacts/{id}/regions` → action `segment.convert_and_edit`) ← `Views/Preview/ImageViewer/Regions/ZoomableImagePreviewMac+Regions.swift` (`commitRegionMove`, `deleteSelectedRegions`, `combineSelectedRegions`, `promoteMarquees`, `promoteSelectedWords`, `registerRegionUndo`). It is gated on `WindowState.isEditingSegments`, the **Edit Segments** toggle in the preview head (`PreviewHeadControls.swift`) and the what-to-show menu (`ReaderToolbar.swift:240`).
- **IMPORTED-PAGE CAVEAT** (read from code, not run): an imported pass has no `sourceArtifactId`, so OVL sets `ocrGeometryArtifactId = nil`. `RegionInteractionLayer` selects only `if let artifactId` (lines 378–386) and `RegionEditTarget.forDirectEdit/forSelectionEdit` refuse a nil artifact. On a page whose shown pass came from **Import Page From…**, the boxes draw (#5146) but they **cannot be selected or edited**. The Inspector's segment level (INSP) is therefore unreachable there too, because `selectedSegmentIds` needs `pass.sourceArtifactId == selection.artifactId`.

Python e2e test paths are relative to `fichero-server/tests/unit/`. "Real data" means a real interchange file or corpus page imported through `format.import` or the import route.

## Table 1 — behaviours

### formats-and-training.md (19)

| id | spec file | tag | engine | swift_caller | visible | e2e_test | gap |
|---|---|---|---|---|---|---|---|
| source.format.one-model-one-harness | formats-and-training.md | OK | `formats/` registry + `SourcePage`, harness | n/a | engine-internal (format architecture) | n/a | |
| source.format.schemas-on-disk | formats-and-training.md | OK | `formats/schemas/`, offline validation | n/a | engine-internal (validation never goes to the network) | n/a | |
| source.format.first-four | formats-and-training.md | PARTIAL | format registry (pagexml, alto, tei, hocr, yolo, iiif_georef, qgis-points); `GET /api/formats`; export/import routes | `DocumentService.formats()` → `PageExportChoice.offers` (Inspector › Making, per pass, #5162); File › Export Page As still the fixed three | yes (Making) — every format the engine writes, of the pass's kind | `ImportedPageDrawsItsBoxesTests.testExportChoicesOfferWhatTheEngineWritesPerPassAndAsImportedIsTheFile` + recorder `test_export_choices_are_recorded_as_edited_and_as_imported_for_the_making_section` (real Syriac page) | build File › Export Page As from the same list |
| source.format.package-folder | formats-and-training.md | PARTIAL | `POST /api/ingest/folder` → `import.folder` → `interchange_pairing.plan_pairs` → `format.import` | `Services/ImportService+Ingest.swift` / `DocumentService.ingestFolder` (the existing folder import) | yes — the ordinary folder import/drop | none via the route; action-level on real files: `importers/test_folder_of_images_and_layout.py::TestDroppingTheFolder::test_the_images_become_pages_with_their_passes` | |
| source.format.import-is-pass | formats-and-training.md | OK | `POST /api/documents/{doc_id}/import` (action `format.import`) | PIO `importPage` ← `PageImportRunner.importPage` ← ReaderExportMenuItems | yes — File ▸ Export ▸ Import Page From… (macOS) | `formats/test_import_into_library.py::TestTheImportRoute::test_a_person_uploads_a_file_and_gets_a_pass`; unit: `PageImportTextTests` | no way to see or choose the new pass afterwards (see source.pass.named-authored) |
| source.format.reimport-recognised | formats-and-training.md | OK | same route, 409 naming the pass | PIO `importPage` → `.alreadyImported(detail:)` → PageImportRunner alert | yes — the alert names the pass that holds the bytes | `formats/test_import_into_library.py::TestReimportIsRecognised` (unsure whether through the HTTP route) | |
| source.format.keeps-unrecognised | formats-and-training.md | OK | `format.import` → `metadata["foreign"]`; `page_export` writes it back | carried through PIO; nothing displays it | engine-internal (kept and written back; nothing to show) | `formats/test_import_into_library.py::TestWhatTheImportKeptSurvivesTheExport::test_the_library_round_trip_keeps_it_the_way_a_format_round_trip_does` (import+export routes, real file) | |
| source.format.export-validated | formats-and-training.md | OK | harness validation inside the export route | the refusal sentence reaches PageExportRunner via `DocumentServiceError.serverError` | engine-internal (a refused export shows the engine's sentence) | route-level on synthetic rows: `api/test_page_export_route.py::TestTheRefusalsAreDeclaredAndNotOnlyRaised` | |
| source.format.validate-a-directory | formats-and-training.md | OK | `scripts/validate_exports.py` | n/a | engine-internal (dev/CI command) | n/a | |
| source.format.every-writer-is-validated | formats-and-training.md | OK | guard `formats/test_export_validation.py` | n/a | engine-internal (CI guard) | n/a | |
| source.format.loss-report | formats-and-training.md | OK | export response `losses` | PIO `exportPage` → `PageExportRunner.Text.losses` in the completion alert (selectable) | yes — the Export Page As completion message | none on real data; route test on a synthetic page: `api/test_page_export_route.py::TestExportingAPage::test_the_loss_report_reaches_the_caller`; unit: `PageExportTextTests` | |
| source.format.round-trip-pagexml | formats-and-training.md | OK | pagexml reader/writer | n/a | engine-internal (format property; reached via Import/Export Page) | format-level `formats/test_pagexml_round_trip.py`, `test_pagexml_real_file.py` | |
| source.format.round-trip-alto | formats-and-training.md | OK | alto reader/writer | n/a | engine-internal (format property) | format-level `formats/test_alto.py::TestTheAltoRoundTrip` | |
| source.format.round-trip-hocr | formats-and-training.md | OK | hocr reader/writer | n/a | engine-internal (format property; hOCR export is not offered in the app) | format-level `formats/test_hocr_and_yolo.py::TestHocrRoundTrip` | |
| source.format.round-trip-yolo | formats-and-training.md | OK | yolo reader/writer | n/a | engine-internal (format property; YOLO export is not offered in the app) | format-level `test_hocr_and_yolo.py::TestYoloIsHonestAboutLosingAlmostEverything` | |
| source.format.export-choices | formats-and-training.md | OK | `GET /api/documents/{id}/export/{fmt}?pass_id&order_id&reading_kind` | Making's Export sends `pass_id` (the pass picked); "As Imported…" saves the pass's original (`GET /api/segments/passes/{id}/original`) byte for byte (#5162) | yes — pass and format chosen, and as imported vs as edited; order and reading kind still the engine's defaults, stated in the report | `ImportedPageDrawsItsBoxesTests.testExportChoicesOfferWhatTheEngineWritesPerPassAndAsImportedIsTheFile` + recorder `test_export_choices_are_recorded_as_edited_and_as_imported_for_the_making_section` (real Syriac page) | choose the order and the reading kind |
| source.format.everywhere | formats-and-training.md | OK | the two routes above; CLI `fichero export page` + `fichero import-page`; MCP `fichero_page_export/import` | PIO ← ReaderExportMenuItems | yes on macOS; **no on iOS** (`#else EmptyView`) | `formats/test_import_into_library.py::TestTheImportRoute::test_a_person_uploads_a_file_and_gets_a_pass`, `::TestWhatTheImportKeptSurvivesTheExport::test_a_files_custom_survives_import_then_export` | iOS has no page import or export |
| source.format.alto-in | formats-and-training.md | OK | alto reader via the import route | PIO importPage | yes — through Import Page From… | none via the route (format-level `formats/test_alto.py::TestReadingARealAltoFile`) | |
| source.format.alto-out | formats-and-training.md | OK | alto writer (ALTO 4.4) via the export route | PIO exportPage (`Format.alto`) | yes — Export Page As ▸ ALTO | none via the route on a real file (format-level `test_alto.py`) | |

### languages-scripts-signs.md (17)

| id | spec file | tag | engine | swift_caller | visible | e2e_test | gap |
|---|---|---|---|---|---|---|---|
| source.lang.three-facts | languages-scripts-signs.md | OK | `Segment.language/script` + provenance; `LibraryScript.encoding`; `segment.update` | `Segment.language/script/direction` are decoded (`Models/Segment.swift:223`) but no view reads them | no | none | the Inspector does not show a segment's language, script or encoding |
| source.lang.registries | languages-scripts-signs.md | PARTIAL | ISO 15924 vocabulary, `LanguageSpec.glottocode` | none | engine-internal (vocabulary; BCP 47 half is GAP #5078) | n/a | |
| source.lang.project-declared | languages-scripts-signs.md | OK | `LibraryScript` + `assert_known_script` (in `representation.create`, `segment.update`) | none | no | none | no way to declare a project script in the app |
| source.lang.unknown-is-not-unexamined | languages-scripts-signs.md | OK | cascade resolution control flow | only the pre-existing document language row (`DocumentInspectorInfoTab+Language.swift`, `document.set_language`, "clear" back to never-determined) | engine-internal (resolution rule) | n/a | |
| source.lang.cascade | languages-scripts-signs.md | OK | `source_settings` action (project/node) + `segment.update`; `GET /api/source-settings/resolve` | only the document level, via `document.set_language` in the Info tab (predates the programme); `resolveSourceSettings…` is uncalled | partial — document level only | none | cannot set at folder/page/segment level or see the inherited value |
| source.lang.says-where-from | languages-scripts-signs.md | OK | `GET /api/source-settings/resolve` → `LanguageResolution.level` | none | no | none | a shown language does not say which level it came from |
| source.lang.reading-overrides | languages-scripts-signs.md | OK | cascade (reading rung) | none (`InspectorText.Reading` has no language/script) | no | none | the Inspector's Text section does not show a reading's language/script |
| source.lang.many-per-page | languages-scripts-signs.md | OK | `PUT /api/segments/{id}` (`segment.update` language/script) | none (`updateSegment…` uncalled; `SegmentEditCommand.plan` has no caller) | no | route-level on synthetic regions: `api/test_many_languages_per_page.py::TestManyPerPageEndToEnd::test_three_regions_are_SET_to_three_scripts_and_READ_BACK_as_three` | cannot set a region's language/script |
| source.dir.per-segment | languages-scripts-signs.md | PARTIAL | `segment.update` direction; `resolve_direction` | none | no | none | cannot set or see a segment's direction |
| source.dir.logical-order-stored | languages-scripts-signs.md | OK | engine never reorders text | display bidi by WebKit/SwiftUI | engine-internal (storage rule) | n/a | |
| source.sign.declared | languages-scripts-signs.md | PARTIAL | `POST /api/signs` (`sign.declare`) | none | no | none | declare a sign from a segment (spec: waits for wireframes) |
| source.sign.list-authority | languages-scripts-signs.md | PARTIAL | `sign.declare` with authority + number | none | no | none | look up a sign by catalogue number |
| source.sign.project-list | languages-scripts-signs.md | PARTIAL | `GET /api/signs`, `POST /api/signs/{id}/withdraw` | none | no | none | see or export the project's sign list |
| source.sign.in-readings | languages-scripts-signs.md | PARTIAL | text keeps the PUA character; `DeclaredSign` gives its meaning | reading text is shown as plain text in INSP | partial — the character shows, its declared meaning does not | none | show which declared sign a character is |
| source.sign.variants | languages-scripts-signs.md | PARTIAL | `sign.declare` (variant fields) | none | no | none | declare or mark a variant |
| source.sign.gather-instances | languages-scripts-signs.md | PARTIAL | `GET /api/signs/{id}/instances` | none | no | none | list every instance of a sign |
| source.sign.export-honest | languages-scripts-signs.md | PARTIAL | TEI writer `<g ref>` + `charDecl`; other writers' loss report | PIO exportPage (TEI) | partial — automatic in Export Page As ▸ TEI; losses shown in the alert | none via the route on real data (`api/test_declared_signs.py` exports through `/export/tei` on a MUFI page — unsure whether through the client) | |

### maps-and-georeference.md (4)

| id | spec file | tag | engine | swift_caller | visible | e2e_test | gap |
|---|---|---|---|---|---|---|---|
| source.geo.gazetteer-candidates | maps-and-georeference.md | PARTIAL | external authority reconciliation: `POST /api/kg/entity-curation/authority/refresh`, `/link` | `KGCurationService.swift` calls only the authority **settings** get/put; refresh and link are uncalled | no (settings only; where they show is unsure) | none | see and choose authority candidates for an entity |
| source.geo.iiif-georef-in | maps-and-georeference.md | PARTIAL | `formats/iiif_georef.py` reader (registered); library half #5122 | possibly PIO importPage (the registry holds iiif_georef) — unsure whether the route accepts it | unsure | none via the route (format-level `formats/test_iiif_georef.py`) | library half (#5122); no map view |
| source.geo.iiif-georef-out | maps-and-georeference.md | PARTIAL | `iiif_georef` writer | none (`PageExportRunner.Format` has no georef) | no | none via the route | export a georeferencing pass |
| source.geo.iiif-georef-round-trip | maps-and-georeference.md | OK | format-to-format round trip | n/a | engine-internal (format property) | format-level `test_iiif_georef.py::TestWriting::test_the_round_trip_keeps_gcps_mask_and_transformation` | |

### readings-and-apparatus.md (17)

| id | spec file | tag | engine | swift_caller | visible | e2e_test | gap |
|---|---|---|---|---|---|---|---|
| source.reading.set | readings-and-apparatus.md | OK | action `representation.create`; `POST /api/content-representations`; read `GET /api/segments/{id}/readings` | read: `SS.readings(segmentId:)` ← `SegmentInspectorView.task` (INSP); write: none | partial — readings are **listed** (INSP ▸ Text); none can be added | none on real data (route test on synthetic rows: `api/test_segment_readings.py::TestReadingsAreWritten::test_three_readings_of_one_line_coexist_and_adding_one_changes_no_other`); unit `InspectorTextTests` | type or add a reading (Reader typing not built, #5001); not reachable on imported pages (caveat) |
| source.reading.kinds | readings-and-apparatus.md | OK | reading-kind registry | INSP groups readings by kind | yes — headings per kind in the Text section | none | |
| source.reading.level-recorded | readings-and-apparatus.md | OK | `ContentRepresentation.level` | not mapped into `InspectorText.Reading` | no | none | the Text section does not show a reading's normalisation level |
| source.reading.read-from | readings-and-apparatus.md | OK | reading's rendition + `derived_from` | not mapped | no | none | does not show which image or reading it was read from |
| source.reading.author-and-guideline | readings-and-apparatus.md | OK | `created_by`, `guideline` | `InspectorText.Reading.author/guideline` → `InspectorTextSection.detail` | yes — INSP Text row detail line | none on real data; unit `InspectorTextTests` | |
| source.reading.corrections-are-new | readings-and-apparatus.md | OK | `representation.create` with a correction target | none (the target is not mapped) | no | none | make a correction; see what a correction corrects |
| source.reading.equal-alternatives | readings-and-apparatus.md | OK | counting rule | INSP lists every live reading per kind | yes — all alternatives are listed | none | |
| source.reading.chosen-is-worked-out | readings-and-apparatus.md | OK | `counting` + `basis` in the readings route; `POST …/readings/choice` (`reading.choose`) | read: `InspectorText.Counting/Why` (checkmark + "Chosen by a person" etc.); choose: none (`chooseSegmentReading…` uncalled) | partial — which counts, and why, is shown; cannot choose | none | choose the reading that counts |
| source.reading.chosen-follows-project-rule | readings-and-apparatus.md | OK | project strict/relaxed rule | shown only via `Why` labels | partial — the rule is reflected, not settable | none | no project setting for strict/relaxed (unsure whether one exists elsewhere) |
| source.reading.machine-is-labelled | readings-and-apparatus.md | OK | `provenance_kind` on the reading; export marks | `InspectorText.Reading.maker` shown capitalised; "Machine reading, not yet checked" | yes — INSP Text | none | |
| source.reading.maker-set-by-engine | readings-and-apparatus.md | OK | engine-set `ProvenanceKind` | n/a | engine-internal (never sent by a client) | n/a | |
| source.reading.stretch-names-its-reading | readings-and-apparatus.md | OK | anchor `representation_id` + offset carry-over | `Segment.swift` maps the anchor field | engine-internal (bookkeeping) | n/a | |
| source.reading.written-read-pair | readings-and-apparatus.md | OK | `representation.pair` / `unpair` | read: `pairRole` (sic/corr) in the INSP row; write: none | partial — shown, cannot be made | none | join two readings as written/read |
| source.reading.char-confidence-on-line | readings-and-apparatus.md | OK | per-character detail on the line reading | none | no | none | show per-character confidence |
| source.hand.record | readings-and-apparatus.md | OK | `POST/GET /api/hands`, `hand.create/withdraw`, `GET /api/hands/{id}/attributions` | none | no | none | make or browse hands |
| source.hand.attributed | readings-and-apparatus.md | PARTIAL | `POST /api/hands/attributions` (`hand.attribute`); EpiDoc `handShift` → hand on `format.import` | import only: attributions arrive through PIO importPage; nothing reads them (`handsOfSegment…` uncalled) | no | none | attribute a segment to a hand; see a segment's hands |
| source.hand.not-provenance | readings-and-apparatus.md | PARTIAL | attribution vs `created_by` / `provenance_kind` | none | no | none | the Inspector shows neither the hand nor who judged it |

### rights-and-access.md (3)

| id | spec file | tag | engine | swift_caller | visible | e2e_test | gap |
|---|---|---|---|---|---|---|---|
| source.rights.record | rights-and-access.md | PARTIAL | `POST /api/rights` (`rights.set`), `…/withdraw` | none | no | none | attach a rights/consent record to a project, source or segment |
| source.rights.tighten-only | rights-and-access.md | OK | `effective_rights`; `GET /api/rights/effective` | none | engine-internal (combination rule), but nothing shows the effective answer | none | (see record: no view of effective rights) |
| source.rights.who-acts | rights-and-access.md | PARTIAL | write-check on `rights.set` | none | engine-internal (permission check) | n/a | |

### segment-editor.md (30)

| id | spec file | tag | engine | swift_caller | visible | e2e_test | gap |
|---|---|---|---|---|---|---|---|
| source.app.one-segment-store | segment-editor.md | OK | `GET /api/segments/document/{doc_id}` | STORE → `SS.listDocumentSegments`; readers OVL, PDFBOX, INSP, ReadingOrderList labels | yes (indirect: the boxes on the image/PDF) | Swift `Tests/Unit/general/Models/ImportedPageDrawsItsBoxesTests.swift::testTheImportedSyriacPageDrawsTheFilesRegionsAndLines` (recorded engine answer for a real imported PAGE file, transport stubbed) + `api/test_imported_page_draws_its_boxes.py::test_an_imported_page_s_segments_reach_the_canvas_s_call_as_the_file_s_regions_and_lines`; unit `SegmentStoreTests` | |
| source.app.index-is-the-engines | segment-editor.md | OK | seam box index | `SegmentDisplay.geometry` (placeholders; refuses gapped passes) | engine-internal / app-internal invariant (addressing) | unit `SegmentDisplayTests` | |
| source.app.edits-name-the-chosen-pass | segment-editor.md | OK | PUT `/api/artifacts/{id}/regions` | `RegionEditTarget.forDirectEdit/forSelectionEdit` in RGN | yes — preview edits in Edit Segments | none on real data; unit `RegionEditTargetTests` | imported passes have no artifact, so no edit is sent at all (caveat) |
| source.app.curated-pass-stays-on-top | segment-editor.md | OK | seam pass provenance | `OCRGeometrySelection.rankedPasses` via `SegmentDisplay.selected` in OVL/PDFBOX | yes — which boxes are drawn | unit `OCRGeometrySelectionTests.rankedPassesAuthorityBeatsRecency`, `OCRGeometryCurationAuthorityTests` | |
| source.app.overlays-draw-from-the-seam | segment-editor.md | PARTIAL | `GET /api/segments/document/{doc_id}` | OVL + PDFBOX → `SegmentDisplay.selected(for:store:)`, artifact fallback | yes — Source view image and PDF | `ImportedPageDrawsItsBoxesTests::testTheImportedSyriacPageDrawsTheFilesRegionsAndLines` + `api/test_imported_page_draws_its_boxes.py::test_an_imported_page_s_segments_reach_the_canvas_s_call_as_the_file_s_regions_and_lines` | imported-page boxes draw but cannot be selected (caveat) |
| source.app.segment-events-patch-in-place | segment-editor.md | PARTIAL | change stream `segment.*`/`pass.*` ids; `GET /api/segments/{id}` | `LibraryManager.swift:274` registers STORE (`ChangeEventConsumer`) → `SS.segment(id:)` | yes (indirect: the overlay refreshes) | engine half `api/test_change_stream_segment_ids.py::TestChangeSpecReachesSubscriber::test_changespec_segment_and_pass_ids_reach_the_subscriber`; app half unit `SegmentStoreTests.testAnEventNamingHeldSegmentsPatchesThoseAndDoesNotReload` (spec: "not yet compiled by anyone") | |
| source.editor.segment-focus | segment-editor.md | PARTIAL | n/a (UI mode) | `WindowState.isEditingSegments`; `SegmentEditingMode`; toggle in `PreviewHeadControls` and `ReaderToolbar` ("Edit Segments") | yes — preview head button + what-to-show toggle | unit `SegmentEditingModeTests` | |
| source.textedit.reader-shows-segments | segment-editor.md | PARTIAL | `document_text()` blocks; Reader HTML `GET /view/document/{id}` line map (`views.py:page_line_map`) | Reader web view (engine-rendered); `GET …/text` is not called by Swift | partial — the Reader shows the page text in order, with a hidden line map; not per-block, not editable, no line pictures | `api/test_reader_line_map.py::test_the_map_names_each_line_and_covers_its_text` (real CLM page, the Reader route) | editable per-line text in the Reader; line pictures when no Source view is open |
| source.textedit.typing-is-a-new-reading | segment-editor.md | PARTIAL | `representation.create` (maker from context) | none | no | none | type in the Reader to correct a line |
| source.textedit.return-splits-the-line | segment-editor.md | PARTIAL | `POST /api/segments/split` (`segment.split`) | none (`splitSegment…` uncalled) | no | none | Return splits a line |
| source.textedit.backspace-joins-in-reading-order | segment-editor.md | PARTIAL | `POST /api/segments/merge` (`segment.merge`) | none from the Reader (`mergeSegments…` uncalled) | no | none | Backspace joins lines |
| source.editor.one-overlay | segment-editor.md | PARTIAL | n/a | OVL (Canvas) + PDFBOX (`PDFAnnotation`), both fed by `SegmentDisplay` | yes (two renderers, one geometry source) | covered by the overlay rows above | spec wording vs platform (two renderers); no user-facing gap |
| source.editor.shapes-in-source-view | segment-editor.md | PARTIAL | PUT `/api/artifacts/{id}/regions` → `segment.convert_and_edit` | RGN (Source view) and `ArtifactPanel+Regions` (Inspector Combine) both call `ArtifactService.combineRegions` | yes — move, delete, combine, add in the Source view; Combine in the Inspector's regions panel | none on real data (route tests `test_first_edit_conversion.py`, `test_artifact_regions_edit.py`, synthetic rows) | reshaping a polygon/baseline (unsure it exists); imported pages not editable |
| source.editor.selection-shared | segment-editor.md | PARTIAL | n/a | `RegionSelection.shared` (preview ↔ Inspector); `.readerTextSelection` notification (Reader → preview); **`SegmentSelection.shared` is never written** | partial — Source view → Inspector works (artifact passes only); Reader ↔ others is text ranges; Source → Reader absent | unit `SegmentSelectionTests` only | selecting in the Reader or the Order list does not select the segment elsewhere |
| source.editor.edits-are-actions | segment-editor.md | PARTIAL | `segment.convert_and_edit` (undoable, one audit row) | RGN | yes (for the edits that exist) | none on real data; route-level synthetic `api/test_first_edit_conversion.py::TestTheFirstEditConvertsAndEdits::test_one_action_and_one_undo_step` | |
| source.editor.redo-works | segment-editor.md | PARTIAL | `POST /api/actions/audit/{id}/undo` (redo = undo of undo) | `RegionEditResult.registerUndo` / `ActionUndo.swift` | yes — Edit ▸ Redo after a region edit | none (engine `test_action_undo.py`, `TestSegmentUpdateUndoRedo`) | |
| source.editor.system-undo | segment-editor.md | PARTIAL | the audit undo route; the regions route returns `audit_id` | `ZoomableImagePreviewMac+Regions.registerRegionUndo`; `ReadingOrderStore.registerUndo` (ORDER, RLM) | yes — ⌘Z/⇧⌘Z after a region edit or a reorder | none e2e in Swift; reorder undo on real pages: `api/test_text_follows_the_order.py::test_a_move_shows_in_the_text_and_undo_restores_it_byte_for_byte` | |
| source.editor.agent-parity | segment-editor.md | PARTIAL | CLI generated surface; MCP tools | n/a | engine-internal (other surfaces) | n/a | |
| source.editor.join-group | segment-editor.md | PARTIAL | `POST /api/segments/merge` (`segment.merge`); grouping lines into a region is unbuilt | model only: `SegmentEditCommand.mergePlan` (no caller outside its tests); the existing Combine uses RGN `combineRegions` instead | partial — Combine exists (artifact regions); segment merge via the plan and grouping do not | unit `SegmentMergePlanTests` | merge by segment id; group lines into a region / ungroup |
| source.editor.set-kind | segment-editor.md | PARTIAL | `PUT /api/segments/{id}` / `PATCH /api/segments` (`segment.update(_many)`) | model only: `SegmentEditCommand.plan` — no caller | no | unit `SegmentEditCommandTests` | set a selection's kind (text/furniture) |
| source.editor.set-direction | segment-editor.md | PARTIAL | `segment.update` direction | model only: `SegmentEditCommand.plan` — no caller | no | unit `SegmentEditCommandTests` | set a direction / reverse a line |
| source.editor.set-language-script | segment-editor.md | PARTIAL | `segment.update` language/script | model only: `SegmentEditCommand.plan` — no caller | no | unit `SegmentEditCommandTests` | set a selection's language/script |
| source.editor.reorder | segment-editor.md | PARTIAL | `POST /api/reading-orders/{id}/place` (`reading_order.place`); `GET …/document/{id}`, `GET …/{id}/entries` | ORDER (drag `onMove`, ⌥⌘ arrow buttons) and RLM (Reader keys) | yes — Inspector ▸ Source ▸ Order tab, the Order section at a level, and the Reader caret keys | `api/test_text_follows_the_order.py::test_a_move_shows_in_the_text_and_undo_restores_it_byte_for_byte` (real imported pages, the place route); unit `ReadingOrderMoveTests`, `ReadingOrderStoreTests` | on-page "click segments in turn" is not built; only the `as-written` order is loaded (no picker for other named orders) |
| source.perf.worst-frame-not-mean | segment-editor.md | PARTIAL | `scripts/perf_trial.py` verdict | n/a | engine-internal (perf harness) | n/a | |
| source.perf.five-runs-median | segment-editor.md | PARTIAL | perf harness | n/a | engine-internal (perf harness) | n/a | |
| source.perf.names-its-machine | segment-editor.md | PARTIAL | perf harness | n/a | engine-internal (perf harness) | n/a | |
| source.perf.declared-fixture | segment-editor.md | OK | `scripts/perf_fixture.py` | n/a | engine-internal (fixture) | n/a | |
| source.perf.void-when-throttled | segment-editor.md | PARTIAL | perf harness | n/a | engine-internal (perf harness) | n/a | |
| source.perf.baseline-or-fail | segment-editor.md | PARTIAL | perf harness | n/a | engine-internal (perf harness) | n/a | |
| source.perf.memory-growth | segment-editor.md | PARTIAL | perf harness | n/a | engine-internal (perf harness) | n/a | |

### segments-and-geometry.md (52)

| id | spec file | tag | engine | swift_caller | visible | e2e_test | gap |
|---|---|---|---|---|---|---|---|
| source.segment.lasting-id | segments-and-geometry.md | OK | `segment.create/update`, engine-made ids | STORE keys by id | engine-internal (identity invariant) | n/a | |
| source.segment.rerun-is-new-pass | segments-and-geometry.md | OK | `segment.pass_create` | n/a | engine-internal (storage rule) | n/a | |
| source.segment.carry-across-a-match | segments-and-geometry.md | OK | `POST /api/segments/carry` (`segment.carry`) | none | no | none | carry readings/marks across an accepted match |
| source.segment.versioned-alone | segments-and-geometry.md | OK | `GET /api/segments/{id}/versions`, `segment.restore_version` | `SegmentService.versions`, `SegmentHistory` (Inspector › Making at segment level, #5163) | yes — each kept version with what the change after it did; Restore checked against the version read, ⌘Z | `ImportedPageDrawsItsBoxesTests.testALinesHistoryShowsWhatEachChangeDidAndRestoreSendsTheCheckedCall` + recorder `test_a_line_s_history_is_recorded_and_restoring_it_is_the_app_s_exact_call` (real Syriac page) | compare two versions side by side |
| source.segment.delete-is-undoable | segments-and-geometry.md | OK | `segment.delete/undelete`; in the app via `segment.convert_and_edit` + audit undo | RGN `deleteSelectedRegions` + `registerRegionUndo` | yes — ⌫ in Edit Segments, then ⌘Z | none on real data | imported pages cannot be selected for delete (caveat) |
| source.segment.shape-kinds | segments-and-geometry.md | OK | `SourceAnchor` shapes | `SegmentShapes.drawn` → `OCRGeometryBox.shapes` → `DocumentOverlayView` (image pages) | yes — polygon, open path, point and baseline drawn as themselves on image AND PDF pages (`PDFShapeAnnotations`) | `ImportedPageDrawsItsBoxesTests.testALinesOutlineAndBaselineAreDrawnAsThemselvesAndReshapeSendsTheCheckedUpdate` + engine pin against the PAGE file | reshape on PDF pages |
| source.segment.box-is-derived | segments-and-geometry.md | OK | bbox from anchor | n/a | engine-internal | n/a | |
| source.segment.curved-baseline | segments-and-geometry.md | OK | baseline shape; `GET /api/segments/{id}/picture` levelling | drawn on the image (`ShapeDrawing`), said in Inspector › Making, reshaped in Edit Segments (`SegmentShapes.reshape`, #5163 residue) | yes on image pages — drawn, points dragged/added/removed, ⌘Z | same e2e + `…testReshapingABaselineSendsItAloneAndTheRefusalsHold` | PDF pages |
| source.segment.names-its-image | segments-and-geometry.md | OK | seam rendition id | `SegmentDisplay.geometry(... renditionId:)` | engine-internal (coordinate frame) | n/a | |
| source.segment.picture-by-shape | segments-and-geometry.md | OK | `GET /api/segments/{id}/picture` | `SegmentPictureService` (Segments pane strip/grid; Inspector › Making) | yes | `…testAStripCellsPictureIsTheEnginesCutOfTheLine` (the same call the Section makes) | |
| source.segment.one-primitive | segments-and-geometry.md | OK | one `Segment` table with kind | `Segment.kind` | engine-internal (model) | n/a | |
| source.segment.open-kinds | segments-and-geometry.md | OK | kind + `kind_raw` | `Segment.kind` used in INSP crumbs/counts and ReadingOrderList labels | partial — the kind is shown as a label | unit `SegmentMappingTests` | |
| source.segment.flow | segments-and-geometry.md | PARTIAL | `reading_order` of kind flow (reading straight through is GAP #5090); `GET /api/reading-orders/flows/onto/{page}` (bugs2 7f5cacecb) | `ReadingOrderPicker` New Flow…, Next across pages (#5160); "Continue a Flow Here" (`ReadingOrderService.flowsOnto`, `placeAtEnd`, `ReadingOrderChoice.continuation`) | yes — make a flow, follow it onto another page, and continue one from an earlier page (or the project) with this page's segments in its order, one ⌘Z | `…testTheOrderPickerListsNamedOrdersAndAFlowWhoseNextOpensTheNextPage`, `…testAFlowFromAnEarlierPageIsOfferedAndContinuingItPlacesThisPagesSegmentsAtTheEnd` + recorders on two pages of one imported Syriac source | read straight through (#5090) |
| source.segment.table-cells | segments-and-geometry.md | PARTIAL | PAGE `TableCell` → region; `SegmentRead.cell` {row, column, spans} | `Segment.cell`; `InspectorPath.name(of:)` names a cell by its place in the path head and the Segments pane rows (#5168) | yes — read only: "Cell, Rows 3–4, Column 1", counted from 1 | recorder `test_an_imported_table_s_cells_say_their_row_and_column_to_the_app` (real Transkribus table, 172 cells checked against the file) + `ImportedPageDrawsItsBoxesTests.testATableCellIsNamedByItsRowAndColumnInThePathAndTheRows` | make cells (the Shape tool) |
| source.table.is-a-segment | segments-and-geometry.md | PARTIAL | `table` kind on import | via import | partial — drawn as a box | none via the route | draw a table |
| source.table.cell-text-is-lines | segments-and-geometry.md | PARTIAL | cell parent on import | via import | engine-internal (structure) | n/a | |
| source.form.label-and-answer | segments-and-geometry.md | PARTIAL | `labels`/`answers` link types (`POST /api/links`) | none | no | none | link a form's label to its answer |
| source.pass.named-authored | segments-and-geometry.md | OK | `SegmentPass` name/author; `POST/DELETE /api/segments/passes` | STORE holds passes; the shown pass follows `FocusedArtifact` (Artifacts inspector) for artifact passes only | partial — no pass list; imported passes cannot be picked, hidden or compared | none | show, hide and compare passes (incl. imported ones) |
| source.pass.never-overwrites | segments-and-geometry.md | OK | pass storage | n/a | engine-internal | n/a | |
| source.pass.working-follows-project-rule | segments-and-geometry.md | OK | working-pass rule | n/a | engine-internal (rule) | n/a | |
| source.pass.working | segments-and-geometry.md | PARTIAL | action `pass.choose_working` (no typed route in the contract); export and derived text follow it | none; the overlay ranks passes itself (`OCRGeometrySelection.rankedPasses`), not by the engine's working pass | no | route-level on synthetic rows: `api/test_working_pass_across_surfaces.py` | choose the working pass; show which pass is working |
| source.order.named-multiple | segments-and-geometry.md | OK | `GET /api/reading-orders/document/{id}`, `reading_order.create` | `ReadingOrderPicker` (the Order list's head: Inspector › Order and the Segments pane), `ReadingOrderStore.choose` (#5160) | yes — pick As Written / named / flow; New Order… (a copy to rearrange), ⌘Z | `ImportedPageDrawsItsBoxesTests.testTheOrderPickerListsNamedOrdersAndAFlowWhoseNextOpensTheNextPage` + recorder `test_a_named_order_and_a_flow_onto_the_next_page_are_recorded_for_the_order_picker` (real Syriac page + a second imported page) | set an order by clicking segments in turn |
| source.order.next-previous | segments-and-geometry.md | OK | `GET /api/reading-orders/{id}/neighbours` | `ReadingOrderService.neighbours`; Previous / Next in the picker (#5160) | yes — from the selected segment in the order shown; across pages in a flow | `ImportedPageDrawsItsBoxesTests.testTheOrderPickerListsNamedOrdersAndAFlowWhoseNextOpensTheNextPage` + recorder `test_a_named_order_and_a_flow_onto_the_next_page_are_recorded_for_the_order_picker` (real Syriac page + a second imported page) | |
| source.link.typed | segments-and-geometry.md | PARTIAL | `POST /api/links`, `GET /api/links/types` | none | no | none | link two segments with a type |
| source.link.both-ways | segments-and-geometry.md | OK | `GET /api/links/of/{end_id}` | none | no | none | see a segment's links from either end |
| source.point.by-id-or-span | segments-and-geometry.md | OK | anchor `segment_id` / span | `SourceAnchorValue` decodes | engine-internal (pointer model) | n/a | |
| source.point.text-is-derived | segments-and-geometry.md | OK | `document_text()`; `GET …/text`; `page_content` cache | Reader shows the derived text via the engine view (Swift does not call `…/text`) | yes (indirect: Reader text follows the segments/order) | `api/test_page_text_follows_the_file.py::test_the_syriac_lines_follow_the_files_reading_order` (real file; function-level, not the route) | |
| source.point.anchor-names-its-segment | segments-and-geometry.md | OK | anchor `segment_id` on readings/marks/claims | n/a | engine-internal | n/a | |
| source.statement.old-segment-field-left-alone | segments-and-geometry.md | OK | claim `source_segment_id` unchanged | n/a | engine-internal (data invariant) | n/a | |
| source.segment.match-record | segments-and-geometry.md | OK | `GET /api/segments/document/{id}/matches?state=proposed`; `segment.match_accept` / `segment.match_reject` | `SegmentService.proposedMatches`; Segments pane gathered set "Proposed matches" (head button with the count, shown only when some wait) (#5165) | yes — each row the newer segment, what it was, who proposed, how sure; Accept / Reject, ⌘Z | recorder `test_a_page_s_proposed_matches_are_recorded_and_accept_and_reject_are_the_app_s_exact_calls` + `ImportedPageDrawsItsBoxesTests.testAPagesProposedMatchesAreListedAndAcceptAndRejectSendTheirVerbs` | carry readings and marks across an accepted match; the head's count re-reads only on a page change |
| source.segment.forwarding-notes | segments-and-geometry.md | OK | forwarding resolution in `GET /api/segments/{id}` | `SS.segment(id:)` (resolves through forwarding, used by the STORE patch) | engine-internal (resolution; used implicitly) | n/a | |
| source.segment.citable | segments-and-geometry.md | OK | `GET /api/segments/{id}/reference` → `fichero:segment/<lib>/<doc>/<seg>`; `POST /api/locations/resolve` | Copy Reference (Inspector › Links); macOS `onOpenURL` → `SegmentReference.parse` → `resolve(with:)` → sidebar reveal + the window selects the segment (#5164) | yes (macOS) — a link opens its page with the segment selected, following a merge; one that does not resolve logs and beeps; iOS ignores it | `ImportedPageDrawsItsBoxesTests.testASegmentReferenceURLResolvesToItsPageAndFollowsAMerge` + recorder `test_a_citable_reference_resolves_to_its_page_and_follows_a_merge_for_the_url_handler`; parsing `SegmentReferenceTests` | say why a link did not open (a message, not a beep); iOS handler |
| source.edit.stale-is-refused | segments-and-geometry.md | OK | `expected_version` compare-and-set | RGN edits (the refusal sentence is shown — unsure) | engine-internal (refusal) | n/a | |
| source.derived.recomputable | segments-and-geometry.md | OK | derived records name their inputs | n/a | engine-internal | n/a | |
| source.seam.read-either-store | segments-and-geometry.md | OK | `GET /api/segments/document/{doc_id}` | STORE via `SS.listDocumentSegments` | engine-internal (the app reads one call; boxes visible via OVL) | `api/test_imported_page_draws_its_boxes.py::test_an_imported_page_s_segments_reach_the_canvas_s_call_as_the_file_s_regions_and_lines` | |
| source.seam.maker-for-each-segment | segments-and-geometry.md | OK | seam `provenance_kind` | used by `OCRGeometrySelection` ranking | engine-internal (drives ranking, not shown) | n/a | |
| source.seam.provisional-ids-refused | segments-and-geometry.md | OK | typed refusal on writes | `Segment.swift` notes provisional ids | engine-internal | n/a | |
| source.events.segment-ids | segments-and-geometry.md | OK | change stream `ChangeSpec` segment/pass ids | `LibraryChangeStream` → STORE | engine-internal (plumbing; see segment-events-patch-in-place) | `api/test_change_stream_segment_ids.py::TestChangeSpecReachesSubscriber::test_changespec_segment_and_pass_ids_reach_the_subscriber` | |
| source.store.one-page-per-conversion | segments-and-geometry.md | OK | conversion action | n/a | engine-internal | n/a | |
| source.store.undo-first-edit-keeps-conversion | segments-and-geometry.md | OK | `segment.convert_and_edit` invert | reached by ⌘Z after the first region edit | engine-internal (invariant) | n/a | |
| source.store.conversion-changes-nothing-seen | segments-and-geometry.md | OK | conversion | n/a | engine-internal | n/a | |
| source.store.conversion-ids-repeatable | segments-and-geometry.md | OK | conversion ids | n/a | engine-internal | n/a | |
| source.store.converted-boxes-keep-their-maker | segments-and-geometry.md | OK | conversion provenance | n/a | engine-internal | n/a | |
| source.store.old-app-still-works | segments-and-geometry.md | OK | live geometry projection | artifact fallback in OVL/PDFBOX | engine-internal (compatibility) | n/a | |
| source.store.bounded-reads | segments-and-geometry.md | OK | filtered queries | n/a | engine-internal (performance) | n/a | |
| source.store.record-per-segment | segments-and-geometry.md | OK | per-segment rows | n/a | engine-internal | n/a | |
| source.convert.only-the-running-engine | segments-and-geometry.md | OK | project conversion lock | n/a | engine-internal (migration safety) | n/a | |
| source.convert.snapshot-first-and-proved | segments-and-geometry.md | OK | pre-conversion snapshot | n/a | engine-internal (migration safety) | n/a | |
| source.convert.refused-when-disk-is-short | segments-and-geometry.md | OK | preflight | n/a | engine-internal (migration safety; the report's surfacing in the app is unsure) | n/a | |
| source.convert.the-machine-stays-usable | segments-and-geometry.md | OK | background priority | n/a | engine-internal | n/a | |
| source.convert.stops-starts-and-repeats-safely | segments-and-geometry.md | OK | resumable runner | n/a | engine-internal | n/a | |
| source.convert.half-done-reads-the-same | segments-and-geometry.md | OK | invisibility of a partial conversion | n/a | engine-internal | n/a | |

### source-model.md (2)

| id | spec file | tag | engine | swift_caller | visible | e2e_test | gap |
|---|---|---|---|---|---|---|---|
| source.one-store | source-model.md | OK | `GET /api/segments/document/{doc_id}` (either store) | STORE/SS; `Segment.init(generated:)` | yes (indirect: boxes drawn) | `ImportedPageDrawsItsBoxesTests::testTheImportedSyriacPageDrawsTheFilesRegionsAndLines`; unit `SegmentMappingTests` | |
| source.builds-on-the-anchor | source-model.md | OK | `SourceAnchor` | `SourceAnchorValue` | engine-internal (model) | n/a | |

### Counts (by the `visible` column)

Counted by script over the table rows.

- behaviours audited: **144**
- **yes** (wired and visible, including indirect ones such as boxes drawn and the Reader text): **26**
- **partial** (reachable, but part of the behaviour has no surface): **18**
- **no**: **39** in total:
  - **3 model/service only, with no UI caller**: `set-kind`, `set-direction` and `set-language-script`, all through `SegmentEditCommand.plan`. `join-group`'s `mergePlan` is also uncalled, but that row is counted under partial because the existing Combine covers part of it.
  - **5 where some Swift touches the data** but nothing shows it: fields decoded but unshown (`lang.three-facts`, `reading.level-recorded`, `reading.read-from`), hand attributions arriving by import, and authority settings only.
  - **31 with no Swift caller at all**.
- **engine-internal**: **60**
- **unsure**: **1** (`source.geo.iiif-georef-in`)
- There is **no "service only" case among the network services**. Every `SegmentService`, `ReadingOrderService` and PageIO method has a UI caller; the unwired parts are either uncalled generated routes or the pure `SegmentEditCommand` / `SegmentSelection`.

## Table 2 — Swift types added by the source-model programme, and their callers

Callers are outside the type's own file, excluding tests. The source is `grep -w` over `fichero/fichero`, with each hit checked by reading the line (doc-comment mentions do not count).

| type | file | callers (outside own file and tests) |
|---|---|---|
| `Segment` | Models/Segment.swift | SegmentStore, SegmentService, SegmentDisplay, OCRGeometrySelection, InspectorPath, WindowState, LibraryChangeStream, ReadingOrderList, SegmentInspectorView, SegmentEditingMode (the `Segment` hits in Workflow*/ImageEdit*/BreadcrumbBuilder are other words — unsure for BreadcrumbBuilder) |
| `SegmentPassValue` | Models/Segment.swift | SegmentStore, SegmentService, SegmentDisplay, OCRGeometrySelection, InspectorPath |
| `AnchorShapeValue`, `SourceAnchorValue` | Models/Segment.swift | **no caller outside Segment.swift** (used only as `Segment`'s anchor fields; no view reads the shapes) |
| `SegmentStore` | Models/SegmentStore.swift | LibraryManager (owns it and registers it on the change stream, :274), SegmentDisplay, LibraryChangeStream, SegmentService, OCRGeometryOverlay, PDFPageView+OCRBoxes, PDFPageWithToolbar, SourceSectionView, SegmentInspectorView, ReadingOrderList, ArtifactPanel+Regions, LibraryServiceEnvironment |
| `SegmentService` (+ `SegmentServiceError`) | Services/SegmentService.swift | LibraryManager, SegmentStore, LibraryServiceEnvironment (env), SourceSectionView, SegmentInspectorView, ReadingOrderList, ArtifactPanel+Regions, ZoomableImagePreviewMac, PDFPageWithToolbar. `SegmentServiceError`: only thrown inside its own file |
| `SegmentDisplay` | Models/SegmentDisplay.swift | OCRGeometryOverlay, PDFPageView+OCRBoxes, SourceSectionView, InspectorPath, RegionEditTarget, OCRGeometrySelection, SegmentStore |
| `OCRGeometrySelection` (programme-extended: `rankedPasses`) | Models/OCRGeometrySelection.swift | SegmentDisplay, OCRGeometryOverlay, PDFPageView+OCRBoxes |
| `InspectorText` | Models/InspectorText.swift | SegmentService (`readings(segmentId:)`), SegmentInspectorView (`InspectorTextSection`) |
| `InspectorPath` | Models/InspectorPath.swift | SourceSectionView (`segmentIds(selectedIndices:…)`), SegmentInspectorView (crumbs, `kindCounts`) |
| `SegmentInspectorView` / `InspectorTextSection` (views) | Views/Inspector/Source/SegmentInspectorView.swift | SourceSectionView |
| `ReadingOrderMove` | Models/ReadingOrderMove.swift | ReadingOrderStore, ReadingOrderService, ReadingOrderList, ReaderLineMove, InspectorPath |
| `ReadingOrderStore` | Models/ReadingOrderStore.swift | ReadingOrderList, ReaderLineMove, DocumentKGWebPaneCoordinatorMacOS (`lineOrderStore`), SegmentInspectorView (via ReadingOrderList), LibraryManager |
| `ReadingOrderService` / `ReadingOrderTransport` / `ReadingOrderSummary` | Services/ReadingOrderService.swift | LibraryManager (`readingOrderService`), ReadingOrderList (env), ReadingOrderStore, DocumentKGWebPaneCoordinatorMacOS |
| `ReadingOrderList` (view) | Views/Components/ReadingOrderList.swift | SourceSectionView (Order tab), SegmentInspectorView (Order section) |
| `ReaderLineMove` | Views/Reader/Knowledge/ReaderLineMove.swift | DocumentKGWebPaneCoordinatorMacOS (`handleLineMove`/`moveLine`) |
| `RegionEditTarget` | Models/RegionEditTarget.swift | ZoomableImagePreviewMac+Regions (`commitRegionMove`, `deleteSelectedRegions`, `combineSelectedRegions`) |
| `SegmentEditingMode` (+ `SegmentEditAction`, `SegmentDeleteKeyAction`, same file) | Views/Preview/ImageViewer/Regions/SegmentEditingMode.swift | WindowState, RegionInteractionLayer, ZoomableImagePreviewMac, ZoomableImagePreviewMac+Regions |
| `SegmentEditCommand` (`plan`, `mergePlan`, `Update`, `Merge`, refusals) | Models/SegmentEditCommand.swift | **uncalled** — the only other mention is a doc comment in ReadingOrderMove.swift:14 |
| `SegmentSelection` | Models/SegmentSelection.swift | **uncalled, CONFIRMED** — referenced only by SegmentEditCommand (itself uncalled). `SegmentSelection.shared` is declared (:30) and never read or written anywhere else in the app, so nothing writes a selection into it |
| `PageExportRunner` / `PageImportRunner` | App/Menus/*.swift | ReaderExportMenuItems (ReaderExportCommands.swift:110–131), which FileMenuCommands.swift:192 and ReadingPaneView.swift:529 mount; `PageImportRunner.Outcome/Result` also in DocumentService+PageIO |
| `DocumentService.exportPage/importPage` (extension) | Services/DocumentService+PageIO.swift | PageExportRunner, PageImportRunner |


## GAPS: what the maintainer would do in the app (grouped into the issues above)

Ordered roughly by how much of the programme each unblocks.

1. **Imported pages (cross-cutting; not a spec row of its own; read from code, not run): select or edit a box on a page whose pass came from Import Page From…** Today such boxes draw but a click selects nothing: `RegionInteractionLayer` requires an artifact id, and imported passes have none. This also blocks the Inspector's segment level, reading display, move/delete/combine and delete-undo on those pages.
2. source.pass.named-authored: **show, hide and compare passes** on a page, including imported ones. Only artifact passes can be chosen, indirectly through the Artifacts inspector.
3. source.pass.working: **choose the working pass** and see which one it is. `pass.choose_working` has no typed route, and the overlay ranks passes by its own rule.
4. source.reading.set / source.textedit.typing-is-a-new-reading: **type a correction** in the Reader, which records a new reading. There is no reading write path in the app.
5. source.reading.chosen-is-worked-out: **choose the reading that counts** from the Inspector's Text list (`POST …/readings/choice` is uncalled).
6. source.reading.chosen-follows-project-rule: **set the project to strict or relaxed** (no setting found; unsure one exists).
7. source.reading.written-read-pair: **join two readings as written/read** (sic/corr). The pair is shown, but cannot be made.
8. source.reading.corrections-are-new: **see what a correction corrects**, and make one.
9. source.reading.level-recorded / source.reading.read-from / source.reading.char-confidence-on-line: **see a reading's normalisation level, its source image or reading, and per-character confidence** in the Text section.
10. source.textedit.reader-shows-segments: **edit the Reader's text line by line** (blocks per region and direction), and see line pictures when no Source view is open.
11. source.textedit.return-splits-the-line: **press Return** to split a line.
12. source.textedit.backspace-joins-in-reading-order: **press Backspace** at a line start to join it to the previous line.
13. source.editor.join-group: **merge the selected segments by id** (`SegmentEditCommand.mergePlan`, uncalled), and **group lines into a region / ungroup**.
14. source.editor.set-kind: **set the selection's kind** (text or furniture); `SegmentEditCommand.plan` is uncalled.
15. source.editor.set-direction: **set the selection's direction / reverse a line**.
16. source.editor.set-language-script and source.lang.many-per-page: **set a region's language/script**.
17. source.lang.three-facts / source.lang.says-where-from / source.lang.reading-overrides: **see a segment's or reading's language, script and encoding, and which level each came from**.
18. source.lang.cascade: **set language/script at folder/page/segment level and see the inherited value** (only the document level exists).
19. source.lang.project-declared: **declare a project script**.
20. source.dir.per-segment: **see or set a segment's direction**.
21. source.editor.selection-shared: **select a line in the Reader or the Order list and have it selected in the Source view and Inspector** (`SegmentSelection.shared` has no writer). Source → Reader is absent.
22. source.editor.shapes-in-source-view: **reshape a polygon/baseline** (unsure whether it exists), and edit imported pages (see 1).
23. source.editor.reorder and source.order.named-multiple: **pick between named reading orders, create one, and set an order by clicking segments in turn on the page**. Only as-written is loaded.
24. source.order.next-previous: **step to the next/previous segment in a named order** (neighbours route uncalled).
25. source.segment.flow: **make and follow a flow** across columns or pages.
26. source.segment.versioned-alone: **open a segment's history, compare versions, restore one**.
27. source.segment.picture-by-shape / source.segment.curved-baseline: **see a segment's cut-out, straightened picture**, and see or edit a line's baseline.
28. source.segment.shape-kinds: **draw points, lines and time spans as themselves** rather than as boxes (unsure whether they are drawn today).
29. source.segment.match-record: **review proposed matches** (accept or reject).
30. source.segment.carry-across-a-match: **carry readings and marks across an accepted match**.
31. source.segment.citable: **copy a segment's reference, and open a `fichero:segment/…` link** (no URL handler parses it).
32. source.link.typed / source.link.both-ways / source.form.label-and-answer: **link two segments with a type and see a segment's links** (incl. form label → answer).
33. source.segment.table-cells / source.table.is-a-segment: **see a cell's row and column; draw a table or its cells**.
34. source.hand.record: **create or browse hands**.
35. source.hand.attributed: **attribute a segment to a hand**, and see imported EpiDoc attributions.
36. source.hand.not-provenance: **see in the Inspector who wrote the ink versus who judged it**.
37. source.sign.declared: **declare a sign from a segment**.
38. source.sign.list-authority: **look a sign up by catalogue number**.
39. source.sign.project-list: **browse and export the project sign list**.
40. source.sign.in-readings: **see what a PUA character in a reading means**.
41. source.sign.variants: **mark a variant**.
42. source.sign.gather-instances: **gather every instance of a sign**.
43. source.rights.record: **attach a rights or consent record** to a project, source or segment. Nothing shows the effective rights either.
44. source.format.export-choices: **choose which pass, order and reading kind to export**. Today the engine's defaults are only reported.
45. source.format.first-four: **export hOCR and YOLO from the menu**, and build the menu from `GET /api/formats`.
46. source.format.everywhere: **import and export a page on iOS** (the menu is macOS only).
47. source.geo.iiif-georef-out: **export a georeferencing pass**.
48. source.geo.iiif-georef-in: the library half (#5122). Unsure whether Import Page From… already accepts the file.
49. source.geo.gazetteer-candidates: **see and choose authority or gazetteer candidates** for an entity. Only the authority settings are called.
