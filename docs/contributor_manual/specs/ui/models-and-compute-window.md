# UI — The Models and Cluster window — Design Spec (#6588, #4307)

> Named Models and Cluster by the owner (2026-11-19; it was Models and Compute). The file name and the `models.*` ids stay.

> Milestone: ai-settings (until the hygiene in `reviews/2026-11-18-runner-reliability-plan.md` renames it; the window's
> issues are filed there and in `activity`)
> Manual: TBD — a "Models and Cluster" section: what the window shows (every model and place, what is installed and
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
> **Owns / Does not own.** This spec OWNS the Models and Cluster window: every model and place as a row with its state,
> account, memory, what uses it now and what failed on it, the verbs on them (download, unload, delete, add a key, add a Mac or
> a cluster, test), what leaves Settings, the UI of the model loop for each recipe step (section F; the loop itself is
> `compute/distillation.md`'s) and each model's run settings (section G). It does NOT own: the Activity rows and the one job model (`ui/activity-pane.md`);
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

**It is also where a person works the model loop** (the owner's goal of 2026-11-19; `compute/distillation.md`): for
each step of the open project's recipe, one row says which model does the step and where, what taught it, how much
corrected work there is, which trained candidates exist and whether each beat the current model, and offers the next
thing to do: run with a teacher, train, evaluate, use, publish. The same sheet and the same jobs as everywhere else; the
window adds no second way to train.

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
location, and one button "Models and Cluster…" that opens the window.

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
- **Recipe steps** (when a project is open) — one row per step of its recipe, the model loop's state for that step
  (section F).
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

- `models.window.is-activitys-shape` — **[PARTIAL]** (#6588, #4307) the window is a `NavigationSplitView` with a source
  list (Models: All Models, Usable now, Bookmarked, Found; Providers; This Mac, Places, Work), the one table and the Inspector, laid out by a pane kind (`PaneKind.models`) so a main
  window can show it as a pane; the toolbar leads with Activity's run controls; the bottom bar is the filter.
  *Test:* `ModelsWindowLayoutTests.swift` (the three sections, the pane kind, the Inspector follows the selection). **Built:** the sidebar's three sections and the rule that groups the one list under each item (`ModelsWindowModel`), tested in `fichero/Tests/Unit/general/Views/ModelsWindow/ModelsWindowLayoutTests.swift`. **Also built:** the `Window` scene "Models & Cluster" (Window menu, id `models-cluster`), `PaneKind.models`, `ModelsPaneView` (the `NavigationSplitView`, the one table of size, memory, fits here, account, using now and last failed, and the Inspector), reading the one list through `ModelsAnswerStore`, which Activity's Models tree shares. Tested in `fichero/Tests/Unit/general/Views/ModelsWindow/ModelsWindowSceneTests.swift` (the window id and title, the pane kind, the sidebar from the model, the needs-you sort, the Inspector following the selection, the shared store) and `ActivityWindowSelectionStateTests.swift` (the scene is a `Window` that replaces `.newItem` with the File menu). **Also written, without a view test:** the Models section (Usable now the default item, Bookmarked, Found), its Search field and a button column on the rows. **Not built:** the This Mac row's pressure, the run controls, the filter and the column menu.
- `models.window.one-list` — **[PARTIAL]** (#6588; built: `GET /api/activity/models` with place › provider › model,
  `loaded`, `active`, memory, today's pages and calls, `this_mac`; not built: size on disk, `fits_here`, `account`, the
  card's licence, failures today, the Mac's GPU) the window reads ONE engine list, the models answer grown by the columns
  above; the local-models list (`/api/local-models`), the runtimes list (`/api/providers/local-runtimes`), the providers list
  and the clusters list are read by the engine into it, never by the app in parallel. *Test:*
  `fichero-server/tests/unit/api/test_activity_models_6588.py` (extend: each new field; "—" for what nothing measures). **Built:** `size_bytes`, `licence`, `fits_here` with `needs_bytes`, `fits_note` and `unload_to_fit`, `account`, `using_now`, `last_failed` on each model and `gpu` on `this_mac`, read by `ActivityModelEntry`; tested in `test_activity_models_6588.py`. **Not built:** the window that draws them.
- `models.window.columns-and-verbs-are-activitys` — **[PARTIAL]** (#6588) the column menu, the kept widths, the verb pattern
  (one row button = the fix or the state verb; the rest in the context menu) and the Mail rule for several rows are
  Activity's (`activity.pane.columns-from-the-header`, `activity.pane.fix-button-has-words`). *Test:* `ModelsWindowVerbsTests.swift`. **Built:** the row's one button as a rule (`ModelsWindowModel.button`), tested in `ModelsWindowLayoutTests.swift`. **Not built:** the column menu, kept widths, the context menu and the Mail rule for several rows.
- `models.window.needs-you-badge` — **[PARTIAL]** (#6588) each sidebar item is badged with its rows needing you (broken,
  no credit, needs key, not reachable), and those rows sort first. *Test:* `ModelsWindowNeedsYouTests.swift`. **Built:** the count and the sort (`ModelsWindowModel.badge`, `needsYouFirst`), tested in `ModelsWindowLayoutTests.swift`. **Also built:** the badge drawn on each sidebar item (`ModelsWindowModel.sidebar`), tested in `ModelsWindowSceneTests.swift`. **Not built:** a "no credit" row, which the engine does not yet report.

### A2. Search, bookmark, and what a recipe can reach (owner 2026-11-18)

- `models.search.is-the-finder` — **[PARTIAL]** (#5611, #5612, #5970; built in the engine and in Set Up: the `find-models`
  job on the search lane (`recipes/discovery.py` `search_online`, `search_online_for_step`: Zenodo's Kraken repository,
  HTR-United, Hugging Face), what it finds kept in the model store's `discovery/` folder (`keep_hub`, `found_for` per
  language), served as cards by `GET /api/recipes/candidates` with `runs_here`, `cannot_run_because` and `runs_on`, and
  Set Up's finder with "Searching online…" (`ModelFinderStore.searchOnline`); built in the window, untested by any view test: its Search field and its Found item) the window's search IS the recipe finder's job: one search, one kept result, one card shape; nothing is
  searched twice and no second catalogue exists.
- `models.bookmark.kept-not-added` — **[PARTIAL]** (#5460, #6588) a found card is BOOKMARKED, never "added": Bookmark keeps
  the card in the one kept list (`discovery/`, a `bookmarked` mark beside `found_for`) without downloading it, so it
  survives the next search letting it go; Download fetches a bookmarked card; Remove Bookmark lets it go when it is not
  downloaded and not used by a step; a card a step uses cannot lose its bookmark. *Test (to write, in
  `fichero-server/tests/unit/recipes/`):* a bookmarked card outlives a search that no longer finds it; a card a step uses
  refuses Remove Bookmark with the step named. **Built:** `discovery.bookmark` / `remove_bookmark` and `keep_hub` keeping a bookmarked card, tested in `fichero-server/tests/unit/recipes/test_bookmark_kept_not_added_5460.py`; The routes `POST` and `DELETE /api/recipes/candidates/bookmark` (404 for a card no search found, 409 naming the step for a card a step uses), tested in `fichero-server/tests/unit/recipes/test_bookmark_route_5460.py`. `GET /api/recipes/candidates` says on each card `bookmarked` and `bookmark_key` (the key the two routes take), and `discovery.hub_cards` lists a bookmarked card whichever languages are asked, so a card no search finds any more is still listed; this holds for the rules' own list too (a kept card found for German can be ranked for a project in another language), tested in `fichero-server/tests/unit/recipes/test_candidates_say_bookmarked_6588.py`. The app's pure rules for a card's list, one verb and Usable words (`ModelCandidateRules`), tested in `fichero/Tests/Unit/general/Views/ModelsWindow/ModelCandidateRulesTests.swift`. The window's Models section (Usable now, Bookmarked, Found), its Search field and its Search Online button, and each card's one verb through `ModelsWindowStore`, are written but have no test of their own (no view test runs them), so the tag stays [PARTIAL]. Delete of an installed row (`model_type` and `model_id` on the models answer, tested in `fichero-server/tests/unit/api/test_activity_models_6588.py`) asks first, then calls the delete route with `confirm=true`. **Not built:** the bookmark glyph, a per-model Unload (the engine has only unload-idle) and a Load verb (the engine has no load route).
- `models.window.shows-what-a-recipe-can-reach` — **[PARTIAL]** (#6588, #5976, #5974) the default item, Usable now, is
  exactly the set of cards Set Up could give a step this minute (`GET /api/recipes/candidates`, every step, filtered to
  `runs_here` true or a reachable `runs_on` with a key and credit); a card that cannot run says why in the finder's own
  words ("No runtime in this build", "Needs a key at <Provider>", "Too big for this Mac"), under Found or Bookmarked,
  never under Usable now. Acceptance: with Kraken installed, a bookmarked HF reader not downloaded and OpenRouter without
  credit, Usable now lists Kraken's cards and no OpenRouter card; Bookmarked lists the HF reader as "After download". *Test
  (to write):* the window's Usable now equals the candidates route's usable set for a seeded store. **Built:** the acceptance's three cards through `ModelCandidateRules` in `ModelCandidateRulesTests.swift::acceptanceLists`; **Not built:** the equality against the route's own answer.
- `models.row.use-for-a-step` — **[PARTIAL]** (#5611, #5612; built: `POST /api/recipes/candidates/use` sets a step's
  reader as a project override "chosen by you", and Set Up's step menu calls it; not built: the window's verb) Use for…
  on a usable card offers the open project's steps that take its kind and sets it as that step's model; the Start plan
  shows it at once.

### A3. Providers and Models in the sidebar, search over every model, add a model, and the window replaces Settings' AI panes (owner 2026-11-24)

- `models.window.providers-and-models-in-the-sidebar` — **[PARTIAL]** (#6588, owner 2026-11-24) the sidebar has two sections
  beside This Mac, Places and Work: **Models** (All Models: every model, local and cloud, then Usable now, Bookmarked,
  Found) and **Providers** (one item per provider the one list names: the local runtimes Kraken, MLX, Apple Vision and
  Apple Intelligence first, then the cloud providers, each by name, each badged with its rows needing you). Each item
  lists its own rows; the Inspector of a row says what it does, its size, where it runs and its cost. Acceptance: with
  Kraken and Apple Intelligence on this Mac and an Anthropic model without a key, Providers lists Apple Intelligence,
  Kraken, Anthropic in that order, Anthropic badged 1; All Models lists all three models; a provider item lists only its
  own. *Test:* `ModelsWindowLayoutTests.swift::providersSection`, `allModelsAndProviderRows`, `inspectorSaysRunsOnAndCost`.
  **Built:** `ModelsWindowModel.providers`, `Item.provider`, `Item.allModels`, the Providers section in
  `ModelsWindowModel.sidebar`, the Inspector's Runs on and Cost lines, tested there. **Not built:** a cloud model's price (the
  models answer carries none; ui-5 and cards-1), whether the project allows cloud use drawn on a cloud row, "what it does".
- `models.search.over-every-model` — **[PARTIAL]** (#6588, owner 2026-11-24) the window's search field filters the list shown
  by name, provider, place or licence, every word needed, ignoring case and accents; the finder's Search Online reaches
  further (cards, Hugging Face, Zenodo and the cloud providers' lists: by name, job, script, language or period) through
  the one `find-models` job (`models.search.is-the-finder`), not a second catalogue. *Test:*
  `ModelsWindowLayoutTests.swift::searchOverTheList`. **Built:** the filter over the models answer's rows. **Not built:**
  the cloud providers' model lists and a search by job, script, language or period over rows that are not cards.
- `models.apple-intelligence.is-a-provider-and-a-model` — **[OK]** (#6588, owner 2026-11-24: "missing today") on a Mac where
  the engine can run Apple Intelligence (the fm-bridge present, macOS 26 with Apple Intelligence on:
  `local_model_choice.apple_intelligence_in_this_build`), the models answer lists a This Mac row "Foundation Models" under the
  provider "Apple Intelligence"; where it cannot, no row. *Test:*
  `fichero-server/tests/unit/api/test_activity_models_6588.py::test_apple_intelligence_is_a_provider_and_a_model_on_a_mac_that_has_it`.
  Offering it where its jobs fit, and a catalogue card for it, are `models.cards.richer-and-more` (cards-1).
- `models.settings.window-replaces-ai-panes` — **[PARTIAL]** (#6588, #4307, owner 2026-11-24) Models & Cluster folds in Settings'
  AI models and providers panes: every provider's key, switch, base URL and model list, the defaults per kind of work and
  the local models move into the window (a provider item's Inspector holds its key field and its switch; the model rows hold
  the defaults); Settings keeps at most a link, "Models & Cluster…" (this supersedes `models.settings.keeps-preferences`
  where it keeps the defaults and caps in Settings). Acceptance: no provider key field is reachable from Settings; the
  window's provider item saves and clears a key through the engine's key routes; the alert's `settings.ai.providers` link
  lands on that provider item. *Test:* `AISettingsPlacementTests.swift` (every AI tab is in exactly one place: the window or Settings). **Built (ui-4):** `AISettingsView(placement:)`: the window's item "Keys, Defaults & Downloads" (Providers section) draws the existing Defaults, Models & Providers (every provider's key, switch and model list) and Downloads tabs; Settings draws Advanced and an "Open Models & Cluster…" button; the old "Local LLM" selection resolves to Providers. **Not built:** the key field on each provider item's own Inspector (the pane is moved whole, not re-laid per item), and the `settings.ai.providers` deep link landing on a provider item.
- `models.manage.add-by-id-or-url` — **[GAP]** (#6588, #5460, owner 2026-11-24) from a search result the window downloads a
  local model or adds a cloud model; "Add by id or URL…" takes a Hugging Face id or a URL and resolves it through the same
  finder, so the added model is one card like any other, bookmarked until downloaded. *Test (to write):*
  `ModelsWindowAddTests.swift` (ui-5) and a pytest beside `test_bookmark_route_5460.py` for the by-id resolve.
- `models.cards.richer-and-more` — **[GAP]** (#6588, owner 2026-11-24) the catalogue's cards (`recipes/seed/cards.yaml`) say
  what a model does, its size, where it runs and its cost, and cover more models, Apple Intelligence's included, offered
  where its jobs fit. *Test (to write):* `fichero-server/tests/unit/recipes/` over the seed (cards-1).

### B. What a row says

- `models.row.installed-means-it-loads` — **[PARTIAL]** (#6591; `activity.download.installed-means-it-loads` owns the
  engine half, built; owed: the window's red X and Download again) a model reads installed only after a load check;
  a model that will not load reads broken with Download again, and the work blocked under it is listed in Using now.
- `models.row.loaded-and-active` — **[OK]** (#6588; `activity.window.models-tree` owns it) filled when resident,
  hollow when not, a green dot while a page or call is in flight; the memory beside it, estimated where it is. *Tests:*
  `fichero-server/tests/unit/api/test_activity_models_6588.py`, `fichero/Tests/Unit/general/Views/Activity/Pane/ActivityModelsTreeTests.swift`.
- `models.row.fits-here` — **[PARTIAL]** (#5221, #4987) a This Mac model says whether it fits now (the one memory number
  against free memory and pressure, the rule `settings.local-model-refused-before-it-loads` already applies at load), and
  what would have to be unloaded for it to fit. *Test (to write, in `fichero-server/tests/unit/api/`):* with memory injected,
  never the machine's, a model under free memory reads "Yes", one over it "No" naming what to unload. **Built:** `fits_here`, `needs_bytes`, `fits_note` and `unload_to_fit` on each sized installed model from `local_inference.fit_estimate` with memory injected, tested in `fichero-server/tests/unit/api/test_activity_models_6588.py::test_an_installed_model_says_its_size_licence_and_whether_it_fits_with_memory_injected`; `ActivityModelEntry.fitsWords` reads it. **Not built:** the column in a window, and "Tight (needs 6 GB, 4 GB free)" words.
- `models.row.account-from-a-probe` — **[PARTIAL]** (#5369, #4303, #5367; `keys.status-sees-supplied-keys`,
  `runtime.status-from-the-endpoint`) a place's Account column comes from the same lookup a call uses (keys the app
  supplies included) and from a real probe; today key status ignores app-supplied keys and no Swift code reads the
  runtimes endpoint, so a row can read ready with nothing behind it. *Test (to write, in `fichero-server/tests/unit/api/`):* a
  stub probe that refuses gives "Not reachable"; an app-supplied key reads Ready; no key reads Needs key. **Built:** a cloud or remote model row carries its place's `account` (`test_a_cloud_model_carries_its_places_account`); `places()` in `GET /api/activity/models` carries `account` (another Mac from a probe of its address, a cloud provider from `llm.get_api_key`, a cluster null), tested in `fichero-server/tests/unit/api/test_activity_models_6588.py::test_a_places_account_comes_from_a_probe_and_the_key_a_call_uses`; **Not built:** only `ActivityModelEntry.account` reads it (no view), and the probe is a reachability check of the address, not a model-list request.
- `models.row.credit-and-limits` — **[PARTIAL]** (#6675, #6354) a provider that answered no credit, a key limit or a rate
  limit shows it in Account in the provider's words (redacted), with the dead mark's seconds left and the calls in flight
  of its cap; the row's button is Open provider page; the paused runs are listed under Using now with Continue.
  *Test:* `ModelsRowAccountTests.swift` (a `no-credit` failure and a dead mark render those words and that button). **Built:** each cloud place in the answer carries `calls_in_flight`, `calls_cap` and `credit` (the newest no-credit, key-refused or rate-limited failure today on one of its models: words, kind, button), tested in `test_activity_models_6588.py::test_a_cloud_place_says_its_calls_in_flight_and_the_credit_a_failure_named`. **Not built:** the dead mark's seconds left (the engine keeps no provider-wide mark between runs), the paused runs under Using now, the Account cell and `ModelsRowAccountTests.swift`.
- `models.row.using-now-and-last-failed` — **[PARTIAL]** (#6588, #6354) Using now lists the Activity rows in flight on this
  model or place; Last failed shows the newest `failure` on it today with its fix button; Show in Activity filters by it.
  *Test:* `ModelsRowActivityTiesTests.swift`. **Built:** `using_now` (the kinds of job running on a model) and `last_failed` (the newest failed job's row words, kind and fix button) on each model row, tested in `test_activity_models_6588.py::test_a_failure_today_and_the_work_in_flight_ride_on_the_model`. **Not built:** the cells, Show in Activity, and `ModelsRowActivityTiesTests.swift`.
- `models.row.what-unloading-gives-back` — **[PARTIAL]** (#4987, #4999) This Mac's Inspector lists each resident model with
  its memory and the one button Unload idle models, which calls `release_idle_models` and shows what was freed.
  *Test (to write, in `fichero-server/tests/unit/api/`):* the route frees the idle embedder and answers its name; a model with a
  page in flight is kept. **Built:** `POST /api/activity/models/unload-idle` calls `release_idle_models` and answers what it freed by name, tested in `fichero-server/tests/unit/api/test_activity_models_6588.py::test_unload_idle_models_frees_the_idle_and_keeps_a_model_with_a_page_in_flight`; **Not built:** the Inspector's list of resident models and the button. The route and its action `activity.unload_idle_models` are the owner's (the Mac's models are shared by every project; `owner_only`, app scope), tested in `test_model_run_settings_6588.py::test_the_mac_wide_model_writes_are_the_owners`.
- `models.row.download-reports-bytes` — **[PARTIAL]** (#6592; `activity.download.says-bytes-and-time-left` owns it) a
  Downloads row says bytes done of total and the time left for every runtime.
- `models.row.unmeasured-is-dash` — **[OK]** (#6588; `activity.resources.everything-measured` owns it) what nothing
  measures is "—", never 0. *Test:* `fichero-server/tests/unit/api/test_activity_models_6588.py`.

- `models.manage.load-and-unload` — **[GAP]** (#6588, owner 2026-11-19) the window loads a downloaded model into memory now
  and unloads a loaded one (one model, not only the idle ones), refused with the reason when it does not fit
  (`models.row.fits-here`); the work happens as a row in Activity. **Built:** a loaded row's Unload calls `POST /api/activity/models/unload-idle`, which unloads every idle model, not that row's alone. **Not built:** a per-model unload and any load route.
- `models.manage.add-a-model` — **[GAP]** (#6588, #5460, #6747, owner 2026-11-19) the window adds a model: search Hugging
  Face or a provider (`models.search.is-the-finder`), then download it to the models folder (#6747), with its progress in
  Activity (`models.row.download-reports-bytes`).
- `models.manage.delete-a-model` — **[PARTIAL]** (#6588, #6747, owner 2026-11-19) the window deletes a downloaded model's files
  (the bookmark stays), says how much disk it frees, and asks first when a recipe uses it (open question 3), with the
  deletion shown in Activity. **Built:** the engine half of asking first: `DELETE /api/local-models/{model_type}/{model_id}`
  with a library open answers 409 naming the steps of its recipe whose model is this one (`recipes.discovery.steps_using_model`,
  the whole id, never a part of one), and deletes with `?confirm=true`; tested in
  `fichero-server/tests/unit/api/test_delete_model_names_its_steps_6588.py`. **Also written, without a view test:** an installed row's Delete verb calls the route without `confirm` first, shows the 409's step words in its alert, and sends `confirm=true` only on a second yes. **Not built:** the
  disk it frees, Choose for… (open question 3's recommendation) and the row in Activity.

### B2. Run settings per model (owner 2026-11-19)

The Inspector of a local model has a Run settings section: each knob with the engine's own value shown as the default and
what the setting costs this Mac (memory from the engine's per-page figure; time per page "—" until measured). Unset is the
engine's rule; a value out of range is refused with the range, never clamped.

- `models.settings.run-knobs` — **[PARTIAL]** (#6588; built: `llm/model_run_settings.py`, `GET`/`PUT
  /api/activity/models/run-settings/{runtime}`, and Kraken reading them) for Kraken, the knobs the engine has: pages at once
  (the cap `page_fan_out` still bounds by free memory), threads a page, lines per batch (`reader_batch_size`) and device
  (auto / CPU / GPU; `FICHERO_COMPUTE_DEVICE` still wins). Not built: the Inspector section; the other local runtimes
  (MLX, spaCy, Whisper, YOLO) have no such knob in the engine yet. *Tests:*
  `fichero-server/tests/unit/llm/test_model_run_settings_6588.py`. Writing them (the `PUT` and the action `models.set_run_settings`) is the owner's, since they apply to every project and `device` overrides the owner's compute preference; reading them needs a signed-in person.
- `models.settings.run-knobs-image-size-precision` — **[GAP]** (#6588) Kraken's maximum image size and its precision
  (32-bit or 16-bit): the engine has no such knob today (`kraken_runtime.py` reads neither), so each needs the engine rule
  first, with a test that the page is scaled or the reader runs at that precision.
- `models.settings.run-knobs-default-per-mac` — **[GAP]** (#6588, runner-perf's measurements) the default each knob shows
  is the value measured best on this Mac's class (cores, memory), not only the engine's formula; the time cost beside each
  setting is that measurement. Owed until runner-perf has measured.
- `models.settings.run-knobs-cost-shown` — **[PARTIAL]** (#6588; built: the route's `cost.memory_bytes`, tested for pages
  at once) each setting shows what it asks of this Mac before it is applied; not built: the Inspector's display, and
  `seconds_per_page` (null).

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
- `models.place.hf-jobs` — **[PARTIAL]** (#5398, #5740) Hugging Face Jobs is a place row with its token's state, the image,
  the monthly cap (read-only, Settings'), its jobs running and queued with far-side state and cost. **Built:** a Hugging Face Jobs place in the answer, its account the token's state, tested in `test_activity_models_6588.py::test_hugging_face_jobs_is_a_place_with_its_tokens_state`. **Not built:** the image, the cap, the jobs and the row.
- `models.place.egress-from-the-address` — **[PARTIAL]** (#5582; `ai.where.*` A own the rule) the Egress column is worked
  out from the address, never the provider type. **Built:** each place in `GET /api/activity/models` carries `egress` (this-mac, own-machine for an address off this Mac, provider, institution for a cluster), tested in `fichero-server/tests/unit/api/test_activity_models_6588.py::test_a_places_egress_comes_from_its_address_not_its_provider_type`. **Not built:** the column in the window, and the provider's company and country.

Carried from `ai/where-models-run.md` §A and §G on 2026-11-18 (ids, tags, citations and issue numbers unchanged); the window is
the surface those two lines describe, `models.row.account-from-a-probe` is their engine rule.

- `ai.where.settings-lists-places` — **[GAP]** (#5454, #5367) Settings, AI, "Where models run" lists
  the places with probed state, egress class and account.
- `ai.where.place-status-is-probed` — **[BROKEN]** (#5367, #4303) a place's state in Settings is a
  probe's result; today the dot is `isLocalProvider || hasApiKey`
  (`ProvidersView+ProviderSettingsRow.swift:40`), so a stopped remote Ollama shows green.

### D. Trained models and ground truth

- `models.trained.are-rows` — **[PARTIAL]** (#5439, #5440; `compute/training-and-evaluation.md` owns the training) a model
  trained here or on a cluster is a row under This Mac › Trained here with its held-out scores, provenance and where it
  can run, and Choose for… sets it for a step; Train… on a step's row and Train a Model… on a folder's context menu open
  the same sheet, and the training's row is Activity's. **Built:** `trained` in `GET /api/activity/models` (scores, where it can run, `not_for_release`), tested in `test_activity_models_6588.py::test_a_trained_model_is_a_row_under_this_mac_with_its_ground_truth_counts`. **Not built:** the rows in the window, Choose for… and the shared sheet.
- `models.ground-truth.counts` — **[PARTIAL]** (#5119, #5446; the mark, the rule and the sidebar's Ground Truth smart folders
  are `source/ground-truth.md`'s) a trained model's Inspector says how many ground-truth lines and pages it was trained
  on and when the set was last added to, the same count the sidebar's Ground Truth › Lines folder shows; the set itself
  stays in the project. **Built:** each trained row's `ground_truth` (pages, lines, lines checked by a person, held-out pages, from its card). **Not built:** when the set was last added to, the match with the sidebar's folder count, and the Inspector.

### E. Settings after the move

- `models.settings.keeps-preferences` — **[GAP]** (#4307, #4665) Settings › AI is one pane: Allow cloud and the images
  rule, the monthly and daily caps, the defaults per kind of work (the shared model row over the window's one list), the
  download location, and "Models and Cluster…"; the providers list, the local models, the runtimes, the clusters and the
  HF token leave it. *Test:* `AISettingsAfterTheMoveTests.swift` (the pane has those controls and no provider rows).
- `models.settings.one-download-location` — **[GAP]** (#5460) one path field in Settings where models are kept; the
  window shows it read-only on This Mac's row with the space used, and Reveal in Finder opens it.
- `models.settings.deep-links-still-land` — **[GAP]** (#6354) the alert's `open-settings` with `settings.ai.providers`
  opens the window on that provider's row with the key field focused; `settings.ai.localModels` opens This Mac › Models.

### F. The model loop, per recipe step

- `models.loop.steps-are-rows` — **[GAP]** (#5941, #6588) with a project open, Recipe steps lists each step of its
  recipe as a row drawn from the engine's one answer (`distill.loop.one-answer-per-step`): the step; its model and place
  now; its teacher, if one ran; its ground truth in the step's unit ("312 pages of lines corrected, 40 since the last
  training"); its newest candidate with the gate's verdict in words; and a state the person can act on ("Enough to
  train", "Training, epoch 3 of 20", "Candidate is not better: kept, not used", "Published, private"). A step that
  cannot be trained says so, with why. The window computes none of it. *Test (to write):* ModelLoopRowTests.swift
  (rows from a stub answer: each state's words; nothing shown that the answer lacks).
- `models.loop.verbs` — **[GAP]** (#5941, #5440) a step row's verbs, each the existing action and nothing new: **Run
  with a Teacher…** (the step's run on a chosen sample and hosted model, `distill.loop.teacher-any-step`, with its cost
  first); **Train…** (the one start sheet, `compute.tune.start-sheet`, with the places compared,
  `training.place.compared`); **Evaluate** (the evaluation job, `distill.eval.job`); **Use for This Step** (enabled
  only when the gate passed; otherwise the button's help says the verdict); **Publish…** (the publish sheet,
  `compute.publish.is-separate-and-asked-again`); **Show Corrections** (the step's ground truth in the library). The
  row's one button is the next of these the state allows. *Test (to write):* ModelLoopRowTests.swift (the one button per
  state; Use disabled with the verdict when the gate did not pass).
- `models.loop.verdict-in-the-inspector` — **[GAP]** (#4951, #5439) a candidate's Inspector shows it beside the step's
  current model on the same held-out pages: both scores, the pages, the noise band, speed, peak memory and cost per
  page, and the verdict in words (`distill.gate.one-rule`); a candidate that lost stays a row, marked Not Better, and
  can be deleted. *Test (to write):* ModelLoopRowTests.swift.
- `models.loop.published-state` — **[GAP]** (#5971) a trained model's row says where it is kept (In This Project, On
  This Mac, Published with the repository and Private, Gated or Public), and Not for Release where its training data
  forbids release, in which case Publish… is disabled with that reason (`compute.model.never-publishable-stays-so`).
  *Test (to write):* ModelLoopRowTests.swift.

### G. A model's run settings

- `models.run-settings.per-model` — **[GAP]** (#6588, #6351, #5370) a model's Inspector has Run Settings for the place
  it runs on, showing only what its runtime has: Kraken, the largest image side, lines at once, device, threads and
  precision; YOLO, image size, pages at once, device and confidence; an MLX model, the quantised build, the largest image
  side, context and output length; a cloud model, calls at once. Each shows the measured default with its reason ("Auto:
  1,800 px on this Mac's 8 GB", from `runtime.kraken.page-shrinks-to-fit`; "Auto: GPU",
  `runtime.pytorch.device-chosen`), a changed value is kept per model per place, a value that cannot run here is refused
  in words, Reset returns to Auto, and every run records the settings it used. The engine owns the settings, their
  bounds and the defaults (one read and one audited, undoable write); the window draws what it is given. **Built:** for
  Kraken only, `GET /api/activity/models/run-settings/{runtime}` answers `defaults` (each knob's engine value on this Mac
  and its reason, `llm/model_run_settings.py` `defaults`) and `script_heights` (the line finder's network height and base
  per script, #6752, read-only, `script_heights`), tested in `fichero-server/tests/unit/llm/test_model_run_settings_6588.py`;
  the engine still sets Kraken's threads from the plan (`llm/kraken_runtime.py` `threads_each`) and YOLO's device from
  availability (`llm/yolo_runtime.py` `_device`). **Not built:** the Inspector's
  Run Settings, Kraken's largest image side and precision (`models.settings.run-knobs-image-size-precision`), the YOLO, MLX
  and cloud knobs, Reset, and the run's record of the settings it used. *Test (to write):* test_model_run_settings.py in
  fichero-server/tests/unit/api/ (the settings a Kraken, a YOLO and a cloud card offer; a refused value; Reset; the
  run's record), and ModelRunSettingsTests.swift (the rows drawn from the answer).

## Build order

### Stage 1 — The window over the one list

#### Step 1.1 — The pane kind, the three sections, the Inspector (#6588)
- Status: the sections, the needs-you count and sort, and the one button are built as `ModelsWindowModel`; the pane kind, the split view and the Inspector are not.
- Behaviours: `models.window.is-activitys-shape`, `models.window.columns-and-verbs-are-activitys`, `models.window.needs-you-badge`
- Tests: fichero/Tests/Unit/general/Views/Activity/Pane/ActivityModelsTreeTests.swift (the tree the window grows from; new Swift tests of the layout and verbs to write beside it)
- Size: M

#### Step 1.2 — The one list grows: size, fits here, account, failures today, the GPU (#6588)
- Behaviours: `models.window.one-list`, `models.row.fits-here`, `models.row.account-from-a-probe`, `models.row.using-now-and-last-failed`
- Tests: fichero-server/tests/unit/api/test_activity_models_6588.py (extended with the new fields; the fits-here and account-probe tests to write beside it)
- Size: M

#### Step 1.3 — The places listed with a probed state, in the window not Settings (#5454, #5367)
- Status: the engine half is built (a place's Account from a probe, `test_a_places_account_comes_from_a_probe_and_the_key_a_call_uses`; a model row carries it); Settings' dot (`isLocalProvider || hasApiKey`) and the window's own rows are not changed.
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

#### Step 2.3 — Providers and Models in the sidebar, search, Apple Intelligence (#6588; ui-3)
- Behaviours: `models.window.providers-and-models-in-the-sidebar`, `models.search.over-every-model`, `models.apple-intelligence.is-a-provider-and-a-model`
- Tests: fichero/Tests/Unit/general/Views/ModelsWindow/ModelsWindowLayoutTests.swift, fichero-server/tests/unit/api/test_activity_models_6588.py
- Depends on: 2.2
- Size: M

#### Step 2.4 — Providers' keys and switches move into the window; Settings' panes become a link (#6588; ui-4)
- Behaviours: `models.settings.window-replaces-ai-panes`
- Tests: fichero/Tests/Unit/general/Views/Settings/AISettingsPlacementTests.swift
- Status: the panes are moved and Settings links; per-provider Inspector key fields and the deep link are not built.
- Depends on: 2.3
- Size: L

#### Step 2.5 — Add a model: download, cloud, by id or URL (#6588, #5460; ui-5)
- Behaviours: `models.manage.add-by-id-or-url`, `models.manage.add-a-model`
- Tests: ModelsWindowAddTests.swift (to write)
- Depends on: 2.4
- Size: M

#### Step 2.6 — Richer cards and more of them (#6588; cards-1)
- Behaviours: `models.cards.richer-and-more`
- Tests: a pytest over `recipes/seed/cards.yaml` (to write)
- Depends on: 2.3
- Size: M

### Stage 3 — Places

#### Step 3.1 — Providers' credit and limits; Connect… a Mac, a cluster, HF Jobs (#6675, #5951, #5454)
- Behaviours: `models.row.credit-and-limits`, `models.place.every-place-listed`, `models.place.add-a-mac`, `models.place.add-a-cluster`, `models.place.hf-jobs`, `models.place.egress-from-the-address`
- Tests: fichero-server/tests/unit/api/test_activity_models_6588.py (extended: clusters and provider accounts in the one list; a Swift test of the Account cell's words and button to write)
- Status: the engine half is built (credit, in-flight calls, the Hugging Face Jobs place); the Swift Account cell, Connect… sheets and rows are not.
- Depends on: 1.2
- Size: L

### Stage 4 — Trained models, and Settings slimmed

#### Step 4.1 — Trained models as rows; Settings keeps preferences; deep links land (#5439, #4307)
- Behaviours: `models.trained.are-rows`, `models.ground-truth.counts`, `models.settings.keeps-preferences`, `models.settings.one-download-location`, `models.settings.deep-links-still-land`
- Tests: fichero/Tests/Unit/general/Views/RunFailureAlertTests.swift (the `open-settings` deep link lands on the window; a Swift test of the slimmed Settings pane to write)
- Status: the engine half of the trained rows and ground-truth counts is built; the slimmed Settings pane, the download-location field and the deep links are not (Swift, not written here).
- Depends on: 2.1, 3.1
- Size: M

### Stage 5 — The model loop and run settings (written 2026-11-19; after `compute/distillation.md` Stage 2, Step 2.3)

#### Step 5.1 — Recipe steps as rows with their loop state and verbs (#5941)
- Behaviours: `models.loop.steps-are-rows`, `models.loop.verbs`, `models.loop.verdict-in-the-inspector`, `models.loop.published-state`
- Tests: ModelLoopRowTests.swift (not yet written)
- Depends on: 4.1
- Size: M

#### Step 5.2 — A model's run settings, owned by the engine, drawn in the Inspector (#6588)
- Behaviours: `models.run-settings.per-model`
- Tests: test_model_run_settings.py (not yet written), ModelRunSettingsTests.swift (not yet written)
- Depends on: 1.1
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
   Built so far (engine, #6588): the delete answers 409 naming the steps and deletes with `?confirm=true`; Choose for… is
   not built. The question stays open for the owner: whether "delete anyway" stays offered beside Choose for….
