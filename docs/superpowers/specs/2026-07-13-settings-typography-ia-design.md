# Settings IA v2 + Reader/Editor Typography — Design (2026-07-13)

Status: **APPROVED (Daniel 2026-07-13)** — decisions baked in (see "Resolved
decisions" below); implementation may proceed, Lane A first. Milestone: *Settings
IA v2 + Reader/Editor Typography* (#3678–#3684). Follows the inspector/reader/navigation IA design pattern
(`2026-07-11-inspector-ia-design.md`, `2026-07-11-reader-ia-design.md`,
`2026-07-12-navigation-system-design.md`).

Two independent jobs share this milestone because they meet in the same place —
a Settings pane per view:

1. **Settings IA v2** — replace the top-tab Settings window with the standard
   macOS System-Settings **sidebar** (source-list → detail), and add **per-view**
   sections (Library / Reader / Preview / Inspector) alongside the #3396
   Engine / Library-Access groups.
2. **Reader/Editor typography** — a **semantic-default + user-override** font
   size for the Reader and (separately) the Editor, Reader theme/CSS consistency
   with the native app, and code-based paragraph wrapping with no orphan lines.

---

## 0. What already exists (audit, grounded in code)

Not a green field. Each piece extends existing mechanisms.

### 0.1 Settings container — `Views/Settings/SettingsView.swift`

- `SettingsView` is a **`TabView` with `.tabItem` top tabs**, fixed
  `.frame(width: 680, height: 520)`. Tabs: AI, MCP, Integrations, General,
  **Engine**, **Library Access**, About (iOS-only), History, Backups.
- Selection is `appState.selectedSettingsTab: SettingsTab` (a `Binding`).
- #3396 already introduced the reusable **`SettingsGroupContainer<Section>`**:
  a segmented sub-picker over available sub-sections, then the selected
  section's *unchanged* settings view. `EngineGroupSettingsView` folds
  Engine+Backend; `SharingSettingsView` folds People/Devices/Capture.
  Availability is `FeatureManager`-gated and platform-gated (`#if canImport(AppKit)`).
- Every pane (`AISettingsView`, `EngineSettingsView`, `UsersSettingsView`, …)
  is an independent `View` that reads its own `@Observable`/`@AppStorage` state.
- **No per-VIEW settings exist today** (no Library/Reader/Preview/Inspector pane).

### 0.2 View-config store — `App/ViewSettings.swift`

- `ViewSettings` is an **app-wide `@Observable`** (`@State` in `FicheroApp` /
  `FicheroApp_iOS`, read via `@Environment(ViewSettings.self)`), holding
  `libraryLayout` and `previewMode` (+ the `PreviewLayout` Mail-vocabulary
  facade). Per-window state (sidebar mode, inspector visibility) lives in
  `@SceneStorage`, deliberately NOT here.
- `ViewSettings` is **in-memory only** — it is not currently persisted.
- The app uses `@AppStorage` (~30 keys, e.g. `FeatureManager`) for persisted
  scalar prefs, namespaced `fichero.<area>.<key>`.

### 0.3 Reader typography + theme — engine template + Swift injection

- **Template**: `fichero-engine/src/fichero/api/templates/document_view.html`
  (the only `.html` template). Uses CSS custom properties — `--bg --panel
  --text --muted --line --accent --font-system --font-mono` — with a
  `@media (prefers-color-scheme: dark)` block of sensible defaults. **Font
  sizes are hardcoded px** (`14px` body, `line-height: 1.6`, plus `11–14px`
  chrome); `--font-system` is a hardcoded `-apple-system, …` stack.
- **Swift theming**: `DocumentKGPaneRoute.systemThemeCSS()` /
  `themeInjectionScript()` in `Views/Reader/Knowledge/DocumentKGWebPane.swift` inject a
  `<style id="fichero-system-theme">` that overrides the color vars from
  **`NSColor` semantic colors** (`.textBackgroundColor`, `.textColor`,
  `.controlAccentColor`, `.selectedTextBackgroundColor`…), re-run on
  `didFinishNavigation` and on `effectiveAppearance` change.
  - **Gaps**: (a) **colors only** — no font or font-size var is injected;
    (b) **macOS only** — the `#else` (iOS) branch returns `""`, so the Reader is
    **unthemed on iPhone/iPad**; (c) some WebKit content is **inline HTML built
    in Swift** (e.g. `DocumentKGWebPane.swift:67` `body { … background:#f6f6f6;
    color:#222 }`) with **hardcoded** palette that bypasses the vars.
- **Native reader text**: `AnnotatableTextView` (serif, from
  `NSFont.preferredFont(forTextStyle: .body)` at base `pointSize`) is used by
  `Reading/PageContentPane` + `Reading/DocumentTextReader` — these are **Reader**
  surfaces.
- **No `text-wrap`** rule exists anywhere yet.

### 0.4 Editor text surfaces

- `Components/MacPlainTextEditor` exposes a `font:` param defaulting to
  `.preferredFont(forTextStyle: .body)` (NSFont / UIFont) — used by
  ModelComparison + Workflow node configs.
- Inspector-editable text is SwiftUI `TextEditor` with **semantic** fonts
  (`.font(.body)`, `.font(.title3)…`) in `NoteDetailView`, `ArtifactDetailView`,
  the OntologyBrowser sheets, etc.
- **All editor/reader text is already semantic** (`.preferredFont(forTextStyle:)`
  / `.font(.body)`); **zero `.system(size:)`** in the audited text views. This is
  the [[semantic-system-fonts]] rule already holding — the override must *scale
  the semantic base*, never introduce hardcoded sizes.

---

## 1. Settings sidebar architecture (#3679)

**Adopt `NavigationSplitView`** (source list → detail), replacing the `TabView`.
One container adapts to every platform:

- **macOS** (the `Settings` scene): a left **source list** of sections that
  swaps the detail pane — the System-Settings idiom. Grouped with `List` +
  `Section` headers (see §2).
- **iPhone/iPad**: the **same** `NavigationSplitView` collapses to a
  `NavigationStack` list → detail push on compact width — the natural iOS
  Settings pattern the milestone asks for. No separate iOS container needed;
  `.navigationSplitViewStyle(.balanced)` + the automatic compact collapse gives
  list-then-detail for free. (On iOS, where there is no `Settings` scene, host
  `SettingsRootView` in the existing iOS settings presentation.)

**Selection model**: promote `SettingsTab` → a `SettingsSection` enum
(`CaseIterable`, `Identifiable`, `Hashable`) carrying `label` + `systemImage` +
`FeatureManager` availability, bound to `appState.selectedSettingsTab` (kept for
state restoration). The detail `switch`es on the selection to the **existing,
unchanged** pane — this is a *container restructure*, not a rewrite of any pane
([[iterate-never-replace]]). `SettingsGroupContainer` (#3396) still works
verbatim as a detail pane for the Engine / Library-Access groups.

**Not**: a custom sidebar list, a third-party settings framework, or dropping
the #3396 groupings. Reuse `List(selection:)` + `NavigationSplitView`; keep the
segmented sub-picker for the two consolidated groups.

## 2. Per-view settings sections (#3680)

The source list, grouped System-Settings style (`List` + `Section`):

| Group | Sections (source-list rows) | Content |
|---|---|---|
| **Views** | **Library** | `libraryLayout` default, icon size, sort, show-all-no-caps ([[finder-like-ui-principles]]) |
| | **Reader** | Reader **font size** (#3681), **theme** (Match App / System), **paragraph wrapping** (#3684), line spacing |
| | **Preview** | `PreviewLayout` (Side / Bottom / Hidden), loupe defaults |
| | **Inspector** | Editor **font size** (#3682), default Inspector tab, default visibility |
| **Access** | **Engine**, **Library Access** | existing #3396 `SettingsGroupContainer`s, unchanged |
| **System** | AI, MCP, Integrations, General, History, Backups, About | existing panes, unchanged |

Each per-view section is a **new thin `View`** that binds existing/added
`ViewSettings` (app-wide `@Observable`) + `@AppStorage` values — **nothing is
dropped**, existing controls are reused. The four per-view panes are the only
new UI; everything under Access/System is a moved reference to an existing pane.

## 3. Typography model — semantic default + user override (#3681, #3682)

**One formula, two independent scales:**

```
effectivePointSize = preferredFont(forTextStyle: base).pointSize  ×  userScale
```

- `preferredFont(forTextStyle:)` already reflects **Dynamic Type** (iOS) and the
  system size — so the semantic default and Dynamic Type are *inputs to the
  base*, and the user override is a **multiplier** on top. They **compose** by
  construction: bump Dynamic Type → base grows → scaled result grows; the user
  slider is orthogonal.
- **Store two scales**, not absolute sizes, on `ViewSettings`:
  `readerFontScale` and `editorFontScale` (`Double`, default `1.0`, **clamped
  `0.8…2.0`** — Daniel), **persisted** via UserDefaults-backed keys
  `fichero.reader.fontScale` / `fichero.editor.fontScale`. This keeps one
  app-wide source of truth (the [[observable-data-layer]] store) that both the
  Settings controls and the consumers read; storing a *scale* (not px) is what
  honors [[semantic-system-fonts]] — we adjust the semantic base, never hardcode.
- **Control = a font-size STEPPER** (−/+, NSStepper-style), **not** a free
  slider or a point-size field (Daniel). The `Stepper(value:in:step:)` enforces
  the `0.8…2.0` clamp natively (step `0.1`), with a live readout of the resulting
  size. `ViewSettings` also clamps on load, defending against a corrupted key.
- **Reader ≠ Editor** (Daniel): the two scales are separate values, separate
  steppers (Reader View pane vs Inspector pane), separate `@AppStorage` keys,
  separate consumers.

**Consumers:**

- **Reader — WebKit**: compute `readerBasePx = UIFont/NSFont.preferredFont(.body)
  .pointSize × readerFontScale` in Swift, inject as a CSS var
  `--reader-base-size: {px}px` through the **existing** `systemThemeCSS()` /
  `themeInjectionScript()` path (extended in §4). Change the template body/
  paragraph rules from hardcoded `14px` to `font-size: var(--reader-base-size)`
  (chrome sizes derive as `em`). Re-inject on scale change via
  `evaluateJavaScript` — **no reload, no wholesale re-render**
  ([[no-wholesale-list-rerender]], [[every-frame-perfect]]).
- **Reader — native**: `AnnotatableTextView` (Page/DocumentTextReader) scales
  `serifBodyFont` by `readerFontScale` on `base.pointSize`.
- **Editor**: Inspector-editable surfaces (`TextEditor` in NoteDetail/
  ArtifactDetail…, and any `MacPlainTextEditor` used *as an editor*) apply
  `editorFontScale`. For NSFont/UIFont views, scale `preferredFont(.body)
  .pointSize`; for SwiftUI `TextEditor`, a small `ScaledSemanticFont`
  `ViewModifier` maps a `Font.TextStyle` → `preferredFont × scale`.
  *(Implementation audit item: enumerate which text surfaces are "Reader" vs
  "Editor" — the reader/editor split of `AnnotatableTextView` vs Inspector
  `TextEditor` is established above; the long tail is tagged during #3681/#3682.)*

**One shared helper** (`ScaledFont`/`ScaledSemanticFont`) used by both #3681 and
#3682 so the math lives in one place — but two stored scales and two panes.

## 4. Reader theme/CSS consistency (#3683)

Make the WebKit Reader read as *one app*, not a web page, by **feeding the app's
semantic theme into the templates** — extending the mechanism that already
exists (§0.3), not building a new one:

1. **Typography into the vars**: add `--reader-base-size` (§3) and font/weight
   vars to `systemThemeCSS()`; template consumes them.
2. **iOS path**: implement the `#if canImport(UIKit)` branch of
   `systemThemeCSS()` with **`UIColor` semantic colors** (`.systemBackground`,
   `.label`, `.secondaryLabel`, `.separator`, `.tintColor`) + `UITraitCollection`
   for light/dark — closing the "unthemed Reader on iPhone/iPad" gap.
3. **Var-drive all reader HTML**: audit every WebKit surface — the
   `document_view.html` template **and** the Swift-inline HTML fragments
   (`DocumentKGWebPane.swift` inline `body{…}`, `ResearchBrowserPane`) — and
   replace hardcoded hex (`#f6f6f6`, `#222`) with the injected vars.
4. **Re-inject** on load + appearance change (already wired) + on font-scale
   change (§3).

**VISUAL change — verify in both light AND dark** on macOS and iOS (the #3683
acceptance bar; WebKit visual-gate split per [[autonomous-gating-playbook]]).

**Reader theme = the app's semantic light/dark only.** A **Sepia / Paper**
reading theme is explicitly **deferred, out of scope** for this milestone
(Daniel 2026-07-13) — file as a future issue. The template's warm `#f7f4ee`
default becomes a fallback-only value once the semantic vars drive everything;
it does not become a user-selectable theme now.

## 5. Reader paragraph wrapping — no orphans (#3684)

**CSS-first, JS fallback, exposed as a Reader setting.**

- **Default**: `p { text-wrap: pretty; }` on reader paragraphs — prevents short
  last lines / orphans; supported WebKit ≥ Safari 17.4 / macOS 14.4 (in-target
  for the Golden-Gate-only floor, [[golden-gate-only-target-sept-2026]]).
  Headings may use `text-wrap: balance`.
- **Fallback** (older WebKit / when disabled-pretty): feature-detect
  `CSS.supports('text-wrap','pretty')`; if absent, a one-pass JS **"widont"** —
  join the last two words of each `<p>` with `&nbsp;` so a lone last word can't
  strand. Runs once after render; reader paragraphs only; cheap.
- **Setting** (Reader View pane): *Paragraph wrapping* — **System** (`normal`) /
  **Tidy** (`pretty` + widont fallback, default) / **Balanced** (`balance`),
  driven by a `--reader-text-wrap` var + the fallback toggle.

*ponytail: the default is the one-line CSS rule; the JS widont only runs when the
platform can't do `text-wrap: pretty`. No manual per-paragraph editing.*

## 6. Issue reconciliation (#3678–#3684)

| # | Scope | Lane / files (disjoint) | Depends on |
|---|---|---|---|
| **3678** | **This doc** (audit + design) | docs only | — |
| **3679** | Settings → `NavigationSplitView` sidebar | `SettingsView.swift` + new `SettingsSection` | — |
| **3680** | Per-view sections (Library/Reader/Preview/Inspector) | new per-view panes + `ViewSettings` fields | 3679 |
| **3681** | Reader font scale | `ViewSettings` + `DocumentKGWebPane` + template + `AnnotatableTextView` | 3683 (shared injection) |
| **3682** | Editor font scale (separate) | `ViewSettings` + Inspector text surfaces + `ScaledFont` | 3680 (pane) |
| **3683** | Reader theme/CSS consistency + iOS UIColor path | `DocumentKGWebPane` + template + inline HTML | — |
| **3684** | Paragraph wrapping (no orphans) | template CSS + widont JS + Reader setting | 3683 |

**Build order (two parallel, disjoint-file lanes — [[lanes-must-own-disjoint-files]]):**

- **Lane A — Settings container** (`SettingsView.swift`, `ViewSettings.swift`,
  new per-view panes): #3679 → #3680. Adds the empty per-view panes + the
  `readerFontScale`/`editorFontScale` fields the typography slices bind to.
- **Lane B — Reader/typography** (`DocumentKGWebPane.swift`, `document_view.html`,
  `AnnotatableTextView.swift`): **#3683 first** (extend `systemThemeCSS()` for
  fonts + iOS + var-drive all HTML — the injection foundation), then **#3681**
  (reader scale rides that injection), then **#3684** (wrapping CSS/JS).
- **#3682** (editor scale) folds into Lane A's Inspector pane once the
  `ScaledFont` helper from #3681 exists.

Lanes A and B touch disjoint files (Settings/ViewSettings vs Reader-web/template)
and can run concurrently; the only shared symbol is the two new `ViewSettings`
scale properties (added in Lane A, read in Lane B) — a one-time contract.

---

## Resolved decisions (Daniel 2026-07-13)

1. **Font-size control = a STEPPER** (−/+, NSStepper-style) with a live readout —
   not a free slider or a point-size field.
2. **Scale clamp = `0.8…2.0×`** of the semantic base, enforced by the stepper
   and re-clamped on load. Reader and Editor each get their **own** stepper and
   **own** `@AppStorage` key, both clamped `0.8…2.0`.
3. **Reader theme = the app's semantic light/dark only.** Sepia/Paper reading
   themes are **deferred / out of scope** — filed as a future issue, not designed
   here.
4. **Four distinct per-view panes preserved** — Library / Preview / Reader /
   Inspector each keep their own settings section; **no pane is merged or
   dropped** ([[preview-reader-inspector-three-surfaces]]). The Preview pane is
   its *settings*, not a Reader merge.

## What this is NOT

- Not a merge of Preview / Reader / Inspector (they stay three surfaces).
- Not a rewrite of any existing settings pane — a container restructure that
  reuses every pane unchanged (#3396 groups included).
- Not hardcoded font sizes — a scale over the semantic base that composes with
  Dynamic Type.
- Not manual paragraph editing — code-based wrapping (CSS + JS fallback).
