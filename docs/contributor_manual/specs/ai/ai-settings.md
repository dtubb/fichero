# AI Settings — Design Spec (#TBD)

> Milestone: ai-settings
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
> key once entered are `ai/provider-keys.md`'s (→ #4815, → #4816, → #4818, → #4819, → #4820,
> → #4821). This spec owns the SURFACE (rows, tabs, catalog) the key field lives inside.

## Intent (the design)

Every AI provider — cloud or on-device — is a row in ONE list, with the same shape: a name,
a status that means what it says, and a detail view. A local runtime's detail carries what
makes it local (provisioning, its own model catalog, start/stop) instead of living in a
separate pane; a cloud provider's detail carries a key and its models. There is one model
catalog, not several disagreeing lists, and a provider's status dot is never green unless the
thing it names is actually ready. Settings surfaces preferences, not plumbing — no toggle a
user can't explain the consequence of.

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
  persists, which is `ai/provider-keys.md`'s).
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

### What has not shipped (P1's schema half, P2, P3, P4)

- `settings.mlx-runtime-honest-status` — **[BROKEN]** (#4303) a local runtime's status dot
  must reflect whether it is actually provisioned/ready, not just "is local." Verified in
  code: `ProviderDetailView`'s status circle is
  `isLocalProvider || provider.hasApiKey ? Color.green : Color.orange` — an unprovisioned
  MLX renders the identical green dot as a ready one, because no `runtime_state` field
  exists on `ProviderResponse` to tell them apart. This is a verified sub-symptom of #4303's
  broader "MLX appears non-functional" report — a user has no visual signal that MLX needs
  provisioning before it will work.
- `settings.embeddings-download-works` — **[GAP]** (#4304) starting an embeddings download
  from Settings must actually deliver a usable model. Reported broken (field issue); this
  pass did not trace the failure in `local_models.py`'s `download_model` route to a root
  cause, so it stays GAP rather than a code-verified BROKEN — the download route exists
  (`local_models.py:145`) but whether/why it fails was not re-verified here.
- `settings.one-catalog-unification` — **[GAP]** (#4307, → #1059, → #1200, → #1342, → #1152)
  cloud and local models must resolve through ONE response shape (a cloud row's local-only
  fields simply absent), with one shared download-row component and one disk-usage view.
  Not built: cloud (`ProviderAPIService`) and local (`LocalInferenceStore`/
  `LocalModelsSettingsView`) models still come from separate response shapes and separate
  stores. → #4307 is the direct tracker; → #1059 (consolidate ~6 picker UIs), → #1200 (a
  richer searchable browser), → #1342 (centralize download location), and → #1152 (a
  deletable models folder) are related, pre-existing, broader trackers — cross-milestone
  pointers, not folded into this narrower claim.
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
- `settings.health-observability` — **[GAP]** (#4327) a status surface across providers,
  tiers, and tools (plus per-call visibility into the underlying LangChain routing) does not
  exist today — every provider row shows its own status in isolation, with nothing
  cross-cutting.

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

## Issue map (all 28 open issues on "Settings - Models & Providers", #20)

Disposition key: **cited** = moved onto `ai-settings` (#306), backs a behavior above by plain
citation · **related** = arrow-cited above, stays on its own milestone (a broader,
pre-existing tracker, not this spec's narrower claim) · **recommend-close** = looks
superseded by what's already built; the maintainer's call, not closed here · **recommend
re-home** = not really about this Settings surface at all; belongs on a different milestone.

| # | Title | Disposition |
|---|---|---|
| 284 | Re-enable Settings tabs (General/Backend/Models) after 0.0.2 | recommend-close — the tabs this refers to (General/Backend/Models) are long gone from the current tab set; looks stale |
| 484 | Wire: Providers + API Keys | recommend-close — providers + keys are wired (`ProvidersView`, `provider_keys.py`); superseded by what's built + `ai/provider-keys.md` |
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
| 2444 | Expose Translate (DeepL) as a workflow tool/node | recommend re-home — DeepL is already a working provider (real Test Connection probe, per `ai/provider-keys.md`); this is about workflow-node exposure, not Settings |
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
5. Is the three-tab target (Defaults · Providers · Advanced) still right, or does Embeddings
   getting a provider row change what "Downloads retiring" even means?
