# Everything Daniel said this evening (2026-08-29) — status ledger

Legend: ✅ done+committed tonight · 🔨 worker dispatched · 📋 queued (mine, next round) · 💬 design brief awaiting Daniel

## Workflow bar & chain
- ✅ Verbs + chain centred; empty state = centred "Nothing selected"
- ✅ Verb click ALWAYS opens popover; cards in 1–3 columns; FULL descriptions
- ✅ ⓘ on each card opens the node editor
- ✅ "Show steps & prompts" covers uses_llm=false tools with prompts (detect_regions VLM)
- ✅ Chain reads as a SENTENCE: "With [3 images], use [model] to [step], then…"
- ✅ Model change on a failed chain resets that step + later ones to pending
- ✅ Target chip names its scope ("4_Hoja_531_Verso.JPG" / "3 images") — built pending queue
- ✅ Bar toggle = sidebar's branch glyph; Run Workflow button + suggestion glyphs removed
- 💬 Suggestions return later as a recommended row INSIDE the bar

## Toolbar & chrome
- ✅ Pane toggles are Buttons: words flip Show/Hide, no blue fill
- ✅ Server = grey rack (green bolt collision killed); Server/Activity get Labels
- ✅ All lozenges equally circular (Server, Activity, model chip)
- ✅ Model chip = provider logo (bundled assets; Apple ; monogram fallback); OpenRouter corner badge when routed
- ✅ Picker popover: full height on first open, family logos, vision eye, $/M in+out pricing per row
- ✅ Six panes fit on a 14" (canvas 360→330, chat 280→250)
- 📋 Native Mail-style search field (ours is welded to the sidebar lozenge)
- 📋 Toolbar Icon-and-Text mode driving label visibility across the UX (incl. workflow bar labels)
- 📋 Pane-toggle buttons grow Xcode-style submenus (Tab / pane right / pane below)
- 📋 Xcode-style saveable window WORKSPACES + add-window button
- 📋 Chat pane lacks the split-left/right options its siblings have

## Reader
- ✅ One WebKit path: regions fold into /view/document; ?representation= switcher (Content/Transcript/Translate); 0/1 = all, multi = filtered; multi-select in reader
- ✅ Breadcrumbs say "3 items" on multi-selection (Reader + Preview)
- ✅ Workflow node → honest "no transcript possible" + Open in Editor
- ✅ Proxy icon = the page's own THUMBNAIL at icon size (giant-blue-blob CSS leak fixed)
- 📋 Lens menu collapses to icon-only in narrow panes — discoverability pass
- 📋 Cross-parent mixed selections still native (needs multi-root route)
- 📋 Proxy icon drag-out

## Preview (design brief: agent-work/design/preview-toolbars-and-regions.md 💬)
- 💬 Two Golden-Gate lozenge toolbars (top=mode tools, bottom=nav/find/meta); kill the "…" menus
- 💬 Annotation/highlight/line tools arrive at TOP like Edit's do
- 💬 Renditions + page arrows placement (top vs bottom — his call)
- 🔨 Regions in preview: select (rubber-band too), move by drag, delete, add (vision guesses text), combine N selected; inspector-selected regions render in preview in distinct colors
- 🔨 Rubber-band selection → run a workflow on just that crop
- 📋 Top-right region/rendition lens icons in Preview's head (like the reader's)
- 📋 BUG: page swipe left/right broken; up/down rendition swipe broken (scroll-bar gesture conflict)
- 📋 BUG: Image editor — clicking the verb enters edit but there's no EXIT; the verb should flip the pane-header view selector to Edit

## Live-test findings (22:30+)
- ✅ Lens menu's stray line under each group header (inline-Picker chrome) — fixed
- ✅ Bottom bar's metadata control vanished at narrow widths — submenu coat added
- 📋 Icon view: no filter option to hide items WITHOUT images (text-only tiles); the fuller filter cluster missing in icon view
- 📋 PERF P1: 9.6s stall — Observation tracking-list growth in one body eval (near share sheet); 2.2s NSButtonCell; sidebar unifiedRows 835ms; IconCellIdentity copy 903ms; AttributedString iteration 1.8s. Needs an Instruments lane on a Release-ish build.
- 📋 CoreSpotlight donations failing continuously (CSIndex -1000 / service invalidated) — indexing may be dead app-wide

## Selection-as-scope
- 🔨 The SELECTION is the run target everywhere: 5 regions picked in the inspector = the scope (bar + target chip update); a transcription-review artifact selected in the sidebar = run on just that

## Attribute browser
- 🔨 Combine N selected regions (same verbs as preview's region combine)

## iOS
- ✅ openSettings compile break fixed; app runs on iPhone 12 Mini (cert trusted); pairing restores; connects once the Mac app is up
- 📋 "No selection → back → stalls" repro with console attached (session live, awaiting repro)

## Infrastructure
- ✅ Xcode 27 migration committed; SDK `Document` collision pinned; MCP bridge fixed (needs DEVELOPER_DIR)
- ✅ Swift-6 worker: 14/14 diagnostics; WebContentCanvas + DocumentCanvas follow-ups
- ✅ Manual worker: 180 generated reference pages + staleness guardrail (6 questions await Daniel)
- 📋 Remaining iOS-target Swift-6 warnings (WebContentCanvas batch was macOS-visible; sweep iOS scheme)
- 📋 Release-merge lane: site publish + linking, main merge, gate + push of ~150 commits
