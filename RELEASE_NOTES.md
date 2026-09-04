# Release Notes

*Full commit-level history, day by day, lives in [`CHANGELOG.md`](CHANGELOG.md).*

## 2026.09.04.2

The same-day follow-up that makes updating real.

- **Fixed: the updater can install.** Build 1 and this morning's build
  downloaded updates and then failed with "an error occurred while
  launching the installer" — the sandboxed app was missing the entitlement
  that lets it talk to its own installer. **Installs of earlier builds
  need this one manual download; updates are automatic from here on.**
- **The public build is now the Public Alpha.** Fichero.dmg turns on the
  full proven feature set — including the Settings Models and Backend
  tabs — while experimental surfaces stay in the Dev build. When alpha
  features prove out they graduate to beta.
- **Updates check, download, and install automatically by default**, and
  Settings ▸ General ▸ Software Update is where to see or change that.

## 2026.09.04

An overnight fix release built from one evening of live testing — nearly
fifty root-caused fixes.

**Two downloads, from this release on.** **Fichero.dmg is the Public
Alpha** — the recommended build: every feature that has proven itself
(reading, search, markup, workflows, local and cloud AI models, the full
Settings surface). **Fichero-dev.dmg is the Dev build** — the kitchen sink:
all experimental surfaces on (chat, agents, spatial canvas, unfinished
tools), sharp edges included. When alpha features prove out they graduate
to beta; until then, Alpha is the public face. Both builds update
themselves on their own channel.

**Search finds, and shows you why:**
- Fixed: Clicking a search result now opens the reader ON the matched
  passage, highlighted — and the reader stays on the result instead of
  snapping back to the containing folder's first page.
- Fixed: Result badges say what really matched (entity, claim, text) —
  "graph" only appears when the knowledge-graph leg actually ran.
- Fixed: The search scope chip names the library you are actually in.
- New: Search options are also on the toolbar's magnifying glass.

**Markup follows your hand:**
- Fixed: Marquee, word-select, and annotate land exactly under the
  pointer — the drift that grew toward the corner was a hidden scale
  error between the scroll view and its clip view.
- Fixed: Regions you drew and saved can no longer be buried by a later
  machine pass — human-curated geometry now outranks every machine run.
- Fixed: Annotations remember which image variant they were drawn on.
- Fixed: The inspector's edit-steps list shows the steps (two separate
  editor models could not see each other's work).
- New: Original ↔ edited flips with the same up/down swipe as any
  rendition, and edited pages open showing their edited face.
- Fixed: Thumbnails refresh immediately after an edit.

**PDFs behave like documents:**
- Fixed: Image editing on a PDF page works at all (every edit used to
  fail with "source file not available").
- Fixed: Text boxes on PDF pages are no longer sideways — and no longer
  one page's boxes painted over every page.
- Fixed: A big PDF import shows real per-page progress ("pages", counted
  as pages) instead of sitting at 0% — and an import that cannot read
  its source says so loudly instead of hanging silently.

**Workflows that work:**
- Changed: Catalogue is now literally the chain of its six numbered
  stages — and stage 3 finally writes date claims, so timelines fill.
- Fixed: Translation works — four independent causes down, including a
  crash that killed every "Translate the Reviewed Transcription" run.
- Changed: One Extract family — Extract Data folded in, Extract Table
  and Extract Geo moved home.
- Fixed: Recombine Segments saves its result into the library instead of
  a temp folder the cleaner sweeps.
- Fixed: A step that uses no model no longer claims one in the workflow
  bar's sentence.
- New: The artifact picker names each artifact by its model and time,
  and any artifact row offers "Run Workflow on This".
- Fixed: Table extraction can answer "no table" — it no longer invents a
  table out of the ruler lying in the scan margin.
- New: Clean Up Text has a real programmatic mode — dehyphenation,
  paragraph reflow, page-header stripping — no AI required.

**Local AI, actually local:**
- Fixed: On-device OCR models work — vision models were being served by
  a text-only server that rejected every image.
- New: Whisper audio transcription runs in the managed MLX runtime; the
  download buttons that could never work now work (or say why not).
- Fixed: Downloaded models appear in the model pickers.
- Fixed: The model picker no longer shows an eternal "Loading models…" —
  loading, failed, and empty are three different, honest states.
- New: The model catalog states each model's real size, memory floor,
  and whether it has been verified on this app's own tasks.

**Honest accounting:**
- New: Every run records what it actually spent — provider-reported
  tokens, priced per model — shown beside its duration in Activity.
  On-device runs say "Free"; unknown models say "Unpriced", never $0.00.
- New: Export what you are reading as Markdown or Word, from the File
  menu or the reader itself.
- Fixed: Whole-library exports no longer silently drop entities and
  claims that have no source document.
- New: DeepL is configured in Settings → Providers like every other
  provider (the env variable remains as a fallback).
- Fixed: The About box's license link says AGPL-3.0, like the license.
- New: Help → Fichero User Manual.

## 2026.09.03

**First public build.** Versioning starts fresh: the version is the date,
the build is a plain counter — this is 2026.09.03 (1).

**Reading and markup:**
- New: The Select tool is on from the first click — click, ⇧-click, or drag
  a band to select regions; drag a selected region to move it; double-click
  a drawn selection to name and save it.
- Bug: Regions you draw no longer vanish after saving.
- Bug: Selecting regions in the artifacts browser now highlights them on
  the page.
- New: ▲▼ rendition stepping sits by the breadcrumb; swipe up/down still
  flips renditions.
- Bug: Word-box labels never truncate with "…" — they fit their box.
- New: Show/hide word boxes per pane, so a split can compare marked and
  clean views of the same page.
- Loupe: parks where you leave it; ⌥-move or ⌥-click moves it; scroll over
  it zooms it.

**Library:**
- Bug: ⌘A selects all in every view mode, including lists.
- Bug: List scrolling is smooth in both directions; clicking a row no
  longer stalls or jumps the view.
- New: Choose what rows show (status, date, and 2/4/6 lines of text) from
  the metadata menu. Your metadata choices reset once with this build (the
  new defaults apply); set them again from the same menu.

**Search:**
- Bug: Searching again actually refreshes the results.
- New: Result rows show the matched text with your terms highlighted;
  swiping left/right in results steps through the results themselves.
- New: Search scope reads as the breadcrumb — whole library or the folder
  you're in.

**Workflows and AI:**
- Bug: A generative step never lands on Apple Vision by mistake.
- New: When comparing models, a failed model says why — the others keep
  going.
- New: Workspaces restore what was open, including the markup and workflow
  bars, with icons in the menu.

**Image editing:**
- Bug: Background-removed images show a white ground everywhere —
  thumbnails included — instead of black.
- Bug: Thumbnails refresh immediately after edits like rotate.
- New: Edit steps can be re-opened and adjusted in place, Lightroom-style;
  Copy Edits / Paste Edits applies one image's recipe to others.

## 2026.08.27

**Sharing, CLI, and MCP:**
- New: The Sharing toggle now serves the `fichero` command-line tool and MCP
  clients from the running app — no separate engine to start. The toggle's
  description names all three.
- Bug: Turning Sharing on no longer shows "HTTP 400: Unexpected response";
  the pairing QR appears reliably.
- Bug: Sharing to another device on your network (the QR's `.local` address)
  now actually listens on the network — pairing from iPhone/iPad reaches the
  Mac instead of "Could not connect to the server."

**Stability:**
- Bug: A crash in the stall diagnostics (debug tooling) at first stall is
  fixed.
- Bug: Rendition downloads no longer fail with a server error in the
  sandboxed app.

**Library:**
- Bug: Names with numbers sort naturally — "page2" before "page10" — in the
  library, bookmarks, and exports.

**iPhone and iPad:**
- This build restores iPhone/iPad TestFlight (three build errors fixed) and
  adds left/right stepping within a multi-item selection.

## 2026.08.26

**Library:**
- Bug: For New Libraries the save dialog remembers your last folder.
- Bug: Creating a library in a synced location (iCloud Drive, Dropbox, Google Drive, Box)
  warns first — a live database that is being synced is a bad idea.
- Bug: Open Recent in File Menu works: closed libraries stay in the menu.
- Bug: Ghost  "Untitled" entries and duplicate rows in the sidebar are gone.
- Bug: a brand-new library can run workflows immediately — no relaunch.

**Workflows:**
- Bug: Run Workflow runs on what you selected: the long-standing bug where a
  run landed on the parent folder instead of the selected page is fixed.
- the toolbar picker now resolves its scope at the moment it opens.
- Bug: Multi-select reading: select several pages and the reader shows exactly
  those pages in the real WebKit transcript — with the pane's header,
  lens switcher and breadcrumbs intact. Mixed selections get a clean
  archival-order list.
- Bug: Split on a page works: parts are attached as child nodes with regions
  (they used to be cut, written, and silently lost).
- Bug: Transcriptions don't get the script classification at the beginning any more.
  The "[Script: …]" classification line the paleography prompts request is stored as 
  metadata, not in the content.
- Honest boxes (bbox step 4): a maintenance pass marks renditions whose
  pixels can't be matched to a recorded frame, and overlays render
  unanchored on them.
- Under the hood: the engine no longer opens duplicate connections for
  one library reached by two path spellings; library context menus gain
  New Folder / Import Files; a 12-second launch stall moved off the main
  thread; live model catalogs stay per-provider live.

## 2026.08.22

**Bounding-boxes**
- A page's alternative pixels — archival original,
contrast-enhanced, background-removed — are now first-class renditions:
imported from staging sidecars, produced by the image workflows
themselves, listed and served by the engine, and flipped in the preview
with a vertical swipe (↑/↓ keys and chevrons too). Splits made in the
app, by a workflow, or in staging all record one identical geometry, so
"undo the split" is one mechanism and a box drawn on a part means the
same thing everywhere.

**Renditions:**
- To Test: Flip a spread between original / enhanced / split with word boxes showing, and the boxes stay on the words — has NOT yet been run. Everything below is verified in isolation; that flip is the acceptance test for this program and needs a live session.
- Renditions: engine list + content routes; preview flip via vertical
  swipe/↑↓/chevrons with a slide transition; indicator names the
  rendition and marks cropped/deskewed frames.
- Image workflows persist what they make: enhance, fuzzy-clean,
  prepare, rotate, remove-background write renditions (never primary,
  provenance-stamped); split/segment create child nodes with real
  regions; a part that fails to store reaches the caller — no more
  green ticks on runs that changed nothing.
- One geometry: in-app crop/split/segment write region_in_parent with
  measured confidence, converged with staged sidecars.
- Preview: boxes exact at first fit and at zoom-out; boxes survive page
  steps; tall pages fit both axes; page steps land with the image
  ready; entry highlight is a soft wash behind the words; page arrows
  on images match PDFs; fitted images no longer bounce under
  two-finger swipes; pinch snaps to fit.

**Canvas**
- Canvas: ⌘-scroll and pinch zoom into the cursor; double-click zooms
  a card to full view and back (context menu too); ⇧⌥ rubber-band in
  3D; drag stays in the board plane with z behind ⌥; render cap
  10,000; halved edge margins; empirical scroll-sign fixes.

**Libraries**
- Bug: Access: libraries survive relaunch (pre-auth grant race fixed);
  link-mode imports ask to persist folder access; a failed original
  prompts for its folder right in the preview; File ▸ Grant Folder
  Access… for manual grants.
- Artifacts: drag to Finder/apps exports text or .txt; drop on a
  folder/library promotes to a provenance-stamped node; inspector rows
  select on the name click.
- Workflows: force-image-processing genuinely re-runs past the
  skip-if-done cache; transcription geometry survives page steps.

## 2026.08.20

### Dev build

- The speed build: a night of profiling the live library corpus (4,169
documents) and removing whole-collection costs the logs surfaced,
plus the day's live-testing fixes.

- **Browsing stays fast while the engine works.** Folder listings read the
last-committed snapshot instead of queueing behind an import's embedding
transactions (worst case measured: 12 seconds); each row hydrates once,
without its full page text, through a memoized field plan; vector writes
no longer block database reads; and a new index backs every parent-folder
lookup. Listing routes run off the event loop, so concurrent requests
stop serializing.

- **Thumbnails land as they're made.** The derivative queue renders a
folder's thumbnails before starting its slower text embeddings, announces
each image the moment it exists, and reports its progress in the toolbar
island ("Processing imported pages — 42%") instead of claiming Ready.
Quitting mid-import is safe: interrupted work resumes on the next launch.
The thumbnail endpoint serves interactive requests instantly and sheds
import-storm misses to the queue (previously: 15,565 calls averaging
784ms, worst 60 seconds).

- **One request where there were a thousand.** The change-stream patch
flush, workflow-completion refresh, and search resolution now fetch
documents in one batched call each; a live session had issued 1,001
sequential single-document requests.

- **Search results are nodes.** Every hit — document, person, place, claim,
artifact — resolves into the library grid as a clickable node that
preview, reader, inspector, workflows, and Select All all agree on. The
reader follows result clicks and scrolls to the page; clicking a page in
the reader selects its result row.

- **Canvas input works like it should.** Two-finger scroll pans both
canvases (the old overlay never received scroll events), arrow
keys nudge the camera, ⌘A selects every node, and page thumbnails load
from the library you're in — a wrong-library lookup had silently failed
all 1,500 texture loads in a session. The render cap rises to 1,500.

- **The reader scrolls like Safari.** Off-screen pages skip layout and
paint entirely, page positions are measured once instead of per scroll
frame, and hidden panels (graph, timeline, map) render only when opened —
crossing a page boundary used to re-run a force-directed graph layout for
a panel that wasn't visible.

- **Corrections from live testing.** Default workflows appear in every
library again (a legacy flag heal); grouped items stack in place instead
of vanishing to the library root; deleting a corpus can no longer be
raced by its own background embeds resurrecting pages; a stale bookmark
that resolves into the Trash is dropped rather than followed (a library
reference had silently moved to iCloud's Trash); the preview background
follows dark mode; dataset views remember sort and text depth; dataset
cards and sheet rows gain Run Workflow and exclusion menus.

## 2026.08.17

**Drop a corpus, get a corpus.** Dragging a staged folder with a
`manifest.jsonl` into a library imports everything it describes — pages,
transcripts as each page's text, deduped entities, renditions — with real
progress counts, thumbnails, and the corpus landing under the folder you
dropped it on. Re-dropping an already-imported corpus repairs it instead
of silently doing nothing. All 29 Marshall diaries are staged and ready.

**Sidecars carry their own facts.** A `x.jpg.transcript.txt` beside an
image becomes its text on any plain folder drop; an `.iffy.json` stating
`original_date` dates the document on arrival — no Extract Dates run
needed for corpora that already know their dates.

**One selection, four views.** Clicking a row in the Sheet (né Grid), a
day in the Calendar, an entry in the Timeline or Cards routes preview to
the source page with its bounding box, reader to the text, and the
inspector to the entry itself — not its parent. Arrow keys walk the
chronology; ⇧ extends; the status line says "1 of 160 dates selected —
January 14, 1918" instead of counting a list you aren't looking at.

**The calendar is the display.** Day cells grow with the window and carry
the day's words; the below-the-grid list is gone. The Sheet ships Date
first, Text second, Name hidden — with native column show/hide and drag
reordering, and multi-line text on demand.

**Diary extraction honesty.** Entry spans survive line breaks (far more
entries get boxes), printed date headings are stripped structurally for
old and new data alike, and the prompt now forbids moving one day's
writing under another day's heading.

## 2026.08.15

A folder of scanned diary pages now turns into data
you can  read: run Diary Entries on a page and each day becomes its
own node, dated, carrying the text and the exact region of the scan it came
from.

**The Data view modes land.** Grid (a spreadsheet with in-place cell
editing), Cards, Timeline, Calendar, and Map are each a top-level view mode
over whatever the selected folder contains. Clicking the folder shows the
whole folder's data, recursively; clicking a single page scopes to that
page, and selecting an extracted entry shows the dataset it belongs to
instead of a blank pane.

**An entry always points home.** Every extracted row carries its source
reference: selecting a diary entry previews the ORIGINAL page image with
that entry's bounding box highlighted, while the reader shows the entry's
text — where it came from and what it says, side by side. "Show Source
Page" does the same from any renderer's context menu.

**Filters that are facts, not text.** The data views get their own facet
strip: All/Dated/Undated, and a Type facet when a folder mixes document
types. Filters follow you between cards, timeline, and calendar, and a
filtered-to-nothing pane says so and names the way back.

**Entries pop in live.** While a workflow runs over a folder, new entries
and transcripts appear in the data views as they land, instead of waiting
for you to click away and back.

**Workflow runs state their scope before they start.** A right-click run
that reaches beyond the clicked row — a folder's descendants, or a live
multi-selection — now says "Runs on N documents" in the menu itself, and
records why it was that wide. A one-file run stays a one-file run.

**Honesty fixes from live testing.** Finished runs read "Finished," not
"Stopped." Reopened runs keep their console and progress. Text you edited
by hand outranks machine OCR when a workflow re-reads a page. Diary entry
bodies stop repeating the date their title already states. Deleting a
folder names the folder and counts its children first.

## 2026.08.06

### Dev build

A day of live testing turned into a day of fixes. The theme, over and over,
was the app knowing exactly what went wrong and then saying something else.

**Libraries you create now work.** Creating a library outside the app's own
container produced "No Access — Library path is not in an allowed location"
for a folder you had just picked in a save panel. The engine runs sandboxed,
so its idea of your home folder is the app container, and no real location
could ever be served. Fixed at both ends: the grant handoff no longer depends
on a build flag that had stopped tracking whether the process is sandboxed,
and creating a library now mints the access that only opening one used to.

**Imports stop lying about failing.** A 50-page scan took 61 seconds and the
client gave up at 60, so a successful import was reported as "All 1 import(s)
failed" while the document sat in the library with all its pages. Ingest now
gets a deadline that scales with the document. The failure alert also shows
the per-file reasons it had been assembling and discarding, and the progress
label no longer claims to be "preparing" an import it finished a minute ago.

**PDFs get their text back.** The PDF text extractor downloaded a library at
runtime, which macOS quarantines and Gatekeeper then refuses to load — so
PDFs imported as page images with no searchable text, on every machine. It now
ships inside the app, signed with it.

**Transcription keeps the whole page.** Workflows that magnify a page into
strips transcribed every strip and then overwrote each with the next, keeping
only the last. Every piece is now kept and joined in order. The paleography
ensemble's steps also say what they do instead of showing internal ids.

**Errors say why.** A permission failure reports the reason the engine gave
rather than a guess. Startup tells apart "nothing is listening", "the engine
crashed", "another engine has the socket" and "your credentials were
rejected" — four situations with four different remedies that used to share
one message. An API key that cannot be read is no longer reported as absent.
Drag-and-drop outcomes survive in the log where they can be read back, and
the engine log is no longer erased by the restart that follows a crash.

**Windows recover.** Closing the last library left no way to open a window;
File-menu commands now work with no window open. Models & Providers shows the
provider list again after a layout bug collapsed it to nothing.

## 2026.08.02

### Dev build

The overnight build: 122 commits on top of the morning's 2026.07.29
release — the workflow-trust overhaul, the iPhone launch fix, and a
night-long bug sweep. Internal TestFlight + DMG dev prerelease from
green `integration` (1,990 XCTests + 1,927 Swift Testing + 8,500+
Python tests, 0 failures).

### Workflows you can trust

**Every run tells you what it did.** Artifacts now record which run and
step produced them; the artifact browser groups results by run in
pipeline order with "Produced by → View Run" navigation; and a new
Trace tab on every run shows the executed graph — each node colored by
what happened, with the provider and model used, timings, and
per-step outputs one click away.

**Results land where you're looking.** Transcriptions appear in the
content pane the moment a workflow writes them — no reselecting, from
any window, even runs launched from the CLI.

**Honest lifecycle.** Cancel stops multi-file steps within one file;
paused runs can be resumed, cancelled, or deleted; failed runs release
their documents instead of spinning forever; Cancelled shows as
Cancelled; and Pause/Resume/Stop buttons visibly do what they say.

**A node editor that explains itself.** Ports and connection types are
finally visible with distinct parallel edges, fan-out badges reflect
real behavior, execution order is numbered on the canvas, a Tidy
command lays the graph out, drops land under the cursor, and the
palette only offers tools that run. Zoom nodes show a live
tile-grid preview.

**Works out of the box.** A fresh install with no API keys runs every
default workflow on-device; a workflow that needs a missing key says so
before running, naming the provider. Default presets cleaned up
(internal components hidden from Run menus, explicit routing, real
source nodes).

### Fixed

**iPhone launches again.** The iOS TestFlight build crashed instantly at
launch: the shell's fully composed view type overflowed the iPhone's 1MB
main-thread stack during type-metadata instantiation (macOS's 8MB stack
absorbed the identical code). Bounded type-erasures at the compact layout's
chokepoints fix it (#4331).

**Edits can no longer vanish.** A rejected page-content save silently marked
the buffer clean, so the next refresh replaced your edit with stale content.
Saves are now transactional: a failure keeps the buffer dirty, shows an
inline error, and retries — and write conflicts with a running workflow
resolve with retries server-side instead of surfacing as an unexplained
error (#4285, #4286).

**Table sorting can't crash.** Sorting by Name crashed the app when the
persisted sort field had no matching table column; sort state now only emits
column-backed descriptors (#4282).

**Sidebar behaves.** Chevron prefetch restored (#4294), selection survives
tree rebuilds (#4297), drop-hover highlights only the target row instead of
washing the whole subtree (#4229), folders dropped at the library root import
at the root instead of vanishing into Inbox (#4274), and per-row progress
spinners reflect actual running work regardless of selection (#4295).

**Workflows tell the truth.** Single-page runs no longer widen to the whole
PDF (#4298); runs where every file failed record as failed with the real
error instead of a green checkmark (#4283); newly added AI providers appear
in the Run Workflow menu immediately, from any window or device (#4276); and
a connection error in the status island clears itself once the server is
reachable again (#4296).

### New

**iPhone essentials.** Tapping a document on iPhone opens the reader again
(#2666), first-run setup skips the Mac-only steps (#2807), and list rows get
native swipe-to-delete (#2501).

**Recognized-text boxes.** Every OCR/transcription pass now stores the text's
bounding geometry, and the reader gains a Text Boxes overlay showing exactly
where each recognized line sits on the page (#4309).

**Convert to Markdown, HTML, and SVG.** New AI conversion workflows render a
page into portable formats, viewable in place — flip a page between its image
and its generated rendition in the reader (#4329).

**Chat with your library.** The research chat now answers through audited,
read-only library tools with each tool call visible and attributed, and
creating a chat works without an AI provider configured (#2067, #4308).
## 2026.07.29

### Dev build

Internal TestFlight + DMG dev prerelease cut from green `integration` — the
first release gated end-to-end by the new serialized test harness (full unit,
engine, transport-matrix, and UI-session legs all green).

**Fixed**
- Sidebar rows no longer jump after the list loads; root ordering is stable.
- Sidebar clicks are faster: the selection path uses an O(1) index instead of
  re-walking the whole tree, prefetch batches its cache writes, and disclosure
  toggles no longer trigger needless preference writes.
- Folder selection and drops show a loading/importing state immediately
  instead of a dead interval or a false "No Documents".
- Import status can no longer stick at "5/5" after an import finishes.
- Thumbnails: intermittent 500s fixed (alias sync is idempotent and atomic);
  imported images now get thumbnails via a background derivative stage instead
  of staying "Pending"; HEIC photos are supported.
- Legacy .doc files that failed with "Malformed MiniFAT" now extract via a
  fallback reader.
- iCloud placeholder files are refused loudly at import instead of importing
  as empty records.
- Ingest and serving path rules are unified — anything importable is servable.
- Canvas (2D/3D) view modes share the library selection with the list views.
- Engine startup prints a transport diagnostic naming exactly what bound
  where and what a client must set (ends the socket-path guessing game).

**App icon**
- New Icon Composer app icon.

## 2026.07.26

### Dev build

Internal TestFlight + DMG dev prerelease cut from green `integration`.

### New

**Instant launch.** The window mounts real content on the first frame:
saved libraries materialize before the scene graph builds, and nothing
waits for the engine health probe anymore — data streams in as the
engine connects (#4036). Warm first frame dropped from ~1.9s to ~1.4s,
and it shows your library shell instead of a spinner.

**Xcode-style status island.** Engine state, background activity, and
errors now live in one center toolbar island beside the title — a
message area ("Starting engine…", import progress, running workflows,
errors in red) flanked by the engine button (connection details +
Retry) and the activity button (task list). The full-window
"Connecting to backend…" takeover and the login-wall flash at launch
are gone; a broken connection is visible chrome, never a blocked app.

**Finder-grade sidebar.** The full drag grammar landed: insertion-line
drops, Option-drag copies (through the audited `document.duplicate`
deep-copy action), Finder-style aliases (badge, target resolution,
Make Alias), Duplicate parity for workflows, saved searches, and
conversations, multi-item drop feedback, count-aware Delete, and
right-arrow handing keyboard focus from a leaf row to the content
pane. Every library gets its own header row, and the pinned bottom
navigation rows are retired. Document-scoped chat is back on Mac as a
context-menu command on the document ("Add to Chat").

### Fixed

- **100% CPU at idle** — a per-frame UserDefaults write spun the
  AttributeGraph; the app idles at 0% again.
- **Default Workflows tree** — presets seed into the global library
  only, subfolder ids route correctly (no embedded slashes), legacy
  preset folders that lingered at the sidebar's top level re-home
  under the locked "Default Workflows" container on next open, the
  container's read-only lock is enforced on document actions, and
  re-seeding no longer resurrects soft-deleted workflow mirrors.
- **One path, not four** — the location breadcrumb renders only in the
  toolbar; the duplicate in-window path bars are gone and the bottom
  status bar is Finder-style (what's selected, not where it is).
- **Cycle-creating document moves are rejected** by the engine.
- Restored-selection reconcile + launch invalidation storm fixed.

### Under The Hood

The macOS verify leg is genuinely green: a MainActor-isolation crash
that killed the test host mid-run, three stale contracts hidden from
failure greps, and a sub-millisecond Date flake are fixed. New engine
tests cover the Default Workflows tree heal.

## 2026.07.24

### Dev build

Internal TestFlight + DMG dev prerelease cut from green `integration` after
fast-forwarding it into `main` via the new `scripts/merge-integration-to-main.sh`
pre-step. Not promoted to production.

> **Note:** the `v2026.07.23` tag was cut from `main@d141bc139` (the
> 2026.07.22-beta code) before the `integration` lane was merged, so its build
> did **not** contain the workflow sidebar nodes or the chat-tools agent loop.
> `2026.07.24` is the first release that ships that work.

### New

**Workflow nodes in the library sidebar.** Workflows now render as real nodes
under their folders in the library sidebar tree (#4 / #2081) — previously only
the folders showed.

**Read-only chat-tools agent loop.** A read-only agentic chat loop
(`chat_tools.py`) is wired into `/api/chat` behind the `FICHERO_CHAT_TOOLS`
flag (#3 / #1847 / #1848). The model acts as a user issuing audited MCP tools.

### Under The Hood

**Release infra.** `scripts/release-all.sh` now takes `--dev` / `--tier
<release|beta|alpha|dev>` to bake the full dev feature surface (Dev Embedded
mac config + dev `FICHERO_FEATURE_TIER` on iOS), not just stripped release
features. `scripts/merge-integration-to-main.sh` fast-forwards `integration`
into `main` and pushes as the pre-step before a release — so releases no longer
ship without the lane's work.

## 2026.07.23

### Dev build

Internal TestFlight + DMG dev prerelease cut from green `integration`. Not
promoted to production.

### Under The Hood

**Connection hygiene complete.** Every app↔engine call now routes through the
centralized `FicheroClient` transport (UDS / HTTPS-when-sharing / in-memory) —
no remaining hand-rolled `URLSession` bypasses. `EntityService` (the inspector's
"0 entities" bug), `ImageEditingService` preview, the knowledge-graph web pane,
and the workflow diagram were all migrated. The KG web pane works over UDS via a
`WKURLSchemeHandler` bridge (no new network listener), and the workflow diagram
now renders live mermaid (`mermaid.js` in a `WKWebView`) instead of a broken
JSON-as-image.

**Legible failures.** A typed `ConnectionError` classifies transport failures by
`{transport, operation, cause}` so an error names itself instead of a bare
`NSURLErrorDomain -1004`. A wrapped-cancellation fix (`Error.isCancellationError`
across ~60 sites) stops superseded inspector/store loads from mislogging as
failures.

**Fixes.** Sidebar folder-node click (workflow/search/chat folders showed
nothing) now navigates correctly.

**Engine cleanup + speed.** The 61 flat re-export shims left by the package reorg
were removed and 487 callers repointed to the restructured paths; `cryptography`
was deferred off the startup import graph (−50 modules). ModelComparison moved to
an `@Observable` store (#1863). Full engine suite green (7955 passed / 0 failed).

## 2026.07.21-beta

### Dev build

Internal TestFlight + DMG dev prerelease cut from green `main` for Daniel's
testing. Not promoted to production.

### Under The Hood

**Engine hygiene reorg landed on `main`.** The engine's top-level packages were
reorganized into `mcp/`, `security/`, `llm/`, `db/`, `models/`, and `kg/` using
identity-preserving `sys.modules` shims, so every existing import keeps
resolving. Full engine suite green (8048 passed / 0 failed). Route count held at
360 and guardrail allowlists were repointed to the new package paths.

**Transport architecture done.** A pluggable `ClientTransport` seam routes the
app↔engine connection by platform: Unix domain sockets for local Mac, HTTPS
for iOS / remote / sharing / Debug, and in-memory for the Mac Dev/DMG path.
Loopback + UDS/in-memory connections are owner-scoped with no login wall;
`AuthTokenMiddleware` recognizes `http+unix` for bootstrap tokens.

**Crash self-heal.** The embedded engine auto-restarts on an unexpected crash
with a crash-loop guard (max 5 restarts / 60 s, then `.failed`) instead of
needing a manual Retry.

**Test reliability.** Auth middleware now attaches at conftest load, before any
module can start the shared app, fixing the "Cannot add middleware" cascade in
verify-all. `library_discovery.py` (dead home-crawl) was removed; the
recents-registry is the list source.

## 2026.07.20-beta

### New

**Workflow nodes in the sidebar.** Saved workflows now appear in the library
tree. Built-in presets are grouped under a locked **Default Workflows**
hierarchy; duplicate a default to create an editable library copy.

### Improved

**Settings navigation.** The Settings detail pane now has System
Settings-style back and forward controls plus a clearer section header.

### Testing Build

This prerelease uses Fichero's development feature tier, exposing every
implemented app surface and workflow tool for testing.

### Under The Hood

Large SwiftUI files across the app shell, library, sidebar, previews,
Inspector, services, and platform bridges were split into focused extensions
without changing behavior. Source-contract tests were updated to follow the
new file boundaries.

## 2026.07.19.2

### Improved

**RealityKit canvas rendering.** The 2D Canvas and 3D Space views now use the
RealityKit renderers by default. The previous renderers remain available as a
revert path while the new interaction and visual behavior is validated.

**Clearer Settings.** Settings now uses a System Settings-style sidebar with
clearer section names, colored icons, and pairing controls grouped under
Sharing.

### Fixed

- Release builds now reconstruct the embedded Briefcase engine from current
  source every time instead of reusing a potentially stale staged bundle.
- The app, embedded engine bundle, and installed Python package now carry the
  same release version.
- Newest-first activity ordering now handles ISO 8601 timestamps both with and
  without fractional seconds.
- Switching libraries now preserves the app's configured secure network
  session, and Boolean activity metadata displays as `true`/`false` instead of
  `1`/`0`.
- Invalid action payloads now fail safely instead of crashing the app. Legacy
  decomposed library paths normalize correctly, and whitespace-only searches
  remain a local no-op instead of reaching the engine.

### Under The Hood

The Inspector, embedded-engine lifecycle service, chat views, and entity
service were split into smaller concern-focused files without changing their
behavior. The release gate also resolves the shared project Python correctly
when run from a git worktree.

## 2026.07.19

### Improved

**Faster, more reliable local startup.** Fichero now owns the embedded engine at
the app level instead of tying it to a window. Heavy AI, workflow, image, and
network imports are deferred until they are needed; TLS preparation, token
reads, and package creation no longer block the first frame; and a proven local
readiness result is reused without leaking across a host switch.

**Safer imports and library lifecycle.** Path-based imports are confined to
approved roots, Move and Link modes reach the engine intact, route-based ingest
now emits audit and change events, and completed ingest tasks are bounded. When
a library closes in the app it also closes in the engine.

**More dependable workflows, exports, and knowledge data.** Every bundled
workflow preset now passes the execution validator, including the paleography
ensemble workflow. Parent-document exports include page-child transcription,
repeated knowledge claims are stored once with a mention count, and incomplete
task results fail instead of being reported as successful.

### Fixed

- Embedded-engine shutdown now drains live-update streams instead of force
  killing the process after a timeout.
- A broken iPhone or iPad pairing can return to the QR setup screen, and a
  single transient connection blip no longer immediately opens the outage pane.
- Paired remote devices can again load their permitted libraries and live
  update streams.
- Spawned engines no longer inherit environment flags that can disable
  authentication, while app-wide authorization-library requests no longer
  carry an unrelated library header.
- Cancelled thumbnail requests are no longer logged as image failures.

### Under The Hood

The dormant Swift test target was restored and expanded, and the frontend
source tree was reorganized by app surface without changing behavior. The
release gate now covers the real macOS test plan and the current per-platform
Xcode schemes.

## 2026.07.17.2

### Improved

**Faster engine launch.** The engine now defers optional workflow, MCP, and
provider imports until they are needed, reducing the work required before the
local API becomes available.

## 2026.07.17

### Improved

**Faster embedded-engine startup.** The bundled engine ships with precompiled
Python bytecode, waits until it is ready before restoring saved libraries, and
binds before optional heavyweight work. It no longer opens every known library
or warms embeddings during local startup.

**Faster library UI.** This build removes an artifact/entity N+1 fetch, avoids
unnecessary sidebar rebuilds, moves full-image decoding off the main thread,
and improves library filtering, reader, and knowledge-graph work.

**Paleography workflows.** New zoom/image-preparation tools, ensemble
transcription, and deterministic consistency checks are available in the
workflow library.

### Fixed

- Fixed local and embedded engines incorrectly showing a sign-in wall. A
  loopback engine now treats its host as the owner and keeps library-scope
  failures scoped to that library instead of calling them authentication
  failures.
- Fixed healthy launches briefly rendering as `Backend Not Connected` and
  removed a launch-blocking move-to-Applications modal.
- Fixed sandboxed builds opening a library added after engine launch, and
  hardened App Store helper signing and embedded-engine packaging.
- Fixed workflow selection so one click opens the selected workflow in the
  node editor.

## 2026.07.13.4-beta

Inspector and startup hardening after the first notarized beta.

### Improved

**Document Inspector.** Artifact, entity, claim, citation, annotation, note, and
knowledge-graph inspector paths are more consistent. Inspector selections now
preserve focus across tab routing, entity merges, and refreshes. Artifact clicks
route into inspector detail, entity names route into library search, and the
knowledge-graph browser warns when a cap truncates results.

**Mac shell polish.** Toolbar IDs, mini-toolbar chrome, split focus, sidebar PDF
drop targeting, empty activity windows, and live-update pause behavior were
tightened for the internal Mac test build.

**Connection and launch recovery.** Startup errors are classified more clearly,
library live-update streams wait until the backend is ready, and sandbox token
sync handles the UUID container path used by signed/sandboxed app launches.

### Fixed

- Fixed several inspector regressions around artifact selection, entity merge
  refresh, lower-detail layout, outline disclosure, and source routing.
- Fixed catalogue/page-level workflow output refresh so inspector content tracks
  page-scoped workflow results.
- Fixed local pairing QR PIN lookup and kept the shared engine bound to
  loopback unless sharing is intentionally enabled.
- Repaired Swift build and guardrail drift after the inspector and feature-tier
  batches.

## 2026.07.10-beta

The first notarized build, auto-updating via Sparkle.

### New

**Local models, managed for you.** Fichero can now download, store, and run
local models itself — a supervised MLX sidecar with its own isolated runtime,
gated on hardware that can run it. No terminal, no separate server.
Apple Intelligence and Apple Vision remain fully on-device options.

**Knowledge Graph, grown up.** Claims and entities now carry attribution —
speaker, quotation kind, language, audience, genre, and the source of the
confidence score. Claims link to other claims. Everything scopes to a page, a
document, or a folder, and keeps the passage it came from. Entities
de-duplicate; conflicting types get flagged rather than silently merged.

**Document Inspector V2.** Tabbed Info / Metadata / Content / Artifacts /
Knowledge Graph, alongside a multi-pane reading layout with a PDF page view and
per-page artifacts. Content is editable in place.

**Canvas and Space.** Library contents arrange on a 2D canvas or in a 3D space,
with layouts that persist per library.

**Translation.** Translate a document into a language you choose. The
translation is stored as its own artifact, embedded so it turns up in search,
and listed by language in the reader alongside the source. The immersive reader
gains a Source / Diplomatic selector, and every machine-made representation
carries its provenance and an **AI unreviewed** badge until a person says
otherwise.

**Bibliography.** A reference panel that extracts citations from a document,
resolves their metadata from a DOI or ISBN, lets you edit it in a native form,
imports references in bulk, and exports BibTeX. Deletes are undoable.

**Search.** Results show the matched excerpt in context, not just a filename.
Typos are tolerated, and exact matches rank above semantic neighbours.

**Users and sharing.** Fichero now has real user accounts. Libraries can be
shared, access granted and revoked per folder, and every mutation is recorded
with the account that made it. Off by default — a single-user library behaves
exactly as before.

**Device pairing.** Pair your own Macs and iPads over the local network with a
QR code and per-device tokens.

**Static export.** Export a library as a browsable, offline-searchable static
site with per-entity knowledge pages.

**`fichero` command line.** A typed command surface mirroring the engine's HTTP
API — engine lifecycle, library management, import, and a persisted registry of
known libraries.

**Primary Language setting**, and NFC path normalization so accented filenames
round-trip correctly between Finder, the database, and disk.

### Improved

**Chat** has a cleaner header, conversation-scoped attachments, and a compact
layout for iPhone and iPad.

**Cancellation.** Workflows can be cancelled mid-run, and workflow execution
moved off the main event loop — a slow node no longer freezes the engine.

**Multilingual catalogue reliability.** When Apple Intelligence refuses a
locale or trips a safety filter, the run falls back to your configured cloud
model instead of returning an empty catalogue.

**Undo** reaches the surfaces that promised it: documents, images, knowledge
graph and artifacts, claim links, annotations, classifications, snapshots,
bookmarks. Every audited action is recorded centrally, so ⌘Z works across the
app rather than in a handful of places — and when an undo fails it says so
instead of quietly doing nothing.

**Reading layouts.** Multi-page PDFs can be read one page at a time or several
up, with a layout picker in the reader.

**Knowledge graph housekeeping.** A possible-duplicates surface merges entities
in one click, with a picker for which record survives. Repeated claims from
different sources fold into a single canonical row.

**Errors say what happened.** Service, research, and per-library history
failures now surface the real message instead of a generic Cocoa error, and the
engine re-probes with backoff to recover a healthy connection rather than
failing the launch outright.

### Security

**Per-launch API token.** The engine binds loopback-only (`127.0.0.1`) and
requires a startup-generated bearer token
(`~/Library/Application Support/Fichero/.api-key`, mode `0600`). Fichero is not
reachable from the internet or your local network; the token closes the
remaining gap of other apps running as you on the same Mac.

**Audited writes.** Every backend mutation routes through one audited action
layer that records what changed and which account changed it.

**Path confinement.** A lexical `..` traversal in the library path allowlist is
closed, and the QuickLook preview sanitizes a server-supplied filename before
using it as a path. Annotation geometry and colour are validated on the way in.

**Fail loud, not quiet.** Export provenance gaps, importer degradation, and
startup misconfiguration now surface as errors instead of silently substituting
a default. A workflow fan-out that fails completely reports the failure rather
than returning an empty result, and values the pipeline cannot interpret are
routed to human review instead of guessed at.

### Fixed

- **Launch crash.** Opening a library window could crash the app: SwiftUI was
  registering the search field twice, once globally and again in individual
  mode views. Per-view search now defers to the single toolbar search, and the
  first-run provider sheet waits until the toolbar has laid itself out.
- **The app could not open its own library.** A sandboxed build was denied
  access to its container path, and a stale API token produced an
  authorization failure on a freshly started engine.
- **Activity progress and log** stream correctly. The workflow event stream was
  a single-consumer queue that starved a second subscriber, leaving 0% progress
  and an empty log; it is now a fan-out broadcaster with a replay buffer.
- **Chat** no longer blocks while the model is thinking, and it remembers the
  conversation — earlier turns are included in the prompt, and context survives
  a retry.
- **Knowledge Graph and the document reader** render again over the pinned
  engine connection.
- **Per-page transcription** applies across every Transcribe and Catalogue
  preset.
- **Shell**: iPhone inspector opens full-height; the macOS sidebar selection
  updates the view; the iOS reader hides desktop zoom on compact widths.
- Backend 500s on list endpoints, knowledge-graph cascade deletes, LanceDB
  fork-safety, a DuckDB upsert crash, re-OCR of already-digital PDFs, keyword
  over-extraction, and an assortment of inspector, thumbnail, and activity bugs.

### Under the hood

- Every list endpoint speaks one OpenAPI envelope contract, guarded by a
  permanent endpoint-walker test.
- The Swift app talks to the engine through generated, typed operations rather
  than hand-written requests.
- `scripts/verify_all.sh` (SwiftLint + Xcode test suite + backend contract
  tests) is the single answer to "is it green", wired to ⌘U, and renders its
  failures to an HTML dashboard.
- In Debug the engine runs externally; a Release build embeds and launches it,
  signed with hardened-runtime entitlements.
- A launch-crash smoke test boots the built `.app` and asserts it survives.
- Graph retrieval no longer scans the whole table; citation and reference
  filters run in the database.

### Known issues

- The live-updates event stream (`/api/changes/stream`) fails TLS on a
  self-signed `.local` certificate.
- IIIF endpoints are staged behind `FICHERO_FEATURE_TIER=dev` and are off in a
  release build.
