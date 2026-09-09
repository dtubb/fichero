# Workflow Node Config — Design Spec

> Design-led spec (Testing Constitution, #4619 wave 1). The design lead owns this
> intent; tests enforce it; code makes the tests pass. One line per behavior; each
> maps to a pinning test cited by name in the test's docstring.
> Status: APPROVED — creative director ratified; shipped.
>
> Tags: **[OK]** behaves this way today · **[BROKEN]** regression, code contradicts
> the line · **[GAP]** intended behavior never built. Untagged = design intent
> whose current state is not yet pinned either way.

## Intent (the design)

The node popover is the ONE place a step is configured. Opening it shows every
field the tool actually honours, in the state the run will use — the prompt the
model will receive, the provider/model that will answer, and the tool's own knobs.
Nothing is hidden that the run reads; nothing is shown that the run ignores. The
provider/model chooser is the same instrument everywhere (popover, AI Settings,
workflow bar): same list, same labels, same rules. Looking at a node never changes
it; editing it always survives close → reopen → save → reload.

Surfaces: `NodePopover` (+`+Comparison`), `NodeProviderModelSelector` → shared
`ModelPicker`, `PromptPreviewPanel`, the per-tool `NodeConfigs/*`, and the canvas
representations (`WorkflowNodeView` subtitle, `WorkflowNodeCard`, `WorkflowNodeRow`).

## Behaviors (each → one pinning test)

### A. Fields present + editable, per node type

Common chrome (every tool)
- `nodeconfig.fields.label.editable` — [OK] the Label field shows `label ?? tool` and edits write `node.label`.
- `nodeconfig.fields.enabled.toggle` — [OK] the header switch toggles `node.enabled`; a disabled node renders at 50% on the canvas.
- `nodeconfig.fields.tool-name.advanced` — [OK] the Advanced disclosure names the tool id; input mappings appear there only behind the advanced-views flag.
- `nodeconfig.fields.schema-driven.fallback` — [OK] a tool without a custom config view renders every `configSchema` field (string/enum/int/number/array/bool) via `DynamicConfigView`; unknown types say so in red rather than vanishing.
- `nodeconfig.fields.only-honoured-keys` — every field shown maps to a key the server reads for that tool (no dead knobs); every key the server honours for a user-facing option is shown. (Audit line — see Findings F5/F16.)

Transcribe (`transcribe`)
- `nodeconfig.fields.transcribe.language` — [OK] Language/Locale picker; legacy codes (`es`, `es_mx`) normalise to canonical (`es-ES`, `es-MX`); `auto` allowed. (Pinned: `TranscribeNodeConfigTests`.)
- `nodeconfig.fields.transcribe.image-size.llm-only` — Max Image Size appears whenever the run will go through an LLM, hidden when Apple Vision / Kraken will read the page.
- `nodeconfig.fields.transcribe.prompt.llm-only` — **[BROKEN]** the Prompt editor appears whenever the run will go through an LLM — including `vision_mode = "auto"` (the server default for new nodes) and `$vision_*` alias selections. Today it is gated on the literal `vision_mode == "llm"`, so new nodes and alias-configured nodes show no prompt at all. (F2)
- `nodeconfig.fields.transcribe.kraken-model` — [GAP] when the engine offers `kraken` mode, the `kraken_model` choice the server schema declares is offered; today the custom view omits it.

Describe (`describe`)
- `nodeconfig.fields.describe.detail-level` — [OK] segmented Brief/Detailed/Comprehensive → `detail_level`.
- `nodeconfig.fields.describe.focus` — [OK] optional Focus text → `focus`; clearing removes the key.
- `nodeconfig.fields.describe.thinking-mode` — [OK] Thinking Mode picker; `off` removes `thinking_mode`.
- `nodeconfig.fields.describe.prompt` — [OK-shape / BROKEN-content] Prompt editor always shown (LLM-only tool); content rules in section B.

Summarize File / Folder / Collection
- `nodeconfig.fields.summarize.style` — [OK] segmented style → `style` (file/folder: brief/detailed/bullets; collection: executive/detailed/narrative).
- `nodeconfig.fields.summarize.max-length` — [OK] slider → `max_length` with per-tool ranges (50–1000 / 100–2000 / 200–3000).
- `nodeconfig.fields.summarize.thinking-mode` — [OK] Thinking Mode picker on all three.
- `nodeconfig.fields.summarize-folder.include-themes` — [OK] toggle → `include_themes`.
- `nodeconfig.fields.summarize-collection.include-statistics` — [OK] toggle → `include_statistics`.
- `nodeconfig.fields.summarize-file.prompt` — **[BROKEN]** the prompt editor shows the tool's default (ghosted) so the user can see what they are overriding; today it is an empty box labelled "Custom Prompt (optional)". (F5)
- `nodeconfig.fields.summarize-folder+collection.prompt` — **[GAP]** these two have no prompt surface at all, and the server builds their prompt from an f-string with no override and no `prompt_builder`, so even the Prompt Preview shows an empty string. Design decision needed: make the prompt editable end-to-end (server `prompt_builder` + `inputs.get("prompt")`), or state in the popover that this tool's prompt is fixed. Never an empty preview. (F5)

Extract Entities (`extract_entities`)
- `nodeconfig.fields.entities.targets` — [OK] built-in targets plus library-registered custom types as checkboxes → `entity_types` (sorted array).
- `nodeconfig.fields.entities.add-custom` — [OK] adding a target registers it in the library, checks it, clears the field; failure is shown inline, not swallowed.
- `nodeconfig.fields.entities.remove-custom` — [OK] the chip disappears only after the backend confirms; built-ins have no remove button.
- `nodeconfig.fields.entities.include-context` — [OK] toggle → `include_context`.
- `nodeconfig.fields.entities.prompt` — **[GAP]** the server honours a `prompt` override for this tool, but the popover offers no editor; the prompt is invisible except via the collapsed preview. (F5)

Sources: Files / Collection / Search
- `nodeconfig.fields.files.selection-default` — [OK] with no pinned files the node states it uses the library selection at run time, with a "Pin specific files…" affordance.
- `nodeconfig.fields.files.pin-picker` — [OK] the picker stages a selection (Cancel discards, Add commits); rows can be removed; drops of `doc:<id>` are accepted only for files.
- `nodeconfig.fields.collection.folder-picker` — [OK] indented folder tree, Inbox first; a folder that disappears clears the selection rather than pointing at a ghost.
- `nodeconfig.fields.search.saved-search` — [OK] saved-search picker → `search_id` (+ `query` copied for display); empty state offers Reload.

Zoom (`zoom`)
- `nodeconfig.fields.zoom.live-preview` — [OK] tile-grid preview mirrors the server's strip math and updates as rows/overlap/scale change; region mode explains itself instead of drawing strips. (Pinned: `ZoomTileGridTests`.)

### B. Prompt text — surfaced and editable

- `nodeconfig.prompt.shows-effective-prompt` — **[BROKEN]** the editor's initial text is the prompt the run will actually send for the CURRENT config (server `POST /tools/{tool}/prompt`, which applies the tool's `prompt_builder` to language/style/detail…), not the frozen registry default. Today `NodePopover.backendPrompt` is declared and threaded into Transcribe/Describe but never fetched, so only `toolInfo.defaultPrompt` is ever shown. (F1)
- `nodeconfig.prompt.visible-before-registry` — **[BROKEN]** if the tool registry has not loaded when the popover opens, the prompt appears once it does; today the editor initialises once in `onAppear` and never repopulates. (F1)
- `nodeconfig.prompt.default-is-ghost-not-text` — **[BROKEN]** when the node has no `prompt` override, the default is rendered as a placeholder (ghosted, as `DynamicConfigView.promptEditor` already does) and `config.prompt` stays ABSENT. Today Transcribe/Describe copy the default into the editor as real text, which the `onChange` then writes to `config["prompt"]` — so merely opening the popover pins a stale default as a user override (autosaved 300 ms later) and detaches the prompt from later Language/Detail edits. On the server a set `prompt` is also treated as a custom prompt, which changes transcribe's page-content behaviour. (F4)
- `nodeconfig.prompt.edit-writes-override` — [OK] typing writes `config.prompt`; clearing to empty removes the key ("Reset to default").
- `nodeconfig.prompt.reset-affordance` — one explicit "Reset to default" action when an override exists (present in `DynamicConfigView`, absent in the hand-rolled editors).
- `nodeconfig.prompt.one-editor-component` — all prompt editing goes through one component (the `DynamicConfigView.promptEditor` pattern); Transcribe/Describe/Summarize-file stop hand-rolling divergent editors.
- `nodeconfig.prompt.preview.assembled` — [OK] the Prompt Preview disclosure fetches the assembled prompt (config included, arrays and nested values converted recursively), re-fetches 300 ms after any config change while open, and offers Copy.
- `nodeconfig.prompt.preview.shown-for-llm-tools` — **[BROKEN]** the preview shows for every LLM tool regardless of provider choice. Today it is gated on `node.usesLLM`, which the selector flips to `false` when "Default" is chosen — so a Default-provider summarize node loses its preview. (F6)
- `nodeconfig.prompt.preview.never-empty` — **[BROKEN]** a tool with no prompt states "This tool has no prompt" instead of rendering an empty box (folder/collection summaries today). (F5)

### C. Provider / model selection — cross-surface invariant with Settings

- `nodeconfig.model.one-picker` — [OK] popover, AI Settings and workflow bar all render `ModelPicker`; per-surface differences are flags, not forks.
- `nodeconfig.model.same-list-as-settings` — **[BROKEN]** the popover lists exactly the models Settings lists for a provider: the user-configured models (`listProviderModels(providerId:)`). Today the popover loads the full catalog (`listAvailableModels(providerType:)`), offering models Settings deliberately withholds because the provider's API does not serve them — the very runtime-404 class Settings was fixed to prevent. (F7)
- `nodeconfig.model.same-labels-as-settings` — **[BROKEN]** a model is labelled the same everywhere (Settings shows `fullName`, the popover shows the raw id). (F7)
- `nodeconfig.model.default-entry` — [OK] "Default" (tag `""`) clears `providerName`/`modelName` and the model picker hides; the runtime resolves the tier default.
- `nodeconfig.model.aliases` — [OK] `$small`/`$large` always; `$vision_small/medium/large` only for vision tools; choosing one persists the alias as `providerName`, clears `modelName`, hides the model picker. (Pinned: `NodeProviderModelSelectorVisionModeTests`.)
- `nodeconfig.model.apple-vision-entry` — [OK] tools that support on-device OCR list "Apple Vision (On-Device)"; choosing it sets `vision_mode = "apple"` and clears provider/model; the catalog's Apple Intelligence row is hidden to avoid a duplicate Apple choice.
- `nodeconfig.model.vision-only-filter` — [OK] a vision tool lists only vision-capable providers, shows vision aliases, and says "No vision-capable providers available" when none.
- `nodeconfig.model.vision-requirement-from-server` — **[GAP]** which tools need vision / support Apple Vision comes from the served tool definition (server already knows `supports_apple_vision`, `requires_generative_model`, category); today the popover keeps two hard-coded sets (`visionTools`, `appleVisionTools`) that drift from the registry — the pattern #4477 forbade for port conversions. (F8)
- `nodeconfig.model.uses-llm-is-tool-fact` — **[BROKEN]** `node.usesLLM` describes the TOOL and never changes with the provider choice. Today choosing "Default" on a non-vision LLM tool sets it `false`, after which `shouldShowProviderSection` is false on reopen: the provider section, Compare Models button and Prompt Preview all vanish and the user can never pick a provider for that node again. (F6)
- `nodeconfig.model.auto-mode-representation` — **[BROKEN]** a transcribe node whose `vision_mode` is `"auto"` (server default for new nodes) shows "Default" in the picker AND its LLM-only fields (prompt, image size), since auto resolves to LLM unless the resolved provider is Apple. Today it shows Default with the LLM fields hidden. (F2/F3)
- `nodeconfig.model.provider-switch-picks-first-model` — [OK] selecting an LLM provider auto-selects its first model so the node is never provider-without-model.
- `nodeconfig.model.stale-provider-visible` — **[BROKEN]** if the node's saved provider is no longer among the loaded providers (disabled/removed), the picker shows the stale value with a warning; today it silently shows "Default" while `providerName` still carries the stale id the run will use. (F11)
- `nodeconfig.model.compare-apply-updates-picker` — **[BROKEN]** applying a Compare Models result updates the visible provider/model selection immediately; today only the node fields change and the picker is stale until reopen. (F13)
- `nodeconfig.model.reload` — [OK] the header refresh re-loads providers; loading shows a spinner; an empty list says "No providers configured".

### D. Config round-trip (edit → persist → reopen)

- `nodeconfig.roundtrip.open-is-read-only` — **[BROKEN]** opening and closing a popover without touching anything leaves `node` byte-identical (no autosave fires). Today Transcribe/Describe write the default prompt (F4) and Transcribe normalises + rewrites `language` on open; Search rewrites `search_id`/`query` on open. Normalisation of legacy values is allowed only as an explicit, visible migration — not a side effect of looking.
- `nodeconfig.roundtrip.every-field` — each field in section A reads its saved value on open and shows it (language, image size, prompt override, style, max length, thinking mode, toggles, entity types, file ids, collection id, search id, provider, model). (One parameterised test per node type.)
- `nodeconfig.roundtrip.legacy-values` — [OK] legacy shapes still load: `doc:`-prefixed file ids are stripped; `provider_name` inside `config` is read when the typed field is empty; legacy language codes normalise.
- `nodeconfig.roundtrip.autosave` — [OK] any real edit autosaves after a 300 ms debounce; autosave never fires for a locked system preset.
- `nodeconfig.roundtrip.duplicate-copies-config` — [OK] Duplicate copies config, provider, model, `usesLLM`, output schema and mappings, and opens the copy for editing.
- `nodeconfig.roundtrip.remove-means-absent` — [OK] "off"/empty choices REMOVE the key (`thinking_mode`, `prompt`, `focus`) rather than writing an empty value, so the server default applies.
- `nodeconfig.roundtrip.alias-survives` — [OK] a node saved with an alias provider reopens with the alias selected and no model picker.

### E. Canvas representations agree with the config

- `nodeconfig.canvas.subtitle-reflects-provider` — [BROKEN-partial] the node subtitle states what will answer: "Apple Vision", the model name, or the alias (`$vision_large`). Today an alias node shows no subtitle at all (`modelName` is nil for aliases).
- `nodeconfig.canvas.icon-color-from-registry` — [BROKEN-partial] icon/colour come from the served registry on every canvas representation; `WorkflowNodeCard`/`WorkflowNodeRow` still carry their own hard-coded maps (the canvas node already reads the registry).
- `nodeconfig.canvas.list-row-shows-config-summary` — [GAP] the list row shows the same provider/model summary as the canvas subtitle instead of the (x, y) position badge.

## First wave to pin (proposed — awaiting Daniel)

1. `nodeconfig.model.uses-llm-is-tool-fact` + `nodeconfig.prompt.preview.shown-for-llm-tools` (F6) — the trap that hides the provider section for good.
2. `nodeconfig.prompt.default-is-ghost-not-text` + `nodeconfig.roundtrip.open-is-read-only` (F4) — looking must not write.
3. `nodeconfig.prompt.shows-effective-prompt` + `visible-before-registry` (F1) — the live "no prompt shown" complaint.
4. `nodeconfig.fields.transcribe.prompt.llm-only` + `nodeconfig.model.auto-mode-representation` (F2/F3).
5. `nodeconfig.model.same-list-as-settings` (F7) — cross-surface invariant.

Everything else is the larger design, pinned in later waves.

## Findings (code evidence)

Paths are relative to `fichero/fichero/` unless noted; server paths under
`fichero-server/src/fichero_server/`.

- **F1 — backend prompt never fetched.** `Views/Workflow/Nodes/NodePopover.swift:32-33` declare `backendPrompt`/`isLoadingPrompt`; they are passed at `:117` and `:123` but no code assigns them (grep `backendPrompt =` → 0 hits). `WorkflowService.getToolPrompt` (`Services/WorkflowService.swift:39`) exists and is used only by `PromptPreviewPanel`. Result: `TranscribeNodeConfig.currentDefaultPrompt` (`NodeConfigs/TranscribeNodeConfig.swift:80-87`) and `DescribeNodeConfig` (`:15-22`) only ever see the static `toolInfo.defaultPrompt`; the `onChange(of: backendPrompt)` repopulation (`Transcribe :188-196`, `Describe :104-112`) is dead code. If `toolInfo` is nil at `onAppear`, the editor stays empty.
- **F2 — LLM-only gate uses the literal `"llm"`.** `TranscribeNodeConfig.swift:89-97` (`isLLMMode`) and the `if isLLMMode` gates at `:126`/`:155`. Server default for new transcribe nodes is `vision_mode: "auto"` (`workflows/tools/transcribe.py:273-274`, applied through `Models/WorkflowTypes.swift:235`), and `auto` resolves to `llm` unless the provider is Apple (`workflows/tools/vision_base.py:3502-3504`). Alias selection removes `vision_mode` (`Nodes/NodeProviderModelSelector.swift:83`). Both states hide Prompt and Max Image Size.
- **F3 — popover has no representation for `auto`.** `NodePopover.swift:154-168` selects Apple Vision only when `vision_mode == "apple"` or the key is absent; `"auto"` falls through to "Default".
- **F4 — opening writes the default prompt.** `TranscribeNodeConfig.swift:210-215` sets `promptText = defaultPrompt` in `onAppear`; `.onChange(of: promptText)` at `:168-177` writes `config["prompt"]`. Same in `DescribeNodeConfig.swift:126-131` + `:85-94`. Autosave fires 300 ms later (`Views/Workflow/Editor/WorkflowEditor.swift:333-338`). Server treats any `prompt` as a custom prompt: `transcribe.py:339` bypasses the language-aware builder and `:373` changes page-content promotion. Language rewrite-on-open: `TranscribeNodeConfig.swift:200-203` + `:113-118`. Contrast the correct ghost pattern in `Nodes/DynamicConfigView+FieldRendering.swift:119-161`.
- **F5 — prompt missing or fixed per tool.** `SummarizeFileNodeConfig.swift:54-76` empty editor, no default. `SummarizeFolderNodeConfig.swift`, `SummarizeCollectionNodeConfig.swift`, `ExtractEntitiesNodeConfig.swift` have no prompt field. Server: `entities.py:260` honours `prompt`; `summarize.py:145` honours it for summarize_file only; `summarize.py:287` and `:452` are f-strings with no override, and only summarize_file registers `default_prompt`/`prompt_builder` (`summarize.py:123-124`). `ToolResponse.default_prompt` defaults to `""` (`api/routes/workflow/workflows.py:109`), so the preview renders an empty string.
- **F6 — provider choice rewrites a tool fact.** `NodeProviderModelSelector.swift:62-69` sets `node.usesLLM = false` on "Default". `NodePopover.swift:313-324` gates the whole provider section on `node.usesLLM` for non-vision tools; `PromptPreviewPanel.swift:22` gates the preview on it; `NodePopover.swift:265` gates Compare Models. Registry sets `uses_llm=True` for all these tools (`summarize.py:117/250/406`, `entities.py:190`, `describe.py:107`).
- **F7 — model list source differs from Settings.** Popover: `Nodes/NodePopover+Comparison.swift:15-37` → `listProviders()` + `listAvailableModels(providerType:)` (catalog), labels = raw id (`:23-25`), `available: true` hard-coded, keyed by `provider.id`. Settings: `Views/Settings/AI/AISettingsView+Helpers.swift:191-193` and `:231-233` → `listProviderModels(providerId:)` (user-configured only; rationale at `:217-221`), labels = `fullName` (`:61`), keyed by `providerType` (`:55`).
- **F8 — client-side vision/Apple sets.** `NodePopover.swift:292-297` (`visionTools`) and `:305` (`appleVisionTools`). Server knows `supports_apple_vision` (`transcribe.py:44`, `describe.py:35`) and `requires_generative_model` but `ToolResponse` (`workflows.py:95-127`) serves neither a vision requirement nor Apple-Vision support.
- **F9 — canvas duplicates.** `Nodes/WorkflowNodeCard.swift:48-74` and `Nodes/WorkflowNodeRow.swift:96-122` hard-code icon/colour maps; `Nodes/WorkflowNodeView.swift:162-172` subtitle shows nothing for alias nodes.
- **F11 — stale provider silently shown as Default.** `NodePopover+Comparison.swift:43-51` only sets the selection when the saved id is an alias or is in the loaded list.
- **F13 — Compare apply bypasses the picker state.** `NodePopover+Comparison.swift:71-75` writes `node.providerName/modelName` without touching `selectedProviderId/selectedModelId`.
- **F16 — schema/UI drift.** Server `transcribe` config_schema declares `language` and `kraken_model` (`transcribe.py:53`, `:84`) but no `prompt`/`max_image_dimension`; the custom view shows prompt + image size and omits `kraken_model`. The `only-honoured-keys` line is the audit for this class.

Existing coverage (kept, all pass today): `fichero/Tests/Unit/general/Views/Workflow/TranscribeNodeConfigTests.swift` (locale table), `NodeProviderModelSelectorVisionModeTests.swift` (alias recognition, legacy provider read, vision_mode cleared on Default/alias — a source-text test), `ZoomTileGridTests.swift`. Nothing pins prompt visibility, prompt round-trip, `usesLLM` stability, or the Settings/popover model-list invariant.
