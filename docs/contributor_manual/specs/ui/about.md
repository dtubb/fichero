# About — Design Spec (#2557)

> Milestone: about
> Manual: TBD — a short "About Fichero" note in the user manual's closing matter: what the About
> window shows (version, build, licence, the credits it carries) and where to report a problem.

> Design-led (Testing Constitution). Creative director owns intent; tests enforce it; code
> makes them pass. **Status: DRAFT — awaiting approval before it counts as ratified intent.**
> Flip the status to APPROVED only after the creative director approves; an APPROVED spec MUST
> carry a filled Test matrix, be cited by ≥1 test, and declare a `Milestone:` matching a GitHub
> milestone of the same name. Tags: [OK] built · [MISSING] not built · [PARTIAL] exists / not wired.
>
> Supersedes the Fabel review at `agent-work/design/about-view-fabel-review.md` (2026-07-25):
> Issues A (copyright), B (repo/license links + acknowledgements sheet), and C (Server row
> omitted when unknown) proposed there have all SHIPPED and are pinned below. This spec migrates
> that review's still-valid intent into the canonical location and adds the a11y ids + preview
> harness the review predated.

## Intent (the design)

The About window is where a user learns *what this is, who made it, what version they are running,
and what it is built on* — and can copy any of that into a bug report. It is a small, static,
single-instance macOS window (`Window("About Fichero", id: "about")`, `.windowResizability(.contentSize)`,
opened from the App menu's About item via `CommandGroup(replacing: .appInfo)`), and on touch
platforms the same content is a Settings tab. It shows: the **real running-app icon**, the app
**name**, the **app version + build** (`Version X (build)` from `CFBundleShortVersionString` /
`CFBundleVersion`), the **server/engine version** when known, a one-line **tagline**, a **credit**
line, the **copyright / license**, and three affordances — a **GitHub** link, an **AGPL-3.0 license**
link, and an **Acknowledgements** sheet crediting the full open-source stack (grouped App / Engine /
On-device AI, with LIVE versions when the engine reports them). Nothing loads asynchronously and the
window is a fixed width, so there is no white flash and no relayout-on-appear. The surface lives in
`fichero/fichero/Views/About/AboutView.swift` — `AboutInfo` (pure formatters), `AboutView`,
`AcknowledgementsView`, `Acknowledgement` / `AckLayer` / `AboutAcknowledgements` (the credits model),
`AboutLinks`, and `AboutWindowMenuButton`; the design-verification harness is
`fichero/fichero/Views/About/AboutPreview.swift`.

## Prior art / best practices (don't invent from scratch)

A macOS About box is a solved, HIG-shaped surface: Apple's standard About panel shows icon · name ·
version · copyright, and apps that embed third-party code add an **Acknowledgements** list (the
convention Apple itself uses in system apps and that CocoaPods/SwiftPM tooling generates). We adopt
that shape rather than inventing one, and deliberately keep it **dead-simple** (two links + one
sheet — no tabs, no scroll-of-legalese in the main window; see the "Dead-simple UX" memory ruling).
What we do differently: the icon is pulled from the **running app** (`NSApp.applicationIconImage`)
rather than a hard-coded asset name, so it can never drift from the shipped icon; and the credits
list is a **Swift-declared, unit-testable** `[Acknowledgement]` derived from the real manifests
(Package.resolved, pyproject.toml, the runtime provisioner) rather than a bundled plist, so it is
covered by tests and carries LIVE versions from the engine's health report instead of stale pins.
We reuse `AboutInfo`'s pure formatters so version/copyright strings are testable without a bundle.

## Behaviors

One line per behavior, each with a stable id and a tag. The id is what a test cites.
- `about.version.formats` [OK] — the app line reads `Version <short> (<build>)`, with an em-dash
  for a missing/blank key. Pinned by `AboutInfoTests.testBothPresent`/`…FallBackToDash*`.
- `about.server.repadded` [OK] — the engine's PEP 440 version is re-padded to the display date form
  so one release never shows as two different-looking versions. `AboutInfoTests.testEngineVersionLineUsesVersion`,
  `testDateStyleVersion*`.
- `about.server.omitted-when-unknown` [OK] — the Server row is omitted entirely (not `Server —`)
  before the first health response and while disconnected. `AboutInfoTests.testEngineVersionLineIsOmitted*`.
- `about.copyright.bundle-then-fallback` [OK] — copyright uses the bundle's
  `NSHumanReadableCopyright` when present, else the AGPL-3.0 fallback. `AboutInfoTests.testCopyrightLine*`.
- `about.icon.real-running-icon` [OK] — the icon is the running app's icon (macOS) / highest-res
  bundled icon (iOS), never an asset-name coupling. `AboutViewIconTests.*`.
- `about.links.canonical` [OK] — GitHub + license links point at the canonical repo URLs.
  `AboutInfoTests.testAboutLinksUseCanonicalRepositoryURLs`.
- `about.acknowledgements.rows` [OK] — every credited project has a non-empty name + license and a
  valid https URL, and a UNIQUE `versionKey` (so the `about.ack.<versionKey>` a11y id never collides).
  `AboutInfoTests.testAcknowledgementsHaveUniqueNamesAndHTTPSLinks`, `AboutAcknowledgementsTests.testVersionKeysAreUnique…`.
- `about.acknowledgements.grouped` [OK] — credits are grouped App → Engine → On-device AI, every
  layer non-empty. `AboutAcknowledgementsTests.testEveryLayerIsPopulated`, `testLayerDisplayOrder`.
- `about.acknowledgements.live-version` [OK] — a row shows `v<version> · <license>` when the engine
  reports that dependency's version, license-only otherwise (never a stale number). *(view-level;
  `versionKey` mapping pinned by `AboutAcknowledgementsTests.testDistributionOverride…`)*
- `about.settings.touch-tab` [OK] — on touch platforms About is a Settings tab, not a window.
  `AboutSettingsSurfaceTests.testSettingsViewHostsAboutTabOnTouchPlatforms`.
- `about.window.single-instance` [OK] — the Mac About window is single-instance, content-sized,
  centered, and does not list itself in the Windows menu. `AboutSettingsSurfaceTests.testMacAboutWindowInjectsAppState` (partial).

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | **y** | version/server/copyright formatting + acknowledgements model | `fichero/Tests/Unit/general/Views/About/AboutInfoTests.swift`, `AboutAcknowledgementsTests.swift`, `AboutViewIconTests.swift` |
| Availability (Swift) | **y** (source-scan) | About tab/window wiring is present + injects AppState | `fichero/Tests/Unit/general/Views/Settings/AboutSettingsSurfaceTests.swift` |
| Backend (pytest) | n | About reads the health version already fetched; no dedicated endpoint | — |
| MCP | n | — | — |
| CLI | n | — | — |
| Click-around (XCUITest, Mac) | **n → [MISSING]** | App menu → About opens; links + Acknowledgements reachable by a11y id | `fichero/Tests/UI/…` (a11y ids now in place; test not yet written) |
| iPhone (iOS) | **n → [MISSING]** | About tab renders in Settings on iPhone | `fichero/Tests/UI/ios` |
| iPad | **n → [MISSING]** | About tab renders in Settings on iPad | `fichero/Tests/UI/ipad` |
| Load (#4634) | n | static surface, no work | — |

About is a static info surface: the load-bearing legs are **Swift pure** (formatters + model) and
**Swift availability** (the wiring source-scans), both green. The click-around/touch legs are tracked
debt — the a11y ids they need are now shipped (below), so the UI tests can be written without further
view changes.

## Documentation matrix

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual + screenshot | y | `docs/user_manual/…` (maintainer-authored in Tinderbox; not written here) |
| Contributor | developer docs | **y** | `docs/contributor_manual/ui-about.md` + this spec |
| AI / agent | MCP tool description | n | — |
| Scripter | CLI `--help` | n | — |
| Reference | capability/endpoint reference | **y** | `docs/reference_manual/about-version-facts.md` |

**Authorship.** The contributor + reference docs above are AI-authored as part of this spec (written
in this pass). `docs/user_manual/` is the maintainer's own (Tinderbox); this spec's job for that
audience is only to keep the facts accurate (behaviors, a11y ids, the preview screenshot source).

## Preview harness

Ships `AboutPreview` (+ `AboutAcknowledgementsPreview`) in
`fichero/fichero/Views/About/AboutPreview.swift`, `#if DEBUG`-gated. It renders the About composition
from STATIC spec data through the pure `AboutInfo` formatters — **no `AppState`/backend boot** — so
the layout renders instantly in the Xcode canvas and via `ImageRenderer`, and is the SOURCE of the
manuals' screenshots (`docs/assets/about/`). Three previews: the card, the card with the Server row
omitted (`engineVersion: nil` — the pre-connection state), and the grouped acknowledgements list.
Mirrors the `WorkspaceLayoutPreview` pattern. (The live canvas is currently blocked by an Xcode 27 RC
arm64e bug; the harness is structured so an `ImageRenderer` snapshot works independent of the canvas.)

## Accessibility identifiers

Stable a11y ids now on the views (added in this pass), for the click-around leg to drive:
- `about.menu.open` — the App-menu "About Fichero" button that opens the window.
- `about.appName` / `about.version` / `about.serverVersion` — the identity + version text.
- `about.link.github` — "Fichero on GitHub" link.
- `about.link.license` — "AGPL-3.0 License" link.
- `about.button.acknowledgements` — opens the Acknowledgements sheet.
- `about.ack.<versionKey>` — one per credited project (key is the unique lowercased dist name).
- `about.acknowledgements.done` — the sheet's Done button.

## UX completeness

| Control (a11y id) | Label | Tooltip/help text | Localized key | Verified by |
|---|---|---|---|---|
| `about.menu.open` | "About Fichero" (menu item) | — (menu item) | `About Fichero` | scan (menu) |
| `about.version` | version text (selectable) | — (static text) | `Version …` (formatted) | `AboutInfoTests` |
| `about.serverVersion` | server text (selectable) | — (static text) | `Server …` (formatted) | `AboutInfoTests` |
| `about.link.github` | "Fichero on GitHub" | "Open the Fichero source repository on GitHub" | `Fichero on GitHub` | `.help` present · UI test [MISSING] |
| `about.link.license` | "AGPL-3.0 License" | "Read Fichero's AGPL-3.0 license on GitHub" | `AGPL-3.0 License` | `.help` present · UI test [MISSING] |
| `about.button.acknowledgements` | "Acknowledgements" | "View the open-source projects Fichero is built on" | `Acknowledgements` | `.help` present · UI test [MISSING] |
| `about.ack.<versionKey>` | project name + license | "Open the \<name\> project website" | dynamic (name) | `.help` present · UI test [MISSING] |
| `about.acknowledgements.done` | "Done" | "Close acknowledgements" | `Done` | `.help` present · UI test [MISSING] |

All user-facing strings are `LocalizedStringKey` literals (Link/Button/Text/`.help` all take the key
form) — no `Text(verbatim:)`, so the surface is localization-ready. The icon is `.accessibilityHidden`
(decorative; the name text carries the identity). No icon-only controls on this surface, so the
static tooltip/label scanners have nothing outstanding here; the `[MISSING]` rows are the *behavioral*
UI test, not missing labels.

## Open questions for the creative director
- **Tagline sign-off.** The tagline is the website sentence (2026-09-02); confirm it is the final copy
  or supply the "literary-carpentry" wording the #2557 NOTE still references.
- **Copyright single-sourcing (#3234).** The bundle `NSHumanReadableCopyright` is still empty in all
  configs, so the Swift AGPL fallback is what ships. Folding copyright into the same xcconfig as
  `MARKETING_VERSION` (deferred with #3234) would make the bundle branch live again.
- **Help menu.** A Help menu with a website/docs link is the conventional home for the repo link; the
  app registers none today. In scope for About, or its own surface?
- **Milestone name.** This spec declares `Milestone: about`; confirm/create the matching GitHub
  milestone before flipping to APPROVED (spec name == milestone name == test tag).
