# How work runs in Fichero: a design review (2026-10-27)

Read-only, against origin/integration `864293bd3`. Nothing was run; no engine, no app database. Paths are
relative to `fichero-server/src/fichero_server/`. Each claim is **VERIFIED** (file and line read) or
**INFERRED**. The spec `ui/activity-and-automatic-work.md` is revised in place on branch
`fable/run-system-review` and marked DRAFT for maintainer approval; `source/recipes-run.md` is not
touched (its proposed lines are in section 3 below).

## 1. The ten questions, one answer each

**1. One backend for workflows and recipes?** Mostly yes. One `jobs` table, one scheduler, one set of
lanes (`execution/jobs.py:105` `LANES`), one throttle (`execution/throttle.py:540` `decide`), one
Activity read. VERIFIED. The forks: a workflow run's state lives in three places (the runner's in-memory
`_running_workflows`, `execution/runner.py:129`; the `workflow_runs` record; the `jobs` row mirroring it
through `_RUN_STATES`, `execution/jobs.py:473`), and Pause and Stop have a job route and a run route
each. A recipe run is a job on the one-wide `recipes` lane (`recipes/runner.py:1818`); a workflow run
has no lane of its own, only its pages take slots (the spec's `activity.throttle.background-qos`, #4740).
Should they fork? No. The record and the row should be one (the spec's one-job-model lines, #5353), and
the run routes should call the job routes (`activity.pause.one-start-stop`). Neither needs a new system.

**2. The Activity window: solid, not too much?** The one-bar design (NOW · UP NEXT · DONE TODAY, one row a
run, one button) is built in Swift and uncompiled (`Views/Activity/Window/ActivityGroupsView.swift`,
VERIFIED: three `Section`s, 189 lines). A person should see: what runs now with its stage and pages,
what comes next and why it waits, what finished today with one line each. Noise today: the Details
view's Trace and Comparison views (`Views/Activity/Trace/*`, `Comparison/*`, 1,543 lines) are developer
surfaces; the popover's CPU %, Importing… and BackendWorkPill rows still show
(`activity.popover.now-plus-next`); the machine state as text. Not noise: the one grey line of why.
The spec itself was noise too: three paragraphs pasted four times (removed), and 145 PARTIAL lines of
build notes. The engine side that the window needs is the GAP block of #5960 (stage counts, pace, cost,
one row per run), now Stage 2 of the build order.

**3. The slow-downs: too aggressive?** The holds are right; the slow is too slow. VERIFIED thresholds
(`execution/throttle.py`): in use = any input in 30 s (`IDLE_BEFORE_HEAVY_SECONDS`, `:28`); build =
`pgrep xcodebuild|swift-build|swift-frontend|clang` every 10 s (`:401`); battery or Low Power Mode
(`:456`); memory = free under the model's need (Kraken 2.5 GB) or pressure critical, or pressure warn
with 64 MB paged in the last minute (`memory_short`, `:99`; `PAGING_GROWTH_BYTES`, `:41`); heat =
thermal serious (`:46`). Memory and heat hold everything; battery holds background work and slows a
person's; in use and a build never hold. What "slow" costs: `decide` answers priority `background`,
which `core/compute_preferences.py` `apply_to_this_thread` turns into a QUARTER of the performance
cores (one thread on a 4-core Mac) at utility QoS (lifted from the background class on 2026-10-20;
the background class measured 18x slower, #4959). A person reading pages beside a recipe keeps the
Mac "in use" the whole sitting, so an automatic run spends hours on one thread. Decision 1.

**4. Does every wait, skip or failure say why?** Waits: yes, one function (`execution/jobs.py`
`waiting_reason`, `activity.waiting-says-why`), and the gate's figure is now served as fields
(`recipes-run.memory.gate-shown`). Skips: yes, a step not run says why on the plan and the summary
(`test_every_step_says_why_it_did_not_run.py`, VERIFIED present). Failures: a step that raises is
worded in one plain line (`recipes/runner.py:900` `could_not_start`), but a job that raises still puts
`str(exc)` on its row (`execution/jobs.py:3529`), so a page's failure can read as Python. Two gaps the
spec already carries: a system stop reads "Stopped by you" (#6005), and a run's log repeats a page
once per step (#5960, `activity.log.one-line-per-page`).

**5. Cores.** The engine finds the performance cores correctly: `core/cores.py` reads
`hw.perflevel0.physicalcpu` (VERIFIED, `:44`), and under Slurm or a cgroup the quota. It then gives
them away. `apply_to_this_thread` (`core/compute_preferences.py:88-101`): `fast` = all performance
cores at user-initiated QoS; `balanced` (the default setting) = half, utility QoS; `background` = a
quarter, never below 1. `kraken_runtime.py` ~1022 divides that by the pages inside the gate
(`threads = cores // pages_inside`), and the gate is 2 (`PAGES_AT_ONCE_GATE_5929`, `:875`) for a
person's run and 1 for an automatic one (`pages_at_once_and_why`, `:883-906`). On the owner's
4-performance-core Mac: a hand-started run reads 2 pages x 2 threads; an automatic run while idle 1
page x 2 threads; an automatic run while the Mac is used 1 page x 1 thread. Also INFERRED: Kraken's
baseline segmenter (`blla`) is mostly single-threaded Python after the convolution, so threads beyond
two buy little a page; pages at once is the lever that fills cores, and it is gated at 2 until the
exit-time MPS crash (#5929) closes. A machine with dozens of cores gets at most 2 pages x
(cores ÷ 2) threads, and most of those threads idle. How to measure, no code needed: the per-page
engine log line `kraken page …: load … segment … recognise … total … | priority= qos= threads=`
(`kraken_runtime.py:968`); `fichero-server/scripts/bench_priority_qos.py` (fast / balanced /
background on one page); `fichero-server/scripts/bench_same_model_pages.py` (1 against 2 pages at
once); `sudo powermetrics --samplers cpu_power -i 1000` during a run for P-cluster against E-cluster
residency (utility-QoS threads are scheduled mostly on the efficiency cores: INFERRED from Apple's
QoS documentation, not measured here). Filed: #6229 (the cores are used, and the row says so).

**6. MLX and spaCy like Kraken?** MLX yes: a served model's page or text call is a row on the model
lane through `llm.model_call_slot` (`llm/__init__.py:1636-1646`, VERIFIED), one served model, reads
follow memory, idle stop at 600 s, node cache keyed on the text. spaCy half: the import draft and the
correction re-read are rows on the embed lane (`importers/derivatives.py:1207`,
`actions/page_text_cache.py:516`); spaCy inside a workflow step (the Names step's `spacy` provider,
`workflows/tools/entities.py:35`) runs under `knowledge/spacy_ner.py:231` `_spacy_lock` on the run's
own thread with no row, no lane and no gate. The embedder is deliberately off the model lane (#5847),
which #6176's `engine.embedder-in-the-model-lane` contradicts: decision 3. Never-rerun reuse: the node
cache (`workflows/cache.py:78`, text steps keyed on the text, image readers on the file) plus the
recipe's done-is-not-redone; Kraken has no cache of its own, the step skips done pages.

**7. Logical order?** Yes. Stages in `recipes/stages.py:53`: prepare-images → find-regions →
find-lines → leave-out → read → normalise → translate → organise → names → statements → dates →
passages → structured-data → search → catalogue (VERIFIED). Inside a batch `_run_batch_steps`
(`recipes/runner.py:1444`) runs them in that order, each step's end saved on the batch; a step whose
input is missing is "not run" with why (`_blocked`); the one overlap is `_beside` (`:1297`): a local
reading step and a hosted one that take nothing from each other run side by side. Catalogue and
publish run once at the end, not per batch (`:1474`).

**8. Hugging Face and the cluster through the same run model?** Yes, one kind: `read-at-scale` on the
`remote` lane, `request.target` either `huggingface-jobs` or a cluster id (`remote_read/job.py:30,
159-184, 234-247`, VERIFIED); the same loop sends shards, polls statuses in one call, fetches parts.
Training likewise: `train-a-model` on `remote` for Kraken and vision LoRA on Hugging Face or a
cluster (`training/job.py:48, 115-132, 415`). The cluster target itself is refused by name: the app's
key and sign-in step are not built (`cluster_target`, `remote_read/job.py:147-153`, #5238), so today
only Hugging Face runs; the cluster path is exercised by injected targets in tests. The recipe step
does not yet pass its parent id, so a remote run is not under its step (`activity.remote-under-its-step`).

**9. Fine-tuning like a run?** Kraken on this Mac: a row (`train-on-this-mac`, model lane, utility
QoS), holds at every batch for the throttle, cancellable, resumes from `last.ckpt` with `--resume`
(`training/local.py:19-21, 233`, VERIFIED). On Hugging Face or a cluster: a row on `remote` whose
state is the far side's, cancellable there, never retried in place (a new training is started). The
reasons A/B (`training/reasons_job.py`) is a remote row too. Vision LoRA has no local path. Reporting
is the same row; recovery differs by design (checkpoint here, far-side state there), which is right.

**10. Each step solid on its own?** Each of the ten recipe steps has a run-side test
(`test_a_run_through_every_step.py`, all ten in one Start) and a not-run side
(`test_every_step_says_why_it_did_not_run.py`), VERIFIED present, and recipes-run tags all ten [OK].
What those tests do not reach: the models are stubbed at the function the step calls, so the lane,
the gate and the throttle are not in the loop; the M4 load leg (`tests/perf/test_recipe_run_100_pages.py`)
is written and unrun. "Solid" is therefore proven for the step's bookkeeping, not yet for the step under
load.

## 2. What was done to the spec (`ui/activity-and-automatic-work.md`)

- Status: DRAFT for maintainer approval, 2026-10-27. A **Boundary** paragraph names what this spec,
  recipes-run and workflows each own, and lists every line this spec now defers to recipes-run by id.
- A **Reviewed 2026-10-27** section: one table of every kind of work (row, lane, gate, reuse, file:line),
  the four forks, and the slow-down thresholds as built.
- Noise: three pasted duplicates of one paragraph removed (the old lines 1506–1510).
- Honest tags: `engine.file-time-is-per-file` → [OK] (same test as `activity.file-time-is-the-files-own`);
  `engine.model-stays-for-the-job` → [PARTIAL] (Kraken half pinned); `engine.embedder-in-the-model-lane`
  → [GAP] awaiting decision 3; `activity.run.stop-reaches-in-flight-calls` now cites the open #4402.
- Two new lines: `activity.lane.cores-are-used` [BROKEN] (#6229), `activity.throttle.in-use-slows-to-half`
  [GAP] (#6230).
- A **Build order** in the guard's shape: BROKEN first (Stage 1), then the engine summary (2), the window
  (3), the Mac's work and efficiency (4), parked (5). Guards: `check_spec_broken_has_issue` OK,
  `check_spec_behaviors_are_tagged` OK, `check_spec_build_order_shape` warns only on PARTIAL lines (DRAFT).
- Counts now: 13 BROKEN, 38 GAP (three added by section 7).

Issues: every BROKEN and GAP line already cited an issue; 32 of those issues did not name the line id,
so each got one comment binding the ids (#6005, #5359, #4949, #5960, #5839, #5354, #5245, #6001,
#5358, #5934, #5240, #5370, #5376, #1830, #2277, #5116, #5117, #6178, #6176, #4402, #5932). Two new
issues on the `activity` milestone: #6229, #6230. Not moved: issues on `Next release`, `cand 16` and
`Performance - Engine` (#5932, #6005, #5960, #5939, #6001, #6000, #5934, #6178, #6176) stay on those
milestones, since they are the owner's release buckets; decision 4.

## 3. Proposed lines for `source/recipes-run.md` (not edited; the builder owns the file)

1. Under section 7, after `recipes-run.memory.pages-at-once-bounded`:
   - `recipes-run.memory.threads-fill-the-cores` — **[GAP]** (#6229) a page's torch threads are the
     performance cores divided by the pages at once, for a person's run and an automatic one alike
     (`core/compute_preferences.py` `apply_to_this_thread`, `kraken_runtime.py` ~1022); the grey line
     says "2 pages at once, 2 threads each". Owned by `activity.lane.cores-are-used`; this line is the
     run's half: the figure is served on the run status beside `pages_at_once`.
2. Under section 6, after `recipes-run.engine.empty-kraken-lines-are-named`:
   - `recipes-run.engine.failure-in-words` — **[PARTIAL]** (#6212) a page or job that fails says why in
     words on its row, never a Python exception's text: `recipes/runner.py:900` `could_not_start` words a
     step; `execution/jobs.py:3529` still puts `str(exc)` on a job row. Test (to write): a job whose body
     raises `KeyError('x')` reads "<kind> could not finish: …", not `'x'`.
3. Section 3, `recipes-run.journey.progress-in-words`: add to *Left:* "the Names step's spaCy call is not
   a row, so the row cannot name the page it is on (`activity.every-worker-is-a-row`, #5359)".
4. Section 11, `recipes-run.order.folders-then-pages-queued`: note that `_beside`
   (`recipes/runner.py:1297`) lets a hosted reading step run beside a local one, the one exception to
   step-major, and that the summary's timings count the two as overlapping.

## 4. Per-step reviews for the Recipe Designer: what each should cover

Each step review reads the step's card (`recipes/jobs.py`), its tool, its test in
`test_a_run_through_every_step.py`, and its not-run case, and answers: what it takes and gives, which
lane and gate it runs under, what it does with a page it cannot do, what is reused on a rerun, what
the row says while it waits, and what the summary counts.

- **Lines** (`find-regions`, `find-lines`, `put-in-order`, `refine-shapes`): Kraken on the model lane;
  the page gate and threads (question 5); `blla` single-thread cost; a page with no lines; the segmenter
  as a lane job under the run (`test_regions_one_pass_5689.py`); done-is-not-redone per page.
- **Leave out**: judged per pass, noted per page; never meets its own take (#6212); what "blank verso"
  counts as on the summary; no model lane use.
- **Read** (`read-a-line`, `read-a-page`, `correct`, `tie-text-to-lines`, `find-where-readers-disagree`):
  one live read per page (#5848); empty Kraken lines named (#6219); a reader per material
  (`activity.run.stage-names-each-reader`); hosted beside local (`_beside`); Stop mid-call (#4402);
  the node cache key; the per-line cost of a vision reader (`activity.run.lines-batched-per-call`).
- **Translate / normalise**: a page done when it holds the step's reading by its model; the model-less
  reader wait; text steps keyed on the text so a correction re-runs it; cloud cost on the row.
- **Names** (`find-names-tag-words`, gazetteer, authorities): spaCy with no row inside the step
  (question 6); the `_turn` lock against the import draft (#5690); counts by kind on the summary;
  `nlp_text_sha` reuse; the LLM path's claims not withdrawn on rerun (`activity.auto.reextract-on-change`).
- **Dates**: waits for Names; "0 pages dated" against "no dates stage"; the date's provenance to the span.
- **Documents** (`find-documents-in-a-folder`, `split-into-entries`): per folder, deepest first; Stop
  keeps finished folders' proposals; proposed groups on the summary; the folder-scoped Start.
- **Statements** (`find-statements`): waits for Read; claims count; the cache on changed text;
  the `ask-a-model` rows under the step; cost null unless priced.
- **Vector** (`make-a-vector`): once at the end of the batch (ruling 5); the embed lane, a child process
  that never downloads (#6218); a stopped run's pending pages embed on the next open; the stale marker
  (`activity.derived.stale-is-marked`).
- **Catalogue** (`describe-for-the-catalogue`): once at the end over the whole run, not per batch
  (`runner.py:1474`); deepest folder first; the model-less wait.
- **Image prep** (`split-pages`, `prepare-the-image`): the images lane, two wide, one when memory is
  busy; thumbnails first and the 60 s stuck rule (#6213); the reduced-size decode (#6193); PDF pages
  counted once (#5690).

## 5. Decisions for the owner

1. **"In use" slows to half the cores, not to one thread** (#6230). Today any input in 30 s drops an
   automatic Kraken run to a quarter of the performance cores at utility QoS; a person reading beside a
   run keeps that for hours. *Recommend:* yes. Keep the holds (battery, memory, heat) and the 30 s
   window; make slow = half the performance cores at utility. Pause All remains the way to have the
   Mac to oneself.
2. **Lift the pages-at-once gate from 2 on the M4 bench evidence, or wait for the exit-time crash fix**
   (#5929, #5931). The gate, not the thread count, is what fills a many-core machine. *Recommend:* wait
   for #5929 on the Mac (a crash at exit is a crash), but let a cluster task or container read
   `cores ÷ 2` pages at once now, since that process exits by itself.
3. **The embedder's lane** (#6176 against #5847). #6176 asks for the embedder in the model lane; #5847
   put it on its own lane, as a child process, so an embed never unloads Kraken, and recipes-run's
   ruling 5 runs search once at the end. *Recommend:* keep #5847 (off the model lane) and close the
   #6176 ask as superseded; the memory rule already frees the embedder child when memory is tight
   (`activity.machine.models-held`).
4. **Milestones.** Nine issues the Activity spec's BROKEN and GAP lines cite sit on `Next release`,
   `cand 16` and `Performance - Engine`. *Recommend:* leave them where they are and let the spec's build
   order be the cross-reference; moving them to `activity` would hide them from the release bucket the
   owner reads. If the owner prefers one milestone per spec, the list is in section 2.

## 6. Not verified, said plainly

- No run was timed; every "measured" figure is quoted from the spec or the code's own comments.
- Whether utility-QoS threads land on the efficiency cores on this Mac is INFERRED, not measured;
  `powermetrics` during a run settles it in a minute.
- The Swift one-bar window is read from source, not seen in a build.

## 7. The owner's added questions (2026-10-27, afternoon)

**11. Cloud runs and batching.** Same run model: a cloud page or text call is a row on the network lane
(`llm/__init__.py:1636-1646`, VERIFIED), four at once for the whole Mac with a share per provider
(`execution/jobs.py:105`; `activity.run.lane-cap-per-mac`), its cost on the row from the price list and
rolled up the tree. No Batch API path: a batch-only model is refused at validation
(`workflows/validation.py:337`). Inside a recipe batch a hosted reading step may run beside the local
one (`runner.py:1297` `_beside`), the one overlap. *Where to draw the line:* finish lines locally (the
segmenter has no cloud twin, and the images are the heavy part); let Read, Translate, Names, Statements
and Catalogue go to the cloud when the local step's measured seconds a page
(`recipes-run.timing.per-step-recorded`) pass a threshold the plan states; raise the network lane to the
provider's limit; add the Batch API for runs nobody waits for. Filed #6233; decision 5.

**12. Logical progression.** Yes, forward only. `_blocked` (`runner.py:1640`) holds a step only on what
it takes from an earlier step of this run, by declared `takes`/`gives`, and says which; a kind no earlier
step gives is the material's own and never waited for. Stalls that remain, all said in words: a download
under way at Start (`_await_downloads`, `:931`), Pause between steps (`_wait_out_a_pause`), a step parked
on its paused run (`ParkedOnStepRun`, #5933), and the thumbnails-first hold (bounded by #6203/#6213).
Nothing goes back: a batch's finished steps are saved as they end and a resume skips them.

**13. Sidebar order.** One key, three places that use it. `core/naturalsort.py` `natural_key` (digits
numeric, `2` before `10`) and `in_folder_order` (a person's `sort_order`, then `sequence` in the file, then
the natural name, then id); `Database.unit_of_work_ids` (`db/__init__.py:5470`) walks the path from the
root with that key, so two `Folder 1`s in different boxes stay apart; a Start queues pages in that order
(`recipes-run.order.folders-then-pages-queued`); the page grid asks for it
(`activity.py:1239` passes `unit_of_work_ids` to `page_states`, VERIFIED), with the lanes' first-seen order
only as the fallback for a page outside the list. Not checked here: that the Swift sidebar's sort is the
same key (the spec's #5693 says every surface shares it). No gap found.

**14. Redo.** Engine yes, app no. `runner.enqueue(redo=[...])` redoes named steps on done pages
(`runner.py:128-136`, `_asked_again` `:1325`); its only caller is `scripts/realrun_check.py --redo`. A
person has Retry on a page, Read Again on a run's failed pages, and Run again on what was missed; none
redoes a done step. By itself on a change: the re-embed and the names re-read after a correction
(`activity.auto.reembed-on-change`, `.reextract-on-change`); a model's claims are not withdrawn on a
re-run (left in #5361). Filed #6231 (`activity.redo.one-way-per-step`).

**15. Spending.** Per run and per page yes; per step half. The job tree carries `cost_usd` on every
node, null unless every call is priced (`activity.jobs-are-a-tree`); the run status carries each step's
seconds and seconds a page and names the slowest step (`run_view.py:107-192`); the Activity row shows
the run's cost at its right edge. Missing: each step's money on the status beside its seconds (filed
#6234 on recipes-run, a proposed line), the run's cost so far on the live block
(`activity.summary.cost-so-far`, #5960), and the estimate before Start (`activity.run.where-and-estimate`).

**16. No skipped steps, no duplicate work.** Steps: a step is never silently skipped; it runs, or is
"not run" with why (`_blocked`), pinned for all ten (`test_every_step_says_why_it_did_not_run.py`).
Duplicates, as built: embedding once per text version (`runtime.embed.once-per-text-version`,
`db/embeddings.py:610, 832`) and once at the end of a recipe batch (ruling 5); a thumbnail job whose file
exists ends done (`jobs.settle_made_thumbnails`, `:1563`); one live read per page (#5848); a page already
read is a cache hit on Retry; the NLP draft keeps `nlp_text_sha` (`derivatives.py:1042`). Segment (line
and region) pictures are cached: `media/segment_pictures.py:95` keys a picture on the segment's geometry
and the options, `existing_picture` (`:114`) finds it as a rendition row with that key, and an edited
segment is a new key, so nothing is rebuilt that has not changed (VERIFIED). The one gap the spec already
carries: the inputs fingerprint as a general rule (`activity.durable.nothing-twice`, #5357).

**17. Per-step deep reviews: done or owed.** "Done" means spec lines, run-side and not-run tests, and a
real run that exercised the step and left its findings in an issue. All ten steps have the two tests
(`test_a_run_through_every_step.py`, `test_every_step_says_why_it_did_not_run.py`).

| Step | Real runs with findings | Status | Order |
|---|---|---|---|
| Image prep (thumbnails, split) | dogfood B12, M4 (#6193, #6203, #5690) | done | — |
| Lines (regions, lines) | M4 and the Pro (#6075, #6076, #5846, #5929, #6219) | done; the cores line (#6229) is new | — |
| Leave out | tests only | owed | 4 |
| Read | M4 (#6219, #5848, #5932, #6125) | done | — |
| Translate / normalise | tests only (#5921 text-reflow found by the M4 pause tests) | owed | 5 |
| Names | #5690 (drafts starved the step) | partly; the spaCy-in-a-step row is open | 1 |
| Dates | tests only | owed | 6 |
| Documents | #5609 (Stop keeps finished folders) | partly | 3 |
| Statements | tests only | owed | 7 |
| Vector | M4 (#6218, #6186, #6221) | done | — |
| Catalogue | #6087 (deepest first) | partly | 2 |

Order for the owed ones: Names, Catalogue, Documents, Leave out, Translate/normalise, Dates, Statements:
the first three run on every project and touch the cloud and the graph; the last four are cheap and
local or rarely on.

**18. Deleting a folder, and undoing it.** Read from `api/routes/document/documents.py` and the trash spec
(`safety/trash.md`; cross-references, not repeated: `safety.trash.dependants-go-with-their-source`
[PARTIAL] hidden-not-deleted, `safety.trash.every-read-leaves-it-out` [GAP], `safety.trash.put-back`
[PARTIAL], `undo.offered-after-a-removal` [GAP]).
- *Runs and queued jobs on the folder's pages.* Delete is soft (`delete_document_impl`, `:3223`, sets
  `deleted_at` on the subtree and nothing else, VERIFIED). A Start after it plans live pages only
  (`unit_of_work_ids`); a folder trashed after Start planned is an empty scope (`runner.py:1365`); the
  import's stages skip a trashed page (`derivatives.py:771, 858, 984, 1048`). A Kraken, served-model or
  fan-out page already queued or running is NOT checked (INFERRED from the absence of any `deleted_at`
  read in `execution/jobs.py`, `workflows/builder.py`, `vision_base.py`): it reads the hidden page, saves
  its result on it, and Activity says nothing of the Trash. Nothing stops, so nothing fails and nothing
  says why.
- *Readings, names, embeddings, thumbnails, cost record.* Kept, hidden: every row stays, the job rows
  (the cost record, `jobs_on_subjects`) stay; search leaves a trashed page out (`search/core.py:404,
  1816`); only a purge deletes the vectors (`:3300`).
- *Undo or Put Back.* `restore_documents_impl` (`:3321`) clears `deleted_at` and queues nothing: no model
  pass, no re-embed, no thumbnail remade (VERIFIED). Everything is as it was. A run was not stopped by the
  delete, so nothing offers Run again on what was missed; after Put Back the pages read mid-trash are done.
Filed #6232 (`activity.run.trashed-pages-leave-the-run`): a queued page in the Trash ends skipped with
that reason, a page mid-read keeps its result hidden, the summary offers Run again on what was missed.

**Decision 5. Where the local/cloud line is drawn** (#6233). *Recommend:* lines always local; the text
steps to the cloud when the local pace measured on the run passes a stated threshold; the network lane at
the provider's limit; the Batch API for runs nobody waits for.
