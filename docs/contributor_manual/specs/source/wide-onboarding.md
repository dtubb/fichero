# Source Model — Wide onboarding: Set Up as a pager that shows each step's output — Design Spec (#5668)

> Milestone: recipe-designer
> Manual: TBD — a section, "Setting up a project", explaining that Set Up is a row of pages the person
> moves through (swipe, arrow keys, Back and Next), that every page shows what its step makes of the
> person's own pages, how Prepare Images is four steps that can each be left out, and that nothing runs
> on the whole project before Start.
>
> Design-led (Testing Constitution). **Status: DRAFT in the guards' sense (the APPROVED tag waits on the manual
> section and the first pinning test, as `check_spec_manual_refs` and `check_specs_have_tests` require);
> APPROVED TO LAND by the owner, 2026-10-31**: written the same day from the owner's direction by screen share,
> the owner's answers of that evening are in Rulings, and one long-running builder works the build order at the
> end ("Build order for one builder") after `fix/air-engine-oom` and the pairing branch land. Tags: [OK] built
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
  whose model is a **Kraken line reader** (the project's own by `recipe.add_page_step`, else chosen by
  `assemble._choose` from the three reader cards that name the job): the reader's rough read is the anchor
  the page text is aligned to, so the step runs a model and it is the person's to choose (#6256, closed
  2026-10-28 with the registry flag `needs_a_model=True` and the candidates route; nothing on the Swift
  side was changed or pinned).
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

**Layout, macOS.** Set Up **fills the library window** (owner 2026-10-31; no fixed 1040 by 680): the
sheet takes the window's size, at least 820 by 600, and the step list stays 260. A step page is two columns: **the questions on the left** (420 points: what the
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

### G. Tie text to lines: a model step with a picker, and its figures

**Correction (owner 2026-10-31).** An earlier draft of this section said no model ties the page text to
the lines; that was wrong. The owner meant there is **no UX to choose a model** for the step. What the
code does: a model that read the whole page gives text with no lines; the step runs a **Kraken line
reader** over the lines (the rough read) and aligns the page text to those rough reads by edit distance
over the whole page (`checking/tie_text.py`), so each line gets the stretch of page text that best
matches; the match is scored by accent-blind agreement; under 0.30 the stretch is still written but
marked doubtful; a page with over half its lines untied stays a draft; the thresholds are **stated,
not measured** on real pages (the module says so). Its quality is bounded by the rough read — a faded
page the reader reads badly ties badly — which is exactly why the reader is the person's to choose: a
reader trained on this hand ties better. The step is a model step like Read, with the same picker (the
Kraken readers, installed or to download, from `step_candidates`), its default **the project's own line
reader** so the tie matches the reading, and one line saying what the step does and that only the
matching is done by the reader (#6256's three expectations).

**Why the owner cannot see the picker (the defect, `wide.picker.tie-text-picker-visible`).** #6256 was
closed on 2026-10-28 by `ad84655ee`, which changed one line of the registry (`needs_a_model=True`) and
added one engine test (the flag, and the candidates route listing the three Kraken cards). It changed
nothing in the app and pinned nothing on the screen. Read from the code, the row the app draws for the
step on the Read page (`RecipeStepsView`) gets its "Choose a Model…" button only from
`RecipeSetupStore.offersFinder` (the registry flag, loaded once per project) when the stage page is
given a project (`finder`) and Ready's fix handler, and it is a small button under the row; the stage
page's own candidate chooser, Compare on These Pages and the compare window serve only the stage's
**main step** (`mainStep(forJobs:)`, the first recipe step among the stage's jobs: `read-a-line`), so
the tie step, fourth in the Read stage, never gets the chooser the person sees for Read; and the step's
model is the line reader's own pin (`add_page_step`), so its row reads exactly like Read's row and says
nothing about tying. No test pins the row; the issue was closed on the engine half. The fix: the tie
step's row is a chooser like Read's (the three cards, the line reader marked as the default, Change…),
its sentence from the topic, and a Swift test that fails today on the row's shape.

What the person sees under the row, once the step has run on the samples: **its figures on those
pages**, "Tied 41 of 48 lines; 5 doubtful; 2 could not be tied; 1 page left as a draft", from the job's
counts, with the reader named; and a link **"Show the lines it could not tie"** that opens the sample
page in the Reader's disagreement view with the untied and doubtful lines listed (the `reject` verdicts
already written). A step that calls no model (Leave Out, Find the Documents, Prepare Images, Dates)
shows instead one line, **"Fichero does this one: <how, in the engine's words>"** (`how_it_works`);
where no method exists for a job, the line says so and names the by-hand tool, as `by_hand` does.

**The untied remainder, kept (DEFAULT taken 2026-10-31; the owner may change it).** Keep the alignment
anchored on the chosen line reader's rough read and add two things: (1) the unmatched remainder of the
page text — stretches the alignment gave no line — kept on the page as "text not tied to a line" and
shown in the same view, so nothing the page reader wrote is lost; (2) a measured threshold: the bake-off
measures tied-line agreement against the checked lines of the sample and the step shows that figure
beside its reader. A learned aligner is not proposed.

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

### J. Every step that runs a model lets the person choose it; every other step says "Fichero does this one"

The rule (owner 2026-10-31): a step that calls a model has a picker; a step that calls none says plainly
that Fichero does it, and how. What the code has today, job by job, read from `recipes/stages.py` (the
jobs each stage offers), `recipes/jobs.py` (`needs_a_model`), `recipes/assemble.py` (`FICHERO_DOES_IT`,
the `PREPARE` step, `_cloud_text_pick`), `recipes/seed/cards.yaml` (which jobs have a card at all) and
the Set Up rows (`RecipeStepsView`: "Choose a Model…" or "Find a Reader…" is drawn for every job whose
registry entry says `needs_a_model`, `RecipeSetupStore.offersFinder`; the Search step has its own field,
`SetupSearchModelField`):

| Stage | Job | Calls a model? | Picker today | What is wrong |
| --- | --- | --- | --- | --- |
| Prepare Images | `split-pages` | no (Apple Vision's outline, a system framework; no card) | none; the row shows a `builtin` pin "page-splitter" as if it were a model | should read "Fichero does this one: …" |
| Prepare Images | `prepare-the-image` | no (Vision, OpenCV; Vision's text for the turn) | none; the row shows `builtin` "image-preparer" | same |
| Find Regions | `find-regions` | yes | Choose a Model… (2 cards: Kraken `blla`, YOLO) | fine |
| Find Lines | `find-lines` | yes | Find a Reader… (2 cards: Kraken `blla`, Apple's lines) | the plan runs `blla` only; Apple's card is for print |
| Leave Out | `leave-out` | no (rules) | none; `builtin` "leave-out-rules" | should say Fichero does it |
| Read | `read-a-line` | yes | Find a Reader… (6 cards) | fine |
| Read | `read-a-page` | yes | Find a Reader… (4 cards) | fine |
| Read | `tie-text-to-lines` | **yes**: a Kraken line reader whose rough read anchors the alignment | engine built (#6256: `needs_a_model=True`, 3 cards); on screen only the small Choose a Model… under a row that reads like Read's own; no chooser, no Compare, nothing pinned | the one the owner met: the picker is not visible as a picker (section G) |
| Read | `correct` | yes | Choose a Model… (2 cards, plus keyed cloud text models) | fine |
| Read | `find-where-readers-disagree` | yes, the plan's own readers | none (built in, `needs_a_model=False`); its row names the readers | fine, said in words |
| Normalise, Translate | `translate-transliterate-normalise` | yes | Choose a Model… (2 cards, plus keyed cloud text models) | fine |
| Organise | `find-documents-in-a-folder` | no (rules over the text) | none; `builtin` "document-finder" | should say Fichero does it |
| Organise | `split-into-entries` | yes (a text model) | Choose a Model…, but **no card in the catalogue**: the finder lists only the person's keyed cloud text models, else nothing | an empty picker on a Mac with no key |
| Names | `find-names-tag-words` | yes | Choose a Model… (2 cards) | fine |
| Names | `place-in-a-gazetteer`, `link-to-authorities` | no | none (by hand, `BY_HAND_FIX`) | fine, said |
| Statements | `find-statements` | yes (a text model) | Choose a Model…, **no card in the catalogue** | an empty picker without a key |
| Dates & Times | `work-out-dates` | no (rules) | none; `builtin` "date-rules" | should say Fichero does it |
| Structured Data | `find-a-tables-cells`, `extract-to-a-table` | yes | Choose a Model…, **no card in the catalogue** | an empty picker without a key |
| Search | `make-a-vector` | yes | its own field (2 cards) | fine |
| Catalogue | `describe-for-the-catalogue` | yes (a text model) | Choose a Model…, **no card in the catalogue** | an empty picker without a key |

So the gap is not a missing button: it is (a) five no-model steps drawn as a model row with a `builtin`
pin, (b) one model step (`tie-text-to-lines`) whose picker is built in the engine and not visible as one
on the screen (section G), and (c) five model steps with no local card, whose picker is empty on a Mac
without a cloud key. The design: a step's row is one
of two shapes, decided by the engine's registry and nothing else — **a chooser** (the step's candidates
from `step_candidates`, the chosen one marked, Choose a Model… or Find a Reader…; a step with no
candidate on this Mac says "No model on this Mac does this yet: add a cloud key, or <download>" with the
nearest fix) or **"Fichero does this one: <how>"** (section G). `tie-text-to-lines` keeps
`needs_a_model=True` and gets the chooser Read has; the five text-model jobs get their cards now
(below), so no picker is empty on a Mac without a key.

**Cards for the five text-model steps** (`wide.picker.cards-for-the-text-steps`; the catalogue is
`recipes/seed/cards.yaml`, the rule that picks is the existing one: a good-enough installed local model
wins, else the cheapest priced keyed cloud model, `assemble._cloud_text_pick`):

| Job | Local cards (fine without a cloud key) | Cloud cards (a key set) | Default | Words on the row |
| --- | --- | --- | --- | --- |
| `split-into-entries` | the two MLX instruct cards already in the catalogue gain the job: Qwen2.5-VL 7B 4-bit (5.6 GB, slow: seconds a page) and 3B 4-bit (2.3 GB, its research-only licence sheet first) | the keyed frontier providers' text models from the price list (`frontier-cloud-providers.txt`), each priced a page | the installed local card, else the cheapest priced cloud card, else "No model on this Mac does this yet: download Qwen 7B (5.6 GB) or add a key" | "free, on this Mac, about N s a page" or "about $0.0x a page, pages leave this Mac" |
| `find-statements` | the same two MLX cards | the same | the same | the same |
| `describe-for-the-catalogue` | the same two MLX cards | the same | the same | the same |
| `extract-to-a-table` | the same two MLX cards | the same | the same | the same |
| `find-a-tables-cells` | the YOLO DocLayNet layout card (its `table` class finds the table; the cells by the ruling lines, OpenCV, no model) — free, fast | a keyed vision model for cells a ruling cannot find | DocLayNet plus the rules | "free, on this Mac, under a second a page" |

Each card carries `jobs`, `runs_on`, `size_gb`, `memory_gb`, `licence` and, for a cloud card, its listed
price, so the rows' words come from the card and the price list and never from the app. A Mac without
a key has a local answer for all five.

**The guardrail.** `check_setup_model_pickers.py` (named here, not yet written; its test
`test_check_setup_model_pickers.py`): for every stage in `STAGES`
and every job the stage offers (`runs_or_by_hand`), (1) a job with `needs_a_model=True` must have at
least one card in `cards.yaml` whose `jobs` name it, **or** be one of the text-model jobs
`_cloud_text_pick` serves (a constant the guard imports, so the list cannot drift), **or** be in the
guard's allowlist; (2) a job with `needs_a_model=False` must be in `FICHERO_DOES_IT`, the `PREPARE` step
or `BY_HAND_FIX`, and have a topic with `how_it_works` (so "Fichero does this one" has words), or be in
the allowlist; (3) the contract (`openapi.json`) must carry `needs_a_model` on `JobInfo`, which is what
the app's row shape reads. The allowlist is a dict at the top of the script, one line per job, each with
an issue and a reason, and **starts empty** (`NO_PICKER_YET: dict[str, str] = {}`) once the five cards
above land; it may only ever name a job that truly runs no model, and a job in it that gains a card
fails the guard as stale, so the list only shrinks. The
guard runs in `verify_all --fast` with the other `check_*.py`.

### K. Suggestions from the material: one design with the recipe designer

The branch `spec/setup-how-to-run` (merged here) added to `recipe-designer.md` the condition of the
material (`designer.material.condition-asked`, `.condition-suggested-from-a-sample`,
`.condition-feeds-the-defaults`), the page "How do you want to run this?" (`designer.how.where`,
`.model-kind`, `.what-matters`, `.access-derived-and-confirmed`, `.answers-pick-the-card`,
`.risks-in-plain-words`, `.chain-risk-on-ready`, `.what-to-check`), the defaults table
(`designer.defaults.table`, `.says-why`, `.person-wins`, `.caps-proposed-from-the-table`) and Budget
(`designer.budget.*`), with Stage 18 of its build order. This spec **does not restate them**; it is the
pager those pages sit in, and it adds the one thing the owner asked for on 2026-10-31 that they do not
say: **suggestions, each with its reason, each overridable, from the script as well as the condition**.

**One page order** (the merged design; the pager's row): Your Project → Add Material → About the
Material (kind, languages and scripts, **condition**: `designer.material.condition-asked`) → **How do you
want to run this?** (`designer.how.*`) → Choose the Stages → one page per chosen stage → Ready (plan,
**Budget**, Start). The condition and script answers steer, through the defaults table, which stages are
pre-ticked, which card each step suggests, and how the run is placed; every one of those is shown as a
**suggestion row**: the suggestion, its reason in the engine's words ("faded ink on 3 of 5 sample pages:
Clarity is on"; "the script is not Latin: the readers found for it are these two; none is installed";
"damaged handwriting: a second review pass is suggested, the compare on your pages will tell"), and
Change… beside it. The rows come from one engine list, `GET /api/recipes/suggestions` (the defaults
table's chosen rows for this project's answers, each with `why`, `from` naming the answer that fired it,
and `applied`), so the app draws and never reasons.

What came from where: the condition questions, the How page, the defaults table and Budget are the
recipe designer's (`designer.*`, 2026-10-30); the suggestion rows, their reasons and Change…, the
script's part (a reader, a segmenter or training suggested for an unusual script), and the pager they sit
in are this spec's (`wide.suggest.*`, 2026-10-31). `designer.defaults.says-why` and
`wide.suggest.reason-and-override` describe one row: the first owns the words, the second the override
and where the row is drawn. The owner's examples are rulings here: damaged handwriting may do well with
several review passes where one reader does not — so the suggestion is a try on the samples and the
person chooses (section M); an unusual script may need another reader or segmenter, or training — so
the script suggestion names the readers found for the script (`source.find.one-candidate-source`), says
when none is installed, and offers training through the existing offers (`prep.train.*`,
`source.onboard.auto.train-offer-comes`).

### L. Compare: A/B and the bake-off on the person's own page

**What exists.** The engine answers one compare shape for a page, `GET
/api/documents/{page_id}/compare-readers` (`source.compare.readers-answer`, built): the readers, the
page's lines with every reader's text as written, per-word `variants`, agreement, the line's picture,
which reading counts; the same route with `?try_stage=` answers a Set Up try's candidates matched line
for line by box (`source.compare.try-candidates-same-shape`, built). The bake-off answers rows per
candidate with CER, per-page scores (`read` with `why`), seconds, pages an hour and `cost_usd` with its
basis (`BakeoffRow`). In the app: `BakeoffSection` is a table of rows with Use This;
`StageComparisonView` plays each candidate's picture side by side with its measure words;
`StageCompareWindow` and `StageCompareColumns` draw the page's picture with each candidate's boxes
(`ShapesOverlay`) and its reading under it, one model or all, Use This One; `ReaderArtifactDiff` is a
pure LCS diff that renders two to five texts with the differences marked, in the Reader's diff lens. The
Segments pane's Compare mode and the two ways in are specified and not built (`source.compare.segments-mode`,
`source.compare.ways-in`); the designer's side-by-side text is not built (`designer.compare.side-by-side-text`).
Today, on a stage page, the pictures sit at the bottom under the table and the only comparison is by eye.

**The design: one compare view, opened from the pager.** A stage page's output column, in its done
state, has **Compare** when two or more candidates ran (a try, a bake-off, or the readers of a run); it
opens the compare view in place of the output column (the questions stay on the left) or, from the
Inspector's "Compare Readers", in the Segments pane as `source.compare.ways-in` says. The view:

1. **The same page, the same crop, for every candidate.** One page at a time (the sample strip picks
   it); every candidate is drawn on the page's **current image** (`current_page_image`) inside the
   page's box, the candidates' shapes mapped onto that one frame through `frame_map` (a try's copy and
   the project's page are the same page id; a candidate's lines carry their frame), so A and B never
   differ by a crop or a turn. The engine serves the frame with the compare answer (`image_width`,
   `image_height`, `frame`).
2. **Three ways to look**, a segmented control: **Side by side** (one column per candidate, the page
   with its boxes, its text under, `StageCompareColumns` as built, the columns scrolling together),
   **Overlay** (one picture, every candidate's boxes in its own colour with a legend, each toggled by its
   key), and **Wipe** (one picture, a vertical handle the person drags or arrows across; A to its left, B
   to its right; for a text step the two readings wipe with it). The default is Side by side on the Mac
   and Overlay on an iPhone.
3. **Per-line diff where there is text.** Under the pictures, the line rows of the compare answer: the
   line's picture, then one cell per candidate with its text as written, the differing words marked
   from `variants` with the disagreement lens's marks, agreed rows quiet, a filter "only the lines that
   differ"; for a whole-page reading (no lines yet) the two texts through `ReaderArtifactDiff`. Where
   there is truth (checked lines), the best candidate's row shows CER per line and the inserted words
   are marked (`designer.compare.side-by-side-text`'s words, built here).
4. **Price and time per candidate**, in the column head: "4.2 % CER on your 3 pages · 6 s a page ·
   free, on this Mac" or "· $0.02 a page · whole project about $18, 2 h", each figure with its basis
   (`designer.compare.row-sentence`, `designer.compare.predicts-cost-and-time`), from the bake-off row
   or the try candidate; a candidate without a measure says "not measured: <why>"
   (`designer.compare.not-measured`).
5. **Pick a winner.** Use This One under a column sets the step's model (`use-candidate`, unchanged,
   `designer.compare.person-chooses`) and the column is marked chosen; on the project's own lines (not
   a try's copies) clicking a reader's text is the per-line pick (`source.compare.pick`, `reading.choose`,
   never on a try). Review's Accept all is Review's (section M), not the compare's.
6. **Keyboard and accessibility.** ←/→ move the current candidate (and the wipe handle by 5 %), ↑/↓
   move the line, ⌥↓ the next differing line, 1–3 show one candidate alone or all, Return is Use This
   One for the current candidate, Esc closes. Each candidate column is an element "Candidate B, Kraken
   CATMuS: 4.2 % error, 6 seconds a page, free"; each line cell reads "<reader>: <text>"; a row announces
   "readers agree" or "readers differ"; the overlay's legend is a list of toggles with the colour named
   in words; the wipe handle is an adjustable element. Reduce Motion drops the wipe's easing.
7. **Empty and error states**, one sentence each from the engine: one candidate ("one reader: nothing
   to compare"), no reading on the page yet, a candidate that did not read this page (its `why`: the
   reader's error or "returned no text"), a result older than the answers (stale, section B), a try
   whose pages are copies ("these lines are a try's, not yet the project's: Use This One sets the model;
   picks come after Start"). Never an empty picture.
8. **iPad and iPhone.** The columns become a horizontal pager of candidates with the line list under;
   Overlay is the default; the wipe handle is the drag; the sample strip is a row of dots.

**What it replaces.** The caption lines of counts under the pictures (`designer.compare` appendix, fact
10) go; `StageComparisonView`'s three pictures playing side by side become the view's Side by side mode
with the real result, not the animation; `StageCompareWindow` stays as the window host for Find Lines
until the Segments pane's Compare mode exists, then opens that; `BakeoffSection`'s table stays as the
summary above the view (Use This there and here are the same press). No new pane kind, no new window
kind (the 2026-08-25 compare design and `source.compare.*` hold).

### M. The owner's rulings of 2026-10-31 on tries, Leave Out and Review

- **A live try is reused.** Start reuses a try's result on the pages it covered when the try ran the
  same step with the same card and settings on the same image signature (`never-rerun-a-model-pass`,
  #6127): those pages are counted done for that step and not run again; the run's account says "5
  pages from your try".
- **Tries show outside Set Up.** A try's results are visible in the Reader and the Inspector on the
  pages it ran on, labelled as a try's ("Try, 2026-10-31, Kraken CATMuS: not yet the project's
  reading"), never counted as the project's reading and never shown as a run's.
- **Paid tries are allowed**, with the price on the button: "Compare on These Pages, about $0.12"; the
  yes is the same `cost_ok` the try takes today, the spend booked against the project cap.
- **Review has per-line accept and Accept all.** The second model's review proposals are accepted one
  line at a time (one key) or all at once for the page ("Accept all 27"), one audited action with one
  undo for the page. This is Review's and does not change `source.compare.pick`'s per-line rule on the
  compare view.
- **Leave Out has no fixed default.** Set Up decides from the page quality of the sample (the Leave Out
  rules' own findings on the five pages: specks, marks off the page, damage read as ink; and the
  condition answers) whether Leave Out is on, and says why on the stage page as a suggestion row
  (section K); the person changes it.
- **Damaged handwriting: try the samples and let the person choose.** A condition answer of damage
  does not pick a reader or a number of review passes; it suggests a compare of the step's candidates
  (one reader against a reader with a review pass) on the samples, and the person chooses in the
  compare view (section L).
- **A large cloud vision reader turns Review on**, with its price shown, as the suggestion row's reason
  ("<reader> reads fluently and may invent: a second model reviews, about $0.03 a page"); the person can
  turn it off.

### N. Ready shows only what will run

Today's Ready page (`fichero/fichero/Views/Onboarding/RecipeReadyFields.swift`, grouped sections per
`source.onboard.ready.grouped-sections`) carries, under the plan, the comparison, Keep an export, the
training offers and then `OfferedJobsList` (`RecipeSetupPlanFields.swift`): **every job the registry
knows and the recipe does not have, each with Add**, plus `RecipeLeftOffRows` and `RecipeTakenOutRows`
(`RecipePlanEditing.swift`). That long run of steps a person could add is a stage chooser in the wrong
place. The owner's rule (2026-10-31): those belong on their **own stage pages** (Choose the Stages ticks
a stage; a stage page's left-off rows and its Put Back are where a step of that stage is added); Ready
shows **only what will run**, in run order, each step with its model, place, pages and cost
(`RecipeStepRunLine`), then the **estimate** (pages, time, the per-step basis:
`designer.budget.basis-per-step`) and the **Budget** block from the merged design
(`designer.budget.beside-the-estimate`: this run's cap, the project's monthly cap, the fixes in place),
then Start with its reason when it waits. What is skipped and why stays (it is what will not run, said
once per step in its own box); the offered-jobs list, the left-off rows and the taken-out rows leave
Ready for the stage pages; Keep an export and the training offers stay as the two optional sections.

### O. Release: Monday only if solid, and a hold that costs the rest nothing

The owner's rule (2026-10-31): the wide Set Up goes into Monday's release **only if it is solid**; each
step is proven on real test pages with tests to the spec; if the Start gate or the Air try is not green
on Sunday night, the wide Set Up **stays out of the release rather than holding it**.

**Solid, per step, means all of:** (1) the step's behaviours in this spec are tagged [OK] with their
tests named and green: the engine tests under `PYTHONPATH` on the tree's `fichero-server/src`, run by
the builder after each slice and by the manager on the combined tree; the Swift tests run on a Mac
whose XCTest host works (the Pro's `testmanagerd` is stuck: the Air, or the Pro after a restart), by
the manager, never while the owner's app is open; (2) a **real run** on a scratch copy of a real test
set under the dev test folder — the photographed notebooks for Prepare Images (split, straighten, crop,
clarity each seen in the chain strip on a real page), a box of handwritten pages for Read, Tie text to
lines and the compare — driven by `scripts/realrun_check.py` against the dev engine and read by eye in
the app by the manager, with the figures (pages prepared, lines tied, candidates compared) written in
the handoff; (3) the owner has pressed through the pager once on the dev build from Xcode (swipe, keys,
Back and Next, one Compare, one Run this step) and said nothing is wrong.

**The two Sunday-night checks.** The **Start gate**: `scripts/gate part recipes` on the combined tree
(lint, build, the recipes Swift tests, the recipes engine tests, the perf ratchet) plus
`verify_all --standard` and every `scripts/check_*.py`, zero failed. The **Air try**: the release
candidate's dev DMG installed on the Air, the scratch project set up through the wide pager end to end
and started, the run finishing with every step's account non-empty and the Prepare Images chain and the
compare seen on real pages, by the manager over SSH with the owner's GUI session for the screen. Either
one red means the wide Set Up ships off.

**The hold.** The wide pager, the operation rows, the output column, the compare view and the Ready cut
sit behind one feature flag, `wideSetUp` (`FeatureManager`, a persisted flag like the others, under
Settings › Features; off by default in the release tier of `FeatureTiers.generated.swift`, on in the
dev tier). Off, the window is today's: the step list, the tall form, the Prepare Images card as it is,
Ready as it is; the engine changes of Stages 1, 2, 7 and 9.1 (the defects fixed, the operations in the
listing, the cards, the image-chain route, the compare answer's frame) ship either way, because they are
additive and pinned. So the release decision on Sunday is one line in the tiers file, touching nothing
else; and the builder lands slices on `integration` as they go green, behind the flag, never on a
branch held back.

## Behaviors

### The pager

- `wide.pager.swipe-arrows-back-next` — **[PARTIAL]** (#5668) the Set Up window's content is a pager over `SetupFlow.steps`: a horizontal trackpad swipe, ← and → (and ⌘[ ⌘]) with focus outside a text field, and the footer's Back and Next all move one page; the step list on the left still jumps to any page; a forward move saves the draft the page's Continue saves; a page Continue cannot leave bounces back with its reason beside Next (`SetupFooter.waitsFor`). *Test:* Built 2026-10-31 (Swift, pure): `SetupPager.advance`/`retreat`/`jump`, the bounce, `savesDraftOnAdvance`; the keys (← →, ⌘[ ⌘]) and a horizontal drag are bound to it in `FirstRunWindow+Pager.swift` behind `wideSetUp` (written 2026-10-31, not yet compiled or run); a forward move runs the page's `advance()` and is held where the footer already shows its reason. Not yet written: the trackpad two-finger swipe (a scroll event, not a drag), and the footer's Back/Next reduced to the same model. `SetupPagerTests.swift` (written: the move rules over a step list, the bounce; compiled on the Air, not yet run), `fichero/Tests/Unit/general/Views/Onboarding/SetupFooterTests.swift`. Manual: TBD.
- `wide.pager.window-is-wide` — **[PARTIAL]** (#5668; owner 2026-10-31) on the Mac Set Up fills the library window (at least 820 by 600) with the 260-point step list; a stage page is two columns, questions 420 wide on the left and the output on the right (at least 320), Ready one column; on iPad and iPhone the list collapses to "3 of 9" with page dots and the columns stack in one `TabView` page. *Test:* Built (pure): `SetupPager.Layout.of(.mac/.compact)`; the sheet and the columns are not yet written. `SetupPagerTests.swift` (`widths`), `fichero/Tests/Unit/general/Views/Onboarding/SetupSheetFitsTests.swift`. Manual: TBD.
- `wide.pager.accessible` — **[PARTIAL]** (#5668) the pager is one accessibility element containing its page, labelled "Step N of M, <title>"; a page change posts the new label; every control is reachable by Tab and nothing is swipe-only; Reduce Motion cross-fades instead of sliding and the pictures hold their last frame. *Test:* Built (pure): `SetupPager.label`, `compactPosition`, `transition(reduceMotion:)`; the accessibility element and the posted change are not yet written. `SetupPagerTests.swift` (`label`, `motion`), `fichero/Tests/Unit/general/Models/StageShowcaseTests.swift` (the last frame, built). Manual: TBD. Written 2026-10-31 (`FirstRunWindow+Pager.swift`, behind `wideSetUp`): the label from `SetupPager.label` is the pager's accessibility label and is announced on each move, the slide becomes the default animation unless Reduce Motion; not yet compiled or run.
- `wide.pager.position-restored` — **[PARTIAL]** (#5668) Set Up… reopens on the page the person left and the sample page they were looking at, per project on this Mac; a page no longer in the flow falls back to Choose the Stages; try results and answers come from the engine, never from the app's memory. *Test:* Built (pure): `SetupPager.restored(savedId:in:)`; where the id is kept per project is not yet written. `SetupPagerTests.swift` (`restore`). Manual: TBD.

### The output column

- `wide.output.four-states` — **[PARTIAL]** (#5668, #5806) every stage page's output column is in one of four states from the engine's try result: not tried (the picture on the example, the sample strip, "Try on these N pages" with the engine's time and cost line), running (progress in place, Stop), done (the sample page before and after, the step's marks, the measures in words, Use This where compared), refused or failed (the engine's sentence and the one fix it names); never an empty column. Built 2026-10-31 (Swift, pure): `StepOutputState.of` works the state out from the try store's result, refusal, cost question and the listing's revision; the state line is `StepOutputStateView` (written 2026-10-31, behind `wideSetUp`, in `SetupStageSamples`; not yet compiled or run); the example, the strip and the before-and-after are still the existing views. *Test:* `StepOutputStateTests.swift` (written; compiled on the Air, not yet run), `fichero-server/tests/unit/recipes/test_stage_try_does_not_wait_or_hide_5806.py` (the engine's sentences, built). Manual: TBD.
- `wide.output.before-and-after-on-his-page` — **[PARTIAL]** (#5668) (2026-10-31: `StageShowcaseSection` plays the stage on the person's sample page and `RenditionChainStripView` shows each step's picture of it, behind the flag; the side-by-side with the step's marks on the right-hand picture is not built) for a page stage the done state shows the current sample page as it came in on the left and as the step leaves it on the right, with the step's marks on the right-hand picture: the page box and corners, the gutter, the lines, the reading beside; the person steps through the sample pages with the strip; the pictures are the person's pages from the project's storage and the example page is never shown as output. *Test:* `StepOutputStateTests.swift` (not yet written: the right-hand picture's source is the try's page id, never the bundled example; the marks per stage), `fichero/Tests/Unit/general/Models/StageFoundModelsTests.swift` (the samples are his, built). Manual: TBD.
- `wide.output.stale-says-so` — **[PARTIAL]** (#5668) the try result carries `answers_revision`, the stage listing carries the current revision, and a result older than the answers or the chosen card is shown dimmed with "Tried with the earlier answers; try again"; it is never replayed as current. Engine built 2026-10-31 (`stages.answers_revision`: a hash of the stage's own answers, the Prepare Images operations and its steps' models; on the try result and on the listing); the Swift model is built (`StepOutputState.isStale`, `SetupStageTryResult.answersRevision`; compiled on the Air, not yet run), the dimmed view is `StepOutputStateView` with `opacity(of:)` (written, not yet compiled or run). *Test:* `fichero-server/tests/unit/recipes/test_stage_try_result_follows_its_job_5806.py` (`test_wide_*`), `StepOutputStateTests.swift` (`doneAndStale`). Manual: TBD.
- `wide.output.run-this-step` — **[PARTIAL]** (#5806) a stage page's output column has Run this step: the Start route with `only` that stage's step ids over the whole project, the plan's words first (pages, time, cost, what is skipped and why); it lands on the run as Start does (`source.onboard.auto.lands-on-the-run`). Engine built 2026-10-31 (`GET /api/recipes/project/start?steps=a,b` and `POST /api/recipes/project/start {steps: [...]}`: the plan limited to those step ids over the whole project; an id the recipe lacks is a 422); the button is `StepOutputStateView`'s Run This Step over `RecipeSetupStore.start(steps:)` (written, not yet compiled or run; it lands on the run as Start does, the plan's words first are not yet shown). *Test:* `fichero-server/tests/unit/recipes/test_start_plan.py` (`test_wide_run_this_step_*`), `SetUpButtonsActTests.swift` under `fichero/Tests/Unit/general/Views/Onboarding/` (built; add the button). Manual: TBD.

### Prepare Images as steps

- `wide.prepare.four-operations-listed` — **[OK]** (#5382, #5580) the stage listing for Prepare Images carries `operations` in order — split, straighten, crop, clarity — each with its id, its sentence in the engine's words, its default from the questions, and whether it is on; the choice is one answer `prepare_operations`; an operation switched by hand wins over its question. Built 2026-10-31 (`recipes/prepare_operations.py`; `SetupStage.operations` on the listing; an unknown id in `prepare_operations` is refused in words). *Test:* `fichero-server/tests/unit/recipes/test_setup_stages_5668.py` (`test_wide_*`: the four in order, the defaults from each answer, the hand wins, an unknown id refused), Built 2026-10-31 (Swift, behind the flag): `PrepareOperationRows` (pure) and `PrepareOperationRowsView` on the Prepare Images card, a switch per operation with the engine's sentence, `prepareImages.operation.<id>`; the switch writes the whole `prepare_operations` list. `PrepareOperationsTests.swift` (written; compiled on the Air, not yet run). Manual: TBD.
- `wide.prepare.plan-runs-only-chosen-operations` — **[OK]** (#5382, #5580) the Start plan's `prepare` card carries `operations`; `run_prepare` runs only those (turn and straighten under straighten; find the page, square, flatten and the blank mark under crop; the contrast step under clarity); split off takes `split-pages` out of the plan as the explicit no does; every operation off is a plan with no `prepare` run and Start says so. Built 2026-10-31 (`prepare_operations.to_run`/`split_is_off`; `crop_pages(operations=…)`; the stamp holds the operations; a `prepare` card from before the operations existed runs as it did). *Test:* `fichero-server/tests/unit/recipes/test_prepare_step_setup.py` (`test_wide_*`: the card's operations from the questions and from the hand, every operation off, split off, one case per operation run alone, the stamp follows the operations), `fichero-server/tests/unit/recipes/test_start_plan.py`. Manual: TBD.
- `wide.prepare.operations-run-on-every-page` — **[OK]** (#5390, #5706; found on the owner's screen 2026-10-31, cause 1 under section F) straighten and clarity run on a page whether or not the paper was found: today `crop_pages` runs `_prepare` only inside the trusted-finder branch, so a page the finder is unsure of gets no turn, no straighten and no contrast, and the card's sentence promises what does not happen. Fixed: when the finder is not trusted the page itself is the base (no crop, no square, no flatten) and turn, straighten and clarity still run on it, each a rendition only when it changed something. Fixed 2026-10-31 (`page_crop._turn_and_straighten` runs on the whole picture, the photograph's own frame, when no paper is found; the contrast step already ran on every page). *Test:* `fichero-server/tests/unit/media/test_turn_straighten_blank.py` (`test_wide_prepare_*`: an unfound page is still turned and straightened; a level upright one writes nothing), `fichero-server/tests/unit/recipes/test_prepare_images_step.py`. Exception (reviews 8, 9): a page left whole that has any saved transcription (including one from Find Lines, an import or another reader, and one whose line readings were retracted) and no rendition of this step is not turned or straightened, by a normal run or by Redo, because the new image would make the next read pay again (same input, same model: reuse). It is straightened only by Redo after all its artifacts are removed. The four kinds of page that count as read: lines found and never read (Find Lines saves an empty `blla` transcription), every line reading retracted, imported text only, and read by another reader only; all fail in the safe direction (not turned or straightened, no re-read); Clarity may still write `prepared` on a faded page, and the next whole-page read then pays. Named limits for the owner: Redo on a read whole page reports `whole` and changes nothing; an unstamped cut page (Case B, a cut page from an older build with no stamp) pays one re-read after Prepare cuts it again (accepted 2026-11-01). Tools that answer about the picture as a whole (describe, caption, tags, classify, layout, objects, quality, scene, style, faces, colors, safety, diagram) reuse a saved result across Prepare's images (owner ruling 2026-11-01, `llm_base._prepare_image_reused`): a result made from the photograph or a rendition answers for any of them, so the page IS straightened; a result made from a person's edit answers only that same edit. A whole-page transcription is for the image it was read from: a page never prepared, then cut or cleared by Clarity, pays one more read (named limit, also on integration); `handwriting` and `classify_script` send every time (force_ocr, separate issue). Named limits of this reuse: faces, objects and layout hold position words, not boxes, and those words stay as saved, so a quarter turn or a cut can make them wrong; a result saved on a rendition by a build that did not record the image's kind counts as an edit, so it pays once when the image changes. *Test:* `tests/unit/recipes/test_page_crop_writes_page_region.py` (`test_a_skewed_whole_page_*`), `tests/unit/workflows/test_prepare_keeps_read_pages_from_paying_again_6296.py`, `tests/unit/workflows/test_vision_tools_reuse_across_prepare_6296.py`. Manual: TBD.
- `wide.prepare.rerun-follows-the-answers` — **[OK]** (#5706; cause 2 under section F) the `page_prep_stamp` holds the file, the rules' version and the page operations the page was prepared with (`operations`: crop, straighten), and nothing else: the paper answer and Clarity change neither operation's output, so ticking faded or switching Clarity leaves the page `unchanged`, its renditions are not rewritten and its image signature stays (a new signature makes Read read the page again, `never-rerun-a-model-pass`). A page prepared with other page operations is prepared again, and so is one whose file changed. A stamp from before the operations existed (version 2) still holds for a page it cut and is stale only for a page it left whole, which is now turned and straightened. Fixed 2026-10-31 (`crop_pages(signature=…)`, `_stamp_holds`, `PREP_VERSION` 3; review H1). *Test:* `fichero-server/tests/unit/recipes/test_prepare_images_step.py` (`test_wide_the_stamp_follows_only_the_page_operations_*`, `test_wide_a_stamp_from_before_the_operations_*`, `test_wide_the_stamp_keeps_a_changed_file_*`). Manual: TBD.
- `wide.prepare.ticked-later-still-runs` — **[OK]** (#5706; cause 4 under section F) a stage ticked in Set Up… after the project's first Start is in the next Start's plan: with no proposal the next Start plans the whole recipe, so the gained step is in it and nothing is narrowed; a proposal that exists gains the step (`write_proposed`), so `only` holds it, and a stage taken out leaves it. A proposal is never created from the gained steps alone: it would drop every other step from the next Start (review M1). Fixed 2026-10-31 (`_propose_steps_gained` in `project.save_setup`); not built: the proposal write is not in the save's before/after, so Undo of the save does not restore it. *Test:* `fichero-server/tests/unit/recipes/test_start_plan.py` (`test_wide_a_stage_ticked_after_the_first_start_is_in_the_next_plan`). Manual: TBD.
- `wide.prepare.folder-picker-removed` — **[PARTIAL]** (behind `wideSetUp`; the old picker shows when the flag is off; `PrepareImagesCard.ownAnswersLine`) (#5580) the "Answer for one folder" picker and its folder list leave the Prepare Images page; the engine keeps reading `job_answers_by_folder` and a project that has folder answers keeps them, said on the page in one line ("2 folders answer for themselves") with no list of names. *Test:* `fichero/Tests/Unit/general/Models/PrepareImagesFolderAnswersTests.swift` (built; the engine half stays), `PrepareOperationsTests.swift` (not yet written: the page has no picker; the one line's count). Manual: TBD.

### The pictures

- `wide.picture.one-per-operation` — **[PARTIAL]** (behind `wideSetUp`: `StagePictures+Operations.swift`, `PrepareOperationPicture` per operation, the stage plays the four in turn; `PrepareOperationRowsView` shows each at its last frame beside its switch, with no Replay there; a `#Preview` per operation; written, not compiled or run by the worker that wrote the previews and the duration test) (#5668) each of the four operations has its own SwiftUI picture drawing one frame from a progress of 0 to 1 (split: the halves part at the gutter; straighten: the page turns upright and its lines settle; crop: a dashed box with corner handles draws around the paper and the table falls away; clarity: the page brightens and its ink darkens under the light sweep), 3.5 seconds, Replay, the last frame under Reduce Motion, each with its sentence for VoiceOver; the stage's own picture plays the four in turn. *Test:* `fichero/Tests/Unit/general/Views/Onboarding/StageShowcasePicturesTests.swift` (built; add the four: a frame at 0, 0.5 and 1 differs and the last frame is still), `fichero/Tests/Unit/general/Models/StageShowcaseTests.swift`. Manual: TBD.

### The rendition chain

- `wide.chain.served-by-the-engine` — **[OK]** (#6296, #5386) `GET /api/pages/{id}/image-chain` answers the page's current image (`read_from`: original, edited or rendition), the renditions in the order they were made with role, the row's figures in words from `transform` and `note`, which one every later step reads (`reads_this`), and each passed-over rendition with its reason (`PageImage.why`); the same answer Preview's rendition axis reads (`axis`: the ids in `order_renditions` order). Built 2026-10-31 (`media/image_chain.py`, `GET /api/pages/{id}/image-chain`; the bytes are the existing `/api/documents/{id}/renditions/{rendition_id}/content`). *Test:* `fichero-server/tests/unit/media/test_current_image_6296.py` (`test_wide_chain_*`), `fichero-server/tests/unit/media/test_image_chain_route.py` (a real Prepare Images run read back as a chain; the words; passed over; an edit; 404). Manual: TBD.
- `wide.chain.strip-on-the-page` — **[PARTIAL]** (behind `wideSetUp`: `RenditionChainStrip.swift`, `RenditionChainStripView` under the first sample page; the "nothing written" mark is not built: the engine serves no such field) (#5668, #5386; cause 3 under section F) the Prepare Images output column shows the sample page as the operations left it and under it the chain strip: the photograph then each rendition as a thumbnail with its operation's name and figure, "Find Lines reads this one" on the one the current-image rule returns, a passed-over rendition's reason, and "nothing written" on an operation that changed nothing; clicking a thumbnail shows it. *Test:* `RenditionChainStripTests.swift` (not yet written: the strip's rows from an image-chain answer; the reads-this mark; the nothing-written row). Manual: TBD.

### Start and the one step

- `wide.start.enabled-on-any-run` — **[PARTIAL]** (#5806, #5801; found on the owner's screen 2026-10-31, section F) Start is enabled when the engine's plan has any run and no refusal, whatever the card (`runs`, not `workflows`); the footer says what will run; "Nothing in this plan runs yet: every step is skipped" is said only when the engine's plan says it. Today `canStart` requires a workflow, so a plan whose only steps are Prepare Images (with split off), Find Regions, Leave Out, Find the Documents, Catalogue or Search cannot be started from the app although the engine would run it. Engine half pinned 2026-10-31 (`plan_start` gives `runs` and no refusal for a card-only recipe: `test_wide_a_plan_whose_only_step_is_a_card_has_a_run_and_no_refusal`); the app half is built 2026-10-31 (`RecipeSetupStore.canStart` is true when the plan has any run or any workflow and no refusal, so `startDisabledReason` says "every step is skipped" only for a plan with neither); compiled on the Air, not yet run. *Test:* `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift` (`startReadsRunsNotWorkflows`: a plan with one `prepare` run and no workflow can start and its reason is nil; a plan with neither cannot), `fichero-server/tests/unit/recipes/test_start_plan.py` (the plan's `runs` for a prepare-only recipe). Manual: TBD.

### A step with no model to choose

- `wide.nomodel.fichero-does-this-one` — **[PARTIAL]** (#5721, #5668) a step whose job has no model to choose (Leave Out, Find the Documents, Prepare Images, Dates & Times) shows no chooser and no radio row but one line, "Fichero does this one: <how>", from the topic's `how_it_works`; a job nothing does yet says so with its by-hand tool. Engine half built 2026-10-31 (`JobInfo.how_it_works`); the row is Swift, not yet written. *Test:* `fichero-server/tests/unit/recipes/test_tie_text_to_lines_picks_a_reader_6256.py` (built; add: the step's `how` names the anchor, not a model to choose), `TieTextStepTests.swift` (not yet written: the row's words for a no-model step). Manual: TBD.
- `wide.nomodel.tie-figures-on-his-pages` — **[PARTIAL]** (#5721, #5720) after Read has run on the samples the Tie text to lines row shows, under its chooser, its figures from the job's counts — tied, doubtful, could not be tied, pages left as a draft — and "Show the lines it could not tie" opens the sample page in the Reader's disagreement view with the untied and doubtful lines listed from their `reject` verdicts. Built 2026-10-31 (engine): the Read try runs the tie on each candidate's copy (`samples._tie_on`) and the result and each candidate column carry `tie`: `counts` (the job's totals) and `pages` (per project page id: `tied`, `doubtful`, `untied`, `draft`), from `per_page` on the tie job's result. Swift: the figures line is `StepResultFiguresView` (written, behind `wideSetUp`, not yet compiled or run). Not built: the link into the disagreement view. *Test:* `fichero-server/tests/unit/recipes/test_tie_text_counts_on_the_stage_try.py` (built), `TieTextStepTests.swift` (not yet written); the figures' words are built in `StepRowWords.tieFigures`/`offersUntied` (`StepRowWordsTests.swift`, compiled on the Air, not yet run), the link is not yet written. Manual: TBD.
- `wide.nomodel.untied-remainder-kept` — **[GAP]** (#5721; DEFAULT taken 2026-10-31, the owner may change it) the stretches of the page text the alignment gives no line are kept on the page as text not tied to a line and shown in the same view, so nothing the page reader wrote is lost; the tie threshold is measured by the bake-off against the checked lines of the sample and the figure is shown beside the step. *Test:* `fichero-server/tests/unit/media/test_transcript_alignment.py` (built; add the remainder), `test_tie_text_remainder.py` (not yet written). Manual: TBD.

### Faded pages and Find Lines

- `wide.faded.find-lines-reads-the-clarified-copy` — **[PARTIAL]** (#6271, #6296) Find Lines segments the page's current image, which is the `prepared` rendition once Clarity has written one, and its lines map back to the photograph. Built: the current-image rule and the `prepared` rendition read as the photograph's frame (`_same_frame_map`). Built 2026-10-31: the `prepared` rendition carries its own transform (the whole page) like the other operations' (`test_wide_faded_the_prepared_rendition_*`). Not built: anything the person sees of it. *Test:* `fichero-server/tests/unit/media/test_current_image_6296.py` (built), `fichero-server/tests/unit/recipes/test_find_regions_inside_page.py`. Manual: TBD.
- `wide.faded.line-counts-before-and-after` — **[PARTIAL]** (#6271) the Find Lines page's output column shows, for a sample page the paper answer calls faded or Clarity measured faded, the line count on the photograph and on the clarified copy side by side, the compare window drawing both, and Use the clarified copy; with Clarity off and a faded sample it says so with a link to Prepare Images. Built 2026-10-31 (engine): the Find Lines try result carries `line_counts` (`samples.line_counts_on_both`): per project page whose current image is a `prepared` rendition, the lines Kraken's segmenter finds on the photograph and on the clarified copy, and `not_clarified`, the pages with no such copy (the app joins that with the paper answer to say Clarity is off). Swift: the per-page counts and the Clarity-off note are `StepResultFiguresView` (written, behind `wideSetUp`, not yet compiled or run; the note is shown for any page with no clarified copy, the join with the paper answer is not yet written). Not built: the compare window drawing both, Use the clarified copy. *Test:* `fichero-server/tests/unit/recipes/test_find_lines_try_counts_on_both_images.py` (built), `StepOutputStateTests.swift` (not yet written); the words are built in `StepRowWords.lineCounts`/`clarityOff` (`StepRowWordsTests.swift`). Manual: TBD.
- `wide.faded.segmenter-choices-named` — **[PARTIAL]** (#6271, #5668) the Find Lines page names its segmenter cards from the one candidate source — Kraken `blla`, Apple Vision's lines — and the person picks and compares them there; the Apple Vision line card is offered on handwriting as a candidate, adopted only when the compare shows it finds more lines that read no worse; a vision model's boxes stay a Detect Regions node option until a plan card exists. Built: the two cards, the per-stage rows, the bake-off compare. Built 2026-10-31: Apple's card is offered on handwriting as a candidate to compare (`compare_on: [handwriting]` on its seed card, `assemble.offered_to_compare`): listed with no rule rank and not in the rules, joins the Find Lines try beside Kraken's when there is room, and the assembled default stays Kraken. Not built: the vision-model card. *Test:* `fichero-server/tests/unit/recipes/test_model_chooser_per_step_5668.py` (built, `test_wide_apples_line_card_*`, `test_wide_the_find_lines_try_compares_*`), `fichero-server/tests/unit/recipes/test_stage_compares_candidates_5668.py`. Manual: TBD.

### Every model step has a picker; every other step says Fichero does it

- `wide.picker.row-shape-from-the-registry` — **[PARTIAL]** (#5721, #6052; section J) a step's row is one of two shapes decided by the registry's `needs_a_model` and nothing in the app: a chooser (the step's candidates from `step_candidates`, the chosen one marked, Choose a Model… or Find a Reader…) or "Fichero does this one: <how>"; today five no-model steps (`split-pages`, `prepare-the-image`, `leave-out`, `find-documents-in-a-folder`, `work-out-dates`) are drawn as a model row with a `builtin` pin. Fixed: a `builtin` pin is never drawn as a model; the row shape follows `needs_a_model` alone. Engine built 2026-10-31 (`JobInfo.how_it_works` carries the words of 'Fichero does this one' for a job with no model; the topics of Leave Out, Split pages and Find documents gained their `How it works:` text); the Swift row is not yet written (Step 7.1 Swift). *Test:* `fichero-server/tests/unit/recipes/test_setup_stages_5668.py` (`test_wide_every_stage_jobs_row_shape_*`: every stage job's `needs_a_model` matches the table in section J and says how where it runs no model), `TieTextStepTests.swift` (not yet written: the row shape per job from a stage listing). Manual: TBD.
- `wide.picker.tie-text-picker-visible` — **[PARTIAL]** (#6256, closed on the engine half 2026-10-28 and to be reopened; section G) the Read page's Tie text to lines row is a chooser like Read's: the three Kraken reader cards from `step_candidates`, the project's own line reader marked as the default, Change…, and one sentence from the topic saying the step matches the page text to the found lines and only the matching is done by the reader; today the engine lists the candidates (`ad84655ee`) but the row shows the line reader's pin as Read's row does, the stage page's chooser and Compare serve only the stage's main step, and nothing pins the row. Engine half built 2026-10-31 (`assemble.tie_follows_the_line_reader`: the assembled tie step's default is the project's line reader where that is a Kraken reader); the Swift row is still to build and is what the owner sees. *Test:* `TieTextStepTests.swift` (not yet written: from a stage listing and a recipe with a tie step, the row model is a chooser with three candidates and the line reader as default); `fichero-server/tests/unit/recipes/test_tie_text_to_lines_picks_a_reader_6256.py` (`test_wide_the_assembled_tie_step_defaults_to_the_projects_line_reader`). Manual: TBD.
- `wide.picker.cards-for-the-text-steps` — **[PARTIAL]** (#6052; section J) the catalogue carries cards for `split-into-entries`, `find-statements`, `describe-for-the-catalogue` and `extract-to-a-table` (the two MLX instruct cards gain the jobs; the keyed cloud text models through `_cloud_text_pick`) and, as written, for `find-a-tables-cells` (not true: see Left below); each step's default is the installed local card, else the cheapest priced cloud card, else the sentence naming the download or the key; a Mac without a key has a local answer for all five. **Corrected 2026-10-31 after reading the code:** four of the five already list local candidates without a key (`discovery.other_text_cards`: Qwen3-4B and Llama-3.2-3B text MLX models to download, any installed text model, Apple Intelligence; `discovery.TEXT_MODEL_JOBS`), so their picker was never empty; the two Qwen2.5-VL cards were deliberately not given the jobs, because a card in `cards.yaml` that names a job makes the rules pick it and plan a 5.6 GB download as the default, against the default above. **Left, [GAP] (#6326):** `find-a-tables-cells` is a job of the Structured Data stage (`stages.py`, added by the `tables` goal in `assemble.py`) and nothing can run it: no card in `cards.yaml` names it, `plan_start` has no branch for it, no runner writes table cells, so `start_runs` is false and its picker is empty; `GET /api/recipes/candidates` for it says "add a cloud key", which is false because no cloud card does it either. Needed, in order: a card (a layout or table-structure model), a `plan_start` branch with a runner that writes `table_cells`, and the guard then checks it on its own. *Test:* `fichero-server/tests/unit/recipes/test_one_candidate_source_5808.py` (`test_wide_each_text_step_lists_a_local_candidate_without_a_cloud_key`). Manual: TBD.
- `wide.picker.empty-says-why` — **[OK]** (#6052; section J) a model step with no candidate on this Mac (a card not yet downloaded and no cloud key) does not show an empty chooser: it says "No model on this Mac does this yet" with the nearest fix (add a cloud key, or the download the catalogue names once a local card exists). Built 2026-10-31: `GET /api/recipes/candidates` carries `why` and `fix` when no candidate can run on this Mac now (the smallest download with its size, else adding a key); the Swift row that shows it is Step 7.1 Swift. *Test:* `fichero-server/tests/unit/recipes/test_one_candidate_source_5808.py` (`test_wide_nothing_installed_says_so_with_the_nearest_fix`), `TieTextStepTests.swift`. Manual: TBD.
- `wide.picker.guard` — **[OK]** (#6052; section J) `check_setup_model_pickers.py` fails the fast gate when a stage job with `needs_a_model=True` has no card in the catalogue and is not a text-model job `_cloud_text_pick` serves and is not allowlisted, when a job with `needs_a_model=False` has no `FICHERO_DOES_IT`, `PREPARE` or `BY_HAND_FIX` entry with a `how_it_works` topic, when `JobInfo.needs_a_model` is missing from the contract, or when an allowlist entry is stale; the allowlist is one line per job with its issue and reason. Built 2026-10-31 (`scripts/check_setup_model_pickers.py`, which counts `discovery.TEXT_MODEL_JOBS`, the real source of the text-model candidates, where this text said `_cloud_text_pick`'s three). *Test:* `fichero-server/tests/unit/scripts/test_check_setup_model_pickers.py` (a scratch registry with one unlisted model job fails, one allowlisted passes, a stale entry fails; the real registry passes). Manual: TBD.

### Suggestions from the material

- `wide.suggest.one-list-from-the-engine` — **[PARTIAL]** (#6052; section K; the rows' words are `designer.defaults.says-why`) `GET /api/recipes/suggestions` lists, for this project's answers, every default the defaults table chose — a stage pre-ticked, a step's card, a review pass, where the work runs, a cap — each with `why` in words, `from` (the answer that fired it: a condition, the script, the material's kind, the How answers), `applied`, and `change` (the step or question Change… opens); the app draws the list and reasons about none of it. *Test:* `test_suggestions_route.py` (not yet written: faded on three of five gives the Clarity row with its why; a non-Latin script gives the readers-found row; no answer gives no row). Manual: TBD.
- `wide.suggest.reason-and-override` — **[PARTIAL]** (#6052; section K) a suggestion is a row on the page it concerns (About the Material, How, the stage page, Ready): the suggestion, its reason, Change…; changing it is the person's choice and wins (`designer.defaults.person-wins`), the row then saying "yours" and keeping the engine's reason beside it; a suggestion never acts by itself beyond being the default it already is (open question 8). *Test:* `SuggestionRowTests.swift` (not yet written: the row's three parts from a listing; Change… writes the answer; the yours mark). Manual: TBD.
- `wide.suggest.script-steers-reader-segmenter-training` — **[PARTIAL]** (#6052, #5808; section K) a script with no installed reader gives a suggestion row naming the readers found for it (`source.find.one-candidate-source`), that none is installed, and the training offer where corrections could make one (`prep.train.*`); a script with no reader found says so and names the nearest (`source.onboard.nothing-fits-names-nearest`); the row never picks a reader by itself. *Test:* `test_suggestions_route.py`. Manual: TBD.
- `wide.suggest.damage-suggests-a-try` — **[PARTIAL]** (#6052; owner 2026-10-31, section M) a condition answer of damaged handwriting gives a suggestion row for a compare on the samples — the step's reader alone against the reader with a review pass — with its price, and the person chooses in the compare view; it never sets the review passes by itself. *Test:* `test_suggestions_route.py`. Manual: TBD.

### Compare

- `wide.compare.one-view-from-the-pager` — **[GAP]** (#5900, #6052; section L) a stage page whose output has two or more candidates shows Compare, which opens the compare view in the output column (the questions stay); the Inspector's Compare Readers opens the same view in the Segments pane (`source.compare.ways-in`); no new pane kind and no new window kind. *Test:* `CompareViewTests.swift` (not yet written: Compare appears at two candidates and not at one; the two doors open the same model). Manual: TBD.
- `wide.compare.same-page-same-crop` — **[PARTIAL]** (#5900, #6296; section L) the boxes follow the picture shown, which is the page's saved edits when it has any, else the photograph (a rendition is not shown). A page with saved edits and a known frame (`frame.followed`) draws each line's `frame_bbox` at `frame.image_width/height`; one whose frame cannot be followed draws no box (a wrong box is worse) and says so under the picture; any other page draws `bbox` at the photograph's size. The compare answer carries `frame` (which image, its size, `followed`, a note) and `CompareLine.frame_bbox` through `frame_map`. Engine built 2026-10-31; the drawing is built, unrun. (The engine's `followed` description still says "drawn on the photograph": the app does not draw on an unfollowed edited frame.) *Test:* `fichero-server/tests/unit/api/test_compare_readers_5900.py` (`test_wide_*`), `CompareViewTests.swift` (`drawnBoxFollowsThePicture`, `noBoxesSaysWhy`). Manual: TBD.
- `wide.compare.three-modes` — **[PARTIAL]** (#5900, #6052; section L) Side by side (one column per candidate, boxes and text, columns scrolling together), Overlay (one picture, each candidate's boxes in its colour, a legend of toggles) and Wipe (one picture, a handle dragged or arrowed across, A left and B right, the texts wiping with it); Side by side is the Mac's default, Overlay the iPhone's. Built 2026-10-31 (Swift, pure): `CompareViewModel` (the default mode per platform, the legend toggles, the wipe handle and pair, the characters that wipe); no view yet. *Test:* `CompareViewTests.swift` (`defaultModes`, `legend`, `wipe`; compiled on the Air, not yet run). Manual: TBD. Swift view written 2026-10-31 (`CompareReadersView` over `CompareReadersStore`, shown in `StageCompareWindow` behind `wideSetUp`; not yet compiled or run): the three modes are text-only layouts under the page with its lines boxed (no per-reader boxes: the engine answer has one box per line); the per-line pick posts `readings/choice` with kind `transcription` (unchecked against a real page).
- `wide.compare.per-line-diff` — **[PARTIAL]** (#5900, #6052; section L; the words of `designer.compare.side-by-side-text`) under the pictures, the compare answer's line rows: the line's picture, one cell per candidate with its text as written, differing words marked from `variants` with the disagreement lens's marks, agreed rows quiet, a filter for the lines that differ; a whole-page reading with no lines goes through `ReaderArtifactDiff`; with truth, CER per line on the best and inserted words marked. Built (Swift, pure): `CompareViewModel.rows` (a text per reader, the words with variants, the differs filter); not built: the rows' view, the per-line CER and inserted words, the page-reading diff. *Test:* `CompareViewTests.swift` (`rows`), `fichero/Tests/Unit/general/Views/Reader/ReaderArtifactDiffTests.swift` (built). Manual: TBD. Swift view written 2026-10-31 (`CompareReadersView` over `CompareReadersStore`, shown in `StageCompareWindow` behind `wideSetUp`; not yet compiled or run): the three modes are text-only layouts under the page with its lines boxed (no per-reader boxes: the engine answer has one box per line); the per-line pick posts `readings/choice` with kind `transcription` (unchecked against a real page).
- `wide.compare.price-and-time-per-candidate` — **[PARTIAL]** (#6052; section L; the figures are `designer.compare.row-sentence` and `designer.compare.predicts-cost-and-time`) each column head carries the candidate's error rate on the person's pages, seconds a page, price a page and the whole project's cost and hours, each with its basis, from the bake-off row or the try candidate; an unmeasured candidate says why. Engine built 2026-10-31 for a Try's candidates (`CompareReader.measure`: error rate, seconds, cost on the sample pages with its basis, local, `not_measured`); the whole-project figures are built too (`seconds_per_page`, `pages_per_hour`, `project_pages`, `project_hours`, `project_cost_usd`, `project_basis`: the sample's seconds and cost scaled to the project's page count, the basis said in words; none for an unmeasured candidate); the head's words are Swift, not yet written. *Test:* `fichero-server/tests/unit/api/test_compare_readers_5900.py` (`test_wide_a_candidates_head_*`), `CompareViewTests.swift` (the head's words from a row with and without measures). Manual: TBD.
- `wide.compare.pick-a-winner` — **[PARTIAL]** (#5900, #6052; section L) Use This One under a column sets the step's model through `use-candidate` and marks the column chosen (built: the press, `RecipeSetupStore.useCard`); on the project's own lines a click on a reader's text is the per-line pick through `reading.choose` (`source.compare.pick`), never on a try's copies, which say so. Not built: the chosen mark in the view, the per-line pick in the app. *Test:* `CompareViewTests.swift`, `fichero-server/tests/unit/api/test_compare_pick_5900.py` (built, unrun). Manual: TBD.
- `wide.compare.keyboard-and-voiceover` — **[GAP]** (#5900; section L) ←/→ the candidate and the wipe handle, ↑/↓ the line, ⌥↓ the next differing line, 1–3 one candidate or all, Return Use This One, Esc close; each column an element with its name and figures, each cell "<reader>: <text>", a row announcing agree or differ, the legend a list of named toggles, the handle an adjustable element; Reduce Motion drops the wipe's easing. *Test:* `CompareViewTests.swift` (the key map as a pure table; the labels). Manual: TBD.
- `wide.compare.empty-and-error-states` — **[PARTIAL]** (#5900, #5806; section L) one candidate, no reading yet, a candidate that did not read this page (its `why`), a stale result and a try's copies each show the engine's one sentence in place of the picture or the row; never an empty picture. Built (pure): `CompareViewModel.emptyState` and `notReadBecause`; the stale and try-copy sentences and the view are not yet written. *Test:* `CompareViewTests.swift` (`states`). Manual: TBD. Swift view written 2026-10-31 (`CompareReadersView` over `CompareReadersStore`, shown in `StageCompareWindow` behind `wideSetUp`; not yet compiled or run): the three modes are text-only layouts under the page with its lines boxed (no per-reader boxes: the engine answer has one box per line); the per-line pick posts `readings/choice` with kind `transcription` (unchecked against a real page).
- `wide.compare.compact-layout` — **[GAP]** (#5900; section L) on iPad and iPhone the columns are a horizontal pager of candidates with the line list under, Overlay the default, the handle the drag, the sample strip a row of dots. *Test:* `CompareViewTests.swift` (the layout rule per width class). Manual: TBD.
- `wide.compare.replaces-the-captions-and-the-animation` — **[GAP]** (#6052; section L) the caption lines of counts under the stage pictures go; `StageComparisonView`'s pictures become Side by side over the real result; the bake-off's table stays as the summary; `StageCompareWindow` hosts Find Lines' compare until the Segments pane's Compare mode exists. *Test:* `fichero/Tests/Unit/general/Views/Onboarding/StageShowcasePicturesTests.swift` (built; adjust: no caption counts), `CompareViewTests.swift`. Manual: TBD.

### Ready and the release

- `wide.ready.only-what-will-run` — **[PARTIAL]** (#5840, #6295; section N) Ready lists only the steps that will run, in run order, each with its model, place, pages and cost, then the estimate with its per-step basis, then the Budget block, then Start with its reason; the skipped steps stay, each in its own box with why; the offered-jobs list (`OfferedJobsList`), the left-off rows and the taken-out rows are not on Ready. *Test:* `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift` (built; add: Ready's section model holds no offered job), Built 2026-10-31 (Swift, pure): `ReadyWillRun` (the runs in order with their progress, the skipped with why and fix, the estimate, Start's reason; no field for an offered, left-off or taken-out step); Ready's view, behind `wideSetUp` (written 2026-10-31, not yet compiled or run), no longer shows the taken-out, offered and left-off rows (`RecipeReadyFields`, `RecipeStartFields`); it does not yet read `ReadyWillRun` itself (its boxes are still `ReadySection`s), and the Budget block is the recipe designer's. `ReadyOnlyRunsTests.swift` (written; compiled on the Air, not yet run). Manual: TBD.
- `wide.ready.adding-a-step-is-on-its-stage-page` — **[GAP]** (#5840; section N) a step the recipe does not have is added on its stage's page (the left-off rows with Add, Put Back for a step taken out) or by ticking the stage on Choose the Stages; a stage not chosen is not offered anywhere else. *Test:* `fichero/Tests/Unit/general/Models/RecipeLeftOffTests.swift` (built; add: the rows are the stage page's and filtered to its jobs), `ReadyOnlyRunsTests.swift`. Manual: TBD. Written 2026-10-31 (behind `wideSetUp`, not yet compiled or run): the stage page lists the stage's taken-out steps with Put Back and its offered jobs with Add (`OfferedJobsList(onlyJobs:)`), beside the left-off rows it already had; status stays [GAP] until the host shows it.
- `wide.release.behind-one-flag` — **[PARTIAL]** (#5668; section O) the pager, the operation rows, the output column, the compare view and the Ready cut are behind the `wideSetUp` feature flag, off in the release tier and on in the dev tier; off, Set Up is today's window unchanged; the engine changes ship either way. Built 2026-10-31: the `wideSetUp` feature (`features.yaml`, tier dev, no stored switch; `FeatureManager.isWideSetUpEnabled`): hidden in release, beta and alpha, shown in dev; nothing reads it yet (the surfaces behind it are not yet written). *Test:* `fichero/Tests/Unit/general/Models/FeatureManagerTests.swift` (`testWideSetUpIsOffInReleaseBetaAndAlphaAndOnInDev`, compiled on the Air, not yet run), `SetupPagerTests.swift` (the flow with the flag off is today's). Manual: TBD.
- `wide.release.solid-per-step` — **[GAP]** (#5668; section O) a step is in the release only when its behaviours are [OK] with green tests, a real run on a scratch copy of real pages has been read by eye with its figures in the handoff, and the owner has pressed through it once; the Sunday-night Start gate and Air try decide the flag's release value. *Test:* the gate itself (`scripts/gate part recipes`, `verify_all --standard`) and `scripts/realrun_check.py` on the scratch project; no unit test. Manual: TBD.

### Tries, Leave Out and Review (owner 2026-10-31)

- `wide.try.start-reuses-a-matching-try` — **[PARTIAL]** (#6127; section M) Start counts a page done for a step when a try ran that step with the same card and settings on the same image signature, runs it on the other pages only, and the account says how many came from the try. *Design (approved 2026-11-02; to build, engine first):* (1) the try keeps its scratch copy (`samples._run_one` deletes it today) until its result expires, after 7 days or at the next try of the same stage (both settings, not constants); its result records per page the card id, a hash of the step's settings, the page's image signature (`PageImage.signature`) and the copy's page id (`back[new]`). (2) Pages map by `plan.id_map`; lines do not share ids, so a copy line is matched to the project's by page and polygon overlap (IoU 0.9, a setting); an unmatched copy line is created on the project page (a Find Lines try), a matched one only gets the reading. Readings are copied as new `ContentRepresentation` rows keeping `derived_from_*`, with `producer_run_id` the try's job id. (3) Start adopts as its own first action, audited: whoever may Start may adopt, an agent included, the same way as `reading.choose`; there is no separate gate. A page is adopted only when its current image signature, card id and settings hash equal the try's, and nothing is written over a person's reading; any other page is left for Start to run and is named in the answer. (4) `recipes/done.py` counts a page done for a step when it has a reading whose `producer_run_id` is an adopted try's, so there is no new rule; the plan's account says "N pages came from your try". Set Up itself still never writes the project. (5) Undo: the action's `before` lists the created segment and reading ids and its inverse retracts them (`retracted_at`) and soft-deletes the created lines, one undo, nothing erased. (6) A try on the same input and model is reused, never rerun; a paid try's spend is booked once and adoption books none. (7) A folder-level override adopts only on that folder's pages. (8) The label slice (`wide.try.shown-outside-set-up`) reads the same record. *Built (engine, 2026-11-02):* a done try keeps its copy and a per-page record (`recipes/adopt.py`; `keep_days` 7 and `match_iou` 0.9 in `recipe/try-settings.yaml`); `try.adopt` (Start's first action, `POST /api/recipes/project/start`) adopts readings onto the project's matching lines, once, never over a person, and `try.unadopt` is its undo; `StartPlan.from_tries` says how many pages came from a try. *Not built:* creating a line the page lacks (a Find Lines try), folder-level overrides, and the app's account words. *Test:* `fichero-server/tests/unit/recipes/test_start_plan_counts_what_ran_5616.py` (built; add the try's pages). Manual: TBD.
- `wide.try.shown-outside-set-up` — **[GAP]** (#5806; section M) a try's readings and lines are visible in the Reader and the Inspector on the pages it ran on, labelled as a try's with its date and model, never counted as the project's and never shown as a run's. *Test:* `test_try_results_labelled_outside_setup.py` (not yet written: the try's artifacts carry `try_stage` and are left out of the counting rule), `TryLabelTests.swift` (not yet written). Manual: TBD.
- `wide.try.paid-with-the-price-on-the-button` — **[PARTIAL]** (#5806; section M) a try whose candidates cost money is allowed; the button says the price ("Compare on These Pages, about $0.12"); the yes is `cost_ok` and the spend is booked against the project cap. Built: the 402 and Compare, at That Cost. Not built: the price on the first button. *Test:* `fichero/Tests/Unit/general/Models/SetupStagesTests.swift` (built; add the button's words from the stage plan's cost). Manual: TBD.
- `wide.review.accept-line-and-all` — **[PARTIAL]** (#5720; section M) Review's proposals on a page are accepted one line at a time or all at once ("Accept all N"), one audited action with one undo for the page; the compare view's per-line rule is unchanged. *Built (engine; the maintainer's ruling 2026-11-02):* a review's readings count at once, so no proposal waits for a yes; "Accept all N" confirms them. `reading.choose_many` (one page, `reading.choose` per line whose counting reading is a `transcription_review`'s and that no person has chosen) is one audited action; `reading.restore_choices` is its one-step undo, each line back to its earlier choice or none. A person only (`source.reading.chosen-is-worked-out`); a page with nothing waiting is refused (409) in words. The button is built in the reader's head (`ReviewAcceptAllButton`, behind `wideSetUp`, count from `GET /api/content-representations/document/{id}/review-waiting`), not yet seen in a build. *Test:* `test_review_accept_all.py`. Manual: TBD.
- `wide.leaveout.decided-from-page-quality` — **[PARTIAL]** (#6070; section M) Leave Out has no fixed default: the sample's own Leave Out findings and the condition answers decide whether it is on, and the stage page says why as a suggestion row; the person changes it. *Test:* `fichero-server/tests/unit/recipes/test_prepare_step_setup.py` (built; add: a clean sample leaves it off with its why, a speckled one turns it on). Manual: TBD.
- `wide.review.on-for-a-large-cloud-reader` — **[PARTIAL]** (#6052; section M) choosing a large cloud vision reader turns Review on as a suggestion row with its price and the reason in words; the person can turn it off. *Test:* `test_suggestions_route.py`. Manual: TBD.

## Test matrix

| Leg | This surface? | Pins | File |
| --- | --- | --- | --- |
| Pure rule (Swift) | y | the pager's moves, widths, labels, restore; the output state; the chain strip rows; the no-model row | `SetupPagerTests.swift`, `StepOutputStateTests.swift`, `RenditionChainStripTests.swift`, `TieTextStepTests.swift`, `PrepareOperationsTests.swift` (not yet written) |
| Engine (pytest) | y | the operations in the listing and the plan; the stamp with answers; the proposal for a stage ticked later; `runs` for a prepare-only plan; the image-chain route; the tie counts on a try; the two line counts | `fichero-server/tests/unit/recipes/test_prepare_step_setup.py`, `fichero-server/tests/unit/recipes/test_start_plan.py`, `fichero-server/tests/unit/recipes/test_setup_stages_5668.py`, `fichero-server/tests/unit/media/test_current_image_6296.py`, `test_image_chain_route.py`, `test_tie_text_counts_on_the_stage_try.py`, `test_find_lines_try_counts_on_both_images.py` |
| Contract | y | the stage listing's `operations`, the try's `answers_revision`, the image-chain schema | the regenerated client (`sync_openapi_schema.sh`) |
| Click-around (XCUITest) | y | swipe and arrow keys move a page; Run this step; the strip | `fichero/Tests/UI/general/Shell/PrepareImagesSetupUITests.swift` (built, unrun; add the pager) |
| iPhone / iPad | n | the widths are written down; no companion Set Up exists | — |
| Pickers (engine + guard) | y | every stage job's row shape; the empty picker's why; the guard's three rules and its allowlist | `fichero-server/tests/unit/recipes/test_setup_stages_5668.py`, `test_check_setup_model_pickers.py` |
| Suggestions (engine + Swift) | y | the suggestions list per answer; the row's parts and Change… | `test_suggestions_route.py`, `SuggestionRowTests.swift` |
| Compare (engine + Swift) | y | the frame on the compare answer; the modes, the diff rows, the key map, the states, the compact layout | `fichero-server/tests/unit/api/test_compare_readers_5900.py`, `CompareViewTests.swift` |
| Ready (Swift) | y | Ready's sections hold only what runs, the estimate and the Budget; adding is on the stage page | `ReadyOnlyRunsTests.swift`, `fichero/Tests/Unit/general/Models/RecipeLeftOffTests.swift` |
| Release (flag + gates) | y | the flag off gives today's window; the Start gate and the Air try | `fichero/Tests/Unit/general/Models/FeatureManagerTests.swift`, `scripts/gate part recipes`, `scripts/realrun_check.py` |
| Tries, Leave Out, Review (engine) | y | a try's pages counted at Start; the try label outside Set Up; Accept all as one action; Leave Out from the sample | `fichero-server/tests/unit/recipes/test_start_plan_counts_what_ran_5616.py`, `test_try_results_labelled_outside_setup.py`, `test_review_accept_all.py` |

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

### Stage 7 — Pickers and the guard (engine first)

#### Step 7.1 — The tie picker, the row shape from the registry, the five cards, the empty picker's why (#6256, #6052)
- Behaviours: `wide.picker.tie-text-picker-visible`, `wide.picker.row-shape-from-the-registry`, `wide.picker.cards-for-the-text-steps`, `wide.picker.empty-says-why`
- Tests: fichero-server/tests/unit/recipes/test_setup_stages_5668.py, fichero-server/tests/unit/recipes/test_one_candidate_source_5808.py, TieTextStepTests.swift
- Depends on: 6.1
- Size: S
- Engine: `tie-text-to-lines` to `needs_a_model=False`, `why`/`fix` on an empty candidate list. Swift: the row shape; needs the host.

#### Step 7.2 — The guard (#6052)
- Behaviours: `wide.picker.guard`
- Tests: test_check_setup_model_pickers.py
- Depends on: 7.1
- Size: S
- Engine only: the script, its allowlist, its place in `verify_all --fast`.

### Stage 8 — Suggestions (one design with the recipe designer's Stage 18)

#### Step 8.1 — The suggestions list (#6052)
- Behaviours: `wide.suggest.one-list-from-the-engine`, `wide.suggest.script-steers-reader-segmenter-training`, `wide.suggest.damage-suggests-a-try`, `wide.review.on-for-a-large-cloud-reader`
- Tests: test_suggestions_route.py
- Depends on: 7.1
- Size: M
- Engine only, after the recipe designer's Step 18.6 (the defaults table, in its own spec): the route over the defaults table, the script's rows from the candidate source, the review row.

#### Step 8.2 — The suggestion rows in the pager (#6052)
- Behaviours: `wide.suggest.reason-and-override`
- Tests: SuggestionRowTests.swift
- Depends on: 8.1, 5.1
- Size: S
- Swift; needs the host.

#### Step 8.3 — Leave Out from the sample (#6070)
- Behaviours: `wide.leaveout.decided-from-page-quality`
- Tests: fichero-server/tests/unit/recipes/test_prepare_step_setup.py
- Depends on: 8.1
- Size: S
- Engine only.

### Stage 9 — Compare

#### Step 9.1 — The frame on the compare answer; the figures per candidate (#5900)
- Behaviours: `wide.compare.same-page-same-crop`, `wide.compare.price-and-time-per-candidate`
- Tests: fichero-server/tests/unit/api/test_compare_readers_5900.py
- Size: S
- Engine only: `frame` and mapped shapes on the compare answer; the figures carried from the bake-off row and the try candidate.

#### Step 9.2 — The compare model: modes, rows, states, pure (#5900, #6052)
- Behaviours: `wide.compare.three-modes`, `wide.compare.per-line-diff`, `wide.compare.empty-and-error-states`
- Tests: CompareViewTests.swift, fichero/Tests/Unit/general/Views/Reader/ReaderArtifactDiffTests.swift
- Depends on: 9.1
- Size: M
- Swift, pure (no view): its tests run when the host is back.

#### Step 9.3 — The view in the pager and in the Segments pane (#5900)
- Behaviours: `wide.compare.one-view-from-the-pager`
- Tests: CompareViewTests.swift
- Depends on: 9.2, 4.2
- Size: M
- Swift; needs the host.

#### Step 9.4 — Pick a winner, keys, VoiceOver, compact (#5900)
- Behaviours: `wide.compare.pick-a-winner`, `wide.compare.keyboard-and-voiceover`, `wide.compare.compact-layout`, `wide.compare.replaces-the-captions-and-the-animation`
- Tests: CompareViewTests.swift, fichero-server/tests/unit/api/test_compare_pick_5900.py, fichero/Tests/Unit/general/Views/Onboarding/StageShowcasePicturesTests.swift
- Depends on: 9.3
- Size: M
- Swift, with the per-line pick on the engine's existing action; needs the host.

### Stage 10 — Tries and Review (owner 2026-10-31)

#### Step 10.1 — Start reuses a try; a try is labelled outside Set Up; the price on the button (#6127, #5806)
- Behaviours: `wide.try.start-reuses-a-matching-try`, `wide.try.shown-outside-set-up`, `wide.try.paid-with-the-price-on-the-button`
- Tests: fichero-server/tests/unit/recipes/test_start_plan_counts_what_ran_5616.py, test_try_results_labelled_outside_setup.py, TryLabelTests.swift, fichero/Tests/Unit/general/Models/SetupStagesTests.swift
- Size: M
- Engine: the done rule and the try label. Swift: the label and the button's words; needs the host.

#### Step 10.2 — Review's Accept all (#5720)
- Behaviours: `wide.review.accept-line-and-all`
- Tests: test_review_accept_all.py
- Size: S
- Engine: one action, one undo. The button is the Review surface's (`readings-and-apparatus.md`), not this spec's.

### Stage 11 — Ready and the flag

#### Step 11.1 — The flag, first (#5668)
- Behaviours: `wide.release.behind-one-flag`
- Tests: fichero/Tests/Unit/general/Models/FeatureManagerTests.swift, SetupPagerTests.swift
- Size: S
- Swift only; lands before any pager slice so every later Swift slice is behind it.

#### Step 11.2 — Ready shows only what will run (#5840, #6295)
- Behaviours: `wide.ready.only-what-will-run`, `wide.ready.adding-a-step-is-on-its-stage-page`
- Tests: ReadyOnlyRunsTests.swift, fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift, fichero/Tests/Unit/general/Models/RecipeLeftOffTests.swift
- Depends on: 11.1
- Size: M
- Swift; the Budget block is the recipe designer's Step 18.3; needs the host.

#### Step 11.3 — Solid per step: the real runs and the Sunday checks (#5668)
- Behaviours: `wide.release.solid-per-step`
- Tests: scripts/realrun_check.py
- Depends on: 11.2
- Size: S
- The manager's, not the builder's: the real runs, the gate and the Air try, the flag's tier value.

## Build order for one builder (owner 2026-10-31: one long-running builder, after `fix/air-engine-oom` and the pairing branch land)

One Sonnet builder, one worktree off `integration` once those two branches are in, working the stages
above in this order, each slice engine first, committed on its own with its tests red then green, the
Swift tests written beside the code and run when the XCTest host is back (the Pro's `testmanagerd` is
stuck; a slice is not blocked on it). The builder hands off at 120k context with a note naming the next
slice. The order:

0. Step 11.1 — the `wideSetUp` flag, so every Swift slice after it is behind it. Test:
   `fichero/Tests/Unit/general/Models/FeatureManagerTests.swift`.
1. Step 1.1 then 1.2 — the two defects (`wide.prepare.operations-run-on-every-page`,
   `wide.prepare.rerun-follows-the-answers`, `wide.prepare.ticked-later-still-runs`,
   `wide.start.enabled-on-any-run`). Tests: `fichero-server/tests/unit/media/test_turn_straighten_blank.py`,
   `fichero-server/tests/unit/recipes/test_prepare_images_step.py`, `fichero-server/tests/unit/recipes/test_start_plan.py`,
   `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift`.
2. Step 7.1 and the tie picker (`wide.picker.tie-text-picker-visible`, `wide.picker.row-shape-from-the-registry`,
   `wide.picker.cards-for-the-text-steps`, `wide.picker.empty-says-why`), then Step 7.2 the guard
   (`wide.picker.guard`). Tests: `fichero-server/tests/unit/recipes/test_tie_text_to_lines_picks_a_reader_6256.py`,
   `fichero-server/tests/unit/recipes/test_setup_stages_5668.py`, `fichero-server/tests/unit/recipes/test_one_candidate_source_5808.py`,
   `TieTextStepTests.swift`, `test_check_setup_model_pickers.py`.
3. Steps 2.1, 2.2, 2.3 — Prepare Images as steps and the image chain, engine. Tests:
   `fichero-server/tests/unit/recipes/test_setup_stages_5668.py`, `fichero-server/tests/unit/recipes/test_prepare_step_setup.py`,
   `fichero-server/tests/unit/media/test_current_image_6296.py`, `test_image_chain_route.py`.
4. Steps 3.1, 3.2, 3.3 — the operation rows (picker gone), the four pictures, the chain strip, Swift.
   Tests: `PrepareOperationsTests.swift`, `fichero/Tests/Unit/general/Views/Onboarding/StageShowcasePicturesTests.swift`,
   `RenditionChainStripTests.swift`.
5. Steps 4.1, 4.2 — the try's revision, Run this step, the four output states. Tests:
   `fichero-server/tests/unit/recipes/test_stage_try_result_follows_its_job_5806.py`, `StepOutputStateTests.swift`.
6. Steps 5.1, 5.2 — the pager filling the window, keys, swipe, accessibility, position restored. Tests:
   `SetupPagerTests.swift`, `fichero/Tests/Unit/general/Views/Onboarding/SetupFooterTests.swift`.
7. Steps 6.1, 6.2, 6.3 — the no-model rows and the tie's figures, the untied remainder, faded pages and
   the two line counts. Tests: `test_tie_text_counts_on_the_stage_try.py`, `test_tie_text_remainder.py`,
   `test_find_lines_try_counts_on_both_images.py`, `fichero-server/tests/unit/recipes/test_model_chooser_per_step_5668.py`.
8. Steps 9.1 to 9.4 — the compare view, engine then Swift. Tests:
   `fichero-server/tests/unit/api/test_compare_readers_5900.py`, `CompareViewTests.swift`,
   `fichero-server/tests/unit/api/test_compare_pick_5900.py`.
9. Steps 8.1, 8.2, 8.3 — the suggestions list and rows, Leave Out from the sample (after the recipe
   designer's Step 18.6, the defaults table; the builder does that step too if it has not landed).
   Tests: `test_suggestions_route.py`, `SuggestionRowTests.swift`, `fichero-server/tests/unit/recipes/test_prepare_step_setup.py`.
10. Steps 10.1, 10.2 — a try reused at Start and labelled outside Set Up, the price on the button,
    Review's Accept all. Tests: `fichero-server/tests/unit/recipes/test_start_plan_counts_what_ran_5616.py`,
    `test_try_results_labelled_outside_setup.py`, `TryLabelTests.swift`, `test_review_accept_all.py`.
11. Step 11.2 — Ready shows only what will run. Tests: `ReadyOnlyRunsTests.swift`,
    `fichero/Tests/Unit/general/Models/RecipeLeftOffTests.swift`. Then the manager's Step 11.3.

After each slice: `ruff`, the slice's pytest with `PYTHONPATH` on the worktree's `fichero-server/src`,
`swiftlint` on the Swift diff, the regenerated client committed when the contract changed, and every
`scripts/check_*.py` on a Swift or contract slice.

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

3. **The tie's method** (section G): the alignment stays anchored on the chosen line reader's rough
   read, with the untied remainder kept and the threshold measured — taken as a DEFAULT (owner
   2026-10-31, "keep the untied-remainder list"); still open only whether the owner wants another
   method tried beside it. Everything else of the earlier question 3 is ruled.
6. **What the material's condition and script change.** Damaged handwriting may do well with several
   review passes where a single reader does not, and an unusual script (for example Cherokee) may need a
   different reader or segmenter, or training, where the defaults fail. The mapping under ruling 7 is the
   DEFAULT; which condition and script answers steer which steps beyond it is for the owner to list.

Questions 1, 2, 4, 5, 7, 8, 9 and 10 of the earlier draft are answered under Rulings (2026-10-31, the
owner's answers), each DEFAULT marked as one the owner may change.

## Rulings

- 2026-10-31 (owner, by screen share, paraphrased): Set Up becomes wide, each step's output shown as the
  person goes, moved between by swipe, arrows, Back and Next; Prepare Images becomes several selectable
  steps (split, straighten, crop, clarity) each with its own picture; the per-folder picker goes; two
  defects to find in the code: Prepare Images seems to do nothing, and one step alone cannot be started.
- 2026-10-31 (owner, second note, paraphrased): a step with no model to choose must say that Fichero does
  it and how well, with its figures on the person's pages and the unmatched lines reachable; faded pages
  need Clarity before Find Lines, said and counted on the person's sample, with the segmenter choices
  named.
- 2026-10-31 (owner, third note, paraphrased): damaged handwriting may be handled well by several steps of
  review where a single reader is not, and an unusual script may need a different approach again, so the
  material's condition and script steer the steps and the model suggested for each (open question 6).
- 2026-10-31 (owner, fourth note, paraphrased): every step that runs a model lets the person choose it
  and a step with no model says Fichero does it; onboarding suggests how to do things from the
  material (script, condition, how to run it) with the reason in words and an override; one design
  with the recipe designer's How page, not two (section K).
- 2026-10-31 (owner, fifth note, paraphrased; section M): Start reuses a matching try; tries show outside
  Set Up labelled as tries; Review has per-line accept and Accept all; paid tries are allowed with the
  price on the button; Leave Out has no fixed default and Set Up decides from page quality, saying why;
  damaged handwriting: try the samples and the person chooses; Review on, price shown, for a large cloud
  vision reader; a real compare view for A/B and bake-off results, folded into the pager (section L).
- 2026-10-31 (owner, Ready and the release, paraphrased): Ready shows only what will run, its estimate
  and its budget; the steps one could add belong on their own stage pages (section N). The wide Set Up
  goes into Monday's release only if solid, each step proven on real test pages with tests to spec; a red
  Start gate or Air try on Sunday night leaves it out rather than holding the release (section O).
- 2026-10-31 (owner, correction, paraphrased): the note that no model ties text to lines was wrong; the
  owner meant there is no UX to choose a model for that step. Tie text to lines shows a working model
  picker like every other model step; the alignment may stay anchored on the reader's rough read; the
  untied-remainder list stays (section G, `wide.picker.tie-text-picker-visible`).
- 2026-10-31 (owner, answers to the open questions, paraphrased): **Q1** a folder's own answers live in
  the folder's context menu in the library (section C). **Q2** Set Up fills the library window, not a
  fixed 1040 by 680 (section A). **Q10** the compare view opens Side by side (section L). The
  recommended answers are taken as DEFAULTS the owner may change: **Q4** Apple Vision's lines are a Find
  Lines candidate on handwriting, never the default, adopted on the compare's evidence; **Q5** Clarity
  with no paper answer keeps today's per-page look, said in words on the row; **Q7** the defaults
  mapping (faded ink → Clarity; tight binding → flatten; ruled lines and show-through → their answers;
  torn, stains, water damage → Leave Out on and a compare suggested; damaged handwriting → a compare of
  reader against reader-with-review; a script with no installed reader → the readers found and the
  training offer; a script with no word spaces → the reader's card must say so); **Q8** a suggestion
  never acts without a tap beyond being the default already applied and marked; **Q9** Review's Accept
  all and the compare view's per-line pick both stand, each on its own surface. The spec is approved to
  land; one long-running builder works the build order below.
