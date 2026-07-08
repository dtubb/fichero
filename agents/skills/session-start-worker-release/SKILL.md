---
name: session-start-worker-release
description: Release worker — assembles RELEASE_NOTES.md and the changelog from what actually shipped. Stages artifacts; the manager owns heavy builds and Daniel owns publishing.
---

# /session-start-worker-release

Specialized `session-start-worker`. Read that skill first for the shared worker
contract. This file narrows it to the release lane.

## Lane — files you own

- `RELEASE_NOTES.md`
- `docs/contributor/release/**`
- `docs/release-notes-*.md`

You do **not** own `scripts/release-all.sh`, `scripts/create-github-release.sh`, or
`fichero/appcast.xml`. Read them; don't edit them without an issue that says so.

## Who does what

| | |
|---|---|
| **You** | assemble the notes, verify every claim, stage the artifacts |
| **The manager** | runs the heavy build (`xcodebuild`, `release-all.sh`), owns the one-build-at-a-time lock |
| **Daniel** | reviews the DMG and the notes, and publishes |

Never start a build while another runs. Never run `verify_all.sh --full` or
`xcodebuild test` on Daniel's desktop. `/fichero-release` is the runbook for the
mechanics; `docs/contributor/release/release-lane.md` is authoritative for signing and
notarization.

## Writing release notes

`RELEASE_NOTES.md`, newest first, Apple "what's new" style, grouped
**New / Improved / Security / Fixed**. Write for a researcher, not a committer:
what changed *for them*, not which module moved.

`scripts/release-notes-gen.sh` drafts a section per day from git history plus closed
issues, using a local ollama model. It is a **draft**. It hallucinates. Every line
it writes must be checked against the diff before it ships.

The bar for a line in the notes:

- It describes something a user can now do, or a bug they hit that is now gone.
- It shipped in a build. A merged commit behind a flag that is `false` in
  `FeatureManager.resetToV001()` **did not ship** — do not announce it. Check
  `docs/user/features.md`, which derives status from that function.
- No internal vocabulary: no issue numbers in prose, no "refactored", no module
  names, no "improved performance" without a number.
- Security fixes get their own **Security** line, always, even when small.

Do not write "Fixed assorted bugs." Name them or drop them.

## Versions are dated, not numbered

`scripts/set-release-version.sh` owns `MARKETING_VERSION` and
`CURRENT_PROJECT_VERSION`. It auto-stamps today's date across frontend and engine; a
second build the same day bumps a sub-number so Sparkle's build integer stays
strictly increasing. Never hand-edit either field. Never write a version number into
the notes that the manifest does not carry:

```bash
cat build/releases/release-manifest.txt
```

## Before you hand a build to Daniel

```bash
scripts/smoke-launch-crash.sh              # launch-time crashes
scripts/smoke-release-embedded-backend.sh  # embedded engine starts
xcrun stapler validate build/releases/Fichero.dmg
```

Release builds embed and spawn the engine; Debug runs it externally on `:8765`. If
notarization returns `Invalid`, do not resubmit — the per-Mach-O signing step in
`scripts/build-release-dmg.sh` is what broke. `codesign --deep` is forbidden here;
Apple has rejected the loose `.so`/`.dylib` files inside the embedded engine before.

## Report

Commit-only, author as yourself, `Directed-By: Daniel Tubb`, notify per commit.

```
RELEASE NOTES — <version from release-manifest.txt>

Entries:   <n> New / <n> Improved / <n> Security / <n> Fixed
Verified:  every entry traced to a commit AND to a flag that is on in release
Dropped:   <entries cut because the feature is still flag-gated>

Daniel: review the notes, then publish.
```
