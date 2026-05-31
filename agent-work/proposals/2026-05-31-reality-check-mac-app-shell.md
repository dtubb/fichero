# Reality Check — Mac App Shell
**Date:** 2026-05-31
**Auditor:** claude-sonnet-4-6
**Scope:** Open issues in "Mac App Shell" GitHub milestone (menus, About, shortcuts, first-run, window-restore, Sparkle)
**Method:** grep + Read only — no build, no exec

---

## Summary

| Metric | Count |
|---|---|
| Open issues checked | 4 |
| DONE (safe to close now) | 0 |
| PARTIAL | 2 |
| OPEN (needs work) | 1 |
| needs:human (release-gate) | 1 |

**Safe to close now:** none — all four issues have genuine remaining work or require human validation.

---

## Issue-by-Issue Classification

### #520 — Integrate and test Sparkle auto-update for 0.0.2 release
**Classification: PARTIAL**

**Evidence:**
- `fichero/fichero/App/SparkleUpdater.swift` (84 lines) — `SPUStandardUpdaterController` initialized, `checkForUpdates()` implemented with proper feed-URL validation and signed-update requirement in release builds.
- `FicheroApp.swift:144-147` — "Check for Updates..." menu item wired to `SparkleUpdater.shared.checkForUpdates()` via `CommandGroup(after: .appInfo)`.
- `Info.plist` — `SUFeedURL = $(SPARKLE_FEED_URL)` and `SUPublicEDKey = $(SPARKLE_PUBLIC_ED_KEY)` configured (build-variable substitution — values come from xcconfig, not hardcoded).
- Sparkle framework present: `build/xcode/SourcePackages/artifacts/sparkle/` and linked in the build product (Debug build dir contains `Sparkle.framework`).

**What's missing / needs validation:**
- Acceptance criterion 3: "Test update check flow: Help → Check for Updates" — cannot verify behavior without running the app. The menu item and code exist, but functional test is unconfirmed.
- Criterion 4: "Confirm update check doesn't crash on first launch" — same, needs human QA.
- Criterion 5: "Document appcast URL and signing key location" — no documentation of where the actual `SPARKLE_FEED_URL` xcconfig value points or where the signing key lives.
- The feed URL is a build variable: if `FICHERO_FEED_URL` is unset in the release xcconfig, `SparkleUpdater.checkForUpdates()` will show the "Updates Not Configured" alert — that may be intentional for dev builds but should be confirmed for release.

**Action:** Add `needs:human` label. Daniel should do a quick "Check for Updates" click and document the xcconfig/appcast URL source. Once confirmed functional + documented, close.

---

### #296 — Later: Sparkle release hosting and auto-update distribution pipeline
**Classification: OPEN (needs:human)**

**Evidence:**
- No `appcast.xml` found anywhere in the repo (`site/src/apps/fichero/`, scripts/, etc.).
- No CI step generating or publishing an appcast.
- `site/src/apps/fichero/index.md` mentions Sparkle auto-update as a shipped feature but acknowledges "first end-to-end update test happens against the next release."
- The issue body explicitly scopes this as post-0.0.1 release operations work.

**Action:** This is correctly open. It requires decisions (hosting location, channel strategy) and operational setup (CI step, signing key management). Leave for Daniel — mark `needs:human`.

---

### #733 — First-run wizard: 'Use the cheapest model that works' framing
**Classification: OPEN**

**Evidence:**
- `FirstRunWindow.swift` (393 lines) — a multi-step first-run wizard EXISTS with steps: Welcome, Library, Permissions, Cloud (OpenRouter key). It is wired: `ContentViewModifiers.swift:214-217` shows `FirstRunWindow()` presented when `appState.isBackendRunning && !featureManager.firstRunCompleted`.
- `FeatureManager.swift:104` — `@AppStorage("fichero.first_run.completed") var firstRunCompleted: Bool = false`.

**However**, the existing `FirstRunWindow` does NOT implement the issue's specific requirements:
- No "three ways to run AI" cards (Apple Intelligence / local Ollama / cloud APIs).
- No "cost-efficiency principle" — no "cheapest that works" framing anywhere in the file.
- No `ModelComparisonService` integration or surfacing.
- No Apple vs. local vs. cloud side-by-side path selection.

The current wizard covers library setup + OpenRouter key only. The issue is about a richer model-choice framing wizard that repurposes `WelcomeView.swift` and surfaces `ModelComparisonService`.

**Action:** Leave open. The foundational first-run flow exists but the issue's specific design (cost-efficiency framing, three-path picker, ModelComparisonService) is not implemented.

---

### #760 — Bash-launched Fichero binary doesn't get window/scene activation on macOS 26
**Classification: OPEN**

**Evidence:**
- No `scripts/launch-release.sh` exists (searched `scripts/` — no file matching `launch*.sh` or `launch_release.sh`).
- No `open -n -W` pattern found in any script in `scripts/`.
- The issue asks for: (1) a `scripts/launch-release.sh` helper using `open -n -W`, and (2) a note in the README's debugging section.
- No README debugging section addresses CLI-vs-Finder launch behavior.
- The issue body says "fixing it isn't possible from inside Fichero" — this is a docs + helper script task, not a code fix.

**Action:** Leave open. The script and documentation don't exist yet. Low-effort (30-min) task: write `scripts/launch-release.sh` + a brief debugging note in docs.

---

## Disposition Table

| # | Title | Classification | Action |
|---|---|---|---|
| 520 | Sparkle integrate + test | PARTIAL | Add needs:human; Daniel validates "Check for Updates" click + xcconfig docs |
| 296 | Sparkle release hosting pipeline | OPEN (needs:human) | Leave open; requires hosting decision + CI setup |
| 733 | First-run wizard: cheapest model framing | OPEN | Leave open; wizard exists but missing cost-efficiency content |
| 760 | Bash-launch helper script | OPEN | Leave open; script and docs note not created |

## Safe to close now
None.

## Needs:human (can't be auto-closed)
- **#520** — functional Sparkle test + xcconfig docs (Daniel clicks "Check for Updates")
- **#296** — release hosting decisions + CI pipeline (operational setup)
