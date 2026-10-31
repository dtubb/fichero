# Source Model — Wide onboarding: Set Up as a pager that shows each step's output — Design Spec (#5668)

> Milestone: recipe-designer
> Manual: TBD — a section, "Setting up a project", explaining that Set Up is a row of pages the person
> moves through (swipe, arrow keys, Back and Next), that every page shows what its step makes of the
> person's own pages, how Prepare Images is four steps that can each be left out, and that nothing runs
> on the whole project before Start.
>
> Design-led (Testing Constitution). **Status: DRAFT — written 2026-10-31 from the owner's direction by
> screen share the same day; awaiting the owner's rulings on the questions at the end.** Tags: [OK] built
> and pinned · [PARTIAL] exists, partly wired or unpinned · [GAP] not built · [BROKEN] built, wrong.
>
> **Where this sits.** `models-chains-and-projects.md` owns Set Up's questions, the stages list and the
> plan (`source.onboard.*`); `image-preparation.md` owns what Prepare Images does to a photograph
> (`prep.*`); `image-enhancement.md` owns the pixel steps (`image.enhance.*`); `recipes-run.md` owns the
> run. This spec owns the **shape of the Set Up window** (the pager and the output column, `wide.*`),
> the **cut of Prepare Images into selectable steps** as the person sees them, the **no-model step**
> (Tie text to lines) as the person sees it, and the **two defects** found on the owner's screen. Where
> another spec already says a thing, this one cites it and does not restate it.

## Intent

Set Up today is a list of pages down the left and one tall form on the right: a person answers questions
and reads sentences about what a stage will do, and sees nothing of what it does until Start has run over
the whole project. The owner's direction (2026-10-31): make Set Up **wide**. Each step is one page of a
row; the person moves **left and right** between steps with a trackpad swipe, the arrow keys, or Back
and Next; and each page shows, beside its questions, the **output of that step on the person's own
pages**: the photograph as it came in and as the step leaves it, the lines found, the reading, the names.
The output is never a drawing of what the step would do. Where it has not run yet the page says so, with
the time and cost of trying it; where it is running the page shows its progress in place; where the
engine refuses, the page shows the engine's sentence.

Prepare Images stops being one card with a sentence. It becomes **four steps the person can each leave
in or out** — split a book photograph into two pages; straighten (turn upright, straighten the lines);
crop to the paper; and clarity (brightness, contrast, sharpen) — each with its **own picture**, and each
showing what it did to the sample page as a rendition the person can look at. The "Answer for one
folder" picker leaves the card: the owner calls its list of folder names noise.

## What exists today

- **The window** (`fichero/fichero/Views/Onboarding/FirstRun/FirstRunWindow.swift`): a fixed 820 by 600
  card on the Mac; a 260-point step list on the left (`List(selection:)`, every page reachable by click
  once a project exists), the page's content in a scroll view on the right, the Mac setup assistant's
  footer (`fichero/fichero/Models/SetupFooter.swift`: one secondary choice at the far left, Back, the
  default button at the far right, Return). No swipe, no arrow keys: the list and the footer are the
  only ways between pages. Steps come from `SetupStep` and `SetupFlow`
  (`fichero/fichero/Models/SetupFlow.swift`): the app's three pages, then Your Project, Add Material,
  About the Material, Choose the Stages, one page per chosen stage in the engine's order, Ready.
  Continue saves the answers so far as a draft (`savesDraft`); Start saves and starts.
- **A stage page** (`fichero/fichero/Views/Onboarding/Stages/SetupStagePage.swift`): the stage's
  picture at the top (`StageShowcaseSection`), the engine's example sentence, "Which model does it"
  (`RecipeStepsView` filtered to the stage's jobs), the left-off rows, the questions, and below a
  Divider "On your pages" (`SetupStageSamples`): the sample thumbnails, Compare on These Pages, Stop,
  the result per page in words, and a compare window for the lines. The Prepare Images page adds its
  card (`PrepareImagesCard.swift`): the engine's sentence, suggested answers with Use, the time line,
  the Pages to check worklist, and the per-folder picker (`PrepareImagesFolderAnswers`).
- **The pictures** (`fichero/fichero/Views/Onboarding/Stages/Showcase/`): one SwiftUI view per stage
  drawing **one frame from a progress of 0 to 1** (`StagePictures+Page.swift`,
  `StagePictures+Knowledge.swift`), played by `StageShowcaseView` with a `TimelineView` over 3 to 5
  seconds, Replay, and the last frame still under Reduce Motion (`StageShowcasePlayback`). The picture
  for Prepare Images is one: a tilted dim page settles, scales down, brightens, and a light sweeps it.
  It plays on the example page shipped with the app, or on the person's sample page once a try has a
  result (`StageShowcaseSource.showcase(for:)`); a try result carries lines and text, **never a picture
  of a prepared page**, so for Prepare Images the animation always plays over the sample's original.
- **The engine's stages** (`fichero-server/src/fichero_server/recipes/stages.py`): `STAGES`, fourteen
  in pipeline order, each with jobs, a sentence, an example, questions and needs; Prepare Images carries
  `split-pages` and `prepare-the-image` and four questions (two pages, beside the page, the paper, missed
  lines). A try (`POST /api/recipes/stages/{stage}/try`, `recipes/samples.py`) runs the stage's own
  steps on a scratch copy of the samples and keeps the result beside the setup.
- **The plan** (`fichero-server/src/fichero_server/recipes/assemble.py`, `recipes/start.py`): a ticked
  stage's jobs reach the recipe through `answers.jobs` (`SetupStageChoice.jobsAddedAndRemoved` →
  `assemble`: `jobs |= {j for j in a.jobs if j in STEP_ORDER}`). The `photographs` and `faded_pages`
  gates (`assemble.py` near line 1055) are the **automatic** way in, taken when a reading or Find Lines
  step is in the plan; they are not the only way. `plan_start` turns `split-pages` into the `split_pages`
  workflow and `prepare-the-image` into the `prepare` card (`OTHER_CARDS`), which is **not** a workflow.
  `canStart` in the app (`fichero/fichero/Models/RecipeSetupStore.swift`) is
  `refusals.isEmpty && !workflows.isEmpty`.
- **The run** (`recipes/prepare_run.py`, `recipes/page_crop.py`): `crop_pages(prepare=True, reuse=True)`
  on every page, then the contrast step where the paper answer allows it (`prepare.runs_contrast`). On
  each page: find the page (Vision, then contour); when the finder is **trusted** (contour confidence
  at least 0.8, box share at least 0.15) write `page_box`, `page_region`, a `crop` rendition, and then
  the operations in order (square, flatten, turn by the text, straighten), **each a rendition only when
  it changed something**; when it is **not trusted**, count the page as `whole`, write the stamp, and
  run **none** of the operations. `reuse` skips any page whose `page_prep_stamp` (file and rule version)
  matches, whatever the answers now say.
- **The current image** (`fichero-server/src/fichero_server/media/current_image.py`, #6296): every step
  that sends a page to a model reads the edit chain if there is one, else the newest rendition whose
  frame can be followed (`frame_map.py`), else the photograph. The Prepare Images renditions carry their
  transform (`page_crop._write`); the contrast step's `prepared` rendition carries none and is read as
  the photograph's frame when its shape matches (`_same_frame_map`). Preview flips between renditions on
  its vertical axis (`rendition_order.py`: primary first, then by role).
- **Tie text to lines** (`fichero-server/src/fichero_server/checking/tie_text.py`): a page reading
  (a model that read the whole page) is aligned, character by character, to Kraken's rough read of each
  line (`align`, one edit-distance alignment of the page text against the rough reads joined), and each
  line gets the stretch it matches; a stretch that agrees with its rough read under 0.30 is written but
  marked doubtful (a `reject` verdict); a page with over half its lines untied stays a draft; the counts
  (`tied`, `doubtful`, `untied`, `drafts`, `no_lines`, `no_page_reading`) are on the job. It runs by
  itself after every page reading (`after_page_reading`) and as the recipe step `tie-text-to-lines`,
  whose "model" is the **line reader's** (`recipe.add_page_step`): no model ties; the rough read is the
  anchor.
- **Find Lines' cards**: Kraken's `blla` (the plan's only `find-lines` card; `start.py` skips any other
  pin), Apple Vision's lines for print and typescript (`APPLE_LINES_PIN`, workflow
  `detect_regions_apple_lines`), and, on the Detect Regions node only, a vision model's boxes (`provider:
  vlm`) and Apple (`provider: apple`) — `workflows/tools/detect_regions.py`. Find Regions has Kraken and
  YOLO (`prep.regions.open-default`). Find Lines is tried by the bake-off (`TRIED_BY_THE_BAKEOFF`).

## Prior art

Apple's Setup Assistant and Migration Assistant are a row of pages with Back and Continue and a fixed
card; Photos' import and Preview's adjustments show the picture changing as a slider moves. ScanTailor
is the model for the cut of image preparation: fix orientation, split pages, deskew, select content,
margins, output — one page per operation, each with its own preview of the current page, each skippable,
settings per page or for all. Transkribus and eScriptorium show the segmentation result on the page
before the person commits a model. Apple's own `TabView(.page)` is the pager on iOS; on the Mac a pager
is a horizontal scroll view with paging, driven by the trackpad's horizontal scroll and the arrow keys,
with the page index announced to VoiceOver. Fichero adopts all of this and invents none of it: the
output column shows the current sample page as the step leaves it, the way ScanTailor does per
operation; the Prepare Images cut follows ScanTailor's order with Fichero's own finders behind it.

## The design

### A. The pager: one row of pages, moved left and right

The Set Up window keeps its step list on the left as the **index** (it says where the person is and lets
them jump) and turns the content column into a **pager**: one page per step in `SetupFlow.steps`, the
current page filling the column, the next and previous pages off to the sides. Three ways move between
pages: a **horizontal trackpad swipe** (a two-finger scroll with a horizontal phase; on iOS a drag), the
**arrow keys** (← and →, and ⌘[ and ⌘] as the menu's Back and Next) when focus is not in a text field,
and the footer's **Back and Next** (Next is the page's default button as today; a page that saves a
draft on Continue still does, so swiping forward saves the same draft Continue did). Every move keeps the
page's scroll position and its answers; a page the engine refuses to leave (Add Material with no
material, About the Material with no language: `SetupFooter.waitsFor`) **bounces back** with the reason
beside Next, so a swipe can never skip a page Continue could not.

**Layout, macOS.** The window grows from 820 by 600 to **1040 by 680** (the owner asked for wide; the
step list stays 260). A step page is two columns: **the questions on the left** (420 points: what the
page asks, "Which model does it", the stage's own questions, left-off rows) and **the output on the
right** (the rest, at least 320): the picture at the top, then the sample strip and the step's result on
the current sample. The picture moves from above the questions into the output column, so the person
reads "what it does" and "what it did to my page" in one place. Ready keeps one column (its plan is
already a list).

**Layout, iPad and iPhone.** The step list collapses to a title with "3 of 9" and a page dot row under
it; the two columns stack (questions, then output) in one scroll view; the pager is `TabView` with the
page style and its own dots hidden (the row above shows them). iPhone and iPad have no local engine
(`SetupFlow.isCompanionPlatform`): their Set Up is the welcome alone today, and this spec changes
nothing there until a companion Set Up exists; the widths are written down so the views do not assume
the Mac's.

**Accessibility.** The pager is one accessibility element containing its current page, labelled "Step
3 of 9, Prepare Images"; a page change posts a layout-changed notification with the new label, so
VoiceOver says where the person landed. Back, Next and every control on the page are reachable by Tab;
← and → move pages only when focus is on the pager or the footer, never inside a text field or a list.
With Reduce Motion the page change is a cross-fade, not a slide, and the pictures show their last frame
(already so). The swipe has a keyboard twin always; nothing is swipe-only.

### B. The output column: the person's own pages, never invented

Every stage page's output column has the same four states, decided by the engine's try result for that
stage (`GET /api/recipes/stages/{stage}/try`):

1. **Not tried yet.** The sample strip (the project's sample pages, marked as the person's,
   `source.onboard.stages.samples-are-his`), the stage's picture playing on the example page, and one
   line in words with a button: "Try on these 5 pages: about 40 s on this Mac, free" or "...sends the
   pages to <provider>, about $0.04" (from the stage plan's estimate; a cloud try asks the yes it asks
   today). No result is drawn.
2. **Running.** The picture holds; under it the engine's progress words per page and model
   (`source.onboard.stages.try-progress-in-place`), with Stop. A page's result appears as that page
   finishes.
3. **Done.** For a page stage (Prepare Images, Find Regions, Find Lines, Read): the current sample page
   **as it came in on the left and as the step leaves it on the right**, the step's marks drawn on the
   right-hand picture (the page box and corners, the gutter, the lines, the reading beside), the
   measures under it in words (count of lines, agreement, seconds, cost), and Use This where candidates
   were compared. For a text stage (Normalise onward): the sample page's picture and what the step made
   of its text, as today's result rows. The person can step through the sample pages with the strip.
4. **Refused or failed.** The engine's own sentence (its 422 detail, or the try's `error`), in place of
   the result, with the one fix the sentence names where the app has that button (choose a model, allow
   the cloud). Never an empty column (#5806).

A try result that is older than the stage's answers or chosen model is shown **stale**: dimmed, with
"Tried with the earlier answers; try again" and the button. The engine says so: the try result carries
the answers' revision it ran with (`answers_revision`), and the listing's questions carry the current
one.

### C. Prepare Images as four selectable steps

The stage keeps its two jobs in the recipe (`split-pages`, `prepare-the-image`) and its questions; what
changes is **how the person sees and chooses the work**. The engine's listing for the stage carries an
ordered list of **operations**, each selectable, each with its own picture, in ScanTailor's order:

| Operation | id | What it does (the engine's words) | Default | Runs as |
| --- | --- | --- | --- | --- |
| Split a book photograph | `split` | cuts a photograph of two pages at the gutter into its left and right pages | on when "Two pages in one picture?" is yes; off otherwise | the `split-pages` job (the `split_pages` workflow) |
| Straighten | `straighten` | turns a page upright by its text and straightens the lines (a quarter turn, then up to 15°) | on | `prepare-the-image`: turn by the text, straighten |
| Crop to the paper | `crop` | finds the paper, cuts away the table, ruler and colour card, and squares a page photographed at an angle; flattens a page curved into the gutter | on | `prepare-the-image`: find the page, square, flatten |
| Clarity | `clarity` | brightens, raises the contrast and sharpens faded or dim writing on a new copy | on when the paper is faded; otherwise off, with "Fichero looks at each page and raises only the faded ones" | `prepare-the-image`: the contrast step |

The person's choice is saved as one answer, `prepare_operations` (a list of the ids that are on), with
the stage's other answers in `job_answers`; `plan_start` carries it onto the `prepare` card
(`entry["operations"]`) and `run_prepare` runs only those (`crop_pages` takes which operations to run;
`split` on means the `split-pages` job stays in the plan and off takes it out as the explicit "no" does
today). Blank pages are marked under Crop (they are found with the paper). The four questions stay and
set the defaults; an operation switched by hand wins over its question. Each operation's row on the
page shows its **own picture** (section D), its **on/off**, and after a try **what it did to the sample
page** (section E). Nothing new is built in the engine's operations: the four map onto `page_crop._prepare`,
`turn_by_text`, `auto_straighten_angle`, `find_page`, `square_page`, `flatten_curve`, `page_split` and
`prepare.prepare_pages` as they are.

**The per-folder picker goes.** `PrepareImagesFolderAnswers` and its "Answer for one folder" picker leave
the card. The engine keeps reading `job_answers_by_folder` (a folder's own run, `folder_id`, the Start
plan's own row) so a project that already has folder answers keeps them. Where a folder's own answer is
set from now on is an open question for the owner (section "Open questions"); the recommended default
is the folder's context menu in the library ("This folder's pages: two in one picture"), outside Set Up.

### D. One picture per operation

`StageShowcaseCatalogue` gains a picture per operation, each a SwiftUI view drawing one frame from
`progress` 0 to 1 over the showcase page, 3.5 seconds, Replay, last frame under Reduce Motion, as the
stage pictures do (`StageShowcaseView`):

- **Split**: the page layer is drawn as a wide spread (two page halves side by side with a dark gutter
  line); from 0.3 to 0.8 the halves part along the gutter and settle as two upright pages with a gap.
- **Straighten**: the page starts turned 90° and skewed 6°; from 0 to 0.5 it turns upright; from 0.5 to
  0.9 the skew comes out and the lines (the showcase's line boxes) settle horizontal.
- **Crop**: the page sits small on a dark table with a ruler strip at the top; from 0.2 to 0.6 a dashed
  page box with four corner handles draws itself around the paper; from 0.6 to 1 the table falls away and
  the paper fills the frame, one corner pulled square.
- **Clarity**: the page starts dim and low-contrast; from 0.2 to 0.8 it brightens and its ink darkens
  (`brightness`, `contrast`), the existing light sweep across it.

The stage's own picture (the one at the top of the page) becomes the four played in turn, each a quarter
of the play, so the stage still has a picture when no operation row is open. Every picture has its
sentence in `descriptions` for VoiceOver.

### E. What the output column shows for Prepare Images: the rendition chain

After a try (or after Start, when the run has prepared the sample page) the right-hand picture is the
**sample page as the operations left it** — the page's current image (`current_page_image`), the one
Find Lines will read — and under it a **chain strip**: the photograph, then each rendition the step wrote
in order (`crop`, `squared`, `flattened`, `rotated`, `deskewed`, `prepared`), each a small thumbnail with
its operation's name and the row's figure in words ("squared from its corners", "turned 90° from its
text", "straightened 1.3°", "contrast raised"), from the rendition's `transform` and `note`. Clicking a
thumbnail shows that rendition on the right; the strip says which one every later step reads ("Find
Lines reads this one"), from `PageImage.read_from`, and names a rendition that was passed over with the
engine's reason (`PageImage.why`). An operation that wrote nothing on this page says so on its row ("the
page was already upright: nothing written"). The engine serves this as `GET /api/pages/{id}/image-chain`:
the current image, the ordered renditions with role, note, transform figures and `reads_this`, and the
passed-over notes; the same answer Preview's rendition axis will read, so the two never disagree.

### F. The two defects on the owner's screen

**"Prepare Images doesn't seem to do anything."** Checked in the code; four causes, each real, in the
order a person meets them:

1. **The operations run only when the page finder is sure.** `page_crop.crop_pages` runs `_prepare`
   (square, flatten, turn, straighten) **inside** the branch where the finder's box is trusted
   (`contour` confidence at least 0.8 and a box share of at least 0.15); a page where Vision returns no
   outline and the contour finder is unsure — a flat scan that fills the frame, a cut page, a dark
   photograph — is counted `whole`, stamped, and **no operation runs at all**: no turn, no straighten,
   no clarity. The sentence on the card ("turns it upright and straightens it") promises what the code
   does only on a found page.
2. **A re-run skips the page whatever the answers.** `reuse=True` skips every page whose
   `page_prep_stamp` matches the file and `PREP_VERSION`; the stamp does not include the answers, so a
   person who ticks "faded" or "two pages" after a first run and presses Start sees the step finish in
   seconds with `unchanged` on every page.
3. **Nothing in the app shows what it made.** The renditions land on the page, but Preview opens the
   primary (the photograph) and the renditions sit on the ↑/↓ axis nobody is told about; the card has
   no output; the run's account (`page_prep`, `prepared`) is only in the run detail. A step whose
   output is invisible looks like a step that did nothing.
4. **After the first Start, a stage ticked later may run nothing.** `_start_plan` limits the plan to
   `proposal["steps"] | unfinished` once the project has been started; a stage ticked in Set Up… after
   that first Start is in the recipe but, with no proposal written for it, is **not** in `only`, so
   its steps are skipped and the plan says "nothing in this recipe can run yet". (The `photographs` /
   `faded_pages` hypothesis is **not** the cause: a ticked stage's jobs reach the recipe through
   `answers.jobs`; those two gates are only the automatic way in.)

**"I can't run just that one step: it won't let me start."** Checked in the code; one cause in the app
and one in the engine:

1. **The app's Start reads `workflows`, not `runs`.** `RecipeSetupStore.canStart` is
   `refusals.isEmpty && !workflows.isEmpty`. `prepare-the-image` is an `OTHER_CARDS` card (`prepare`),
   not a workflow; so are Find Regions (`regions`), Leave Out, Find the Documents, Split into entries,
   Catalogue, Search (`embed`), Export and Publish. A plan whose only runnable step is one of these has
   `runs` and no refusals, and the app greys Start with `startDisabledReason`'s last line, "Nothing in
   this plan runs yet: every step is skipped (see why above)" — a sentence that is **false** (nothing
   is skipped). With Prepare Images alone and "Two pages: no" (which takes `split-pages`, the one
   workflow, out of the plan), Start cannot be pressed.
2. **The engine's own refusal is right but reached by another path.** `plan_start` refuses only
   "nothing in this recipe can run yet: every step is skipped" when `runs` is empty; a try of the stage
   (`samples.start_try`) refuses with 422 when the stage's plan has refusals, and the app showed
   nothing for it (#5806).

What the person should see instead: Start enabled whenever the engine's plan has **any run** and no
refusal, with the footer saying what will run ("Start: Prepare Images on 374 pages, about 2 min"); when
the plan has nothing to run, the engine's sentence and, per skipped step, its why and fix (already
there). A stage page gets its own **Run this step** on the output column (the Start route with `only`
that stage's step ids, over the whole project, and the same plan words first), so "just that one step"
is a button, not a trick of unticking the rest.

### G. A step with no model to choose: Tie text to lines

Some steps give the person no model to choose; the Read stage's **Tie text to lines** is the one that
matters, because the owner's experience is that a model reading the whole page gives excellent text and
nothing then ties that text back to the lines. What the code does today, honestly: the page text is
aligned to **Kraken's rough read of each line** by edit distance over the whole page, so each line gets
the stretch of page text that best matches its rough read; the match is scored by accent-blind
agreement; under 0.30 the stretch is still written but marked doubtful; a page with over half its lines
untied stays a draft and is not written at all; the thresholds are **stated, not measured** on real
pages (the module says so). Its quality is bounded by the rough read: a faded page Kraken reads badly
ties badly, and a page with no lines gets lines found first. No model is chosen because no model does
the tying — the line reader named on the step is the anchor, which is why "Which model does it" shows a
model that does something else.

What the person sees for any step with no model to choose (Tie text to lines, Leave Out, Find the
Documents, Prepare Images): not an empty chooser and not a radio row, but one line, **"Fichero does this
one: <how, in the engine's words>"** (`how_it_works` from the topic), then, once the step has run on the
samples, **its figures on those pages**: "Tied 41 of 48 lines; 5 doubtful; 2 could not be tied; 1 page
left as a draft", from the job's counts; and a link **"Show the lines it could not tie"** that opens the
sample page in the Reader's disagreement view with the untied and doubtful lines listed (the `reject`
verdicts already written). Where no method exists for a job, the line says so and names the by-hand
tool, as the plan's `by_hand` does.

**Recommended method, marked for the owner.** Keep the alignment as it is, anchored on the line reader's
output (it is the right anchor: it is the only text with a known line), and add two things: (1) the
unmatched remainder of the page text — stretches the alignment gave no line — kept on the page as
"text not tied to a line", shown in the same view, so nothing the page reader wrote is lost; (2) a
measured threshold: the bake-off measures tied-line agreement against the checked lines of the sample
and the stage shows that figure beside the step. A learned aligner is not proposed.

### H. Faded pages: clarity before Find Lines, and the segmenter choices

Kraken's segmenter finds few or no lines on faded pages (#6271: more than half the pages of one box had
no lines on their working pass). The stage order already answers it — Prepare Images before Find Lines —
and the current-image rule carries the answer through: when Clarity has written a `prepared` rendition,
`current_page_image` returns it (the newest rendition whose frame is known), so Find Lines segments the
clarified copy and its lines map back to the photograph. What is missing is that nobody sees it. The
Find Lines page's output column shows, for a sample page the paper answer calls faded (or Clarity
measured faded), **the line count on the photograph and on the clarified copy side by side** ("Kraken:
12 lines on the photograph, 27 on the clarified copy"), the compare window drawing both, and Use the
clarified copy (which is only Clarity on, and the default). Where Clarity is off and the sample measures
faded, the page says "These pages look faded; Clarity in Prepare Images is off" with a link to that page.

**The segmenters the code has, and how the person picks.** Find Lines' plan card is Kraken `blla` (the
only pin `start.py` runs for `find-lines`); Apple Vision's lines are the card for print and typescript
(`APPLE_LINES_PIN`, the `detect_regions_apple_lines` workflow); a vision model's boxes exist only as the
Detect Regions node's `vlm` provider and are not a plan card. Find Regions has Kraken and a YOLO layout
model. The person picks per stage where they pick every model: the "Which model does it" rows and Compare
on These Pages on that stage's page (`source.onboard.stages.page-who-runs-it`,
`source.onboard.stages.compares-candidates`); Find Lines' compare is the bake-off's line comparison.
This spec adds no segmenter; it asks that the Apple Vision line card be offered on handwriting too as a
candidate (it finds lines on faded print where Kraken finds none, measured by the compare, never
assumed) and that a vision model's boxes stay a node option until a plan card for them is specified.

### I. State: leaving and coming back

Every answer on a stage page is already a draft on the project (saved on Continue and on a forward
swipe, `PUT /api/recipes/project`); the operation choices join `job_answers`. The pager's **position**
(the step id) and each stage's **chosen sample page** are saved per project on this Mac
(`UserDefaults`, keyed by the project id), so Set Up… reopens on the page the person left, with the
page they were looking at; a stage no longer chosen falls back to Choose the Stages. Try results are the
engine's and survive (`samples._write`); a stale one is shown stale (section B), never replayed as
current. A try or Start under way when the window closes keeps running (it is a job) and the page shows
its progress again when reopened (`source.onboard.stages.try-progress-in-place`).

## Behaviors

### The pager

- `wide.pager.swipe-arrows-back-next` — **[GAP]** (#5668) the Set Up window's content is a pager over `SetupFlow.steps`: a horizontal trackpad swipe, ← and → (and ⌘[ ⌘]) with focus outside a text field, and the footer's Back and Next all move one page; the step list on the left still jumps to any page; a forward move saves the draft the page's Continue saves; a page Continue cannot leave bounces back with its reason beside Next (`SetupFooter.waitsFor`). *Test:* `SetupPagerTests.swift` (not yet written: the move rules over a fake step list, keyboard and swipe reduced to one `advance`/`retreat` on the same model; the bounce), `fichero/Tests/Unit/general/Views/Onboarding/SetupFooterTests.swift`. Manual: TBD.
- `wide.pager.window-is-wide` — **[GAP]** (#5668) on the Mac the window is 1040 by 680 with the 260-point step list; a stage page is two columns, questions 420 wide on the left and the output on the right (at least 320), Ready one column; on iPad and iPhone the list collapses to "3 of 9" with page dots and the columns stack in one `TabView` page. *Test:* `SetupPagerTests.swift` (not yet written: the widths and column rule as pure values per platform), `fichero/Tests/Unit/general/Views/Onboarding/SetupSheetFitsTests.swift`. Manual: TBD.
- `wide.pager.accessible` — **[GAP]** (#5668) the pager is one accessibility element containing its page, labelled "Step N of M, <title>"; a page change posts the new label; every control is reachable by Tab and nothing is swipe-only; Reduce Motion cross-fades instead of sliding and the pictures hold their last frame. *Test:* `SetupPagerTests.swift` (not yet written: the label for each step; the Reduce Motion transition flag), `fichero/Tests/Unit/general/Models/StageShowcaseTests.swift` (the last frame, built). Manual: TBD.
- `wide.pager.position-restored` — **[GAP]** (#5668) Set Up… reopens on the page the person left and the sample page they were looking at, per project on this Mac; a page no longer in the flow falls back to Choose the Stages; try results and answers come from the engine, never from the app's memory. *Test:* `SetupPagerTests.swift` (not yet written: restore to a kept step, fallback for a dropped stage). Manual: TBD.

### The output column

- `wide.output.four-states` — **[GAP]** (#5668, #5806) every stage page's output column is in one of four states from the engine's try result: not tried (the picture on the example, the sample strip, "Try on these N pages" with the engine's time and cost line), running (progress in place, Stop), done (the sample page before and after, the step's marks, the measures in words, Use This where compared), refused or failed (the engine's sentence and the one fix it names); never an empty column. *Test:* `StepOutputStateTests.swift` (not yet written: the state from a result of each shape, the words of the not-tried line from a plan estimate), `fichero-server/tests/unit/recipes/test_stage_try_does_not_wait_or_hide_5806.py` (the engine's sentences, built). Manual: TBD.
- `wide.output.before-and-after-on-his-page` — **[GAP]** (#5668) for a page stage the done state shows the current sample page as it came in on the left and as the step leaves it on the right, with the step's marks on the right-hand picture: the page box and corners, the gutter, the lines, the reading beside; the person steps through the sample pages with the strip; the pictures are the person's pages from the project's storage and the example page is never shown as output. *Test:* `StepOutputStateTests.swift` (not yet written: the right-hand picture's source is the try's page id, never the bundled example; the marks per stage), `fichero/Tests/Unit/general/Models/StageFoundModelsTests.swift` (the samples are his, built). Manual: TBD.
- `wide.output.stale-says-so` — **[GAP]** (#5668) the try result carries `answers_revision`, the stage listing carries the current revision, and a result older than the answers or the chosen card is shown dimmed with "Tried with the earlier answers; try again"; it is never replayed as current. *Test:* `fichero-server/tests/unit/recipes/test_stage_try_result_follows_its_job_5806.py` (built; add the revision), `StepOutputStateTests.swift` (not yet written: stale when revisions differ). Manual: TBD.
- `wide.output.run-this-step` — **[GAP]** (#5806) a stage page's output column has Run this step: the Start route with `only` that stage's step ids over the whole project, the plan's words first (pages, time, cost, what is skipped and why); it lands on the run as Start does (`source.onboard.auto.lands-on-the-run`). *Test:* `fichero-server/tests/unit/recipes/test_start_plan.py` (built; add a plan with `only` one stage's steps that runs and nothing else), `SetUpButtonsActTests.swift` under `fichero/Tests/Unit/general/Views/Onboarding/` (built; add the button). Manual: TBD.

### Prepare Images as steps

- `wide.prepare.four-operations-listed` — **[GAP]** (#5382, #5580) the stage listing for Prepare Images carries `operations` in order — split, straighten, crop, clarity — each with its id, its sentence in the engine's words, its default from the questions, and whether it is on; the choice is one answer `prepare_operations`; an operation switched by hand wins over its question. *Test:* `fichero-server/tests/unit/recipes/test_setup_stages_5668.py` (built; add the four and their defaults from each answer), `PrepareOperationsTests.swift` (not yet written: the rows from the listing, the toggle writes the answer). Manual: TBD.
- `wide.prepare.plan-runs-only-chosen-operations` — **[GAP]** (#5382, #5580) the Start plan's `prepare` card carries `operations`; `run_prepare` runs only those (turn and straighten under straighten; find the page, square, flatten and the blank mark under crop; the contrast step under clarity); split off takes `split-pages` out of the plan as the explicit no does; every operation off is a plan with no `prepare` run and Start says so. *Test:* `fichero-server/tests/unit/recipes/test_prepare_step_setup.py` (built; add one case per operation off), `fichero-server/tests/unit/recipes/test_start_plan.py`. Manual: TBD.
- `wide.prepare.operations-run-on-every-page` — **[BROKEN]** (#5390, #5706; found on the owner's screen 2026-10-31, cause 1 under section F) straighten and clarity run on a page whether or not the paper was found: today `crop_pages` runs `_prepare` only inside the trusted-finder branch, so a page the finder is unsure of gets no turn, no straighten and no contrast, and the card's sentence promises what does not happen. Fixed: when the finder is not trusted the page itself is the base (no crop, no square, no flatten) and turn, straighten and clarity still run on it, each a rendition only when it changed something. *Test:* `fichero-server/tests/unit/media/test_turn_straighten_blank.py` (built; add a page the finder is unsure of that is still turned), `fichero-server/tests/unit/recipes/test_prepare_images_step.py`. Manual: TBD.
- `wide.prepare.rerun-follows-the-answers` — **[BROKEN]** (#5706; cause 2 under section F) the `page_prep_stamp` includes the operations and the paper answer, so a page prepared under other answers is prepared again and only a page prepared under the same file, rules and answers is `unchanged`. *Test:* `fichero-server/tests/unit/recipes/test_prepare_images_step.py` (built; add: ticking faded after a run prepares the page again). Manual: TBD.
- `wide.prepare.ticked-later-still-runs` — **[BROKEN]** (#5706; cause 4 under section F) a stage ticked in Set Up… after the project's first Start is in the next Start's plan: saving a setup whose recipe gained steps writes those steps into the proposal (`write_proposed`), so `only` holds them; a stage taken out is not. *Test:* `fichero-server/tests/unit/recipes/test_start_plan.py` (built; add: a started project, a stage ticked later, the plan runs its steps). Manual: TBD.
- `wide.prepare.folder-picker-removed` — **[GAP]** (#5580) the "Answer for one folder" picker and its folder list leave the Prepare Images page; the engine keeps reading `job_answers_by_folder` and a project that has folder answers keeps them, said on the page in one line ("2 folders answer for themselves") with no list of names. *Test:* `fichero/Tests/Unit/general/Models/PrepareImagesFolderAnswersTests.swift` (built; the engine half stays), `PrepareOperationsTests.swift` (not yet written: the page has no picker; the one line's count). Manual: TBD.

### The pictures

- `wide.picture.one-per-operation` — **[GAP]** (#5668) each of the four operations has its own SwiftUI picture drawing one frame from a progress of 0 to 1 (split: the halves part at the gutter; straighten: the page turns upright and its lines settle; crop: a dashed box with corner handles draws around the paper and the table falls away; clarity: the page brightens and its ink darkens under the light sweep), 3.5 seconds, Replay, the last frame under Reduce Motion, each with its sentence for VoiceOver; the stage's own picture plays the four in turn. *Test:* `fichero/Tests/Unit/general/Views/Onboarding/StageShowcasePicturesTests.swift` (built; add the four: a frame at 0, 0.5 and 1 differs and the last frame is still), `fichero/Tests/Unit/general/Models/StageShowcaseTests.swift`. Manual: TBD.

### The rendition chain

- `wide.chain.served-by-the-engine` — **[GAP]** (#6296, #5386) `GET /api/pages/{id}/image-chain` answers the page's current image (`read_from`: original, edited or rendition), the renditions in the order they were made with role, the row's figures in words from `transform` and `note`, which one every later step reads (`reads_this`), and each passed-over rendition with its reason (`PageImage.why`); the same answer Preview's rendition axis reads. *Test:* `fichero-server/tests/unit/media/test_current_image_6296.py` (built; add the chain's words and `reads_this`), `test_image_chain_route.py` (not yet written). Manual: TBD.
- `wide.chain.strip-on-the-page` — **[GAP]** (#5668, #5386; cause 3 under section F) the Prepare Images output column shows the sample page as the operations left it and under it the chain strip: the photograph then each rendition as a thumbnail with its operation's name and figure, "Find Lines reads this one" on the one the current-image rule returns, a passed-over rendition's reason, and "nothing written" on an operation that changed nothing; clicking a thumbnail shows it. *Test:* `RenditionChainStripTests.swift` (not yet written: the strip's rows from an image-chain answer; the reads-this mark; the nothing-written row). Manual: TBD.

### Start and the one step

- `wide.start.enabled-on-any-run` — **[BROKEN]** (#5806, #5801; found on the owner's screen 2026-10-31, section F) Start is enabled when the engine's plan has any run and no refusal, whatever the card (`runs`, not `workflows`); the footer says what will run; "Nothing in this plan runs yet: every step is skipped" is said only when the engine's plan says it. Today `canStart` requires a workflow, so a plan whose only steps are Prepare Images (with split off), Find Regions, Leave Out, Find the Documents, Catalogue or Search cannot be started from the app although the engine would run it. *Test:* `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift` (built; add: a plan with one `prepare` run and no workflow can start, and its reason is nil), `fichero-server/tests/unit/recipes/test_start_plan.py` (the plan's `runs` for a prepare-only recipe). Manual: TBD.

### A step with no model to choose

- `wide.nomodel.fichero-does-this-one` — **[GAP]** (#5721, #5668) a step whose job has no model to choose (Tie text to lines, Leave Out, Find the Documents, Prepare Images) shows no chooser and no radio row but one line, "Fichero does this one: <how>", from the topic's `how_it_works`; a job nothing does yet says so with its by-hand tool. *Test:* `fichero-server/tests/unit/recipes/test_tie_text_to_lines_picks_a_reader_6256.py` (built; add: the step's `how` names the anchor, not a model to choose), `TieTextStepTests.swift` (not yet written: the row's words for a no-model step). Manual: TBD.
- `wide.nomodel.tie-figures-on-his-pages` — **[GAP]** (#5721, #5720) after Read has run on the samples the Tie text to lines row shows its figures from the job's counts — tied, doubtful, could not be tied, pages left as a draft — and "Show the lines it could not tie" opens the sample page in the Reader's disagreement view with the untied and doubtful lines listed from their `reject` verdicts. *Test:* `test_tie_text_counts_on_the_stage_try.py` (not yet written: the try result carries the counts per page), `TieTextStepTests.swift`. Manual: TBD.
- `wide.nomodel.untied-remainder-kept` — **[GAP]** (#5721; recommended, for the owner) the stretches of the page text the alignment gives no line are kept on the page as text not tied to a line and shown in the same view, so nothing the page reader wrote is lost; the tie threshold is measured by the bake-off against the checked lines of the sample and the figure is shown beside the step. *Test:* `fichero-server/tests/unit/media/test_transcript_alignment.py` (built; add the remainder), `test_tie_text_remainder.py` (not yet written). Manual: TBD.

### Faded pages and Find Lines

- `wide.faded.find-lines-reads-the-clarified-copy` — **[PARTIAL]** (#6271, #6296) Find Lines segments the page's current image, which is the `prepared` rendition once Clarity has written one, and its lines map back to the photograph. Built: the current-image rule and the `prepared` rendition read as the photograph's frame (`_same_frame_map`). Not built: the `prepared` rendition carrying its own transform like the other operations' (today it is accepted by shape), and anything the person sees of it. *Test:* `fichero-server/tests/unit/media/test_current_image_6296.py` (built), `fichero-server/tests/unit/recipes/test_find_regions_inside_page.py`. Manual: TBD.
- `wide.faded.line-counts-before-and-after` — **[GAP]** (#6271) the Find Lines page's output column shows, for a sample page the paper answer calls faded or Clarity measured faded, the line count on the photograph and on the clarified copy side by side, the compare window drawing both, and Use the clarified copy; with Clarity off and a faded sample it says so with a link to Prepare Images. *Test:* `test_find_lines_try_counts_on_both_images.py` (not yet written: the try runs the segmenter on both and answers two counts), `StepOutputStateTests.swift`. Manual: TBD.
- `wide.faded.segmenter-choices-named` — **[PARTIAL]** (#6271, #5668) the Find Lines page names its segmenter cards from the one candidate source — Kraken `blla`, Apple Vision's lines — and the person picks and compares them there; the Apple Vision line card is offered on handwriting as a candidate, adopted only when the compare shows it finds more lines that read no worse; a vision model's boxes stay a Detect Regions node option until a plan card exists. Built: the two cards, the per-stage rows, the bake-off compare. Not built: Apple's card offered on handwriting; the vision-model card. *Test:* `fichero-server/tests/unit/recipes/test_model_chooser_per_step_5668.py` (built; add Apple's card on handwriting), `fichero-server/tests/unit/recipes/test_stage_compares_candidates_5668.py`. Manual: TBD.

## Test matrix

| Leg | This surface? | Pins | File |
| --- | --- | --- | --- |
| Pure rule (Swift) | y | the pager's moves, widths, labels, restore; the output state; the chain strip rows; the no-model row | `SetupPagerTests.swift`, `StepOutputStateTests.swift`, `RenditionChainStripTests.swift`, `TieTextStepTests.swift`, `PrepareOperationsTests.swift` (not yet written) |
| Engine (pytest) | y | the operations in the listing and the plan; the stamp with answers; the proposal for a stage ticked later; `runs` for a prepare-only plan; the image-chain route; the tie counts on a try; the two line counts | `fichero-server/tests/unit/recipes/test_prepare_step_setup.py`, `fichero-server/tests/unit/recipes/test_start_plan.py`, `fichero-server/tests/unit/recipes/test_setup_stages_5668.py`, `fichero-server/tests/unit/media/test_current_image_6296.py`, `test_image_chain_route.py`, `test_tie_text_counts_on_the_stage_try.py`, `test_find_lines_try_counts_on_both_images.py` |
| Contract | y | the stage listing's `operations`, the try's `answers_revision`, the image-chain schema | the regenerated client (`sync_openapi_schema.sh`) |
| Click-around (XCUITest) | y | swipe and arrow keys move a page; Run this step; the strip | `fichero/Tests/UI/general/Shell/PrepareImagesSetupUITests.swift` (built, unrun; add the pager) |
| iPhone / iPad | n | the widths are written down; no companion Set Up exists | — |

## Build order

The Pro's test host is stuck (`testmanagerd`), so every step separates the engine part (pytest, runnable
anywhere) from the Swift part whose tests need the XCTest host; a Swift step is written and lint-clean
first and its tests run when a host is available. Engine before app throughout.

### Stage 1 — The two defects, engine first

#### Step 1.1 — The operations run on every page; the stamp follows the answers (#5706)
- Behaviours: `wide.prepare.operations-run-on-every-page`, `wide.prepare.rerun-follows-the-answers`
- Tests: fichero-server/tests/unit/media/test_turn_straighten_blank.py, fichero-server/tests/unit/recipes/test_prepare_images_step.py
- Size: S
- Engine only; no host needed.

#### Step 1.2 — A stage ticked later runs; `runs` is what Start reads (#5806)
- Behaviours: `wide.prepare.ticked-later-still-runs`, `wide.start.enabled-on-any-run`
- Tests: fichero-server/tests/unit/recipes/test_start_plan.py, fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift
- Depends on: 1.1
- Size: S
- Engine: the proposal on save. Swift: `canStart` and `startDisabledReason` read `runs`; its test needs the XCTest host.

### Stage 2 — Prepare Images as steps (engine)

#### Step 2.1 — The operations in the listing and the answer (#5382)
- Behaviours: `wide.prepare.four-operations-listed`
- Tests: fichero-server/tests/unit/recipes/test_setup_stages_5668.py
- Size: S
- Engine only: `stages.py` operations, the `prepare_operations` answer, the client regenerated.

#### Step 2.2 — The plan and the run follow the chosen operations (#5580)
- Behaviours: `wide.prepare.plan-runs-only-chosen-operations`
- Tests: fichero-server/tests/unit/recipes/test_prepare_step_setup.py, fichero-server/tests/unit/recipes/test_start_plan.py
- Depends on: 2.1
- Size: M
- Engine only: `plan_start` carries `operations`; `run_prepare` and `crop_pages` take them.

#### Step 2.3 — The image chain served (#6296)
- Behaviours: `wide.chain.served-by-the-engine`
- Tests: fichero-server/tests/unit/media/test_current_image_6296.py, test_image_chain_route.py
- Size: S
- Engine only; the same answer Preview's rendition axis later reads.

### Stage 3 — Prepare Images as steps (Swift)

#### Step 3.1 — The operation rows, the picker gone (#5580)
- Behaviours: `wide.prepare.folder-picker-removed`
- Tests: fichero/Tests/Unit/general/Models/PrepareImagesFolderAnswersTests.swift, PrepareOperationsTests.swift
- Depends on: 2.1
- Size: S
- Swift; tests need the host.

#### Step 3.2 — One picture per operation (#5668)
- Behaviours: `wide.picture.one-per-operation`
- Tests: fichero/Tests/Unit/general/Views/Onboarding/StageShowcasePicturesTests.swift, fichero/Tests/Unit/general/Models/StageShowcaseTests.swift
- Size: M
- Swift only, pure views over `StagePageLayer`; a `#Preview` per picture; tests need the host.

#### Step 3.3 — The chain strip on the page (#5386)
- Behaviours: `wide.chain.strip-on-the-page`
- Tests: RenditionChainStripTests.swift
- Depends on: 2.3, 3.1
- Size: M
- Swift; tests need the host.

### Stage 4 — The output column

#### Step 4.1 — The try result knows its revision; Run this step (#5806)
- Behaviours: `wide.output.stale-says-so`, `wide.output.run-this-step`
- Tests: fichero-server/tests/unit/recipes/test_stage_try_result_follows_its_job_5806.py, fichero-server/tests/unit/recipes/test_start_plan.py
- Size: S
- Engine: `answers_revision` on the try and the listing; the Start route's `only` from the app. Swift: the button, in 4.2.

#### Step 4.2 — The four states and the before-and-after (#5668)
- Behaviours: `wide.output.four-states`, `wide.output.before-and-after-on-his-page`
- Tests: StepOutputStateTests.swift, fichero/Tests/Unit/general/Views/Onboarding/SetUpButtonsActTests.swift
- Depends on: 4.1
- Size: M
- Swift; the state model pure and testable without a host, its tests run when the host is back.

### Stage 5 — The pager

#### Step 5.1 — The pager, the widths, the keys (#5668)
- Behaviours: `wide.pager.swipe-arrows-back-next`, `wide.pager.window-is-wide`
- Tests: SetupPagerTests.swift, fichero/Tests/Unit/general/Views/Onboarding/SetupFooterTests.swift, fichero/Tests/Unit/general/Views/Onboarding/SetupSheetFitsTests.swift
- Depends on: 4.2
- Size: M
- Swift only; the move model is pure (`advance`, `retreat`, the bounce) and the view binds to it.

#### Step 5.2 — Accessible and restored (#5668)
- Behaviours: `wide.pager.accessible`, `wide.pager.position-restored`
- Tests: SetupPagerTests.swift, fichero/Tests/Unit/general/Models/StageShowcaseTests.swift
- Depends on: 5.1
- Size: S
- Swift only; the XCUITest leg (`PrepareImagesSetupUITests`) gains the swipe when a GUI host runs.

### Stage 6 — No-model steps and faded pages

#### Step 6.1 — Fichero does this one; the tie's figures (#5721)
- Behaviours: `wide.nomodel.fichero-does-this-one`, `wide.nomodel.tie-figures-on-his-pages`
- Tests: fichero-server/tests/unit/recipes/test_tie_text_to_lines_picks_a_reader_6256.py, test_tie_text_counts_on_the_stage_try.py, TieTextStepTests.swift
- Size: M
- Engine: the counts on the Read try; `how` on the step. Swift: the row and the link into the disagreement view; needs the host.

#### Step 6.2 — The untied remainder kept and the threshold measured (#5721; after the owner's ruling)
- Behaviours: `wide.nomodel.untied-remainder-kept`
- Tests: fichero-server/tests/unit/media/test_transcript_alignment.py, test_tie_text_remainder.py
- Depends on: 6.1
- Size: M
- Engine only.

#### Step 6.3 — Find Lines on the clarified copy, said and counted (#6271)
- Behaviours: `wide.faded.find-lines-reads-the-clarified-copy`, `wide.faded.line-counts-before-and-after`, `wide.faded.segmenter-choices-named`
- Tests: fichero-server/tests/unit/media/test_current_image_6296.py, test_find_lines_try_counts_on_both_images.py, fichero-server/tests/unit/recipes/test_model_chooser_per_step_5668.py, StepOutputStateTests.swift
- Depends on: 2.2, 4.2
- Size: M
- Engine: the `prepared` rendition's transform; the try's two counts; Apple's card on handwriting. Swift: the two counts and the link; needs the host.

## Accessibility identifiers

| Identifier | What it is on |
| --- | --- |
| `setup.pager`, `setup.pager.page.<step id>` | the pager; one page |
| `setup.footer`, `setup.footer.startReason` | the footer (built) |
| `setup.stage.output`, `setup.stage.output.try`, `setup.stage.output.stop`, `setup.stage.output.runThisStep` | the output column and its buttons |
| `setup.stage.output.before`, `setup.stage.output.after` | the two pictures |
| `prepareImages.operation.<id>`, `prepareImages.operation.<id>.picture` | an operation's toggle and picture |
| `prepareImages.chain`, `prepareImages.chain.<role>` | the strip and a thumbnail |
| `setup.step.noModel.<job>`, `setup.step.noModel.<job>.showUntied` | the "Fichero does this one" line and its link |
| `setup.findLines.clarifiedCount` | the two line counts |

## UX completeness

| Control (a11y id) | Label | Tooltip/help text | Localized key | Verified by |
| --- | --- | --- | --- | --- |
| `setup.pager` | Step N of M, <title> | — | `setup.pager.label` | [MISSING] |
| `setup.stage.output.try` | Try on these pages | the engine's time and cost line | `setup.output.try` | [MISSING] |
| `setup.stage.output.runThisStep` | Run this step | the plan's words | `setup.output.runThisStep` | [MISSING] |
| `prepareImages.operation.<id>` | the operation's name | the engine's sentence for it | `prepare.operation.<id>` | [MISSING] |
| `prepareImages.chain.<role>` | the rendition's name and figure | "Find Lines reads this one" where it does | `prepare.chain.<role>` | [MISSING] |
| `setup.step.noModel.<job>.showUntied` | Show the lines it could not tie | — | `setup.noModel.showUntied` | [MISSING] |

## Open questions for the owner

1. **Where a folder's own answers live once the picker goes.** Recommended default: the folder's context
   menu in the library, outside Set Up ("This folder's pages: two in one picture"), with Set Up saying
   only "2 folders answer for themselves". The engine's per-folder run stays as built.
2. **The window size.** 1040 by 680 is proposed; the owner may want the sheet to fill the library window
   instead. The columns are written for either.
3. **The tie's remainder and its measured threshold** (section G, `wide.nomodel.untied-remainder-kept`):
   keep the alignment on the line reader's rough read as the anchor and add the untied remainder, or ask
   for a different method. Recommended: keep the anchor, add the remainder, measure the threshold.
4. **Apple Vision's lines as a Find Lines candidate on handwriting**, adopted only on the compare's
   evidence (`wide.faded.segmenter-choices-named`). Recommended: yes, as a candidate, never the default.
5. **Clarity's default** when the paper answer is empty: on (every page) or Fichero's per-page look
   (today). Recommended: today's rule, said in words on the row.

## Rulings

- 2026-10-31 (owner, by screen share, paraphrased): Set Up becomes wide, each step's output shown as the
  person goes, moved between by swipe, arrows, Back and Next; Prepare Images becomes several selectable
  steps (split, straighten, crop, clarity) each with its own picture; the per-folder picker goes; two
  defects to find in the code: Prepare Images seems to do nothing, and one step alone cannot be started.
- 2026-10-31 (owner, second note, paraphrased): a step with no model to choose must say that Fichero does
  it and how well, with its figures on the person's pages and the unmatched lines reachable; faded pages
  need Clarity before Find Lines, said and counted on the person's sample, with the segmenter choices
  named.
