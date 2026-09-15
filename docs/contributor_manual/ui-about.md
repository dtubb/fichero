(AI generated. Not reviewed.)

# About Window

The design intent lives in `docs/contributor_manual/specs/ui/about.md`. This page
documents what is shipped in the merged code.

## What it is

A small, static, single-instance macOS window that tells the user what the app is,
who made it, which version they are running, and what it is built on. It is opened
from the App menu's **About Fichero** item and is sized to its content. On touch
platforms (iOS/iPadOS) the same content is a tab in Settings rather than a window.

## Where it lives

- `fichero/fichero/Views/About/AboutView.swift`
  - `AboutInfo` — pure, bundle-independent formatters (version line, server line,
    PEP 440 → display-date re-padding, copyright). Unit-tested without a bundle.
  - `AboutView` — the window body: icon, name, version, server row, tagline, credit,
    copyright, and the GitHub / License / Acknowledgements affordances.
  - `Acknowledgement` / `AckLayer` / `AboutAcknowledgements` — the Swift-declared
    open-source credits model, grouped App → Engine → On-device AI.
  - `AcknowledgementsView` — the credits sheet (grouped list, live versions when known).
  - `AboutLinks` — the canonical repository + license URLs.
  - `AboutWindowMenuButton` — the App-menu button that opens the window.
- `fichero/fichero/Views/About/AboutPreview.swift` — the `#if DEBUG` preview harness
  (`AboutPreview`, `AboutAcknowledgementsPreview`): renders the composition from static
  spec data with no `AppState`, for canvas verification and doc screenshots.
- Window wiring: `Window("About Fichero", id: "about")` in `fichero/fichero/FicheroApp.swift`,
  with `.windowResizability(.contentSize)`, `.defaultPosition(.center)`, `.commandsRemoved()`
  (so it does not list itself in the Windows menu), and the App-menu replacement via
  `CommandGroup(replacing: .appInfo)`.

## How the values are sourced

- **App version + build** — `CFBundleShortVersionString` / `CFBundleVersion` from the live
  bundle, formatted by `AboutInfo.versionLine` (em-dash fallback for a missing key).
- **Server / engine version** — `AppState.backendVersion` from the cached health response
  (no extra request from the view). The engine reports a PEP 440 string
  (e.g. `2026.9.3`); `AboutInfo.dateStyleVersion` re-pads it to the display date form
  (`2026.09.03`) so one release never appears as two different-looking versions. When the
  version is unknown (before the first health response, or while disconnected) the row is
  **omitted entirely** — never rendered as `Server —`.
- **Icon** — the running app's icon: `NSApp.applicationIconImage` on macOS (no asset-name
  coupling); the highest-resolution `CFBundleIconFiles` entry on iOS, resolved by the pure
  `AboutView.appIconAssetName`.
- **Copyright** — the bundle's `NSHumanReadableCopyright` when present, else the AGPL-3.0
  fallback string (the bundle key is currently empty in all configs, so the fallback ships;
  single-sourcing it into the version xcconfig is deferred with issue #3234).
- **Acknowledgements** — a curated `[Acknowledgement]` derived from the real manifests
  (`Package.resolved`, `fichero-server/pyproject.toml`, and the runtime provisioner for the
  on-device AI stack that is provisioned at runtime rather than pinned). Each entry carries a
  `versionKey` (its lowercased pip/SPM distribution name); the sheet shows `v<version> · <license>`
  when the engine's health report includes that dependency's version, license-only otherwise.

## Accessibility

Every interactive control carries a stable `accessibilityIdentifier` and a `.help` tooltip:
`about.menu.open`, `about.link.github`, `about.link.license`, `about.button.acknowledgements`,
`about.ack.<versionKey>` (one per credited project), `about.acknowledgements.done`; the identity
text carries `about.appName` / `about.version` / `about.serverVersion`. The icon is
`.accessibilityHidden` (decorative). All strings are `LocalizedStringKey` literals — the surface
is localization-ready. See the spec's UX-completeness table for the exact tooltip text.

## Tests

- `fichero/Tests/Unit/general/Views/About/AboutInfoTests.swift` — version/server/copyright
  formatting, the date re-padding edge cases, and acknowledgement URL/uniqueness.
- `fichero/Tests/Unit/general/Views/About/AboutAcknowledgementsTests.swift` — the credits model:
  unique version keys (so the a11y ids never collide), distribution-override key mapping, every
  layer populated, and the App → Engine → On-device layer order.
- `fichero/Tests/Unit/general/Views/About/AboutViewIconTests.swift` — icon-asset resolution.
- `fichero/Tests/Unit/general/Views/Settings/AboutSettingsSurfaceTests.swift` — the tab/window
  wiring (About is a Settings tab on touch, a single-instance window on Mac that injects AppState).

The Mac click-around and touch UI tests are tracked debt; the a11y ids they need are in place.
