# Fabel Review — About View (Milestone 127)

Date: 2026-07-25 · Branch `feat/about-view` · Reviewer: Claude (Opus 5)

Scope reviewed: `fichero/fichero/Views/About/AboutView.swift` (the whole surface —
`AboutInfo`, `AboutView`, `AboutWindowMenuButton`), the `Window("About Fichero",
id: "about")` scene and `CommandGroup(replacing: .appInfo)` wiring in
`FicheroApp.swift:263,409`, the iOS/touch surface in
`Views/Settings/SettingsView.swift:190` + `SettingsDetailHeader.swift:41`, the
version/copyright build settings in `project.pbxproj`, and the three existing test
files (`AboutInfoTests`, `AboutViewIconTests`, `AboutSettingsSurfaceTests`, 187
lines).

---

## Verdict

About is **structurally good and close to done**. The architecture is right, and the
four closed issues in this milestone did real work: the crash (#3853) is gone, the
icon is the real running-app icon on both platforms (#3236), the engine version is
derived and surfaced (#3232). Nothing here needs re-architecting.

What is missing is not layout — it is **three concrete content/correctness gaps**
plus the already-filed version single-sourcing (#3234). I am proposing 3 new issues,
not a redesign.

### What About already has

| Expected in a shipping Mac About box | Fichero |
|---|---|
| Real app icon | ✅ `NSApp.applicationIconImage` on macOS (no asset-name coupling); highest-res `CFBundleIconFiles` entry on iOS |
| App name | ✅ |
| Version + build | ✅ `CFBundleShortVersionString` + `CFBundleVersion`, em-dash fallback, `textSelection(.enabled)` so a tester can copy it into a bug report |
| Engine/component version | ✅ `Engine X` from cached health — no extra request from the view |
| One-line description | ✅ tagline (copy still unconfirmed, see Question 1) |
| Author credit | ✅ "Created by Daniel Tubb" |
| Copyright | ⚠️ present but **stale and hardcoded** → Issue A |
| Link to the project / site | ❌ **absent anywhere in the app** → Issue B |
| Path to licences / third-party credits | ❌ **absent** → Issue B |
| Native window behaviour | ✅ single-instance `Window`, `.windowResizability(.contentSize)`, `.defaultPosition(.center)`, standard `CommandGroup(replacing: .appInfo)` |
| Semantic fonts only | ✅ `.title`, `.callout`, `.body`, `.caption` — zero `.system(size:)` |
| Dead-simple UX | ✅ no toggles, no tabs, no preferences |
| No local filesystem paths rendered | ✅ |

### Every-Frame-Perfect audit

- No async image load, no network request, no task on appear → **no white flash, no
  relayout-on-load** on the version/icon path. Fixed `width: 360` + `minHeight: 360`
  means the window never resizes under the user.
- **One real violation:** the engine line renders **`Engine —`** whenever
  `appState.backendVersion` is `nil` — which is every launch before the first health
  response lands, and permanently while disconnected. That is partial content
  presented as if it were data. → Issue C.

---

## Issue A — About shows a stale, hardcoded copyright year

`INFOPLIST_KEY_NSHumanReadableCopyright = ""` in **all four** build configurations
(`project.pbxproj:1283,1355,1434,1513`). `AboutInfo.copyrightLine` treats empty as
missing, so the bundle branch is dead code in every build and the view's
`fallbackCopyright` is what ships:

> `© 2025 Daniel Tubb · MIT License`

`LICENSE` already says `Copyright (c) 2025-2026, Daniel Tubb`. About therefore
disagrees with the repo's own licence, and will drift further every January.

**Fix, in two parts (deliberately split around the release):**

1. **Now (this milestone, Swift-only):** correct the fallback to the licence's own
   range and stop it being a year that can silently rot — derive the end year, keep
   the start fixed. Test: `AboutInfo` copyright formatting with an empty bundle
   value, a present bundle value, and a whitespace-only bundle value.
2. **With #3234 (after the release):** set the real
   `INFOPLIST_KEY_NSHumanReadableCopyright` from the same xcconfig that carries
   `MARKETING_VERSION`, so copyright and version are single-sourced together and the
   Swift fallback becomes a true fallback again.

Deliberately **not** touching `project.pbxproj` in this milestone — a release is
being stamped from those exact configs.

## Issue B — About offers no link to the project and no path to licences

Fichero is heading for open-source publication, and About is where a user looks for
"what is this, who made it, what is it built on, what may I do with it". Today:

- The string "MIT License" appears with no way to read it.
- There is **no link to the repository or site anywhere in the app** — not in About,
  not in a Help menu (the app registers no Help commands at all).
- No third-party acknowledgements, though the shipped product embeds Sparkle plus an
  entire Python engine (FastAPI, Uvicorn, Pydantic, DuckDB, LanceDB, LangChain,
  LangGraph, MCP, PyMuPDF, Pillow, httpx, cryptography, …).

**Fix (ponytail-shaped, no new bundle resources, no pbxproj edit):**

- One `Link` — "Fichero on GitHub" → `https://github.com/dtubb/fichero` (the real
  `repo_url` from `mkdocs.yml`). **Do not** use `mkdocs.yml`'s `site_url`; it is
  still the placeholder `https://fichero.example/`, so there is no site to link yet.
- One `Link` — "MIT License" → the `LICENSE` file's canonical URL in that repo.
- An **Acknowledgements** list: a Swift-declared `[Acknowledgement]` (name, licence,
  URL) rendered in a small sheet off About. Swift-declared, not a bundled file, so
  there is no resource to register and the list is unit-testable (every entry has a
  non-empty name/licence and a valid `https` URL, no duplicates).
- Stays dead-simple: **two links and one sheet.** No toggles, no scroll-of-legalese
  in the main window.

Both links are external URLs, not filesystem paths — the no-local-paths rule holds.

## Issue C — "Engine —" is partial content (Every Frame Perfect)

`AboutInfo.engineVersionLine(nil)` → `"Engine —"`, shown on every launch until the
first health response and forever while disconnected. An em-dash reads as "the
engine's version is em-dash", not "not known yet".

**Fix:** make the engine line optional at the formatter level — return `nil` when
there is no version, and let the view omit the row rather than render a placeholder.
Because the window is a fixed `width: 360` with `minHeight: 360`, dropping/adding
that one row does not resize the window, so there is no relayout-on-load either way.
Tests: `nil` → omitted; empty/whitespace → omitted; a real version → `"Engine X"`.

## #3234 — version single-sourcing (planned, DEFERRED, not started)

Already filed and correct as written. **Blocked by the in-flight release** — it
rewrites the exact machinery the release stamps (`project.pbxproj`,
`fichero-engine/pyproject.toml`, `scripts/set-release-version.sh`,
`RELEASE_NOTES.md`). Not touching any of those files in this milestone.

Refinements to fold in when it is green-lit:

- Carry `INFOPLIST_KEY_NSHumanReadableCopyright` in the same `Version.xcconfig`
  (closes the other half of Issue A).
- The issue predates `scripts/set-release-version.sh`; the bump script must not be a
  second, competing stamper — reconcile with the existing release stamp path rather
  than adding a rival one.
- The guardrail it proposes (`check_*.py` asserting no `MARKETING_VERSION` literal
  survives in `project.pbxproj`) is worth keeping, and is path-keyed — it must land
  in the same commit as the xcconfig move.

---

## Questions for Daniel (not filed as issues)

1. **Tagline sign-off.** `AboutView.swift:7-10` still carries the #2557 NOTE that the
   tagline is CONSTITUTION-derived copy standing in for the "literary-carpentry"
   wording, awaiting confirmation. Current copy: *"A document workbench for
   researchers — read, organize, search, and make things from your sources."*
   Confirm it, or supply the wording you want. Once confirmed, the stale NOTE comment
   goes away with it.
2. **PyMuPDF is AGPL-3.0.** It ships inside the embedded engine while Fichero itself
   is MIT. That is a licence-compatibility question for going public, not an About-box
   question — but writing the acknowledgements list is what surfaced it, so flagging it
   rather than quietly listing it. Not blocking Issue B.
3. **A Help menu** with documentation/website items is the conventional home for a
   site link, and the app has none. Adjacent to About but outside milestone 127 — say
   the word and it gets filed on its own milestone rather than smuggled in here.

## Explicitly NOT proposed

No redesign, no icon rework, no window-behaviour change, no font sweep (the fonts are
already semantic), no new Settings toggle, no iOS surface rework. About's structure is
right; these are content and correctness fixes.

## Sequence

1. Issue C (smallest, formatter + test)
2. Issue A part 1 (Swift fallback + tests)
3. Issue B (links + acknowledgements sheet + tests)
4. #3234 — only after the manager green-lights it post-release

Each lands as its own commit with tests. **Tests for the manager to run:**
`AboutInfoTests`, `AboutViewIconTests`, `AboutSettingsSurfaceTests`, plus whatever new
`AcknowledgementsTests` Issue B adds — all in the `FicheroTests` scheme.
