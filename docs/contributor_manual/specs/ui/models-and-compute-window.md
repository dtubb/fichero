# UI — The Models and Compute window — Design Spec (#6588, #4307)

> Milestone: ai-settings (until the hygiene in `reviews/2026-11-18-runner-reliability-plan.md` renames it; the window's
> issues are filed there and in `activity`)
> Manual: TBD — a "Models and Compute" section: what the window shows (every model and place, what is installed and
> loaded, what each costs, what is running on it now), what you can do there (download, unload, delete, add a key, add a
> Mac or a cluster, start a training), and what stays in Settings.
>
> Design-led (Testing Constitution). **Status: DRAFT 2026-11-18** (the reviewer, from the owner's concern of
> 2026-11-18 and his rulings of 2026-11-15/16 on Activity's Models tree; the owner approves). A COMPANION of
> `ui/activity-pane.md` (the house style: sidebar › centre › Inspector, the one verb list, the states table, the graphs
> pane), `ai/ai-settings.md` (what Settings › AI holds today), `ai/where-models-run.md` (the catalogue of places, §2.2)
> and `compute/runner-reliability.md` (what a row says when its work fails). This file holds the DELTA: the things that
> are about MODELS and PLACES leave Settings and become ONE window in Activity's style; Settings keeps preferences.
>
> **Owns / Does not own.** This spec OWNS the Models and Compute window: every model and place as a row with its state,
> account, memory, what uses it now and what failed on it, the verbs on them (download, unload, delete, add a key, add a Mac or
> a cluster, test), and what leaves Settings. It does NOT own: the Activity rows and the one job model (`ui/activity-pane.md`);
> how a failure on a model or place is classified, paused or alerted (`compute/runner-reliability.md`); which model and place a
> step chooses, egress and the caps (`ai/where-models-run.md`); a recipe run (`source/recipes-run.md`); choosing a model in Set
> Up (`source/recipe-designer.md`).
> Tags: **[OK]** built · **[PARTIAL]** exists in part · **[GAP]** designed, not built · **[BROKEN]** built and wrong.
> Every non-[OK] line cites an issue.

## Intent (the design)

A person opens one window and sees everything that can do work for them and how it is: every model (on this Mac, on
another Mac, at a cluster, at a cloud provider), whether it is downloaded, loaded in memory, broken or missing; every
place and its account (a key, credit, limits, reachable or not); this Mac's RAM and GPU and which models can run here;
what is using each model right now and what failed on it and why; what could be unloaded or deleted and how much it
would give back. **Models are found by search and bookmarked, never "added"** (owner 2026-11-18): the window's
search is the recipe finder's one job (`find-models`: Kraken's repository on Zenodo, HTR-United, Hugging Face), a found
card is bookmarked (kept, not downloaded) or downloaded, and **the window shows the cards the recipe runner can actually
use right now**: the same list `GET /api/recipes/candidates` offers Set Up, so what the owner sees here is what a recipe
can reach. They act there: search, bookmark, download, download again, unload, delete, use for a step, add a key to a
provider, connect a Mac or a cluster, test a connection, start or watch a training. Settings keeps what is a preference
(whether cloud is allowed, the caps, the defaults per kind of work); the window holds what is a thing with a state.

It lives beside Activity and shares its bones: the same `NavigationSplitView` (a source list, the one table, the
Inspector), the same toolbar conventions, the same verb list where a verb applies, the same graphs pane. The engine's
one list `GET /api/activity/models` (`workflows/activity_models.py`, built for Activity's Models tree,
`activity.window.models-tree`) is its spine; the window adds no second model list.

## Prior art / best practices (don't invent from scratch)

- **Xcode › Settings › Components / Platforms**: one table of downloadable things with size, installed state, a
  Download and Delete per row, the space they take, and a "what uses it" column. The closest Apple precedent.
- **Ollama, LM Studio, Hugging Face's cache tool (`hf cache`)**: a model list with downloaded, loaded (in memory),
  size on disk, last used, and Unload/Delete; LM Studio shows "fits in your RAM" per model. We adopt the resident/loaded
  distinction and the "fits here" badge.
- **Activity Monitor (macOS)**: the Memory tab's pressure graph and "memory used of total" are the Mac row.
- **Slurm's `squeue`/`sacct` and the Alliance's CCDB**: a cluster has an allocation, a queue and a key; we show the
  same three facts, not Slurm's columns.
- **The owner's rulings of 2026-11-15/16** (`activity.window.models-tree`, `activity.resources.everything-measured`):
  place › provider › model, filled icon when loaded, a dot when active, memory beside each, "what nothing measures is —,
  never 0", every place listed before anything ran there. This window is those rulings grown into a surface.
- **What we do differently.** No toggles for how models run (no "use GPU", no thread count): the engine measures and
  decides; the window shows and lets the person download, unload, delete, add and test. Dead-simple UX.

## What leaves Settings, what stays

| Today in Settings › AI (`ai/ai-settings.md`) | Goes to | Why |
|---|---|---|
| The providers list (cloud and local rows, `ProvidersView`), each row's key, models, runtime status, Download / Start / Stop | **the window** (Places › Cloud; This Mac › runtimes) | a provider is a thing with a state and an account, not a preference |
| Local models and their downloads (`/api/local-models`, Kraken install, spaCy pipelines, Whisper, the search models), disk usage | **the window** (This Mac › models) | things with a state; the downloads are jobs |
| "Where models run" (`compute.target.lives-in-ai-settings`, GAP) and the HPC clusters (`/api/hpc/clusters`) | **the window** (Places › Remote) | a place is a row with a probe, a key and an account |
| Hugging Face: the token, the Jobs target, the monthly HF cap | token and target → **the window** (Places › Hugging Face); the cap stays | the cap is a preference |
| Training, ground truth and fine-tuning (`compute/training-and-evaluation.md`: Train a Model…, the models it made, their scores) | **the window** (Models › Trained here; a model's Inspector shows its held-out scores and provenance) | a trained model is a model row like any other |
| Apple Intelligence / Foundation Models availability, Apple Vision locales (`/api/providers/apple/availability`) | **the window** (This Mac › Apple) | a runtime with a state |
| Allow cloud AI services (the switch), the project override, the monthly and daily caps (`CloudCapsSection`) | **Settings** | preferences and permissions |
| The defaults per kind of work (the Defaults pickers: which model reads, names, embeds, transcribes speech by default) | **Settings**, reading the window's one list | a choice, not a thing; the picker stays the shared model row |
| Download location (where models are kept on disk) | **Settings** (one path field), shown read-only on This Mac's row in the window | a preference |
| Run Automatically, the speed control (#6023) | **Settings** (Activity's) | preferences |

Settings › AI after the move is one pane: Allow cloud (and the images rule), the caps, the defaults, the download
location, and one button "Models and Compute…" that opens the window.

## The window

### Sidebar (the source list)

Three sections, each item a grouping plus a column set over the one list, badged with the rows needing you (a broken
model, a provider without credit, a place not reachable), remembered per window:

- **Usable now** (the default item) — every card a recipe step can be given this minute: downloaded local models whose
  runtime is present and that fit this Mac, cloud models behind a provider with a key and credit, remote places that
  answered their probe. It is `GET /api/recipes/candidates` without a step filter: the finder's cards with `runs_here` or a
  reachable `runs_on`, nothing else. Beside it, **Bookmarked** (cards kept from a search, downloaded or not) and
  **Found** (the last search's cards, with why each cannot run here).
- **This Mac** — Runtimes (Kraken, spaCy, the search embedder, MLX / oMLX, Apple Vision, Apple Intelligence and Foundation
  Models, Whisper, YOLO and OpenCV), Models (every downloaded model, by runtime), Trained here.
- **Places** — Cloud (one item per provider row: OpenRouter, OpenAI, Anthropic, Google, Hugging Face's router, …),
  Remote (another Mac by name, each cluster, Hugging Face Jobs).
- **Work** — Running now (every model with a page or call in flight, from Activity's rows), Failed today (every failure
  whose cause is a model or a place, from `failure.kind`), Downloads.

This Mac's own row sits at the top of the sidebar (not a section): "This Mac · 16 GB · 9.2 GB used · Apple M-series
GPU · memory pressure normal", from `this_mac` of the models answer.

### Centre (the one table)

Columns (one table, the header's menu chooses; widths and order kept per item as in `activity.pane.columns-from-the-header`):

| Column | Default | Says |
|---|---|---|
| State glyph | on | filled when loaded, hollow when downloaded and idle, dotted when bookmarked and not downloaded, red X when broken, lock when blocked on a key or credit; a green dot (animated) when active |
| Usable | on | "Now" · "After download (2.1 GB)" · "Needs a key at <Provider>" · "No credit" · "Too big for this Mac (needs 9 GB)" · "No runtime in this build": the card's `runs_here` / `cannot_run_because` / `runs_on`, the finder's own words |
| Bookmark | on | a filled bookmark glyph when kept; press to keep or let go |
| Name | on | the model or place's display name; a model's build in grey (bf16, 4-bit MLX, Q4) |
| Where | on | This Mac · <another Mac's name> · <cluster> · <provider> |
| Size | on | on disk (a local model), or "—" |
| Memory | on | resident bytes when loaded; "~2.5 GB (estimated)" for Kraken's readers; "—" when nothing measures it |
| Fits here | on (This Mac items) | "Yes" · "Tight (needs 6 GB, 4 GB free)" · "No", from the one memory table (`ai.where.one-memory-number`) |
| Account | on (Places) | Ready · Needs key · No credit · Limited (the provider's own words, redacted) · Not reachable, from a real probe |
| Using now | on | the Activity rows with this model or place in flight: "Read lines ▶ 34/120 (Letters)" |
| Last failed | on | the newest failure's row words on this model or place today, with its fix button |
| Today | off | pages, calls, seconds, cost today |
| Egress | off | stays on this Mac · your machine · <company, country> · the institution |
| Licence | off | the card's licence and its source |

A model used today and not downloaded stays listed, hollow. What nothing measures is "—", never 0.

### Inspector (the selected row)

The existing Inspector column, an Models section (as `activity.pane.inspector-shows-the-selected-row` does for a job):

- **A model**: name, runtime, build, size, where it is kept (the folder, read-only), loaded since, memory, fits here, the
  card's licence and provenance, held-out scores for a trained model (`training-and-evaluation.md` Screen 4), the rows
  using it now, its failures today with their fixes, its pages and calls today; buttons Download / Download again /
  Unload / Delete / Reveal in Finder / Choose for… (a kind of work).
- **A place**: name, kind (endpoint or batch), egress, account (key present, credit or limit as the provider says it,
  Retry-After if it is limiting now, the dead mark with its cause and seconds left), the models it serves that this
  library's steps use, the calls in flight of its cap ("3 of 4"), cost today and this month against the caps (read-only
  here; the caps are Settings'), its failures today; buttons Add key… / Test connection / Open provider page / Remove.
- **This Mac**: RAM used of total, swap, pressure, the GPU, the processor's load, each lane's jobs of its width, which
  models are resident and what unloading each would give back; one button Unload idle models.
- **A cluster**: host alias, allocation, the key's state and the second factor, the image's presence and version, queue
  limits read from the profile, jobs queued and running with their `sacct` states; buttons Test connection / Make key /
  Sign in / Install image / Remove.
- **A download**: bytes done of total, time left, the row it will unblock; Stop.

### Toolbar

Leading: the same run controls as Activity (Play/Pause, Stop; `activity.window.run-controls`), since what runs on these
models is Activity's work. Then the **Search** field (the finder's one job, `find-models`: typed words, a language or a
script, searched on Zenodo's Kraken repository, HTR-United and Hugging Face; results land in **Found** as cards with the
finder's words for why each can or cannot run here; "Searching online…" while the job runs, as Set Up shows it), and
**Connect…** for PLACES only (a provider's key, a Mac, a cluster; never a model: a model is found and bookmarked, or
imported from a file by `#5460`'s path). The filter field sits in the bottom bar (`panes.chrome.one-filter-pattern`); the
centre's view picker is **Table | Graph** (Graph: memory resident over time per model; calls and pages per place; cost per
place), as `activity.window.centre-views`.

### Verbs

One list, in the context menu, the row's one button and the Models menu: **Bookmark** / **Remove Bookmark**,
**Download**, **Download Again**, **Unload**, **Delete** (the files; the bookmark stays), **Reveal in Finder**, **Use
for…** (a step of the open project's recipe: `POST /api/recipes/candidates/use`, the same route Set Up's finder calls),
**Add Key…**, **Test Connection**, **Open Provider Page**, **Show in Activity** (the rows using it), **Disconnect** (a
place). The row's one button is the fix of its newest failure when it has one (Download again, Add key, Open provider
page), else its state verb (Bookmark on a Found card / Download on a bookmarked one / Unload on a loaded one).

### Ties to Activity and to the runner contract

Every row answers "what is using it now" and "what failed on it and why" from Activity's rows and `failure.kind`
(`compute/runner-reliability.md`): a provider out of credit shows "No credit" in Account and the paused runs under
Using now, with the same Open provider page and Continue the alert offers; a broken search model shows red with
"Download again" and the embed jobs blocked under it; a Mac short of memory shows the held pages and which model is
resident. Choosing a model in Activity's Models tree opens it here; choosing a row here and pressing Show in Activity
filters Activity by `model:`.

## Behaviours

### A. The window and its bones

- `models.window.is-activitys-shape` — **[GAP]** (#6588, #4307) the window is a `NavigationSplitView` with a source
  list (This Mac, Places, Work), the one table and the Inspector, laid out by a pane kind (`PaneKind.models`) so a main
  window can show it as a pane; the toolbar leads with Activity's run controls; the bottom bar is the filter.
  *Test:* `ModelsWindowLayoutTests.swift` (the three sections, the pane kind, the Inspector follows the selection).
- `models.window.one-list` — **[PARTIAL]** (#6588; built: `GET /api/activity/models` with place › provider › model,
  `loaded`, `active`, memory, today's pages and calls, `this_mac`; not built: size on disk, `fits_here`, `account`, the
  card's licence, failures today, the Mac's GPU) the window reads ONE engine list, the models answer grown by the columns
  above; the local-models list (`/api/local-models`), the runtimes list (`/api/providers/local-runtimes`), the providers list
  and the clusters list are read by the engine into it, never by the app in parallel. *Test:*
  `fichero-server/tests/unit/api/test_activity_models_6588.py` (extend: each new field; "—" for what nothing measures).
- `models.window.columns-and-verbs-are-activitys` — **[GAP]** (#6588) the column menu, the kept widths, the verb pattern
  (one row button = the fix or the state verb; the rest in the context menu) and the Mail rule for several rows are
  Activity's (`activity.pane.columns-from-the-header`, `activity.pane.fix-button-has-words`). *Test:* `ModelsWindowVerbsTests.swift`.
- `models.window.needs-you-badge` — **[GAP]** (#6588) each sidebar item is badged with its rows needing you (broken,
  no credit, needs key, not reachable), and those rows sort first. *Test:* `ModelsWindowNeedsYouTests.swift`.

### A2. Search, bookmark, and what a recipe can reach (owner 2026-11-18)

- `models.search.is-the-finder` — **[PARTIAL]** (#5611, #5612, #5970; built in the engine and in Set Up: the `find-models`
  job on the search lane (`recipes/discovery.py` `search_online`, `search_online_for_step`: Zenodo's Kraken repository,
  HTR-United, Hugging Face), what it finds kept in the model store's `discovery/` folder (`keep_hub`, `found_for` per
  language), served as cards by `GET /api/recipes/candidates` with `runs_here`, `cannot_run_because` and `runs_on`, and
  Set Up's finder with "Searching online…" (`ModelFinderStore.searchOnline`); not built: the window's Search field and its
  Found item) the window's search IS the recipe finder's job: one search, one kept result, one card shape; nothing is
  searched twice and no second catalogue exists.
- `models.bookmark.kept-not-added` — **[GAP]** (#5460, #6588) a found card is BOOKMARKED, never "added": Bookmark keeps
  the card in the one kept list (`discovery/`, a `bookmarked` mark beside `found_for`) without downloading it, so it
  survives the next search letting it go; Download fetches a bookmarked card; Remove Bookmark lets it go when it is not
  downloaded and not used by a step; a card a step uses cannot lose its bookmark. *Test (to write, in
  `fichero-server/tests/unit/recipes/`):* a bookmarked card outlives a search that no longer finds it; a card a step uses
  refuses Remove Bookmark with the step named.
- `models.window.shows-what-a-recipe-can-reach` — **[GAP]** (#6588, #5976, #5974) the default item, Usable now, is
  exactly the set of cards Set Up could give a step this minute (`GET /api/recipes/candidates`, every step, filtered to
  `runs_here` true or a reachable `runs_on` with a key and credit); a card that cannot run says why in the finder's own
  words ("No runtime in this build", "Needs a key at <Provider>", "Too big for this Mac"), under Found or Bookmarked,
  never under Usable now. Acceptance: with Kraken installed, a bookmarked HF reader not downloaded and OpenRouter without
  credit, Usable now lists Kraken's cards and no OpenRouter card; Bookmarked lists the HF reader as "After download". *Test
  (to write):* the window's Usable now equals the candidates route's usable set for a seeded store.
- `models.row.use-for-a-step` — **[PARTIAL]** (#5611, #5612; built: `POST /api/recipes/candidates/use` sets a step's
  reader as a project override "chosen by you", and Set Up's step menu calls it; not built: the window's verb) Use for…
  on a usable card offers the open project's steps that take its kind and sets it as that step's model; the Start plan
  shows it at once.

### B. What a row says

- `models.row.installed-means-it-loads` — **[PARTIAL]** (#6591; `activity.download.installed-means-it-loads` owns the
  engine half, built; owed: the window's red X and Download again) a model reads installed only after a load check;
  a model that will not load reads broken with Download again, and the work blocked under it is listed in Using now.
- `models.row.loaded-and-active` — **[OK]** (#6588; `activity.window.models-tree` owns it) filled when resident,
  hollow when not, a green dot while a page or call is in flight; the memory beside it, estimated where it is. *Tests:*
  `fichero-server/tests/unit/api/test_activity_models_6588.py`, `fichero/Tests/Unit/general/Views/Activity/Pane/ActivityModelsTreeTests.swift`.
- `models.row.fits-here` — **[GAP]** (#5221, #4987) a This Mac model says whether it fits now (the one memory number
  against free memory and pressure, the rule `settings.local-model-refused-before-it-loads` already applies at load), and
  what would have to be unloaded for it to fit. *Test (to write, in `fichero-server/tests/unit/api/`):* with memory injected,
  never the machine's, a model under free memory reads "Yes", one over it "No" naming what to unload.
- `models.row.account-from-a-probe` — **[BROKEN]** (#5369, #4303, #5367; `keys.status-sees-supplied-keys`,
  `runtime.status-from-the-endpoint`) a place's Account column comes from the same lookup a call uses (keys the app
  supplies included) and from a real probe; today key status ignores app-supplied keys and no Swift code reads the
  runtimes endpoint, so a row can read ready with nothing behind it. *Test (to write, in `fichero-server/tests/unit/api/`):* a
  stub probe that refuses gives "Not reachable"; an app-supplied key reads Ready; no key reads Needs key.
- `models.row.credit-and-limits` — **[GAP]** (#6675, #6354) a provider that answered no credit, a key limit or a rate
  limit shows it in Account in the provider's words (redacted), with the dead mark's seconds left and the calls in flight
  of its cap; the row's button is Open provider page; the paused runs are listed under Using now with Continue.
  *Test:* `ModelsRowAccountTests.swift` (a `no-credit` failure and a dead mark render those words and that button).
- `models.row.using-now-and-last-failed` — **[GAP]** (#6588, #6354) Using now lists the Activity rows in flight on this
  model or place; Last failed shows the newest `failure` on it today with its fix button; Show in Activity filters by it.
  *Test:* `ModelsRowActivityTiesTests.swift`.
- `models.row.what-unloading-gives-back` — **[GAP]** (#4987, #4999) This Mac's Inspector lists each resident model with
  its memory and the one button Unload idle models, which calls `release_idle_models` and shows what was freed.
  *Test (to write, in `fichero-server/tests/unit/api/`):* the route frees the idle embedder and answers its name; a model with a
  page in flight is kept.
- `models.row.download-reports-bytes` — **[PARTIAL]** (#6592; `activity.download.says-bytes-and-time-left` owns it) a
  Downloads row says bytes done of total and the time left for every runtime.
- `models.row.unmeasured-is-dash` — **[OK]** (#6588; `activity.resources.everything-measured` owns it) what nothing
  measures is "—", never 0. *Test:* `fichero-server/tests/unit/api/test_activity_models_6588.py`.

### C. Places

- `models.place.every-place-listed` — **[PARTIAL]** (#6588; the owner's ruling of 2026-11-16, built in Activity's
  Where) every place work can run is listed before anything ran there: this Mac, each enabled provider, each added Mac,
  each cluster, Hugging Face Jobs. Owed here: the window's own rows and the Connect… sheet.
- `models.place.add-a-mac` — **[GAP]** (#5951, #5238; `compute/targets-and-connection.md` owns the connection) Connect… a
  Mac asks its address, probes it, labels it "your machine" (egress own-machine) and lists the models it serves.
- `models.place.add-a-cluster` — **[GAP]** (#5454, #5642; `compute/hpc-runner-acenet.md` owns the flow) Connect… a cluster is
  the existing `/api/hpc/clusters` flow (host, user, folder, allocation; Make key; Sign in; Test connection; Install image)
  as the Inspector's buttons; the row's Account is the probe's answer. Built: the routes and the HPC settings view; owed:
  the rows here and Settings' view retired.
- `models.place.hf-jobs` — **[GAP]** (#5398, #5740) Hugging Face Jobs is a place row with its token's state, the image,
  the monthly cap (read-only, Settings'), its jobs running and queued with far-side state and cost.
- `models.place.egress-from-the-address` — **[GAP]** (#5582; `ai.where.*` A own the rule) the Egress column is worked
  out from the address, never the provider type.

Carried from `ai/where-models-run.md` §A and §G on 2026-11-18 (ids, tags, citations and issue numbers unchanged); the window is
the surface those two lines describe, `models.row.account-from-a-probe` is their engine rule.

- `ai.where.settings-lists-places` — **[GAP]** (#5454, #5367) Settings, AI, "Where models run" lists
  the places with probed state, egress class and account.
- `ai.where.place-status-is-probed` — **[BROKEN]** (#5367, #4303) a place's state in Settings is a
  probe's result; today the dot is `isLocalProvider || hasApiKey`
  (`ProvidersView+ProviderSettingsRow.swift:40`), so a stopped remote Ollama shows green.

### D. Trained models and ground truth

- `models.trained.are-rows` — **[GAP]** (#5439, #5440; `compute/training-and-evaluation.md` owns the training) a model
  trained here or on a cluster is a row under This Mac › Trained here with its held-out scores, provenance and where it
  can run, and Choose for… sets it for a step; Train a Model… stays on the folder's context menu and the training's row is
  Activity's.
- `models.ground-truth.counts` — **[GAP]** (#5119, #5446; the mark, the rule and the sidebar's Ground Truth smart folders
  are `source/ground-truth.md`'s) a trained model's Inspector says how many ground-truth lines and pages it was trained
  on and when the set was last added to, the same count the sidebar's Ground Truth › Lines folder shows; the set itself
  stays in the project.

### E. Settings after the move

- `models.settings.keeps-preferences` — **[GAP]** (#4307, #4665) Settings › AI is one pane: Allow cloud and the images
  rule, the monthly and daily caps, the defaults per kind of work (the shared model row over the window's one list), the
  download location, and "Models and Compute…"; the providers list, the local models, the runtimes, the clusters and the
  HF token leave it. *Test:* `AISettingsAfterTheMoveTests.swift` (the pane has those controls and no provider rows).
- `models.settings.one-download-location` — **[GAP]** (#5460) one path field in Settings where models are kept; the
  window shows it read-only on This Mac's row with the space used, and Reveal in Finder opens it.
- `models.settings.deep-links-still-land` — **[GAP]** (#6354) the alert's `open-settings` with `settings.ai.providers`
  opens the window on that provider's row with the key field focused; `settings.ai.localModels` opens This Mac › Models.

## Build order

### Stage 1 — The window over the one list

#### Step 1.1 — The pane kind, the three sections, the Inspector (#6588)
- Behaviours: `models.window.is-activitys-shape`, `models.window.columns-and-verbs-are-activitys`, `models.window.needs-you-badge`
- Tests: fichero/Tests/Unit/general/Views/Activity/Pane/ActivityModelsTreeTests.swift (the tree the window grows from; new Swift tests of the layout and verbs to write beside it)
- Size: M

#### Step 1.2 — The one list grows: size, fits here, account, failures today, the GPU (#6588)
- Behaviours: `models.window.one-list`, `models.row.fits-here`, `models.row.account-from-a-probe`, `models.row.using-now-and-last-failed`
- Tests: fichero-server/tests/unit/api/test_activity_models_6588.py (extended with the new fields; the fits-here and account-probe tests to write beside it)
- Size: M

#### Step 1.3 — The places listed with a probed state, in the window not Settings (#5454, #5367)
- Behaviours: `ai.where.settings-lists-places`, `ai.where.place-status-is-probed`
- Tests: fichero-server/tests/unit/api/test_activity_models_6588.py (extended: a stub probe's answer is the row's Account)
- Depends on: 1.2
- Size: S

### Stage 2 — Models: search, bookmark, download, load, unload, delete

#### Step 2.1 — Installed means it loads; downloads report bytes; unload gives back (#6591, #6592)
- Behaviours: `models.row.installed-means-it-loads`, `models.row.download-reports-bytes`, `models.row.what-unloading-gives-back`
- Tests: fichero-server/tests/unit/llm/test_every_download_reports_bytes_6592.py, fichero-server/tests/unit/db/test_search_model_downloads_in_the_app.py (the unload route's test to write)
- Depends on: 1.2
- Size: M

#### Step 2.2 — Search is the finder; bookmark, not add; Usable now is what a recipe can reach (#5611, #5460)
- Behaviours: `models.search.is-the-finder`, `models.bookmark.kept-not-added`, `models.window.shows-what-a-recipe-can-reach`, `models.row.use-for-a-step`
- Tests: fichero-server/tests/unit/recipes/test_hub_discovery_quality_5594.py, fichero-server/tests/unit/recipes/test_candidates_filtered_then_ranked_4950.py (extended with the bookmark mark; the Usable-now equality test to write beside them)
- Depends on: 1.2
- Size: M

### Stage 3 — Places

#### Step 3.1 — Providers' credit and limits; Connect… a Mac, a cluster, HF Jobs (#6675, #5951, #5454)
- Behaviours: `models.row.credit-and-limits`, `models.place.every-place-listed`, `models.place.add-a-mac`, `models.place.add-a-cluster`, `models.place.hf-jobs`, `models.place.egress-from-the-address`
- Tests: fichero-server/tests/unit/api/test_activity_models_6588.py (extended: clusters and provider accounts in the one list; a Swift test of the Account cell's words and button to write)
- Depends on: 1.2
- Size: L

### Stage 4 — Trained models, and Settings slimmed

#### Step 4.1 — Trained models as rows; Settings keeps preferences; deep links land (#5439, #4307)
- Behaviours: `models.trained.are-rows`, `models.ground-truth.counts`, `models.settings.keeps-preferences`, `models.settings.one-download-location`, `models.settings.deep-links-still-land`
- Tests: fichero/Tests/Unit/general/Views/RunFailureAlertTests.swift (the `open-settings` deep link lands on the window; a Swift test of the slimmed Settings pane to write)
- Depends on: 2.1, 3.1
- Size: M

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | the row's glyph from `loaded`/`active`/`broken`/account; the one button is the fix; needs-you first | `fichero/Tests/Unit/general/Views/Models/` |
| Availability (Swift) | y | the window opens from Settings and from Activity's Models tree; the pane kind is offered | the same |
| Backend (pytest) | y | the one list's fields; "—" for the unmeasured; fits here from injected memory; account from a stub probe | `fichero-server/tests/unit/api/test_activity_models_6588.py` and the files named above |
| MCP | y | `fichero_local_models`, `fichero_providers`, `fichero_hpc_clusters` read the same facts | `fichero-mcp/tests/test_mcp_generated.py` |
| CLI | n | — | — |
| Click-around (XCUITest, Mac) | later | choose a broken model, press Download again, the blocked rows start | — |
| iPhone / iPad | n | the window is the Mac's; the iPad shows the Mac's list read-only (later) | — |

## Accessibility identifiers

`models.window` · `models.sidebar.<item>` · `models.table` · `models.row.<id>` · `models.row.<id>.button` ·
`models.inspector` · `models.toolbar.search` · `models.toolbar.connect` · `models.toolbar.runControls` · `models.filter` ·
`models.row.<id>.bookmark`.

## UX completeness

| Control (a11y id) | Label | Tooltip/help text | Localized key | Verified by |
|---|---|---|---|---|
| `models.toolbar.search` | Search | Find models on Zenodo, HTR-United and Hugging Face; bookmark what you want to keep | `models.search` | test |
| `models.toolbar.connect` | Connect… | Connect a provider's key, a Mac or a cluster | `models.connect` | test |
| `models.row.<id>.bookmark` | Bookmark | Keep this card without downloading it | `models.bookmark` | test |
| `models.row.<id>.button` | the fix or state verb | the row's one action | `models.row.button.<verb>` | test |
| `models.inspector.unloadIdle` | Unload Idle Models | Frees the memory of models nothing is using | `models.unloadIdle` | test |

## Open questions for the owner

1. **Window or pane first?** Recommended: the pane kind first (Activity's own rule, `activity.window.views-are-panes`),
   with the window as that pane plus the Inspector; the Settings button opens the window.
2. **Does the HF monthly cap stay in Settings with the cloud caps, or move with the token?** Recommended: stays (a cap is
   a preference); the window shows it read-only on the Hugging Face Jobs row.
3. **Delete a model that a step's default names?** Recommended: refuse with the step named and offer Choose for….
