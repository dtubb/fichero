# Cloud permission and spend (cluster A)

> Status: approved 2026-11-04 (manager, delegated by the owner; owner's request of 2026-11-03, for this release). Extends
> `ai/where-models-run.md` §D–E (`ai.where.one-egress-gate`, `ai.where.cloud-spend-cap`,
> `ai.where.run-cap-beside-the-project-cap`) and `source/recipe-designer.md` §11b (`designer.budget.*`). Iterate on
> what exists; nothing here replaces the one spend hold (`llm/spend.py`) or the one egress gate (`llm/egress.py`).

## The problem, and one decision per question

Today a cloud spend cap exists only as a project's Set Up answer (`answers.cloud_spend_cap_usd`, US$10 a month unless
set, held by `llm/spend.py`, booked in the project's `recipe/cloud-spend.json` by UTC month), and whether pages may go to
the cloud is a project answer (`cloud_allowed`) under an app-wide places tick (`recipes/places.py`, `models_may_run`,
the Settings > AI "Allow cloud AI services" switch). Someone who never runs Set Up has no cap control, and no daily cap
exists anywhere. A refusal from a hand-run path (the context menu, the workflow bar, the runner) is a validation 400
whose only switch is in the error text (#6028), or a page row with category `egress_refused` / a run paused at the cap
with words the app does not act on. The CLI and MCP get the same bare detail.

Decisions (details under "Decisions I made"):
1. **App-wide caps are defaults, not second ceilings.** Settings > AI holds a monthly and a daily cap; a project with
   its own answer uses its own, a project with none uses the app's. The hold still judges one project ledger.
2. **A daily cap is held exactly like the monthly one**, from the same ledger, which gains a day total.
3. **Images-to-cloud: the Settings switch is the default; a project may say yes or no for itself.** A project that
   has not answered inherits. This replaces "the app's places cap every project" for the cloud place only.
4. **One typed refusal, served, never computed in the app**, for every cap and the images rule, with its fixes.
5. **A person never has to answer per project.** The Settings defaults (the two caps, the images switch) are enough on
   their own; a project answer only departs from them, and every refusal offers the app-wide fix beside the project one.
6. **Overrides are of two kinds**: a permanent one (an audited action: raise the cap, allow for this project) and a
   one-run one (carried on the run row, written nowhere else).

## Behaviours

Status tags are as of 2026-11-04 (A: the engine half of its first three lines is built, three PARTIAL, the Swift half is Step 1.2; nothing in C or D is built; B's three OK lines and two PARTIAL are as named). Tests are files that must exist when the line is built.

### A. Caps in Settings (#6346, #6347)

- `ai.cloud.monthly-cap-in-settings` [PARTIAL] (#6346; engine built, the Settings field is Step 1.2, uncompiled) — Settings > AI > Cloud has "This Mac a month, at most", an app
  setting (`cloud_monthly_cap_usd` in the app DB, beside `models_may_run`), default US$10; `spend.cap_usd()` reads it
  for a project with no `cloud_spend_cap_usd` answer, in place of the constant `DEFAULT_CAP_USD`. Tests:
  `fichero-server/tests/unit/llm/test_app_cloud_caps_6346.py`,
  `fichero/Tests/Unit/general/Views/Settings/CloudCapsSettingsTests.swift`.
- `ai.cloud.daily-cap` [PARTIAL] (#6347; engine built: the ledger, the hold, the plan line, the project's route and the refusal words, also pinned by `fichero-server/tests/unit/recipes/test_daily_cap_paths_6347.py`; the Set Up field and the typed refusal are Steps 1.2 and 3.1) — the ledger (`recipe/cloud-spend.json`) keeps a `day` and `day_usd` beside the
  month; a daily cap (the app's `cloud_daily_cap_usd`, or the project's `cloud_daily_cap_usd` answer, normalised like
  the monthly one: 0 is a cap, below 0 refused, empty is none) is a third ceiling in `_past_a_cap`, `_cap_stop` and
  `plan_line` (`over_day`, `needed_day_cap_usd`), named in words when it refuses ("capped at $N a day, of which $M is
  spent today"). Tests: `fichero-server/tests/unit/llm/test_daily_cloud_cap_6347.py` (a day rolls over; the daily cap
  refuses first when lower; a run cap, a daily cap and a monthly cap all hold through the one hold).
- `ai.cloud.caps-are-one-audited-action` [PARTIAL] (#6346; built: the audited `app.set_cloud_cap` row and `PUT`/`GET /api/ai/cloud-caps`, a project's daily answer on `PUT /api/recipes/project/cloud-cap`; NOT built: Undo, by decision 10; the route test sets the cap back to its `from` figure instead; `project.set_budget` is the existing `project.save_setup` behind that route) — the app caps are set through one audited action,
  `app.set_cloud_cap` (which cap, from, to; undoable), route `PUT /api/ai/cloud-caps` with `GET` beside it, so MCP and
  the CLI get it from the regen; a project's daily answer rides on the existing `project.set_budget`. Tests:
  `fichero-server/tests/unit/api/test_cloud_caps_route_6346.py` (set, read back, undo, below 0 refused).
- `ai.cloud.set-up-shows-the-defaults` [GAP] (#6346) — Set Up's Budget block (`designer.budget.beside-the-estimate`)
  shows the app's figure greyed as the default when the project has no answer, and a daily field beside the monthly
  one. Tests: `fichero/Tests/Unit/general/Models/MoneyAndPlaceAnswersTests.swift` (extended).

### B. Images to the cloud (#6348, #6022, #6037, #6031)

- `ai.cloud.images-default-in-settings` [PARTIAL] (#6348) — the Settings > AI "Allow cloud AI services" switch
  (`CloudAccessSection`, `PUT /api/recipes/places`) is the app-wide default for whether pages may leave. Built: the
  switch and `places.inherits_cloud()` for a project with no answer. Not built: the words saying it is a default a
  project may change, and the count of projects that answered for themselves. Tests:
  `fichero/Tests/Unit/general/Views/Settings/CloudAccessSectionTests.swift`.
- `ai.cloud.project-overrides-the-default` [PARTIAL] (#6348, #6022 place 1; engine built: `may_leave_to` for the cloud, `project.allow_cloud` with `allowed`, and the call-time gate (`llm._enforce_local_only_provider`) now judges the cloud by the project's answer, not by the app's places answer; the Set Up question reads the same `cloud_allowed` answer but is uncompiled, Step 2.2) — a project's `cloud_allowed` answer wins
  over the app switch in both directions: `places.project_says_cloud` returns the project's own answer when it has one
  (today a project may only be stricter); the existing audited `project.allow_cloud` takes `allowed: bool` so one action
  sets yes or no (undoable, Set Up's question shows the same answer). Tests:
  `fichero-server/tests/unit/recipes/test_project_cloud_override_6348.py` (app off + project yes sends; app on +
  project no refuses; no answer inherits; the gate `egress.project_allows_leaving` agrees),
  `fichero-server/tests/unit/recipes/test_places_cap_projects_5828.py` (updated: the cap stays for every place but cloud).
- `ai.cloud.switch-in-the-project` [GAP] (#6022 place 1) — the project's Inspector and the Project menu show "Allow
  cloud AI services for this project" (on, off, or "as Settings: on/off"), calling the action above. Tests:
  `fichero/Tests/Unit/general/Views/ProjectCloudSwitchTests.swift` (three states from a served answer).
- `ai.cloud.switch-in-settings` [OK] (#6022 place 2, #6031) — the Settings switch sets the places answer
  (`CloudAccessSection`; `test_places_cap_the_routes_5831.py`).
- `ai.cloud.switch-in-set-up` [OK] (#6022 place 3, #6031) — Set Up asks it (`designer.rank.cloud-permission-said-once`)
  and the step menu offers "Allow Cloud for This Project" (`StepChoiceMenusView`).
- `ai.cloud.switch-at-first-launch` [OK] (#6022 place 4) — first-launch setup asks where models may run
  (`WhatFicheroRunsFields`, `FirstRunWindow`, `AppPlacesStore`).
- `ai.cloud.finder-carries-the-permission` [PARTIAL] (#6037) — the finder route takes `cloud_allowed` and ANDs it with
  the places (`api/routes/system/recipes.py` finder route), and the finder's Allow Cloud Models button saves the yes
  and reloads with it (`ModelFinderView`, uncompiled). Not built: the finder opened from Settings (no step) has no
  button; after B's override the button calls the one action and the reload reads the engine's answer, not a flag the
  app sets. Tests: `fichero/Tests/Unit/general/Models/ModelFinderStoreTests.swift` (extended),
  `fichero-server/tests/unit/recipes/test_cloud_candidates_need_permission_5768.py` (extended).
- `ai.cloud.never-sent-while-off` [OK] (#6028) — a cloud call under a project that may not send is refused at the
  gate and at validation; nothing leaves (`test_one_egress_gate_5368.py`, `test_egress_gate_every_call_site.py`).
  The refusal's WORDS and action are C below.

### C. A refusal is an alert with a way through (#6349, #6028, #6022, #6350)

- `ai.cloud.one-typed-refusal` [PARTIAL] (#6349, #6350; Step 3.1a built: `llm/refusal.py`, on both errors, the execute 400's `detail.refusal`, a paused run's `stopped_refusal` and a page failure's `refusal`; the `allow-everywhere` and `allow-project` buttons act through the existing actions, app side is Step 3.2) — every refusal for money or images is one served shape,
  `CloudRefusal`: `kind` (`cap-monthly` · `cap-daily` · `cap-project` · `cap-run` · `images`), `scope` (`app` ·
  `project`), `project`, `cap_usd`, `spent_usd`, `estimate_usd` (this call's worst case, or the run's estimate),
  `words`, and `fixes[]` (`raise-to` with `usd`, aimed at the scope the refusal names, so an app cap raises the app setting; `allow-everywhere`, for `images` only: sets the APP default through the audited places action; `allow-project`; `allow-once`; `over-cap-once`; `open-settings`
  with the control's id, `settings.ai.cloudAllowed` or `settings.ai.cloudCaps`), extending
  `designer.budget.refusal-offers-the-fix`'s `fixes[]` and `_cap_stop`'s figures. It rides on `CloudSpendRefusedError`
  and `EgressRefusedError` as a field, on the validation 400 as `detail.refusal`, on a run's paused-at-cap status
  (`spend.stopped_at_cap`) and on the per-page failure (category `egress_refused` gains `spend_refused`). Tests:
  `fichero-server/tests/unit/llm/test_cloud_refusal_shape_6349.py` (each kind, each fix including `allow-everywhere`, the words name the figure).
- `ai.cloud.hand-run-refused-before-it-starts` [PARTIAL] (#6349, #6028; Step 3.1a built the typed 400; the one `refused` stream event is Step 3.1b) — a hand run (`POST
  /api/workflow-execution/execute`) refused at validation for images answers the typed refusal, not prose alone; a run
  whose first cloud call would not fit a cap is refused at that call and paused (built: `_STOPPED_AT_CAP`), and the
  execution stream sends one `refused` event carrying the refusal so the app need not read a sentence. Tests:
  `fichero-server/tests/unit/api/test_execute_refusal_is_typed_6349.py`,
  `fichero-server/tests/unit/workflows/test_paused_at_cap_event_6349.py`.
- `ai.cloud.one-run-overrides` [PARTIAL] (#6349, #6350; Step 3.1b built: the two flags on the execute and resume requests, `llm/run_overrides.py` read by the gate and the hold, the spend still booked; not built: the recipe Start's flags and the Activity row's words) — the execute request (and a recipe Start) take
  `allow_cloud_once: bool` and `over_cap_once: bool`; both are kept on the run row (like `run_cap_usd`), read by the
  gate and the hold for calls of that run only, written to no project or app setting, and shown on the run's Activity
  row ("cloud allowed for this run" / "ran past the cap by your say"); spend is still booked. Resume after a pause at
  the cap accepts the same two flags. Tests: `fichero-server/tests/unit/llm/test_one_run_overrides_6349.py` (the next
  run is refused again; the ledger still books; the row says so).
- `ai.cloud.alert-on-hand-run-paths` [GAP] (#6349, #6028, #6022) — the context menu, the workflow bar and the runner
  show one `CloudRefusalAlert` built from the served refusal: its words, then the fixes as buttons: for a cap "Raise the
  cap to $N" (the audited action for the scope the refusal names), "Run past the cap this once", "Open Settings…"; for
  images "Allow for all projects" (the audited places action: the app default), "Allow for this project"
  (`project.allow_cloud`), "Allow this once", "Open Settings…"; never a raw
  "Server error (400)". After any button the app re-sends the execute (a refusal before the run started) or resumes the
  run (a pause at the cap) with the override, without the person starting it again. `importError` keeps no cloud
  refusal. Tests: `fichero/Tests/Unit/general/Views/CloudRefusalAlertTests.swift` (buttons from each served kind, images
  showing the four in that order; "Allow for all projects" sets the app default and no project answer; the re-send carries the flag; a refusal with no fixes shows Open Settings only),
  `fichero/Tests/Unit/general/Models/CloudCapFixTests.swift` (extended).
- `ai.cloud.allow-everywhere-sets-the-default` [GAP] (#6349, #6348) — the `allow-everywhere` fix of an `images`
  refusal calls the audited places action (the Settings switch's own), so one yes ends the question for every project
  that has not answered for itself; no `project.allow_cloud` row is written. Tests:
  `fichero-server/tests/unit/llm/test_cloud_refusal_shape_6349.py` (the fix names the places action),
  `fichero/Tests/Unit/general/Views/CloudRefusalAlertTests.swift` (the button sets the app default, no project answer).
- `ai.cloud.cli-refuses-in-words` [PARTIAL] (#6350; Step 3.3 built `fichero workflow run`: the words, the figures, each way through as a command or flag, exit 3; a recipe start's refusals are the plan's, not a 400, and are not built) — `fichero workflow run` and a recipe start print the refusal's words,
  the figures, and the route: the flags `--allow-cloud-once` and `--over-cap-once`, the commands that set the caps and
  the project's yes (from the regen), and the Settings control; exit code 3, never a traceback. Tests:
  `fichero-cli/tests/test_cli_cloud_refusal_6350.py`.
- `ai.cloud.mcp-refuses-in-words` [PARTIAL] (#6350; Step 3.3 built `fichero_workflow_run`: `detail.refusal` intact and the message naming `allow_cloud_once`, `over_cap_once` and the tools; the recipe start tool's flags are not built) — `fichero_workflow_run` and the recipe start tool return
  `EngineError` with `detail.refusal` intact and the tool's own arguments `allow_cloud_once`, `over_cap_once` named in
  the words; the cap and allow actions are tools from the regen. Tests:
  `fichero-server/tests/unit/mcp/test_mcp_cloud_refusal_6350.py`.

### D. The plan knows before Start (#6097, #6098, #6099, #6031)

- `ai.cloud.plan-knows-a-dead-key` [OK] (#6097; Step 4.1) — the Start plan reads the provider dead marks (`llm/retry._DEAD`
  with `fatal_cause`) and skips a step whose provider is out of credit or has a refused key, with that cause's words
  (`ai.where.dead-provider-says-why`) and the fix `choose-model`; a rate limit ranks the provider down, not out; the
  mark outlives its 30 s for the plan's purpose (kept with its time, read-only). Tests:
  `fichero-server/tests/unit/recipes/test_plan_knows_dead_key_6097.py`.
- `ai.cloud.plan-checks-the-capability` [OK] (#6098; Step 4.1) — a step's row must have the capability its job needs
  (`start._capability`, `llm._model_has_capability`); a row that lacks it is skipped at plan time with the validation's
  words and `choose-model`, so no Read fails at validation for it. Built beside it: remote reader cards inherit their
  provider's vision (`test_remote_reader_cards_inherit_vision.py`, #6031). Tests:
  `fichero-server/tests/unit/recipes/test_plan_checks_capability_6098.py`.
- `ai.cloud.no-model-names-the-missing-row` [OK] (#6099; Step 4.1) — when a key is set for a provider with no provider row,
  the "no model" line says so and names the place: "a key is set for <provider> but Settings > AI > Providers has no
  row for it; add the row". Extends `provider_without_key`'s neighbour in `recipes/start.py`. Tests:
  `fichero-server/tests/unit/recipes/test_no_model_names_the_row_6099.py`.

Out of this cluster from #6031: reader tiers, HTR-United hidden, `RecipeCard` remote source (the finder spec).

## Build order (engine first; each step shippable alone; one batch of at most ~25 files)

### Stage 1 — Caps in Settings

#### Step 1.1 — App-wide monthly and daily caps in the engine
- Issues: #6346, #6347
- Behaviours: `ai.cloud.monthly-cap-in-settings` (engine), `ai.cloud.daily-cap`, `ai.cloud.caps-are-one-audited-action`
- Files: `llm/spend.py`, `recipes/answers.py`, `recipes/cloud_cap.py`, a new `api/routes/ai/cloud_caps.py`, the OpenAPI regen
- Tests: fichero-server/tests/unit/llm/test_app_cloud_caps_6346.py, fichero-server/tests/unit/llm/test_daily_cloud_cap_6347.py, fichero-server/tests/unit/api/test_cloud_caps_route_6346.py
- Size: M

#### Step 1.2 — The two fields in Settings and Set Up
- Issues: #6346, #6347
- Behaviours: `ai.cloud.monthly-cap-in-settings` (app), `ai.cloud.set-up-shows-the-defaults`
- Files: `Views/Settings/AI/AISettingsView+Tabs.swift` (a `CloudCapsSection` beside `CloudAccessSection`), a `CloudCapsStore`, `RecipeSetupAnswers.swift`, `RecipeSetupPlanFields.swift`
- Tests: fichero/Tests/Unit/general/Views/Settings/CloudCapsSettingsTests.swift, fichero/Tests/Unit/general/Models/MoneyAndPlaceAnswersTests.swift
- Size: S

### Stage 2 — Images to the cloud: default and override

#### Step 2.1 — The project's answer wins; one action sets yes or no
- Issues: #6348, #6022
- Behaviours: `ai.cloud.project-overrides-the-default`, `ai.cloud.never-sent-while-off` (re-pinned)
- Files: `recipes/places.py`, `llm/egress.py`, `api/routes/system/recipes.py` (`project.allow_cloud` with `allowed`), the regen
- Tests: fichero-server/tests/unit/recipes/test_project_cloud_override_6348.py, fichero-server/tests/unit/recipes/test_places_cap_projects_5828.py, fichero-server/tests/unit/llm/test_one_egress_gate_5368.py
- Size: S

#### Step 2.2 — The switch in the project, the Settings words, the finder's permission
- Issues: #6348, #6022, #6037
- Behaviours: `ai.cloud.images-default-in-settings`, `ai.cloud.switch-in-the-project`, `ai.cloud.finder-carries-the-permission`
- Files: `AISettingsView+Tabs.swift` (`CloudAccessSection`), an Inspector project section and the Project menu, `ModelFinderView.swift`, `ModelFinderStore.swift`, `RecipeSetupStore.swift` (`allowCloud(allowed:)`)
- Tests: fichero/Tests/Unit/general/Views/Settings/CloudAccessSectionTests.swift, fichero/Tests/Unit/general/Views/ProjectCloudSwitchTests.swift, fichero/Tests/Unit/general/Models/ModelFinderStoreTests.swift
- Size: M

### Stage 3 — A refusal is an alert with a way through

#### Step 3.1 — One typed refusal, the one-run overrides, the stream event
- Issues: #6349, #6350, #6028
- Behaviours: `ai.cloud.one-typed-refusal`, `ai.cloud.hand-run-refused-before-it-starts`, `ai.cloud.one-run-overrides`
- Files: `llm/spend.py`, `llm/__init__.py` (`EgressRefusedError`), `execution/runner.py` (`_typed_failure`), `api/routes/workflow_execution/core.py`, `recipes/start.py`, `recipes/cloud_cap.py`, the run row store, the regen
- Tests: fichero-server/tests/unit/llm/test_cloud_refusal_shape_6349.py, fichero-server/tests/unit/api/test_execute_refusal_is_typed_6349.py, fichero-server/tests/unit/workflows/test_paused_at_cap_event_6349.py, fichero-server/tests/unit/llm/test_one_run_overrides_6349.py
- Size: L (split the overrides out as 3.1b if the batch passes ~25 files)

#### Step 3.2 — The alert on the hand-run paths
- Issues: #6349, #6028, #6022
- Behaviours: `ai.cloud.alert-on-hand-run-paths`
- Files: a new `Views/Shell/CloudRefusalAlert.swift`, `ContentView+WorkflowActions.swift` (`failWorkflowStart`, the stream handler), the workflow bar's run, `LibraryView+ContextMenu.swift`, `CloudCapFixTests` helpers
- Tests: fichero/Tests/Unit/general/Views/CloudRefusalAlertTests.swift, fichero/Tests/Unit/general/Models/CloudCapFixTests.swift
- Size: M

#### Step 3.3 — The CLI and MCP say it and offer the route
- Issues: #6350
- Behaviours: `ai.cloud.cli-refuses-in-words`, `ai.cloud.mcp-refuses-in-words`
- Files: `fichero-cli/src/fichero_cli/__main__.py` (`workflow_run`, the recipe start command), `fichero-cli/src/fichero_cli/client.py`, `fichero-mcp/src/fichero_mcp/server.py`, the regen outputs
- Tests: fichero-cli/tests/test_cli_cloud_refusal_6350.py, fichero-server/tests/unit/mcp/test_mcp_cloud_refusal_6350.py
- Size: S

### Stage 4 — The plan knows before Start

#### Step 4.1 — Dead key, capability, missing row
- Issues: #6097, #6098, #6099, #6031
- Behaviours: `ai.cloud.plan-knows-a-dead-key`, `ai.cloud.plan-checks-the-capability`, `ai.cloud.no-model-names-the-missing-row`
- Files: `recipes/start.py`, `llm/retry.py` (a read-only `dead_marks()`), `recipes/run_view.py`
- Tests: fichero-server/tests/unit/recipes/test_plan_knows_dead_key_6097.py, fichero-server/tests/unit/recipes/test_plan_checks_capability_6098.py, fichero-server/tests/unit/recipes/test_no_model_names_the_row_6099.py
- Size: S

## Decisions I made (overrule any in one line)

1. **App cap = default, not a ceiling.** The owner said a project's own cap overrides the app's, so the app caps fill
   in for a project with no answer and the hold judges one project ledger as today. Alternative if the owner wants a
   wallet guard across projects: an app ledger booked beside the project's and the lower of the two refusing; one more
   file in Step 1.1, and the refusal's `scope` already says which.
2. **Defaults:** monthly US$10 (today's constant, now editable); daily none. Empty = no cap; 0 = a cap of zero (nothing
   sent); below 0 refused, as `answers.normalise` does now.
3. **Daily and monthly both hold; the lower remainder refuses first**, named. Day and month are UTC calendar units as
   the ledger is today (the owner may prefer the Mac's local day; one line in `_month`'s neighbour).
4. **Per-project override of the images switch goes both ways.** This relaxes `source.onboard.places-cap-projects`
   for the cloud place only; the other places (another Mac, Hugging Face, ACENET) keep the app cap. If the owner wants
   "Settings off" to stay a guarantee, drop the "project yes over app no" half and Step 2.1 shrinks to the action's
   `allowed` parameter.
5. **"Allow once" and "past the cap once" persist on the run row only**, shown in Activity, never in a setting; a
   second run meets the rule again. Spend past the cap is still booked, so the next refusal counts it.
6. **"Raise the cap" raises the cap the refusal names** (project monthly, project daily, app monthly, app daily, or the
   run cap), to the figure the engine serves (`needed_*`, to the cent, no margin), through the existing audited actions.
7. **The refusal before a hand run starts is only for images** (validation already sees the model); a cap is judged
   at the first cloud call and the run pauses, because a hand run has no plan estimate today. A pre-run estimate for
   hand runs is a later line, not this release.
8. **CLI exit code 3** for a cloud refusal, distinct from 1 (any error), so a script can tell a refusal from a failure.
9. **Settings control ids** `settings.ai.cloudAllowed` (exists) and `settings.ai.cloudCaps` (new) are what
   `open-settings` deep-links to.
10. **The app caps are audited, not on the undo stack, same as places** (manager ruling 2026-11-04, delegated by the owner):
    `app.set_cloud_cap` writes its audit row in the account chain and a person undoes it by setting the cap back to the
    row's `from` figure, as `PUT /api/recipes/places` does. Undo for app-chain audits is a later line, not this release.
