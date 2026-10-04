# Settings, AI — providers, keys, local runtimes, compute targets and downloads — Design Spec (#TBD)

> Milestone: ai-settings
> **One home (ruled 2026-10-04).** Every behaviour of Settings' AI pane lives here: the provider rows, the keys (folded from `ai/provider-keys.md`, section K), the one model list and row used everywhere (folded from `ui/model-selector-consistency.md`, section M), each runtime's status and the keys a runtime needs (moved from `ai/local-runtimes.md`), where work runs (moved from `compute/targets-and-connection.md`) and model downloads. How a runtime ships and loads stays in `ai/local-runtimes.md`; how a target connects stays in `compute/targets-and-connection.md`; a download's progress is a job row (`ui/activity-and-automatic-work.md`).
> Manual: TBD — the user manual's Settings section needs "Configuring AI providers": every
> provider (cloud and on-device) is a row you pick from one list; a row's own detail carries
> whatever makes it work — a key, a download, a Start/Stop.

> Design-led (Testing Constitution). Creative director owns intent; tests enforce it; code
> makes them pass. **Status: DRAFT — awaiting approval.** The redesign this spec anchors was
> RATIFIED by the creative director (2026-08-24) but never got a spec; this is that spec,
> written against the code as it stands today, not the proposal as written.
> Tags: **[OK]** built and tested · **[PARTIAL]** built, unproven or partly wired ·
> **[GAP]** intended, never built (needs an issue) · **[BROKEN]** regression, code
> contradicts the intent (needs an issue).
>
> **Provider API keys are OUT OF SCOPE here** — persistence, verification, and security of a
> key once entered are section K's (→ #4815, → #4816, → #4818, → #4819, → #4820,
> → #4821). This spec owns the SURFACE (rows, tabs, catalog) the key field lives inside.

## Intent (the design)

Every AI provider — cloud or on-device — is a row in ONE list, with the same shape: a name,
a status that means what it says, and a detail view. A local runtime's detail carries what
makes it local (provisioning, its own model catalog, start/stop) instead of living in a
separate pane; a cloud provider's detail carries a key and its models. There is one model
catalog, not several disagreeing lists, and a provider's status dot is never green unless the
thing it names is actually ready. Settings surfaces preferences, not plumbing — no toggle a
user can't explain the consequence of.

## Ruled 2026-10-04 (the maintainer, while testing the dev build)

Paraphrased. These narrow the 2026-08-24 target; where they differ, these win.

- **Models live here.** Downloaded or imported, every model (Kraken, YOLO, spaCy, vision and
  text models, LoRA adapters) is managed in Settings. A model a training node produces appears
  here the same way.
- **Training does not live here.** Training, fine-tuning, evaluating and publishing are a node in
  the sidebar with their own history (#5439). Settings only lists the result.
- **Places to run work are configuration, so they live here:** this Mac, Hugging Face, a cluster
  such as Rorqual, an endpoint (Blackfish may be one). Adding a cluster is the guided flow in
  `compute/targets-and-connection.md`; Fichero itself holds the connection.
- **Downloads and installs are jobs** that belong to the Mac, shown in Activity's Mac group
  (`activity.global-work-is-the-macs`), never a progress bar private to Settings.
- **Open: AI settings in the sidebar.** The maintainer wondered whether more of the AI settings
  should move to the sidebar instead of one window. Recommendation: configuration (providers,
  keys, runtimes, places to run) stays in Settings; work (training nodes) is in the sidebar.

- `settings.models.import` — **[GAP]** (#5460) a model you already have (a Kraken or YOLO file,
  a spaCy pipeline, a vision model or LoRA from a Hugging Face repo id) is imported, validated,
  stored with its provenance and licence (and whether release is allowed), and becomes pickable
  wherever that kind of model is. *Test:* importing a fixture Kraken model through the route
  lists it in the catalogue with its licence and origin; a file that is not a model is refused
  with the reason.
- `settings.models.training-is-not-here` — **[GAP]** (#5439) Settings has no training controls;
  the catalogue row of a trained model links to the training node that made it. *Test:* the
  catalogue entry for a model with a training provenance carries the node id.
- `settings.compute.places-to-run` — **[GAP]** (#5454) the Compute section lists this Mac,
  Hugging Face, clusters and endpoints as one list with an honest status each, and adds a
  cluster through the guided flow. *Test:* the targets route returns all four kinds with a
  status that is the check's result, never assumed.
- `settings.downloads-are-jobs` — **[GAP]** (#5415) a download or install started here is a job
  in the Mac's group of the jobs table, pausable and cancellable there. *Test:* starting a model
  download through the route creates a `download-model` job row with no library.

## Why this spec exists

"Settings - Models & Providers" (GitHub milestone #20) accumulated 28 open issues over more
than a year with no spec anchoring any of them — feature requests, regressions, and a whole
redesign proposal, all landing on one bucket. The redesign itself was worked out and ratified
by the creative director on 2026-08-24 (four phases, summarized below) but was never written
as a testable spec, so nothing has been checking whether it actually landed. Reading the code
against that ratified shape found it landed further than expected in some places (the
provider-row unification) and not at all in others (the model-catalog unification, the
runtime-status honesty). This spec draws the line.

## The ratified target (paraphrased from the 2026-08-24 design review, not restated verbatim)

The redesign's core finding: the on-device runtime (MLX, spaCy, Kraken, Whisper — download,
provisioning, start/stop) was bolted onto its own parallel system with its own nouns, reached
only through a pane wedged awkwardly under the provider list. The fix collapses that: every
provider, cloud or local, is a row in the SAME list; a local row's detail carries its runtime
state alongside its models, not in a second surface. Concretely, in four phases:

- **P1 — Schema + seams.** The provider response gains real runtime fields (provisioned or
  not, service running or not, disk used) so the status dot can be HONEST instead of "local
  therefore green." MLX's detail renders those fields; nothing else changes yet.
- **P2 — One catalog.** Cloud and local models converge on one response shape (a cloud row's
  local-only fields are simply absent); the on-device download row becomes one shared
  component every provider's detail reuses; the standalone Downloads tab retires once
  everything it showed lives inside a provider row.
- **P3 — Profiles become rows; routes fold.** The local-inference runtime configuration
  (today a singleton keyed by environment) becomes provider-linked state; the separate
  `/api/local-inference/*` route family folds into `/api/providers/{id}/…`.
- **P4 — Rich defaults + Embeddings.** The Defaults tab's per-purpose pickers read the same
  rich model list the provider browser uses (cost/context/vision visible in both places), and
  Embeddings — a setting that already exists but has nowhere to be picked today — gets a
  section of its own.

Settings collapses to three tabs (Defaults · Providers · Advanced) once Downloads has nowhere
left to point at.

## What the code actually does (verified against the four phases)

- **P1 is DONE for the layout, NOT done for the schema.** `ProvidersView` is one list; every
  managed-local runtime (MLX/spaCy/Kraken/Whisper) is a row in it, and its detail
  (`ProviderDetailView`) renders runtime/model/service sections inline via
  `LocalRuntimeModelsView` — the separate pane and its collapse bug (#4531) are gone. But the
  schema work never landed: `ProviderResponse` carries no `runtime_state`/`requires_runtime`/
  `service_state` field (grep confirms — only `local_inference.py`'s OWN separate response
  model has `disk_usage_bytes`, not shared onto the provider). The status dot
  (`ProviderDetailView.swift`, the `Circle().fill(...)`) is still
  `isLocalProvider || provider.hasApiKey ? .green : .orange` — an unprovisioned MLX shows the
  identical green dot as a ready one. This is the "green-dot lie" the ratified design named
  as the thing P1 exists to kill; it has not been killed.
- **P2 is PARTLY done.** Whisper/spaCy/Kraken download rows moved into their provider
  detail views (confirmed: `ProviderDetailView`'s `showsRuntimeBlock`/`isNoPromptRuntime`
  branches render `LocalRuntimeModelsView` inline). Embeddings has NOT moved — its own
  comment says it stays in the separate Downloads tab "which are a search concept with no
  provider row of their own (**yet**)" (`LocalModelsSettingsView.swift:9-12`). No unified
  model-catalog schema was found (`LocalModelCatalogEntry`'s fields folding into the
  provider-scoped model response, as the design proposed) — cloud and local models still
  come from separate response shapes. The Downloads tab is very much alive, now scoped to
  embeddings alone.
- **P3 is NOT done.** `/api/local-inference/*` is still its own `APIRouter(prefix=
  "/local-inference")` (`local_inference.py:29`), entirely separate from
  `/api/providers/{id}/...`. No profile-as-provider-row work was found.
- **P4 is NOT done.** `AISettingsView+Tabs.swift`'s `defaultsTab` has sections for
  Text/Vision/Audio/Video plus the six `$small`/`$medium`/`$large`/`$vision_*` capability
  tiers — no "Embeddings" section anywhere in it.

## Behaviors

### What shipped (P1's layout half)

- `settings.providers-list-is-one-home` — **[OK]** every provider — cloud and on-device — is
  a row in the same `ProvidersView` list; there is no separate local-runtime pane. Pinned:
  `ProvidersTabLayoutTests.testLocalRuntimesRenderAsProviderRows`,
  `.testProvidersTabHandsTheBrowserTheFlexibleHeight`,
  `.testProvidersTabDoesNotWrapItsPanesInAScrollView`.
- `settings.provider-detail-carries-its-own-controls` — **[OK]** a provider's detail view
  carries whatever it needs — API key + models for a cloud provider, runtime/download/service
  controls for a local one — never a second window or pane. Pinned:
  `ProvidersTabLayoutTests.testAPIKeyEntryRemainsReachableFromTheProviderDetailPane`
  (key entry survived the row unification — the surface itself, not whether saving it
  persists, which is section K's).
- `settings.shared-model-row` — **[OK]** every model-picking surface (the island, the
  workflow bar, chat, Settings) renders the SAME row component; no surface hand-draws its
  own competing row shape. Pinned:
  `ModelRowSourceGuardrailTests.noSecondModelRowStruct`.
- `settings.provider-selection-preserved` — **[OK]** changing a Defaults picker's provider
  never blanks the model selection or silently auto-picks `list.first` — a ship-blocker fix
  that landed as part of the model-selector-consistency milestone's own work (that milestone
  still has open follow-ups of its own, not cited here since they are its claim, not this
  one). Pinned: `AISettingsSelectionTests` (all 5 cases: fetch-failure leaves the
  prior model untouched, an absent-from-the-fresh-list model is not replaced, a
  present model is left as-is, an empty prior selection stays empty, and the load site
  routes only through `selectionAfterModelLoad`).
- `settings.errors-surface-not-swallowed` — **[OK]** a load/save/reset failure on the AI
  defaults always surfaces as `errorMessage`, never a silent `try?`. Pinned:
  `AISettingsStoreTests.testLoadSurfacesFetchFailureInsteadOfSwallowing`,
  `.testSaveSurfacesFailure`, `.testResetSurfacesFailure`, `.testSuccessfulLoadLeavesNoError`,
  `.testCallsAreNoOpBeforeAttach`.

- `settings.local-model-refused-before-it-loads` — **[OK]** (#5221) a local MLX model is refused
  BEFORE its process starts when this Mac cannot hold it right now: it needs about the model's
  weights x 1.2 + 1.5 GB free (an estimate from the catalog's size, overridable with
  `FICHERO_MLX_MEMORY_NEED_MB`; not yet measured per size class as Kraken's 2.5 GB was), and macOS
  memory pressure must not be critical (warn still loads, as ruled for Kraken on 2026-09-28). The
  refusal says what it needs, what is free, and up to two smaller catalog models with a shared
  capability that fit; it is the route's existing 409 for hardware refusals. Pinned by
  `fichero-server/tests/unit/llm/test_mlx_memory_guard.py` (injected memory, never the machine),
  including that a refused load spawns no process. Not covered: user-configured models outside
  the catalog (no known size) and the Whisper models (under 1 GB).

### What has not shipped (P1's schema half, P2, P3, P4)

- `settings.mlx-runtime-honest-status` — **[BROKEN]** (#4303) a local runtime's status dot
  must reflect whether it is actually provisioned/ready, not just "is local." Owned for every
  runtime by `runtime.status-from-the-endpoint` (`ai/local-runtimes.md`); this line is the MLX row's
  symptom. Verified in
  code: `ProviderDetailView`'s status circle is
  `isLocalProvider || provider.hasApiKey ? Color.green : Color.orange` — an unprovisioned
  MLX renders the identical green dot as a ready one, because no `runtime_state` field
  exists on `ProviderResponse` to tell them apart. This is a verified sub-symptom of #4303's
  broader "MLX appears non-functional" report — a user has no visual signal that MLX needs
  provisioning before it will work. Unchanged by the recent Test Connection three-state fix
  landed on the provider-keys milestone (now section K): that fix reworked the DETAIL
  view's test-result icon (`KeyTestOutcome`), not this row. `ProviderSettingsRow`'s own status
  dot (the provider LIST, distinct from the detail view) uses the identical stateless
  boolean — `isLocalProvider || provider.hasApiKey ? Color.green : Color.orange` — and still
  never reads a Test Connection result (verified in code today).
- `settings.embeddings-download-works` — **[GAP]** (#4304) starting an embeddings download
  from Settings must actually deliver a usable model. Reported broken (field issue); this
  pass did not trace the failure in `local_models.py`'s `download_model` route to a root
  cause, so it stays GAP rather than a code-verified BROKEN — the download route exists
  (`local_models.py:145`) but whether/why it fails was not re-verified here.
- `settings.one-catalog-unification` — **[GAP]** (#4307, #1059, #1200, #1342, #1152 — moved
  onto this milestone this pass; previously cross-milestone pointers, now folded in since each
  genuinely backs this same claim) cloud and local models must resolve through ONE response
  shape (a cloud row's local-only fields simply absent), with one shared download-row
  component and one disk-usage view. Not built: cloud (`ProviderAPIService`) and local
  (`LocalInferenceStore`/`LocalModelsSettingsView`) models still come from separate response
  shapes and separate stores. #4307 is the direct tracker; #1059 (consolidate ~6 picker UIs),
  #1200 (a richer searchable browser), #1342 (centralize download location), and #1152 (a
  deletable models folder) are the specific sub-asks this one claim now carries.
- `settings.embeddings-in-defaults` — **[GAP]** (#4302, → #4307) the Defaults tab needs an
  Embeddings section reading the same rich model list its picker uses elsewhere — the
  setting exists in the data model but has no picker anywhere. Verified absent: no
  "Embeddings" section exists in `AISettingsView+Tabs.swift`'s `defaultsTab`.
- `settings.downloads-tab-retirement` — **[GAP]** (→ #4307) the standalone Downloads tab
  should retire once everything it shows lives inside a provider row; today it still exists,
  scoped to embeddings alone (`LocalModelsSettingsView.swift:9-12`'s own comment says
  embeddings has "no provider row of their own (yet)"). Pinned (the CURRENT, un-retired
  shape): `AISettingsDefaultsSurfaceTests.testModelManagementTabsStayInsideSettingsAndRespectTierGate`
  asserts the Downloads tab still exists — this test will need to invert once the tab
  actually retires.
- `settings.profiles-as-rows` — **[GAP]** (#2064) the local-inference runtime profile
  (today `_configured_omlx_profile()`, an environment-keyed singleton) should become
  provider-linked state, and `/api/local-inference/*` should fold into
  `/api/providers/{id}/…`. Verified not done: `local_inference.py:29` still declares its own
  `APIRouter(prefix="/local-inference")`, entirely separate.
- `settings.health-observability` — **[GAP]** (#4327, #4620, #4626, #4628, #4629 — the latter
  four moved onto this milestone 2026-09-19 while folding legacy milestone
  "Settings - Models & Providers - HPC") a status surface across providers, tiers, and tools (plus per-call visibility into
  the underlying LangChain routing) does not exist today — every provider row shows its own
  status in isolation, with nothing cross-cutting. #4620 is the umbrella "declared == embedded
  == runnable == surfaced" ask this behavior already answers structurally; #4626 (loove),
  #4628 (Whisper), and #4629 (Apple Intelligence/Vision) are per-runtime instances of the exact
  same complaint — each wants its OWN availability shown truthfully, which is this behavior's
  claim generalized to every provider, not four separate gaps. `settings.mlx-runtime-honest-
  status` above is the MLX-specific case of this same pattern, already tracked there.

### Runtime status (moved from `ai/local-runtimes.md` §E, 2026-10-04)

- `runtime.status-from-the-endpoint` — **[BROKEN]** (#5367, #4303) every local row's status comes
  from `/api/providers/local-runtimes`, which is built (`api/routes/ai/provider_models.py:1274`)
  and called by no Swift code; synthetic rows hard-code `enabled=True, has_api_key=True`
  *(review)*. Widens `settings.mlx-runtime-honest-status` from MLX to every runtime.
- `runtime.status-covers-every-runtime` — **[GAP]** (#5367) the endpoint reports every runtime,
  including Apple's four (with Apple Intelligence's on/off state), embeddings, Tesseract and the
  local servers (by probing them), with the build state and a reason.
- `runtime.unavailable-says-so` — **[BROKEN]** (#5367, #4973) in a sandboxed build a runtime that
  needs code at run time is shown as "Unavailable in this build" with the reason, never offered as
  Download or Provision.
- `runtime.defaults-name-working-runtimes` — **[BROKEN]** (#5367) the factory defaults name only
  runtimes present in the build, and a tier that promises a prompt never defaults to a
  recognition-only card; today the audio default is `apple-speech` (not bundled) and the
  `$vision_*` tiers default to `apple-vision`, which ignores prompts (`db/app.py:68-78`).

### Keys a runtime needs (moved from `ai/local-runtimes.md` §F, 2026-10-04)

- `keys.status-sees-supplied-keys` — **[BROKEN]** (#5369) every key-status read (provider list,
  catalogue, chat availability) uses the same lookup as a call, including keys the app supplies;
  today `keychain.has_api_key` (`security/keychain.py:303`) reads only the engine keychain.
- `keys.add-provider-uses-the-one-store` — **[BROKEN]** (#5369) a key entered while adding a
  provider is written to the app's Keychain and supplied in memory, never to the engine keychain
  (`AddProviderSheet+Helpers.swift` → `api/routes/ai/providers.py` *(review)*).

### Where work runs (moved from `compute/targets-and-connection.md`, 2026-10-04)

- `compute.target.lives-in-ai-settings` — **[GAP]** (#5238) targets appear in Settings, AI, in a section titled
  "Where work runs", as rows that each carry their own controls, in the way provider rows do
  (`settings.provider-detail-carries-its-own-controls`). Connecting, checking and removing a target stay in `compute/targets-and-connection.md`. *Test:* availability leg: the section and its Add control are
  reachable.

## Dead-simple-UX check (no needless toggles)

No new user-facing toggle was found in this surface beyond what a provider's own nature
requires (a key field for a cloud provider, a Download/Start-Stop for a local one) — the
`isSettingsModelsTabEnabled` feature gate is a build-tier switch, not a user preference. The
one thing that reads as unexplained plumbing today is exactly `settings.mlx-runtime-honest-
status`'s gap: a green dot that doesn't mean "ready" is worse than a toggle, because it
looks like a fact rather than a choice.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | provider-change never blanks/auto-picks the selection | `fichero/Tests/Unit/general/Views/Settings/AISettingsSelectionTests.swift` |
| Availability (Swift) | y | one provider list, one shared model row, key entry reachable | `ProvidersTabLayoutTests.swift`, `ModelRowSourceGuardrailTests.swift` |
| Availability (Swift) | y | Defaults tab tier sections + tab set (current, un-retired shape) | `AISettingsDefaultsSurfaceTests.swift` |
| Pure rule (Swift) | y | load/save/reset never swallow a failure | `AISettingsStoreTests.swift` |
| Backend (pytest) | n | no test found for the local-inference/provider route split, the runtime-status fields, or the embeddings download path | — (the three GAPs above) |
| Click-around (XCUITest) | n | no dedicated Settings AI flow test found | — |

Hard-gate: none yet — this is a DRAFT spec; the hard-gate set is chosen once the phases above
have owners.

## Issue map (all 28 open issues on "Settings - Models & Providers", #20) — HISTORICAL, first pass

Superseded by "Legacy milestone fold, pass 2" below (2026-09-19), which re-read every
remaining issue against today's exact fits/redirect/waiting/verify-close/triage rubric,
executed the moves this table only recommended, and reflects the CURRENT open set (22 on #20,
not 28 — six already moved by this table). Kept for the reasoning trail.

Disposition key: **cited** = moved onto `ai-settings` (#306), backs a behavior above by plain
citation · **related** = arrow-cited above, stays on its own milestone (a broader,
pre-existing tracker, not this spec's narrower claim) · **recommend-close** = looks
superseded by what's already built; the maintainer's call, not closed here · **recommend
re-home** = not really about this Settings surface at all; belongs on a different milestone.

| # | Title | Disposition |
|---|---|---|
| 284 | Re-enable Settings tabs (General/Backend/Models) after 0.0.2 | recommend-close — the tabs this refers to (General/Backend/Models) are long gone from the current tab set; looks stale |
| 484 | Wire: Providers + API Keys | recommend-close — providers + keys are wired (`ProvidersView`, `provider_keys.py`); superseded by what's built + section K |
| 485 | Wire: Local Models | recommend-close — local models are wired (`local_inference.py`, `LocalRuntimeModelsView`) |
| 752 | Settings → Local Models tab: enable + download/manage local model weights | recommend-close — built (local runtime rows + download/manage controls) |
| 853 | Apple Intelligence: proactive token budgeting | recommend re-home — an Apple Intelligence capability, not a Settings-surface concern |
| 854 | Apple Intelligence: prewarm() + contentTagging | recommend re-home — same |
| 1059 | Consolidate model/provider selection — ~6 pickers | **related** → cited on `settings.one-catalog-unification` |
| 1146 | Embed MLX Swift for Qwen3-VL / Nanonets-OCR-s; investigate Chandra | recommend re-home — a model-support feature request, not the Settings surface |
| 1152 | Model management UI: deletable spaCy/embeddings models folder | **related** → cited on `settings.one-catalog-unification` |
| 1200 | Model browser: searchable OpenRouter catalogue with filters | **related** → cited on `settings.one-catalog-unification` |
| 1325 | Settings: clean up the Models window UX | recommend-close — superseded by this spec's more specific behaviors |
| 1342 | Centralize model downloads to Application Support/Fichero/models | **related** → cited on `settings.one-catalog-unification` |
| 1435 | Wire 27 Providers & Models endpoints into SwiftUI | recommend-close — wired (`ProviderAPIService`) |
| 2063 | Privacy guarantee: nothing goes online without consent | recommend re-home — a cross-cutting privacy feature, not this surface |
| 2064 | Frontend: AI-infra surface — profile picker, local-only toggle, engine/model status | **cited** → `settings.profiles-as-rows` |
| 2116 | Model selection that EDUCATES + evaluates (loove) | recommend re-home — a bigger, separate feature (partial overlap: Language Coverage window already exists) |
| 2268 | Providers/Models belong in Settings window + configurable defaults + model location | recommend-close — largely done (they ARE in Settings, with a Defaults tab) |
| 2291 | Projects/Milestones/Tasks as agent-operable objects | recommend re-home — unrelated to AI Settings |
| 2314 | Three chat modes (Simple/RAG/Agent) | recommend re-home — a chat-surface feature, not Settings |
| 2444 | Expose Translate (DeepL) as a workflow tool/node | recommend re-home — DeepL is already a working provider (real Test Connection probe, per section K); this is about workflow-node exposure, not Settings |
| 2450 | Xcode-style activity status widget in toolbar | recommend re-home — unrelated to AI Settings |
| 3411 | Settings: Fonts & Colors controls | recommend re-home — not an AI-provider concern at all; looks mis-filed on this milestone |
| 4268 | Embeddings run automatically after import, visible as activity | recommend re-home — an embeddings-pipeline/background-processing behavior, not the Settings surface |
| 4302 | Default embeddings model: download on first launch, auto-embed backfill | **cited** → `settings.embeddings-in-defaults` |
| 4303 | MLX provider in Settings is untested and appears non-functional | **cited** → `settings.mlx-runtime-honest-status` |
| 4304 | Embeddings model download from Settings fails | **cited** → `settings.embeddings-download-works` |
| 4307 | Unify AI models and embeddings into one models list | **cited** → `settings.one-catalog-unification`, `settings.embeddings-in-defaults`, `settings.downloads-tab-retirement` |
| 4327 | AI health & observability: status surface + per-call LangChain visibility | **cited** → `settings.health-observability` |

Moved onto `ai-settings` (#306) by number: **#2064, #4302, #4303, #4304, #4307, #4327** — the
six behaviors above cite them by plain `#N`. Everything else stays on #20 for the maintainer's
own triage (recommend-close / recommend-re-home are recommendations, not actions — nothing
was closed or moved beyond this list).

## Legacy milestone fold, pass 2 (#20, #126, #257 — 24 open issues, selected by NUMBER)

Every body read fresh at HEAD (2026-09-19), including areas that moved this week: provider
keys live in section K now; Kraken's runtime is verified working with
the gap being import-time wiring (`importer.md`'s `importer.segmentation-automatic-no-toggle`,
#4822); pytz is declared. **No issue among these 24 mentions Kraken, HPC, or remote compute** —
a negative result stated plainly, not assumed.

### Fits (moved onto #306, backing `settings.one-catalog-unification`)

**#1059, #1200, #1342, #1152** — see that behavior's own updated citation above; each is a
specific sub-ask of the one-catalog claim (consolidate ~6 pickers, a richer searchable
browser, centralize the download location, a deletable models folder) and now shares this
milestone instead of being an arrow-pointer to elsewhere.

### Redirected to an existing spec

- **#484** ("Wire: Providers + API Keys") → section K. Its own acceptance
  checklist (add a provider, enter a key, Test Connection, browse the catalog) is that spec's
  subject exactly, and largely already built there (`keys.test-connection-real-probe`,
  the Keychain-and-engine sync fix 101a67cde).
- **#4268** ("Embeddings run automatically after import, visible as activity") →
  `importer/importer.md`, which already has `importer.embeddings-auto-at-import` **[OK]** —
  this is an importer-pipeline behavior, not a Settings-surface one.
- **#2450** ("Xcode-style activity status widget in toolbar") → `ui/panes-workspaces.md`,
  which already documents the status island's separated engine/activity/message items
  (`panes.status-island.separates-connection-and-activity` and siblings) — largely the same
  ask, already substantially built there, not this spec's territory.

### Verify-close — evidence posted, left OPEN, not closed here

- **#284** ("Re-enable Settings tabs General/Backend/Models") — built: `SettingsTab`
  (`App/AppState/AppState.swift:10-29`) has live `.general`, `.backend`, and `.aiModels` cases, each
  mounting a real view in `SettingsView.swift`.
- **#485** ("Wire: Local Models") — built: `LocalModelsSettingsView.swift` exists and mounts.
- **#752** ("Settings → Local Models tab: enable + download/manage") — built: same view,
  download/remove controls present.
- **#1325** ("Settings: clean up the Models window UX") — the whole Settings surface has been
  rebuilt since this was filed: one `NavigationSplitView` (macOS-sidebar source-list →
  detail, collapsing natively on iPhone/iPad) replaced the old top-tab `TabView` (#3679),
  with per-view sections (#3680). The specific "Models window" this issue names no longer
  exists in that shape.
- **#1435** ("Wire 27 Providers & Models endpoints into SwiftUI") — re-ran
  `scripts/check_endpoint_coverage_matrix.py` fresh (the measurement was `check_ui_wiring`'s before it was retired into this one, #5105): ZERO of the 27 endpoints this issue lists appear in the
  current unwired/unallowlisted findings. All 27 are now either called or properly
  allowlisted.
- **#2268** ("Providers/Models belong in the Settings window + defaults + model location") —
  built: they ARE in Settings (`.aiModels` tab), with a Defaults tab for default model
  selection.
- **#3366** ("Settings window should expose feature-gated app menu surfaces — MCP and
  Integrations") — built: `SettingsTab.mcp` mounts `MCPServersView()`, `.integrations` mounts
  `IntegrationsSettingsView()`, both live in `SettingsView.swift`'s own switch.
- **#3678** (#257's own issue — see the full assessment below) — every concrete deliverable
  it asked for is built.

### Maintainer triage — no home found among the specs read this pass

- **#853, #854** (Apple Intelligence `prewarm()`/`contentTagging`; proactive token budgeting) —
  an Apple Intelligence RUNTIME capability, not the Settings surface; #854 is additionally
  blocked on an external SDK version (26.4).
- **#1146** (embed MLX Swift for Qwen3-VL/Nanonets-OCR-s local models) — a specific
  model-integration feature request, not a Settings-surface behavior.
- **#2063** (global local-only/no-cloud privacy guarantee) — a cross-cutting enforcement
  feature at the LLM/vision dispatch layer, not a Settings-UI question, though it would show a
  toggle there.
- **#2116** (model selection that educates/evaluates per-language fit, cost, "test on your
  material") — a large, separate feature; partial overlap with an existing Language Coverage
  window not independently re-verified this pass.
- **#2291** (Projects/Milestones/Tasks as agent-operable objects) — an in-app-agent/chat
  feature, unrelated to AI Settings.
- **#2314** (three chat modes with an on-device AI router) — a chat-surface feature;
  `ui/research.md` was checked and does not cover this specific routing ask, so not redirected
  there without evidence.
- **#2444** (expose Translate/DeepL as a workflow tool/node) — a workflow-node-exposure
  question, not a Settings one; DeepL itself is already a working provider per
  section K.
- **#3411** (Fonts & Colors settings controls for library/reader/labels/inspector/editor) —
  genuinely mis-filed on this milestone, per the historical map's own read, confirmed again
  this pass: this is general app typography/appearance, not an AI-provider concern, and no
  general-settings/typography spec exists to redirect it to.

## #257 assessment ("Settings IA v2 + Reader/Editor Typography", one issue: #3678)

Read in full. #3678 asked for an audit-and-design pass covering seven concrete deliverables.
**Every one of them has landed, each under its own tracking issue, verified on disk, not
assumed from the milestone's age:**

1. A macOS-sidebar (source-list → detail) Settings architecture — **built**: one
   `NavigationSplitView` (`SettingsView.swift:5-33`, its own doc comment names #3679 as the
   tracker) replaced the old top-tab `TabView`.
2. Per-view settings sections (Library/Reader/Preview/Inspector) — **built**: `SettingsTab`
   has `.libraryView`/`.previewView`/`.readerView`/`.inspectorView` cases, each commented
   "#3680."
3. iPhone/iPad mapping — **built**: the same `NavigationSplitView` collapses to a list on
   compact widths natively, per the same file's doc comment — no separate iOS implementation
   needed.
4. A typography model (semantic-default + user-override font sizes, stored in `ViewSettings`/
   `@AppStorage`) — **built**: `ViewSettings.FontScale.readerKey`/`.editorKey` via
   `@AppStorage` in `SettingsViewPanes.swift` — the exact storage location the issue itself
   speculated.
5. A Reader theme/CSS-consistency approach (semantic colors/fonts into the WebKit templates)
   — **built**: `document_view.html`'s own CSS reads Swift-injected semantic variables
   (`--bg`, `--reader-text-wrap`), not a hardcoded "paper" look, per its own comment citing
   #1280.
6. Paragraph-wrapping with no orphaned last-lines — **built**: `document_view.html`'s
   `text-wrap: var(--reader-text-wrap, pretty)`, its own comment naming #3684 as the tracker
   and "pretty" (no-orphan) as the on-target default.
7. A short design doc — **produced**: `agent-work/superpowers/specs/2026-07-13-settings-
   typography-ia-design.md` exists (at a different path than the issue's own
   `docs/superpowers/specs/` suggestion — a location detail, not a substance gap).

**Nothing in #3678 reads as a live blocker today.** Stated as evidence, not as "superseded":
every deliverable the issue named has a corresponding, verifiable piece of code citing its
own follow-up issue number (#3679, #3680, #3684, #1280) — the audit this issue asked for
evidently happened and was acted on. Left OPEN per this fold's own rule (never call an open
issue superseded, never close it myself); posted as verify-close above.

## Open questions

1. Does P1's schema work (`runtime_state`/`requires_runtime`/`service_state` on
   `ProviderResponse`) ship before or after the P2 catalog unification, given they touch
   overlapping response shapes?
2. Does Embeddings get its own provider row (matching every other capability) once
   `settings.one-catalog-unification` lands, or stay a Defaults-tab-only setting with no row
   of its own (`LocalModelsSettingsView`'s "yet" suggests a row was always the plan)?
3. `settings.health-observability` (#4327) is broad (providers + tiers + tools + per-call
   LangChain visibility) — does it belong entirely in this milestone, or does the per-call
   LangChain piece belong to a backend-observability milestone instead?
4. Several "related" issues (#1059, #1200, #1152, #1342) predate the ratified redesign by
   months — do they get closed once `settings.one-catalog-unification` supersedes them, or
   do they carry distinct scope (e.g. #1200's OpenRouter-specific filters) that survives the
   unification?
5. **Recorded request, not decided here** (from the source-model spec work, branch
   `spec/page-model`, `specs/source/models-chains-and-projects.md` — not in this tree): every
   catalogue entry should take one "model card" shape — what a model takes in and gives out,
   the languages/scripts/periods it suits, local-or-cloud, and a licence class — INCLUDING
   embedding models, which today are chosen only by an environment variable. Verified: `db/
   embeddings.py` defines `EMBED_MODEL_ENV = "FICHERO_EMBED_MODEL"` and reads it directly
   (`:37,42,283`) — there is no catalogue row, model card, or UI surface for choosing an
   embedding model today, exactly as the request describes. Whether/how this folds into
   `settings.one-catalog-unification` above is not decided here.
5. Is the three-tab target (Defaults · Providers · Advanced) still right, or does Embeddings
   getting a provider row change what "Downloads retiring" even means?

## K. Provider keys (folded from `ai/provider-keys.md`, 2026-10-04)

### Intent (the design)

A researcher enters a provider's API key once, in Settings, and it keeps working across
every future launch — a restart never quietly reverts to an old or deleted key. Removing a
key removes it, permanently, not until the next relaunch. There is exactly ONE place a local
engine's keys live; a remote engine's keys are that host's own business, never the app's. And
the app never claims a key works unless it actually checked: a "connection valid" green check
means a real probe answered, never "some non-empty string was present."

### Why this spec exists

A field report surfaced two verified defects with no spec behind either of them:

- **#4815** — every app launch re-pushes a stale, once-migrated copy of a provider's key to
  the engine, silently undoing a Settings save or a Settings remove. A whole afternoon of
  OpenRouter `401`s traced to exactly this: the key was fixed by hand in Settings, worked for
  70 consecutive calls, then the next launch resurrected the old, broken key.
- **#4816** — Test Connection reports success for any provider with no real probe wired
  (OpenRouter among them) the moment the key field is non-empty, regardless of whether the
  key is valid. A user who followed the app's own "Update API key in Settings" advice, then
  ran Test Connection and saw a green check, had no way to know the check meant nothing.

Both share one root cause worth naming once: a claim ("this key is saved", "this connection
works") that nothing in the code actually verifies.

### Two stores of truth (the shape of #4815)

- **App-owned Keychain** (`ProviderKeyStore.swift`, service `app.fichero.fichero.provider-keys`)
  — written exactly once, by a one-time migration off the engine's legacy keychain item
  (`migrateFromLegacyIfNeeded`); after that, `.alreadyOwned` forever. Pushed to the engine on
  EVERY connect (`EngineLifecycleController+ProviderKeys.swift`).
- **Settings' own path** (`ProvidersView+ProviderDetailView.swift`'s `saveAPIKey`/
  `removeAPIKey`) never touches the app-owned Keychain at all — it only calls the HTTP
  `providerService.setAPIKey`/`deleteAPIKey`, which reach the engine's OWN legacy keychain
  copy and its in-memory supplied-keys dict, never `ProviderKeyStore`.

So a Settings save/remove changes the engine's copy for the rest of that session, and the
next launch's connect sequence re-pushes whatever the app-owned Keychain item still holds —
the value from the original migration, unaffected by anything Settings has done since.

### Behaviors

#### Persistence (#4815)

- `keys.one-store-of-truth` — **[OK]** (101a67cde, #4815 closed) a local engine's key lives in
  exactly one place the app treats as authoritative (the app Keychain). Before the fix there
  were two: the app-owned Keychain item (written once, at migration) and the engine's own
  legacy Keychain item + in-memory supply (written by every Settings save/remove and
  re-supplied on every connect) — `grep ProviderKeyStore fichero/fichero` found only the three
  launch-push call sites and the migration itself; `store`/`remove` had no production caller
  from Settings. Pinned:
  `ProviderAPIServiceKeyPersistenceTests.testSetAPIKeySuccessStoresTheTrimmedKey`,
  `::testSetAndDeleteAPIKeySkipTheKeychainForARemoteEngine`,
  `::testSupplyAPIKeyToEngineBodyNeverReferencesTheKeychainClosures`,
  `::testSupplyAPIKeyToEngineHasExactlyOneCaller` (all 4 read in full and confirmed to assert
  exactly this — `fichero/Tests/Unit/general/Services/ProviderAPIServiceKeyPersistenceTests.swift`).
- `keys.settings-save-survives-relaunch` — **[OK]** (101a67cde, #4815 closed) saving a new key
  in Settings stays in effect after the next launch. Pinned:
  `ProviderAPIServiceKeyPersistenceTests.testSetAPIKeySuccessStoresTheTrimmedKey`,
  `::testStaleKeyRegression_settingsSaveIsReflectedByTheNextEngineSupply` (the regression test
  named in the issue itself: a stale key seeded, a new one saved, the launch push's own
  read-then-supply shape reads back the NEW value, never the stale one),
  `::testSetAPIKeySuccessButKeychainFailureThrowsDistinctErrorWithNoKeyMaterial`. Honest gap:
  the suite cannot re-read the WIRE body to independently confirm the engine received the
  trimmed value byte-for-byte — the generated client sends this POST as an upload task, whose
  body a `URLProtocol` stub cannot see (the same limitation `BatchServiceTests.swift` already
  documents). What IS proven: `setAPIKey`
  computes ONE `trimmed` local and passes that SAME value to both the engine call and the
  Keychain closure (a source contract, `testSetAPIKeyTrimsOnceForBothTheEngineAndTheKeychain`)
  plus the closure receiving the expected trimmed string dynamically — the closest honest
  proof available without the wire-body seam.
- `keys.remove-survives-relaunch` — **[OK]** (101a67cde, #4815 closed) removing a key in
  Settings stays removed after the next launch. Pinned:
  `ProviderAPIServiceKeyPersistenceTests.testDeleteAPIKeySuccessRemovesTheKeyAndLeavesNothingForTheNextLaunchPush`.
- `keys.launch-supplies-to-engine` — **[PARTIAL]** (#4819, implemented, unpinned) the app supplies
  every candidate provider's app-owned key to the engine on every connect
  (`EngineLifecycleController+ProviderKeys.swift:27-66`,
  `supplyProviderKeysToEngine()`) — this mechanism is real and IS what makes the launch-push
  problem above visible (it works correctly, from a stale source). No Swift test exercises
  `supplyProviderKeysToEngine()` directly; `ProviderKeyStoreTests.swift` only covers the
  underlying `ProviderKeyStore` primitives it calls, not the connect-time supply loop itself.
- `keys.remote-engine-not-app-business` — **[PARTIAL]** (#4820, implemented, unpinned) a remote
  engine's provider keys are that host's own configuration; the app must never push its local
  Keychain keys to one. `supplyProviderKeysToEngine()` guards this explicitly
  (`guard !EngineConfig.engineProvisioningStrategy().connectsToRemoteHost else { return }`,
  `EngineLifecycleController+ProviderKeys.swift:28-31`) — real code, but no test asserts the
  guard actually short-circuits for a remote-configured engine.

#### Verification (#4816)

- `keys.test-connection-real-probe` — **[OK]** (bca344581 app half; 35c4b53f1 + 5a9676909
  engine; #4816 closed) Test Connection only reports success when the app made a real network
  call to the provider and the provider confirmed the key, and a wrong/rate-limited/down
  endpoint never reads as a bad key. Provider breakdown (engine side): **real probes** —
  `apple_vision`, `apple_intelligence` (system checks), `ollama`, `lmstudio` (server
  reachability, no key involved), `openai`, `huggingface`, `google`, `groq`, `deepl` (the five
  original probes, now applying the same "only 401/403 means a bad key" rule), plus NINE
  added: `openrouter`, `anthropic` (a real authenticated request, no longer prefix-only),
  `mistral`, `together`, `deepseek`, `xai`, `perplexity`, `fireworks`, `cohere`. **Still
  unverifiable from here**: `azure`, `bedrock`, `dashscope` — these report a distinct "saved,
  could not verify" state rather than a false green check. The rule throughout: only a
  `401`/`403` (or a provider's own documented bad-key status — Google's `400`, kept as its
  real signal) means the key is bad; any OTHER non-2xx status means "could not verify," never
  "invalid." On the app side, `KeyTestOutcome.from(success:verified:)` is the pure derivation
  (read `KeyTestOutcomeTests.swift` in full — exhaustive over all 6 `(success, verified)`
  combinations, including a `nil` `verified` from an engine with no opinion yet correctly
  landing on "saved, not verified," never a positive claim) that
  `ProvidersView+ProviderDetailView.swift` now renders from instead of `result.success` alone.
  Pinned:
  `test_routes_provider_keys.py::test_connection_test_real_probe_success_sets_verified`,
  `::test_connection_test_real_probe_401_fails_unverified`,
  `::test_connection_test_real_probe_network_failure_reports_connectivity`,
  `::test_connection_test_real_probe_non_auth_status_is_unverified_not_failed`,
  `::test_connection_test_key_never_appears_in_response_or_logs`,
  `KeyTestOutcomeTests.testSuccessAndVerifiedTrueIsVerified`,
  `.testSuccessAndVerifiedFalseIsSavedNotVerified`,
  `.testSuccessAndVerifiedNilIsSavedNotVerified`,
  `.testFailureAndVerifiedTrueIsStillFailed`,
  `.testFailureAndVerifiedFalseIsFailed`, `.testFailureAndVerifiedNilIsFailed`.
- `keys.untested-provider-reports-not-verified` — **[OK]** (bca344581, #4816 closed) an
  untested provider reports a distinct "not verified" state and renders as neutral, never a
  green check — built on both sides now: the engine emits `ConnectionTestResponse.verified:
  bool | None` as a third state distinct from `success`
  (`test_connection_test_untested_provider_reports_saved_not_verified`, "Key saved — this
  provider cannot be verified from here", `azure`/`bedrock`/`dashscope`); the app derives
  `KeyTestOutcome` from the pair rather than keying its icon on `result.success` alone. Pinned:
  `test_routes_provider_keys.py::test_connection_test_untested_provider_reports_saved_not_verified`,
  `KeyTestOutcomeTests.testSavedNotVerifiedTintIsNeverGreen`,
  `.testVerifiedTintIsGreenAndFailedTintIsRed`, `.testEachOutcomeHasADistinctIcon`,
  `.testProviderDetailViewDoesNotKeyTheTestIconOnSuccessAlone` (a source-scan guarding the
  regression directly: the old binary `result.success ? "checkmark..." : "xmark..."` ternary
  must never come back). **What remains, honestly:** the PROVIDER LIST row's own status dot
  (`ProviderSettingsRow`) is unaffected by any of this — it is stateless and never sees a Test
  Connection result at all, still `isLocalProvider || provider.hasApiKey ? .green : .orange`
  (verified in code today). That gap belongs to `ai/ai-settings.md`'s local-runtime honest
  status behavior on the ai-settings milestone, a different behavior, unchanged by this fix.

#### Redirected from the legacy "Settings - Models & Providers" milestone

- **#484** ("Wire: Providers + API Keys") — redirected while folding `ai-settings.md`'s pass
  2. Its own acceptance checklist (add a provider, enter an API key, Test Connection, browse
  the model catalog) is verify-close against `keys.test-connection-real-probe` above and the
  provider-management surface this spec already documents — not re-litigated as a fresh claim
  here since #484 itself names no gap beyond what's already built or already tracked.

#### Legacy milestone fold — "Settings - Models & Providers - HPC" (#240), 2026-09-19

Two of the milestone's seven issues in this spec's scope are genuinely this spec's own subject;
the rest belong to `ai-settings.md` or maintainer triage (folded there, not restated here).

- **#4631** ("Google AI: availability + model-list parity") and **#4632** ("Hugging Face:
  availability + model-list parity") — each names two asks. The AVAILABILITY half ("shown iff
  key configured + reachable") is a verify-close against `keys.test-connection-real-probe`
  above, which already does exactly this for every registered provider, Google AI and Hugging
  Face included — evidence posted on both, left open. The MODEL-LIST-PARITY half ("== Settings
  across surfaces") is NOT this spec's claim — it's `ai-settings.md`'s
  `settings.one-catalog-unification` (GAP), cross-referenced there, not duplicated here.

#### Apple Vision as an OCR/vision capability

- `keys.apple-vision-is-a-capability-not-only-a-key-check` — **[GAP]** (#2060, redirected
  from the legacy "Importer" milestone while folding `importer.md`'s pass 2) `apple_vision` is
  already a recognized provider with a real connection probe
  (`keys.test-connection-real-probe` above), but this issue's actual ask is broader: using
  Apple's Vision framework as an on-device OCR/vision ENGINE the importer or a workflow can
  choose, alongside cloud OCR providers — not only a settings-row key check. Whether Vision is
  wired as a selectable OCR/transcription engine anywhere in the import or workflow path was
  not verified this pass; the provider-key surface and the actual capability are two different
  questions, and this behavior is the capability one.

- `keys.key-never-in-logs` — **[PARTIAL]** (#4821) the app-supplied in-process key is never logged:
  `supply_api_key` (`fichero-server/src/fichero_server/security/provider_keys.py:39-58`)
  logs only the provider name and the fact of supply, explicitly documented ("Never log the
  key") and pinned by
  `test_supplied_provider_keys.py::test_the_key_is_never_logged`. The two other paths that
  touch a key value — `set_provider_api_key_impl`'s route-level logging
  (`api/routes/ai/provider_keys.py:114,120`, logs only the provider name) and
  `keychain.py`'s `set_api_key`/`delete_api_key` debug/warning lines (`keychain.py:266-299`,
  also provider-name-only) — were read and confirmed to never log the key value either, but
  neither has a dedicated test guarding it, hence PARTIAL rather than a blanket OK. A second
  pin lands with the Test Connection probe work: `test_routes_provider_keys.py::test_connection_test_key_never_appears_in_response_or_logs`
  (a sentinel key never appears in the response body, its JSON serialization, or the log
  capture, across a real probe path).
- `keys.argv-exposure` — **[GAP]** (#4818) `keychain.py:253-265` passes the plaintext key as
  `-w <key>` in argv to `/usr/bin/security add-generic-password`, visible to any other
  process on the machine (e.g. `ps`) for the subprocess's brief lifetime. Needs a design
  decision (stdin-based write, or a non-shelling-out primitive) before it can be fixed.

#### Mid-run correctness

- `keys.per-call-key-resolution` — **[OK]** a workflow already in progress must pick up a
  key change without a process restart. `llm.get_api_key(provider)`
  (`fichero-server/src/fichero_server/llm/__init__.py:1222-1246`) resolves per call through a
  process-level cache that both the Keychain write path (`keychain.py`'s
  `_invalidate_llm_api_key_cache`) and the app-supplied path
  (`provider_keys.py`'s `_invalidate_llm_cache`) bust on every write/supply/forget. Pinned:
  `test_llm_api_key_cache.py::TestKeychainWriteInvalidatesCache::test_set_api_key_invalidates_cache`,
  `::test_delete_api_key_invalidates_cache`,
  `test_supplied_provider_keys.py::test_supplying_a_key_busts_the_resolution_cache`.

### Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | `ProviderKeyStore` primitives (store/read/remove/trim/migrate) | `fichero/Tests/Unit/general/Services/ProviderKeyStoreTests.swift` |
| Availability (Swift) | y | `supplyProviderKeysToEngine()` pushes the CURRENT app-owned key, including after a Settings save/remove; remote-engine guard short-circuits | proposed, no file yet — the #4815 regression test |
| Backend (pytest) | y | per-call key resolution + cache invalidation on write/supply/forget | `fichero-server/tests/unit/security/test_llm_api_key_cache.py`, `test_supplied_provider_keys.py` |
| Backend (pytest) | y | `/test` returns a real probe result per provider, `not_verified` for the rest | `fichero-server/tests/unit/api/test_routes_provider_keys.py` (`test_connection_test_real_probe_success_sets_verified`, `test_connection_test_untested_provider_reports_saved_not_verified`) |
| Click-around (XCUITest) | n | this is a Settings + engine-connect contract, not a full-app flow worth a dedicated UI test yet | — |

Hard-gate: `keys.settings-save-survives-relaunch`, `keys.remove-survives-relaunch`,
`keys.test-connection-real-probe` — these three are exactly what the field report broke.

### Open questions

1. Does the app-side fix (`saveAPIKey`/`removeAPIKey` also writing/removing
   `ProviderKeyStore`) fully retire the engine's own legacy-keychain write path
   (`provider_keys.py:143-148`'s own docstring already says the app-supplied POST should be
   memory-only), or does that engine-side cleanup wait for a separate pass?
2. `keys.untested-provider-reports-not-verified`: does "not verified" ever get its own real
   probe over time (starting with OpenRouter, per #4816's fix), or does the provider list
   grow faster than probes can be written, making "not verified" a permanent honest floor for
   most entries?
3. Should `anthropic`'s format-only check be reclassified as "not verified" too, since it
   makes no network call, or does prefix-validity count as a legitimate lightweight probe
   distinct from the `else` branch's true no-check?
4. `keys.argv-exposure` (#4818): stdin-based `security` invocation, or move off shelling out
   to `/usr/bin/security` entirely in favor of a Swift-side write only (the app already owns
   `SecItem` calls directly in `ProviderKeyStore.swift`) — does the engine need to write a
   keychain item at all once #4815 lands, or does #4815's fix make the engine-side Keychain
   write dead code?
5. `keys.launch-supplies-to-engine`/`keys.remote-engine-not-app-business`: worth a dedicated
   Swift test now, or fold into the same regression test #4815 already calls for?

### Legacy milestone note

"Settings - Models & Providers" (#20) is the maintainer's own 55-row triage queue and was not
touched beyond moving #4815/#4816 off it. Of its other open issues, only **#484 "Wire:
Providers + API Keys"** is really about provider KEYS specifically (title search across the
milestone) — everything else on it is about models, embeddings, MLX, or the broader Settings
UI, not key persistence/verification. Flagged for the maintainer's fold-in decision, not
moved.

## M. One model list and row, everywhere (folded from `ui/model-selector-consistency.md`, 2026-10-04)

Folded from `ui/model-selector-consistency.md` on 2026-10-04 (its DRAFT of 2026-09-15). The brief: the model and key picker differed between the document island, the workflow bar and Settings; the island's looked best, and the others should match it. `[PROPOSED]` tags were replaced with real ones on folding.

### Intent (the design)

Choosing which model runs is ONE decision the user makes in several places. Wherever it appears — the
window's model chip, the workflow bar's per-step picker, a chat toolbar, a comparison sheet — it must
look and behave the SAME: same rows, same family glyph, same cost display, same grouping, same
"configured tiers first," same vision/selection awareness. Settings is the one different job (it
MANAGES the catalog — add/remove/configure keys), but even it renders the same ROW so a model looks
identical whether you're picking it or configuring it. One picker component, one list policy, one row.

This is the same "one source, many surfaces" principle as [[menus-and-commands]] and the workspace
consolidation.

---

### Current architecture (grounded, 2026-09-15) — ~7 pickers, 3 list-builders

There is no shared picker. At least seven implementations render "choose a model":

| Surface | File | Shape | List logic |
|---|---|---|---|
| **Document island (REFERENCE)** | `Shell/Toolbar/ModelChipToolbarItem.swift` (`ModelChipToolbarItem` + `ModelFamilyMark` + `ModelPickerRow`) | compact chip → popover | selection-aware (vision vs text tier); loads its own provider cache on menu-open |
| Workflow bar (per step) | `Shell/Toolbar/WorkflowBarModelPicker.swift` (+ `WorkflowBarModelTier`) | Menu | configured tiers first, then provider-grouped, deduped on **provider+model**, vision flag + cost |
| Settings | `Settings/AI/AIProviders/AIModelSelectionView.swift` (+ `AIModelCatalog`, `ModelRowView`) | full filtered list | filter (capabilities/mode) + sort (cost/…) + search + add-model — a MANAGEMENT view |
| Chat toolbar | `Chat/ChatViewToolbar.swift` (`ChatModelPicker`) | Menu | its own |
| Comparison | `Chat/ModelComparison/ModelPickerSheet.swift` | sheet | its own |
| Workflow node | `Workflow/Nodes/ModelPicker.swift`, `NodeProviderModelSelector.swift` | inline | its own |

**Finding S1 — three different list-builders for the same list.** The island loads a provider cache
on open; the workflow bar has a pure tier-first/provider-grouped/deduped builder; Settings has a
filter+sort pipeline. They each claim to use "the same provider cache the Run Workflow menu uses,"
but assemble and order it differently — so the same account can show different models, in a different
order, at different (or no) cost, depending on where you look.

**Finding S2 — the ROW is drawn three ways.** The island's `ModelPickerRow` + `ModelFamilyMark`
(family glyph, tier, vision hint) is the nicest; the workflow bar draws its own menu rows; Settings'
`ModelRowView` draws its own with cost/capabilities. A model has three faces.

**Finding S3 — vision/selection awareness is island-only.** Only `ModelChipToolbarItem` narrows to
vision-capable models when a page is selected. The workflow bar carries a `visionFlag` but the chat
and node pickers don't consistently. Awareness should be a property of the shared component.

**Finding S4 — cost display is inconsistent.** Settings and the workflow bar show per-million cost;
the island shows tier/family; chat shows neither. Cost is a first-class decision input and should
render the same everywhere it's shown.

---

### Proposed design — one picker, one list policy, one row (build on the island)

#### 1. Extract the island's row as the shared row — **[PROPOSED]**
`ModelFamilyMark` + `ModelPickerRow` (the reference's row: family glyph · name · tier · vision hint ·
cost) become a shared component every surface renders — the island, workflow bar, chat, comparison
node, AND Settings' management list (same row, plus its add/remove affordance). No surface hand-draws
a model row.

#### 2. One pure list-builder — **[PROPOSED]**
Generalize `WorkflowBarModelPicker`'s already-pure builder (configured tiers first → provider-grouped
→ deduped on **provider+model** → vision flag → cost, with a tiers-only fallback when the cache is
empty) into the ONE model-list function. The island, workflow bar, chat and node pickers all call it;
Settings' management view filters/sorts ON TOP of the same base list. Selection/vision-awareness is a
parameter (the island passes "vision" when a page is selected), not a fork.

#### 3. One picker component, two presentations — **[PROPOSED]**
A single `ModelPicker` view (the island's chip+popover as the canonical presentation) with a compact
mode (chip, for toolbar/workflow-bar/chat) and, where a sheet is warranted (comparison), the same
rows in a sheet. Settings keeps its management chrome but hosts the shared rows. One component, so
grouping, family marks, cost and vision awareness can't drift.

#### 4. Provider/API-key affordance is consistent — **[PROPOSED]**
Adding/choosing a provider key surfaces the same way from every picker (a "Manage providers…" route
into Settings), so a picker that finds no configured model always offers the same next step, never a
dead empty menu (mirrors `SidebarContextMenuPolicyTests`' never-silently-empty rule).

---

### Behaviors (each → one pinning test)

- `models.one-list-policy` — **[PARTIAL]** (#4883; built: `SharedModelListBuilder` with `SharedModelListBuilderTests`; not yet every picker) every picker's base list comes from the ONE pure builder;
  same account → same models, same order, same dedupe (provider+model), everywhere. *Test:* pure
  unit tests over the builder (extend the existing `WorkflowBarModelPicker` list tests): tier-first
  order, provider+model dedupe, tiers-only fallback, vision filter narrows correctly.
- `models.one-row` — **[PARTIAL]** (#4883; built: `SharedModelRow` with `ModelRowSourceGuardrailTests`; not yet every surface) the island, workflow bar, chat and Settings render the SAME row
  component (family mark + name + tier + cost). *Test:* a source guardrail that no surface defines
  its own model-row struct once the shared one exists.
- `models.vision-awareness` — **[GAP]** (#4883) a page/vision selection narrows every picker to
  vision-capable models identically. *Test:* the builder's vision-filter unit test, plus the island's
  existing selection→tier resolution test.
- `models.cost-shown-consistently` — **[GAP]** (#4883) where cost is shown it is the same value and
  format across surfaces. *Test:* a formatter unit test + a render check.
- `models.never-empty-offers-providers` — **[GAP]** (#4883) a picker with no configured model always
  offers the Manage-providers route, never a silent empty menu. *Test:* pure policy test (the
  `SidebarContextMenuPolicyTests` fallback shape).

---

### Maintainer test, 2026-09-19 morning

Evidence for the "~7 pickers, 3 list-builders" finding above, plus a fourth captured picker and
a ruling.

- `models.four-pickers-today` — **[BROKEN]** (#4883) what each of four surfaces shows today, as
  observed live (workflow bar, centre island, Settings > AI > Defaults, and — newly
  captured, screenshot 9.40.17 — the workflow node's config popover):

  | Picker | Shows today |
  |---|---|
  | Workflow bar | flat text list, "Use the default (model)" first, each row a name + a loose tag mixing capability/size/provider ("Vision", "Text", "Large", "apple", "openrouter", "huggingface", "spacy", "kraken", "whisper"); no icons, no prices; unavailable models greyed |
  | Centre island | provider icon, name, price per million tokens in/out, an eye icon for vision-capable models, a tick on the current one, provider name at the right, "AI Settings..." link at the bottom |
  | Settings > AI > Defaults | grouped under provider headings (Apple Intelligence, Hugging Face, ...), full ids ("datalab-to/chandra-ocr-2"), descriptive names ("Apple Vision (OCR)"), a "None" row |
  | Workflow node config popover | lists ONLY the role defaults, each with a generic "?" icon and no provider icon: Default, $small, $large, $vision_small, $vision_medium, $vision_large; lists NO concrete models at all |

  Four different shapes, confirming Finding S1/S2 above with a fourth data point rather than
  the three already catalogued. Whether a row shows price, capability, provider, or all three
  remains an open DESIGN question (see "Open questions," item three, below) — not decided by this finding.
- `models.four-pickers-four-sources` — **[PARTIAL]** (#4883) cause, verified at each file at the
  time this behavior was written: four pickers, four different data sources, not just four
  different rows/layouts, with the workflow bar's `modelPinMenu` (hand-drawn `Button` rows, no
  `SharedModelRow`/`SharedModelChoice` use) the one outlier surface. **Updated 2026-09-19
  (705e65cf1)**: per that commit's own account, five of the six picker surfaces already shared
  `SharedModelListBuilder` before this fix — the "zero adoption" framing above is stale, corrected
  here. This commit closes the workflow bar's own remaining gap: its model control is now the
  same popover idiom the step inspector uses, rendering `SharedModelRow`, and its two hand-drawn
  menus (`modelMenu`, `modelPinMenu`) are deleted outright. **Which source is canonical is NOT an
  open question** — the node popover's own code already cites the ruling:
  `docs/contributor_manual/specs/ui/workflow-node-config.md`'s
  `nodeconfig.model.same-list-as-settings` (ruled 2026-09-08, `[OK]`, pinned
  `NodeModelListParityTests`) states pickers offer the user-CONFIGURED models, because the live
  catalog used to let a node pick a model its provider does not actually serve → a 404 at run.
  PARTIAL, not OK: **NOT SEEN ON SCREEN** (the fixing commit's own words — build passes, tests
  pass, "how the popover and its rows look on screen" is unverified); the island's own catalog
  source and Settings' own row are still open per the maintainer's own outstanding questions
  (below). Pinned: `SharedModelListBuilderTests` (17 cases), `NodeModelListParityTests`,
  `AISettingsSelectionTests`, `ModelRowSourceGuardrailTests` — all executed through Xcode per
  the commit, all passing.
- `models.role-defaults-always-offered` — **[PARTIAL, RULED]** (#4883) every model picker offers
  the ROLE DEFAULTS (small, large, vision small, and so on) as choices ALONGSIDE concrete models
  — in the workflow bar and the document island the maintainer must be able to choose "small",
  "large", "vision small", etc, not only a named model. The one shared picker (§"Proposed
  design" above) should have two groups: role defaults (resolved to whatever Settings > AI >
  Defaults currently names, and SAYING which model that is) and concrete models. At the time
  this behavior was written, only the workflow node popover offered role defaults, and it
  offered ONLY those, no concrete models — the opposite gap. **Updated 2026-09-19 (705e65cf1)**:
  role defaults now have ONE home, `SharedModelListBuilder.roleDefaultAliases(from:
  includeVision:)` — it builds `$small`/`$large`/the three vision aliases from `AIDefaults`,
  each naming the concrete model it resolves to today (or "not set"); no such resolver existed
  before. The node popover's own private `aliasOptions` is deleted and now takes the shared
  rows; the workflow bar's new popover offers every role default alongside the concrete models
  (picking a role default stores the ALIAS, not the resolved model, so a run-level override
  never silently freezes — a text alias chosen on a vision step raises, and the bar already
  marks that choice unsuitable). Still open, per the maintainer, and NOT decided here: how the
  ISLAND offers role defaults (it stores a CONCRETE (provider, model) pair only —
  `ModelChipToolbarItem.swift:259`, `select(_:)` — it is where a role default GETS its value, so
  it cannot hold a role alias today) and what SETTINGS' own row should show. **NOT SEEN ON
  SCREEN** — same disclaimer as `models.four-pickers-four-sources` above.
- `models.node-popover-vision-check-diverges` — **[BROKEN]** (#4694) the workflow node config
  popover says "No vision-capable providers available" in orange on a vision node
  (screenshot 9.40.17), while the other three pickers on the same machine show vision-capable
  models as available (apple-vision, claude-opus-5, and others with the eye icon) at the same
  time. **Cause: UNVERIFIED — two candidates, both consistent with the code, neither confirmed
  against what the maintainer's machine actually returned.** (a) Stale-capabilities path:
  `NodePopover+Comparison.swift:28-32` derives `supportsVision` from the SAVED rows'
  `capabilities`; the id-based heuristic (`idLooksVisionCapable`) runs only when `capabilities`
  is empty — so a saved row with a non-empty `capabilities` set that happens to lack "vision"
  is marked not-vision-capable even if the island's live catalog flags the same model as
  vision-capable. This is a catalog-content divergence, not a load race. (b) Empty-providers
  path: `loadProviders()` (`:8-23`) only appends a provider when `provider.enabled` is true and
  `listProviderModels` succeeds — the screenshot shows the popover listing NO concrete models
  at all, only role defaults, which equally fits zero enabled/configured providers returned, or
  an unhandled throw into the function's own `catch`. Both are named; neither is the confirmed
  cause. #4694 already names the same CLASS of bug ("Node picker filters providers on the
  provider-level vision flag") — evidence added there rather than duplicated as a new issue.
- `models.chat-picker-uses-the-shared-builder` — **[PARTIAL]** (#4900) the chat toolbar's model
  picker (`ChatViewToolbar.swift`, `ChatModelPicker`) renders the shared
  `SharedModelListBuilder`/`SharedModelRow` spine, not its own inline picker. Built: `21820e8d2`
  (82 insertions, 31 deletions). PARTIAL because nothing tests it — the commit's own message
  states outright: "No tests reference this surface." A high-traffic surface (every chat
  window's model picker) with zero coverage of the rewrite. The test shape that would catch a
  regression: drive the picker through the real shared builder and assert the rendered choice
  set, PLUS an explicit companion asserting the chat toolbar's production call site still
  routes through it rather than a re-inlined picker — the same pure-function-plus-
  call-site-routing pairing `AISettingsSelectionTests` uses for its own
  "productionCallSiteRoutesOnlyThroughThePureFunction" check.

### RATIFIED 2026-09-15 (evening, CD)

- **Adopt the shared spine.** One shared ROW (the island's `ModelFamilyMark` / `ModelPickerRow`) +
  one pure list-builder (generalize `WorkflowBarModelPicker`'s tier-first / provider-grouped /
  provider+model-deduped / vision+cost builder). Every surface — island, workflow bar, chat,
  comparison, nodes — renders both. The ~7 divergent pickers collapse to one spine. Land
  subtractively (shared row → shared builder → per-surface adoption), each step pinned by a pure
  list-builder test. Keep the builder PURE (the island fetches its own cache outside the
  `LibraryWorkspaceRoot` env, #4448) — don't bake an environment read into it.
- **Settings uses the SAME picker — direct, one-step selection.** In the Settings window you choose a
  model the SAME way as the island: the shared picker (chip → popover of the shared rows), picked
  directly — NOT "open a menu, then a submenu" to drill to a model. Settings keeps its management
  affordances (add/remove providers, keys, filters) around that picker, but the act of CHOOSING the
  active/default model is the one shared component, so it looks and behaves identically to the island.
  (This supersedes "Settings reuses the ROW only" — it reuses the whole picker for selection.)
- **Platform = iPad / Mac / iOS first-class** (matches [[menus-and-commands]]): the shared row +
  builder must render correctly on all three; test each.

### Open questions (still open)

1. **Chip vs menu vs sheet** — **ANSWERED 2026-09-19 (705e65cf1)**: the workflow bar's model
   control is now the same popover idiom the step inspector uses (not a `Menu`), rendering
   `SharedModelRow`; its `Choose Model` right-click menu item opens the same popover. Not seen
   on screen yet, per that commit's own disclaimer.
2. **Settings' scope** — Settings manages keys/catalog (a superset job). Confirm it reuses the shared
   ROW only, keeping its filter/sort/add chrome — not that it collapses into the picker.
3. **Cost everywhere?** — should the island show per-million cost too (it shows tier/family today), or
   is cost a workflow-bar/settings concern where budget matters most? **Candidate answer recorded,
   not decided here** (from the source-model spec work, branch `spec/page-model`, `specs/source/
   models-chains-and-projects.md` — not in this tree): a row could show what a "model card" knows
   — what it suits (languages/scripts/periods), whether it's local or cloud, and a licence class —
   alongside or instead of price/capability/provider. See `ai-settings.md`'s own Open Question 5
   for the model-card shape this candidate answer depends on.
4. **Node vs step pickers** — the workflow NODE pickers (`ModelPicker`, `NodeProviderModelSelector`)
   and the workflow BAR picker — one component for both, or do nodes need more (provider+model+params)?
5. **How does the island offer role defaults?** (`models.role-defaults-always-offered`) The island is
   verified to store only a resolved concrete `(provider, model)` pair — it IS where $medium/
   $visionMedium get their value, so it cannot itself hold a role-alias sentinel the way the node
   popover's `aliasOptions` do. Does picking "$medium" from the island mean "show me what $medium
   currently resolves to, then let me change that value" (the island stays the editor of the
   default), or does the shared picker need a genuinely separate role-alias affordance the island
   does not have today?

---

### Ponytail review (2026-09-15)

The lazy, correct move is to promote what already works, not add a new abstraction: the island's
`ModelFamilyMark`/`ModelPickerRow` is the nicest row — make it the shared one; the workflow bar
ALREADY has the pure list-builder with dedupe/tiers/vision/cost — make it THE one and delete the other
list logics. Net change is deletions plus a couple of extractions, not a new picker framework.

Watch-outs:
- **Settings is a different job** (management), not just a picker — reuse its ROW, don't force it into
  the chip. Collapsing them would lose the add/remove/key affordances.
- **Data source boundary** — the island fetches its own cache because a toolbar item lives OUTSIDE the
  `LibraryWorkspaceRoot` env tree (`ModelChipToolbarItem` documents this #4448 boundary). The shared
  list-builder must stay PURE (takes `[LLMProvider]` + tier defaults), so each host feeds it from
  wherever it legitimately gets the cache — don't bake an environment read into the shared component.
- **Don't over-unify presentation** — chip, menu and sheet are legitimately different containers for
  different contexts; share the rows and the list policy, not necessarily one container.
- Land it in increments (shared row first → shared list-builder → per-surface adoption), each pinned
  by an extended existing test, exactly like the menu and workspace programs.

**Verdict:** adopt the island's row + the workflow bar's pure list-builder as the shared spine;
Settings reuses the row; land subtractively. Ready for CD review, not yet code.
