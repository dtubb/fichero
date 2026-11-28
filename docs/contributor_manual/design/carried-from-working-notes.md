# Findings Carried From Deleted Working Notes

The tracked working notes under `agent-work/` (reviews, status files, handoffs, old plans and experiment output) were
read against the specs in November 2026 and deleted, all but six that a spec line still reads (the code-organisation
review, the segment editor review, the reading-levels look, the compute-per-engine review, the image-preparation
review and the July 2026 context-menu plan).
Most were already carried by a spec, by a test or by the code.
This page holds what was recorded nowhere else: measurements a choice rests on, constraints on work that is not built,
and directions the notes attribute to the maintainer.

Each item names the spec and the behaviour it belongs beside. Nothing here is a behaviour line: an item becomes one
when the spec's owner writes it into that spec with an issue. Where a note called something a ruling, the item says
who and when as the note recorded it; nothing was checked against the issue tracker. Figures are from the dates
given and from the machines and pages of that day.

## Workflows and presets

### A validated preset names the configuration it was validated on

Beside `workflows.preset-validated` in `specs/ui/workflows.md` (#4501, #4503). Written by an agent as a requirement
after a validation run billed a cloud provider; no ruling.

A preset that calls a model does not fix its provider: a step that names none takes the app's default for its
category, and a step that names a tier takes whatever that tier points at. So "validated" for such a preset is true
only for the configuration it was checked under. When a model-calling preset loses its "(Untested)" label, the record
of that validation names the provider and model it ran on. A label earned on the on-device defaults says nothing
about an install whose defaults point at a cloud provider. Presets that call no model are exempt.

For whoever runs the validation: pinning a tier by environment needs both `FICHERO_<TIER>_PROVIDER` and
`FICHERO_<TIER>_MODEL`, and it only reaches steps that name a tier. A step that names no provider reads the app
database and ignores the environment. Check the resolved provider with
`fichero-server/src/fichero_server/workflows/provider_preview.py` before running anything.

### First measurement of the four-pass ensemble against on-device OCR

Beside `workflows.defaults.ensemble-workflow-validated-end-to-end` in `specs/ui/workflows.md` (#3905; #4497 for the
locale check). That spec's open question on the ensemble says no run has been made; one was.

Measured 2026-08-03 on one verified page of colonial Spanish, in one paid run the maintainer authorised.
Character error rate, accent-blind, lower is better:

| reader | error rate |
|---|---|
| Apple Vision on the whole page | 0.3571 |
| Apple Vision on the same tiles the ensemble is fed | 0.4586 |
| ensemble after its second pass | 0.3971 |
| ensemble after its fourth pass (the text that became the page) | 0.8814 |

The ensemble was at its best after the second pass, where it beat on-device OCR of the same tiles; its third and
fourth passes made its own text about 2.2 times worse. The recognition language made no difference on this page
(0.398 with a Spanish and with an English locale). The note records that the maintainer had said beforehand that
on-device OCR becomes the default if the ensemble loses; Apple Vision was already the default, so nothing changed.
Whether the ensemble should stop at its second pass was left unanswered. The ensemble has been rebuilt since, so
these figures are a baseline, not a measurement of the current preset. Not measured: a harder page, and the
cheap-tier calibration.

## Reading and marking up

### A check that advances should update its mark

Beside `markup.check.cycle` in `specs/ui/reading-markup-annotations.md`. No issue cited.

Each advance of a check (one tick, two, three) deletes the rating annotation and creates another, so the mark's id
changes on every click and the audit trail gets two rows per click; the engine already has an update for
annotations. The app finds "the mark already at this place" by comparing rectangles within 1% on the same rendition,
not by an id, so a mark whose region was moved is not found by the next check. Not built: the check cycle using the
update, and finding the existing mark by the segment it targets.

### Margin notes are small text in the margin

Beside `markup.paragraph-anchored-checkmark` in `specs/ui/reading-markup-annotations.md`. The note records this as
the maintainer's ruling of 2026-08-30; no issue was filed.

A note written in a page's margin shows as small text in the margin itself, not as a box or an icon that opens. A
margin note can also be spoken: the audio is transcribed and the transcription becomes the note's text.

### The page-level rows of the Levels section

Beside `source.editor.levels-section-and-working-text` in `specs/source/segment-editor-crud.md` (#6429), which says
only "(and the page level of its path)".

At the page level each row counts the page's segments that have that level (for example "Modernised: 112 of 118
lines"), and the row's Make command runs on the whole page.

### What Preview shows for a generated thing

Beside `kg.entity.load-failure-names-its-reason` in `specs/kg/kg-entity-inspector.md`, which calls this question
open. The note lists it under "Rulings, 2026-08-12" without naming who ruled; the spec line calling it open is later
(2026-09-19), so it needs confirming before it is relied on.

For a selected generated thing (a name, a quote, an event, a timeline row) Preview shows a generated summary whose
parts are clickable and lead to the page and passage each came from. The summary is itself generated and carries the
same mark as any machine-made value; it never reads as source.

### Why the Reader's graph shows no verbs

Beside `kg.graph.neighbourhood` in `specs/kg/kg-entities-and-statements.md` (#5551, #4605).

The graph draws a statement's verb on its edge only when the edge is longer than 72 points and its weight is 2 or
more (`fichero/fichero/Views/Library/ViewModes/Graph/Ontology/ForceDirectedGraphView+Render.swift`). In one
document's graph nearly every statement edge has weight 1, so no verb is drawn. That guard, with the earlier change
from the web renderer to the native co-occurrence graph (#3503), is why the "subject, verb, object" view went
missing; the reorganisation commits the issue blames were file moves. Smallest fix: drop the weight condition and
relax the length one. Test to write: a weight-1 statement edge draws its verb.

## Search

### Two constraints on searching every library at once

Beside `search.all-libraries-fanout` in `specs/ui/search.md` (#4110). From the search review of 2026-07-25.

1. Scores from different libraries cannot be merged as they are. Each library has its own full-text index with its
   own corpus statistics, and rank fusion is computed inside one library, so a plain merge favours the smallest
   library. The scores are put on one scale before merging.
2. Permission is checked for each library the search reaches (the allowed-path check and the sandbox grant for that
   package), not once for the request. The app needs one search coordinator over the open libraries, because each
   search service is bound to one library's client.

### The DuckDB Lance extension as the search read path

Beside the `(#4175)` line under "Future" in `specs/source/source-model.md`.

A read-path spike ran on 2026-08-19. On DuckDB 1.5.5 the `lance` extension loads and gives `lance_vector_search`,
`lance_fts` and `lance_hybrid_search` as SQL table functions. On a scratch library of 382 passage vectors (1,024
numbers each): vector search joined to `documents` took 786 ms cold; full text 57 ms; hybrid with the join 660 ms
cold and 17 ms warm. Document id, page id, character offsets and document dates came back in the one statement.

The plan records the maintainer's direction of the same day: the extension binary is bundled in the engine and never
fetched with `INSTALL` at run time; the Python `lancedb` client stays for writes at first and only the read path
moves.

Conditions before any cutover, none of them met:

- The extension is locked to one DuckDB version and to one platform, so `duckdb` and `lancedb` are pinned exactly
  first.
- It is loaded by absolute path from inside the app bundle. `allow_unsigned_extensions` is never set in a sandboxed
  build, so a signed binary matching the bundled DuckDB version is required.
- The load is proved inside the sandboxed embedded engine before any rewrite lands.
- The new path sits behind a flag with the Python path as the other branch until a golden set shows the same or
  better ranking.
- Index build cost, and reading while the writer appends, are measured at scale.
- The extension binary carries the Lance core, so the bundle saving is measured, not assumed.

This does nothing for ranking quality.

## Libraries, sync and sharing

### Managed mode comes before sync, and sync is never the database file

Beside the `(#4463)` Future line in `specs/source/synced-folder.md`. The note calls this the maintainer's stated
prior (2026-08-02); it is not a ruling.

Managed mode, where Fichero owns the file layout inside a cloud-drive folder, is built first and stands alone: it is
useful with one device and keeps the model of one engine as the only writer. Syncing between devices through that
folder is a second consistency model (two devices both writing offline, no authority present), not another
transport. If it is built, what syncs is an append-only log of intents that each device replays; the database file
is never synced, because two devices syncing one database file through a cloud drive corrupt it. No sync code is
written before a design pass answers the issue's open questions.

### No new library over a remote connection

Beside `sharing.guest-addresses-the-hosts-library` in `specs/transport/library-sharing.md`. The note attributes it
to the maintainer as a constraint; undated (July 2026), no issue cited.

Creating a library is unavailable whenever the connection is to a remote engine, which includes iPhone and iPad. A
save panel picks a path on the client's disk and a remote engine cannot see it. The command is disabled and says
why; the request is never sent. No spec states this and no guard in the create path was found; the rule exists as an
aside in a comment in `fichero/fichero/Services/EngineLifecycleController+ProviderKeys.swift`.

## Panes and accessibility

### How a pane claims focus

Beside `source.panes.every-pane-claims-focus-on-click` in `specs/source/panes.md` (#6476; history in #3686, #550,
#560). A finding from commit history; no ruling.

Only the sidebar is bound to the focus state with `.focusable()` and `.focused()`. It pays for that on purpose:
without it the arrow keys stopped moving the list. The other panes track focus with a click handler and a drawn
indicator, because making a whole pane focusable swallows the person's first click. The same binding was once
applied to the content pane and removed after it crashed the app on launch (commit `7c27e9fe2d`). So the step that
makes the Reader, the Source and the Inspector claim focus does not copy the sidebar's binding onto them.
`.focusSection()` was untried at the time and is the first thing to try; it needs a build and a launch test.

### Accessibility conventions

The specs hold one-line gaps for VoiceOver and the system accessibility settings (`shell.accessibility-labels`,
`shell.system-accessibility-settings` and `shell.dynamic-type` in `specs/ui/panes-workspaces.md`;
`reader.voiceover-paragraphs` and `reader.voiceover-paragraph-to-note` in `specs/ui/reader-view.md`;
`commands.pane-focus-navigation` in `specs/ui/menus-and-commands.md`). The design note of 2026-07-13 held the
conventions to build them to. Two points are marked as the maintainer's dispositions of that date; the rest are the
note's conventions.

Labels (#3691):

- A label says what the control does ("Delete annotation"), never what it looks like and never the symbol name.
- A control built with a titled `Label` needs no `accessibilityLabel`; add one only to icon-only controls.
- State goes in traits (selected, expanded, disabled), not in the label text, or VoiceOver says it twice.
- Anything with a current setting (a font-size stepper, zoom, a page number) carries an `accessibilityValue`.
- Hints are the exception: only for a gesture that is not obvious.
- Decorative drawing is hidden from accessibility.
- A composite row (thumbnail, title, date, badge, chevron) is one combined element with one label and its traits.
- Colour is never the only cue: a status dot has a label and, under Differentiate Without Colour, a different shape
  or glyph. A thumbnail's label names the document, not "image".
- Custom-drawn views (canvas, page view, annotatable text, loupe) expose the model they draw through
  `accessibilityRepresentation` or accessibility children, not a hand-built parallel tree.
- Accessibility identifiers are a UI-test hook; identifier coverage is not accessibility coverage (maintainer's
  disposition, 2026-07-13).

Reader paragraphs (#3692, #3693): for Reader content shown in a web view, paragraph and heading navigation comes
from the HTML: real paragraph elements, heading levels and landmark roles in the engine template and in any HTML
built in Swift. VoiceOver's own web rotor then works. A SwiftUI `accessibilityRotor` cannot see inside a web view,
which the wording "a custom rotor" in `reader.voiceover-paragraphs` does not allow for. Capturing the paragraph
being read into a note needs each paragraph to carry a stable id from the engine template, so #3692 is built before
#3693.

System settings (#3695):

- Reduce Motion replaces a transition with a plain fade; it does not remove it.
- Contrast and reduced motion in the Reader's web content go through the existing theme-injection path
  (`prefers-contrast`, `prefers-reduced-motion`), not a new mechanism.
- Reduce Transparency and Increase Contrast on the app's own material backgrounds belong to the same behaviour
  (maintainer's disposition, 2026-07-13).

Dynamic Type (#3694): the work is to survive large text, not to adopt it. Judge each fixed-size font one by one:
display, weighted, serif, monospaced and deliberately conditional sizes can be intended; body prose at a fixed size
is the fault. Most of the work is layout: fixed-height rows, fixed heights on text containers and one-line
truncation. Test the Reader and editor font scale at 2.0 together with the largest accessibility text size.

Verification: VoiceOver correctness is not unit-testable. Unit tests cover the logic only: a row's composed label
uses the right model fields, a status maps to the right words, the Reduce Motion branch returns a fade. Reading
order, rotor navigation and layout at the largest text size are checked by hand on the built app, and each
accessibility issue names that manual check in its acceptance. A label existing in the source is not evidence that
a surface is accessible.

Keyboard reach (#3686): custom-drawn surfaces are unreachable by keyboard by construction, not merely mis-ordered,
so keyboard navigation and the `accessibilityRepresentation` work for those surfaces are sequenced together.

## Compute

All from one time-boxed bench of 2026-10-27 (`fichero-server/scripts/compute_bench.py`, Kraken 7.1.1) and the
compute-per-engine review of the same day. They belong in the section "Proposed for the maintainer (compute per
engine, 2026-10-27)" of `specs/ui/activity-pane.md` unless another spec is named.

### The line finder's network is faster on the GPU, and the engine does not use it

Beside `activity.lane.mlx-one-model-batched-on-the-gpu` (#5931). This contradicts "GPU measured no faster"
(2026-10-01) in `specs/ai/local-runtimes.md`.

On a 16 GB M1 under load, `blla.segment(..., device="mps")` was 28% faster a page (22.1 to 15.9 s, 22.4 to 17.2 s)
with the same lines found. The engine passes no `device` to `blla.segment`, so segmentation is CPU-only. On the same
Mac a third page ran out of GPU memory, so it needs a memory check. The review proposed, as its decision 10, a
bounded trial (two pages at once, the memory guard on, footprint sampled over 50 pages) before any default changes;
not ruled.

### Downscaling a page before the line finder gains nothing

Shrinking a page to 1800 px high before segmenting changed neither the time (22.1 to 24.8 s, 22.4 to 20.0 s) nor the
lines found. The line finder already resizes every page to its network's 1800 px height and does its vector and
polygon work at that scale.

### Where a segmentation page spends its time

Beside `activity.lane.pages-at-once-sized-from-the-machine`.

Profile of one page on one torch thread: network forward 45%, the vectorizer 33% (one ridge filter alone about a
quarter of the page), the polygonizer 18%. Everything after the forward is single-threaded, so going from 1 to 4
torch threads gave 7% more pages a minute for 21% more CPU; pages at once is the only lever.

On an 8 GB M1 with 4 performance cores: segmenting, two pages at once on one thread each was 1.57 times one page
(7.2 against 4.6 pages a minute); four at once was no better (4.9) and swapped. Reading, two pages at once was 1.19
times for 57% more CPU a page.

### A page's memory follows its pixels

Beside the same line, and `source.read.pages-at-once-scales` in `specs/source/models-chains-and-projects.md`, which
budgets a flat 1.5 GB a page.

Peak memory of the line finder is set by the largest page, not by how many run at once: one page of about 34
megapixels took a single-thread process to 7.3 GB on a 16 GB Mac, against about 3 GB for pages a third that size.
The per-page memory budget has to come from the page's size.

### The prior for a Mac with no fit depends on its cores

Beside `activity.lane.fit-learned-from-runs` (#5931). The spec fixes the line finder's prior at two pages on one
thread each; the review proposed this instead as its decision 8, not ruled.

Until a fit exists the line finder's prior is N = min(4, max(1, performance cores ÷ 2)) pages at once on one thread
each; the reader's is one page on all the performance cores; both capped by memory (one page on an 8 GB Mac). A
many-core Mac starts at four and learns upward, never N = cores. The first run replaces the prior.

### The embedder: one session, threads inside it

Beside `activity.lane.embedder-forks-before-threads`.

On an M1, with the app's embedding model and batches of 16 lines: one session at 4 intra-op threads was 2.8 times
one thread (67 against 24 batches a minute); two concurrent calls on 2 threads each was slower (51).

### Bulk insert a page, never row upserts

Beside `activity.lane.writer-batched-per-page` (#6236, #6212).

On a scratch DuckDB file, with a page as 35 lines and 20 names: per-row `INSERT … ON CONFLICT` cost 28 to 33 ms a
page (autocommit, one transaction a page, or `executemany` alike); one DataFrame insert a page cost 1.8 ms and
`append` 2.7 ms. To measure again: 1000 single saves against one batched save of 1000 rows on a scratch library.

### spaCy batching does not clear its bar

Beside `runtime.spacy.batched-and-off-the-loop` in `specs/ai/local-runtimes.md` (#5956), whose result is still
"none yet".

First result, on an M1 with 4 performance cores, the small Spanish pipeline and 320 page-sized texts (not the
machine the line asks for): `nlp.pipe(batch_size=50)` 3633 documents a minute against 3152 for one call a page, 1.15
times, under the 1.5 bar. spaCy's own `n_process` was slower than one thread at 2 and at 4 processes (3144, 2548).

## Apple's on-device models

### The document reader's cold start is not paid once

Beside `runtime.apple.bridge-resident` and `runtime.apple.document-reader` in `specs/ai/local-runtimes.md` (#5370,
#854, #4948). The first of those lines says the cold start is warmed at launch through `--warm-documents` and "is
paid once"; these measurements say otherwise.

Measured 2026-09-04 on six pages: the first call on a cold Mac took 146 to 168 s on a real page and 45 s on a blank
one; warm calls took 0.3 to 2 s. The cost came back after the Mac sat idle (168 s, then 0.7 s, then 45 s some hours
later). It does not depend on image size. A warm-up in a separate short-lived process did not spare the next
process: the warm-up paid 45.5 s, the next page paid 51.3 s, and the call after that 0.6 s. A warm-up from an
in-memory image returned success in 0.4 s and warmed nothing; only a warm-up through a file takes the path
recognition uses. What the cost keys on is not known.

So the first call's timeout absorbs about 170 s, `elapsed_ms` is in every answer so a cold start can be told from a
fault, and `--warm-documents` as a separate process does not help. Whether a resident bridge's own first call warms
what follows, and for how long, is unmeasured; the test is, on a cold Mac, page A, then page B at another size, then
page A.

The reader's answers are also not stable run to run: the same page returned 973 words cold and 964 warm. A word
count kept with a reading is a fact about that run only.

The bridge contract for `--recognize-documents` (built in `fichero-server/bin/fm-bridge/FmBridge.swift`, stated in
no spec): coordinates leave the bridge as fractions of the image, origin top left; the answer names the pixel size
of the image it read, because a page has more than one rendition; failure kinds are the bridge's existing ones; a
failed page never answers with an empty list; the image path is between the engine and the bridge only and never
appears in an API request.

### Private Cloud Compute and the executor seam are macOS 27 APIs

Beside the Apple row of "The places" in `specs/ai/where-models-run.md`. Read from the SDK interface on 2026-09-04;
no issue, no ruling.

Apple's Private Cloud Compute language model is available from macOS 27 only, while the app targets macOS 26. It
conforms to the model protocol the existing bridge's session accepts, so the bridge can host it without a second
bridge. It has no per-call price but is not unlimited: it reports quota use and can refuse when the quota is
reached. If offered, it needs an availability gate with a "not available on this system" state on macOS 26, and a
quota refusal surfaces as a typed error and never falls through to a paid cloud model.

"MLX in the Foundation Models API" is a bring-your-own-executor seam, not MLX in the system. The SDK ships no MLX
framework and Foundation Models loads no community weights; its adapter type is a fine-tune on the system model.
What exists is a pair of protocols (a language model and its executor) that let a third-party model back a
Foundation Models session, both macOS 27 only. The executor is handed the output schema and tool definitions and
must honour them itself, so constrained decoding is the executor's work; a model's capabilities are self-declared
and checked by nobody. The note's recommendation: do not move the MLX path onto this while the deployment target is
macOS 26.

### Preprocessing ahead of Apple Vision is page-dependent

Beside `image.enhance.contrast-clahe` in `specs/source/image-enhancement.md`.

Measured 2026-09-02 on six test pages, as the share of text ink inside a word box. Local contrast raised a
faint-pencil page from 0.75 to 0.85 and lowered a dense printed page from 0.26 to 0.22. Adaptive binarisation raised
a clean printed page from 0.80 to 0.86 and lowered the dense printed page from 0.26 to 0.10 and a cursive page from
0.90 to 0.81. Contrast stretch moved nothing by more than 0.02 except the dense printed page (0.26 to 0.16). The
shipped detection pass rests on the conclusion: a contrast or binarise step is not a hidden default ahead of Vision;
it belongs in a retry on a region that already failed, or in a step the person chose. Giving Vision the page's known
vocabulary changes the text it picks and its confidence and changes no box; a line Vision does not detect stays
undetected.

### Detection variants measured and rejected

Beside `source.read.vision-locale` in `specs/source/models-chains-and-projects.md`.

Measured 2026-09-03 on six test pages, same metric, against the shipped ladder (page pass, band escalation,
ink-residue pass, older-revision second detector):

- The fast recognition level finds dense small print but drops handwriting (0.14 to 0.43 against 0.44 to 0.70) and
  is the only variant that put boxes on blank paper.
- Upscaling the whole page 2× is no better and on two pages much worse (0.13 against 0.54; 0.42 against 0.61).
- Re-reading every detected line on a 2× to 4× crop gains only on dense print (0.54 to 0.63), loses on cursive
  pages, and costs 1 to 47 s a page; the second detector gains more on the same page (0.54 to 0.77) for about 0.2 s.
- Fixed strips (3, 6, 10) never beat the shipped ladder, and denser is worse: a strip edge through a row of numerals
  destroys the line.
- The language list, the minimum text height and recognition revision 2 change no box.

The rule the two shipped gains share: a second pass may only add boxes where the page has not been read; a pass
that replaced the first pass's boxes lost every time. Not run: deskew and illumination flattening ahead of
detection, and a multi-scale union with overlap suppression.

Laying known text over Vision's boxes on the same pages: mean overlap with hidden true boxes was about 0.8, falling
by 0.05 to 0.13 with half the boxes hidden and a third of the characters wrong; about 15% of words get no box on a
typical page because a line with no partner emits none.
