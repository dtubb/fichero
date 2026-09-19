# Release & Versioning — Design Spec (#TBD)

> Milestone: release-and-versioning
> Manual: docs/contributor_manual/guide/17-the-release-lane.md
>
> Design-led. **Status: DRAFT — for the design lead's review.** How a build gets a version, how
> the three stamps stay in agreement, and how a release reaches users. Grounded in the actual
> scripts + configs, 2026-09-12. This spec is the map; the linked runbooks hold the operational
> detail — it summarizes and points, it does not restate them.

## Intent

One repository, **dated releases**, **one build at a time**. The version is *derived and stamped
by a script*, never hand-typed in scattered files — because the version lives in several places
(the app config, the engine manifest, three OpenAPI copies) and they must always agree. A reader
should never wonder "which version is this?" or edit a version literal by hand: `set-release-version.sh`
is the one writer, guardrails enforce agreement, and a release is a gated, dated, tagged event that
ships only after the design lead's verdict.

## Prior art

CalVer (calendar versioning) for the user-facing string; PEP 440 for the Python engine; Sparkle's
appcast model (order by a strictly-increasing build **integer**, not the display string) for macOS
auto-update; Apple's `CFBundleShortVersionString` + `CFBundleVersion` split for the App Store /
TestFlight. We adopt each as-is rather than inventing a scheme.

## The versioning scheme — three stamps, one writer

A release stamps **three** things that must agree, all set by the single command
`scripts/set-release-version.sh` (auto-stamps today; a second release the same day auto-bumps a
sub-number, `N = (count of existing v<DATE>* tags) + 1`):

| Stamp | Where | Form | Notes |
|-------|-------|------|-------|
| App marketing version | `fichero/Configs/Version.xcconfig` → `MARKETING_VERSION` | `YYYY.MM.DD[.N][-beta]` (zero-padded, **UNQUOTED**) | The single source of the app version (#3234); `project.pbxproj` carries no version literals. `CURRENT_PROJECT_VERSION` is a plain increasing build integer. |
| Engine version | `fichero-server/pyproject.toml` → briefcase `version` **and** `[project] version` | `YYYY.M.D[.N]` PEP 440 (**no** zero-pad; `-beta` → `bN`) | Both fields must match each other. |
| OpenAPI schema version | all **three** `openapi.json` copies → `info.version` | = the engine version | Kept in sync by `fichero-server/scripts/sync_openapi_schema.sh` (which refuses a backwards move via `check_openapi_version_regression.py`, run only inside the sync, not as a standalone gate check). **No script yet verifies, as a standalone guardrail, that the three already-committed copies agree with each other** — `check_openapi_shadow_types.py` checks something unrelated (Swift types shadowing generated schema NAMES, not `info.version`). This cross-copy agreement checker is NOT YET BUILT; the rule above remains intent until it exists. |

**Zero-pad difference is intentional, not a bug:** the app date is zero-padded (`2026.09.08`) because
Apple accepts it; the engine strips leading zeros (`2026.9.8`) because PEP 440 forbids them
(`2026.09.08` is an invalid PEP 440 version). Same date, two required spellings — do not "fix" one
to match the other.

**Version never goes backward.** When reconciling branches, the newer date wins for every stamp; a
merge must not regress a shipped version.

Guardrails that enforce this (run in `verify_all`):
- `scripts/check_version_date.sh` — the app version is a valid unquoted date.
- `scripts/check_engine_version_stamp.py` — the embed phase records what engine it actually embedded
  (`FicheroEmbeddedEngineVersion` / `FicheroExpectedEngineVersion` in `Info.plist`) and the app checks
  it against `/api/health` at launch, so a stale engine can't masquerade as current.
- `scripts/check_openapi_shadow_types.py` — checks Swift types don't shadow generated OpenAPI
  schema NAMES; it does **not** check that the three `openapi.json` copies' `info.version`
  agree with each other. **A standalone gate check for that cross-copy `info.version`
  agreement does not exist yet** (`check_openapi_version_regression.py` only guards against
  going backward during a sync, and is not itself invoked by `verify_all`) — this is a real
  gap, not yet built, corrected here after an earlier miscitation.

## The release lane (process)

Detail lives in [`../../release/release-lane.md`](../../release/release-lane.md) (the runbook) and
[`../../architecture/release-process.md`](../../architecture/release-process.md) (the feature→ship
sequence); [`../../release/sparkle-release.md`](../../release/sparkle-release.md) covers Sparkle
— **found 2026-09-19 marked, in its own header, "(AI generated. Not reviewed.)" and "HISTORICAL
SETUP NOTE... do not use it as the current release procedure" (it still names a retired feed
URL)** — recorded as found, not rewritten here; `release-lane.md`'s own Sparkle section is the
current procedure. [`../../release/release-readiness.md`](../../release/release-readiness.md) is
a point-in-time readiness snapshot. Shape:

1. **Integrate + gate.** Multi-lane work lands on `integration` and is gated there (`verify_all`,
   0 failed) — see [`git-worktree-workflow.md`](git-worktree-workflow.md).
2. **Merge to main.** `scripts/merge-integration-to-main.sh` fast-forwards `integration` into `main`
   (refuses anything but a clean fast-forward) as the pre-step; `release-all.sh` builds from the
   `main` checkout. It stamps the version *after* the merge, so the dated stamps are not a merge
   conflict source.
3. **Readiness gate (blocks distribution).** `scripts/check_release_docs_ready.py` runs in
   `release-all.sh`'s preflight and **fails the lane** unless, for the version being stamped:
   (a) `RELEASE_NOTES.md` has that `## <version>` section, (b) `CHANGELOG.md` carries the day's
   entry, and (c) the docs guardrails pass (`check_capability_reference_current`,
   `check_features_freshness`, and every `mkdocs` nav path resolves). A release cannot ship with
   stale or missing docs — the docs are part of the release, not an afterthought.
4. **Build + sign + ship.** `scripts/release-all.sh` runs the lane **unattended**: builds the
   embedded engine once, then DMG (Developer ID → notarize → staple → Sparkle-sign → GitHub release
   via `create-github-release.sh`) + Mac TestFlight + iOS TestFlight. iOS is remote-only (no embedded
   engine, no Sparkle).
5. **Smoke the optimized build locally.** Before the verdict, run the *shipped* optimized artifact
   (the notarized DMG / `scripts/smoke-release-embedded-backend.sh`), **not** a `-Onone` RUN scheme.
   The RUN schemes build Swift `-Onone` (see AGENTS.md), so a debug-layout regression can reach a
   shipped build unseen — exactly what `2026.09.08` had to fix. The release is not verified until the
   real optimized build has been exercised locally.
6. **Tag.** `vYYYY.MM.DD[.N]` on the shipped commit; the GitHub release carries that version's notes.

**Tested before published.** Releases are notarized/verified, the optimized build is smoke-tested
locally (step 5), and the design lead gives the verdict *before* anything goes public (GitHub,
TestFlight, the site). The lane does not self-publish on a green build.

## Release notes — two artifacts, different owners

Two files, two conventions — do not conflate them:

| Artifact | What | Heading | Who | How |
|----------|------|---------|-----|-----|
| `CHANGELOG.md` | The commit-level, **day-by-day** record — what changed, every day. Updated as work lands. | `## YYYY-MM-DD` (dashed, **per day**) | Agents (the record). | `scripts/release-notes-gen.sh` writes one section per day from git + closed issues via a local model (zero Claude cost). |
| `RELEASE_NOTES.md` | The human prose — **one section per shipped release**, the story for users. | `## YYYY.MM.DD` (dotted, **per release**) | The **maintainer** owns this prose (user-facing). | Written by hand. `scripts/gen_site_releases.py` slices the newest section onto the landing page. |

The dotted-vs-dashed heading is the tell: a *release* date is dotted (`2026.09.08`), a *calendar*
day is dashed (`2026-09-08`). `CHANGELOG.md` must contain only dashed per-day sections; dotted
release headings there are leakage from `RELEASE_NOTES.md` (or merge debris) and must be removed.

The GitHub release body holds each version's own notes independently of these files, so a version's
notes survive even if a later re-date reshuffles the local files.

## Updates reach the user and install

Grounded in a read-only Sparkle update review, 2026-09-19 (`agent-work/spec-pipeline/
sparkle-update-review-2026-09-19.md`), requested after the maintainer reported Sparkle SAW an
update and FAILED to install it. Every behavior below cites #4901, the one issue this review's
evidence backs.

- `release.update.feed-is-current` — **[BROKEN]** (#4901) the public appcast
  (`https://tubb.ca/apps/fichero/appcast.xml`) should carry the release just made. Verified live
  (2026-09-19, a genuinely fresh fetch — `age: 0`, `cache-status: fwd=miss` — not a stale edge
  cache): the feed's newest item is `2026.09.07` build 3, while the tree is stamped `2026.09.18`
  with dozens of commits since. What publishes the feed: `create-github-release.sh` writes and
  COMMITS `appcast.xml` into the separate `tubb.ca` site repo checkout
  (`$FICHERO_SITE_DIR/apps/fichero/appcast.xml`), explicitly NOT deploying it — the script's own
  comment says so ("Committed in site repo — DEPLOY tubb.ca to publish the feed"). A second,
  fully separate step, `deploy-site.sh`, is what actually pushes the site live. Nothing forces
  that second step to run, nothing warns if it's skipped, and nothing after the fact re-checks
  that the live feed actually reflects what was just released — so this can, and evidently did,
  silently not happen for however many releases separate `2026.09.07` from today's stamp.
- `release.update.build-number-strictly-increases` — **[BROKEN, historical]** (#4901) Sparkle
  compares `sparkle:version` (the integer build number), not the marketing string; two different
  releases must never share one. Verified live: the feed's own `2026.09.04` and `2026.09.05`
  items BOTH carry `sparkle:version=2` — a real collision, not a hypothetical risk. What assigns
  the build number today: `set-release-version.sh`'s `next_build_int`, a plain local increment
  read from `CURRENT_PROJECT_VERSION` in `fichero/Configs/Version.xcconfig` (or an explicit
  `FICHERO_BUILD_NUMBER` override) — purely a function of the LOCAL checkout's current stamp, not
  of what the live feed actually already has. Nothing enforces monotonicity against the feed
  itself, so two releases stamped from two different local states (a stale checkout, a manual
  override, a partial re-run) can independently compute the same "next" number with nothing to
  catch the collision before it ships. Any check built against this must compare PER CHANNEL,
  not globally: the live feed legitimately carries a public item and a dev-channel item for the
  same version and the same build number by design (see `release.update.appcast-item-insert-is-
  idempotent` below) — comparing the new build number against the feed's newest item regardless
  of channel would false-positive on that intentional pair.
- `release.update.signature-made-after-stapling` — **[PARTIAL]** (#4901) an EdDSA signature must
  be computed AFTER `xcrun stapler staple`, since stapling modifies the file and a
  pre-staple signature would no longer verify. Verified BY READING, not by a test or script
  check: `release-all.sh` runs `build-release-dmg.sh` → `notarize.sh "$DMG_PATH"` (which staples
  the DMG itself) → only then `create-github-release.sh` (which calls `sign_update` on that same,
  already-stapled `$DMG_PATH`) — the correct order, today, in the scripts as checked in. PARTIAL,
  not OK, because no automated check pins this order; a future edit could reorder these steps (or
  a manual/partial release run could skip `notarize.sh`) with nothing to catch it before a
  broken signature ships.
- `release.update.appcast-item-insert-is-idempotent` — **[GAP]** (#4901) re-running the appcast
  step for the SAME release must not append a duplicate item. Verified by reading:
  `create-github-release.sh`'s appcast-update step inserts unconditionally — it always writes a
  new `<item>` immediately after `<language>`, with no check for an existing item it should
  replace instead. An item's true identity is the triple (`sparkle:version`,
  `sparkle:shortVersionString`, channel) — NOT version+build alone, because every release
  legitimately produces TWO items sharing the same version and build number: a channel-less
  public item and a `<sparkle:channel>dev</sparkle:channel>` item (`SparkleChannelDelegate`
  scopes the dev item to dev builds only). A first fix attempt keyed on version+build only was
  considered and REJECTED before it was ever committed, because a re-run would have matched
  and replaced the WRONG item — overwriting the public item with the dev item's enclosure/
  signature, or vice versa, silently pointing one channel's users at the other channel's DMG.
  Expected: a re-run replaces the matching item within its own channel and never touches the
  other channel's item. A fix is IN PROGRESS — not built, not tested, no script or test yet
  proves this either way.
  download and cryptographically verify an update and still fail to install it if the running app
  is translocated (Gatekeeper's randomized, read-only path for an app launched without first
  being moved to `/Applications`) or otherwise sitting on a read-only volume. Verified: no
  `AppTranslocation`/`/Applications`-path check exists anywhere in the Swift source. Expected:
  the app detects this condition (e.g. `Bundle.main.bundlePath` containing `AppTranslocation`, or
  the volume not being writable) and tells the user to move it to Applications BEFORE offering to
  update, rather than letting Sparkle fail with a generic error.
- `release.update.sandboxed-installer-can-launch` — **[PARTIAL]** (#4901) the app is sandboxed on
  the DMG/Developer-ID channel too, not only the Mac App Store build (`FicheroRelease
  .entitlements` declares `com.apple.security.app-sandbox`, corrected 2026-08-27 per that file's
  own comment — a stale "only App Store builds are sandboxed" assumption is retired by this
  finding). Verified: `FicheroRelease.entitlements` carries
  `com.apple.security.temporary-exception.mach-lookup.global-name` for
  `app.fichero.fichero-spks`/`app.fichero.fichero-spki` — Sparkle 2's sandboxed installer/status
  XPC lookups — added specifically because this exact failure shape ("downloads fine, dies at
  'An error occurred while launching the installer'") already happened once, build 1 → 2. The
  exception strings are the LITERAL bundle id (not a build variable, since the DMG lane re-signs
  with this raw file and codesign substitutes nothing) and match the real
  `PRODUCT_BUNDLE_IDENTIFIER` (`app.fichero.fichero`) today. PARTIAL, not OK: correct today, but
  nothing would catch it silently going stale if the bundle id ever changes for any channel or
  variant — no guardrail compares the two.
- `release.update.an-update-is-proven-to-install-before-publishing` — **[GAP]** (#4901) no
  end-to-end check exists anywhere that an older installed build can actually update itself to
  the new DMG before that DMG is published. A real machine running an old build, attempting the
  live update, and confirming the new version launches is the genuine end-to-end proof and is
  not proposed here as automatable pre-publish (it needs a real, disposable macOS install).
  **Nearest automatable proxy**, not yet built: the four cheap, fully scriptable checks in
  `scripts/check_sparkle_update_ready.py` below — they cannot prove the install SUCCEEDS, but
  together they rule out every cause this review found evidence for or against, which is most of
  the realistic failure surface short of an actual translocated-app or Gatekeeper reproduction.

**Pre-publish checks that would have caught this — proposed, not yet written,
`scripts/check_sparkle_update_ready.py`:**
- The live feed's newest `sparkle:version`, fetched live (not from a local copy), is strictly
  less than the build about to publish — catches `release.update.feed-is-current` going stale
  AND `release.update.build-number-strictly-increases` colliding, in one comparison.
- The enclosure `length` in the appcast entry about to be written equals the actual built DMG's
  byte size on disk.
- The EdDSA signature verifies against the baked-in public key, computed on the DMG AFTER
  stapling (run `xcrun stapler validate` first; refuse to sign if it fails) — catches
  `release.update.signature-made-after-stapling` if the order is ever reordered.
- The feed URL baked into the built app's `Info.plist` (`SUFeedURL`) equals the appcast URL the
  release is about to publish to — `create-github-release.sh` already does this one; folding it
  into the same script keeps every update-readiness check in one place.

## Open questions

1. Which build was "the last release" the maintainer means — the one that shipped and then
   failed to update, on which machine? `~/Library/Logs/Autoupdate.log` on THAT machine names the
   actual cause; nothing in this repository can substitute for it.
2. **For the maintainer (#4912):** `check_mac_app_store_target` fails — the `Fichero (App
   Store)` target is missing from `project.pbxproj` entirely, verified long-standing, not a
   this-week regression. Is Mac App Store distribution still a near-term goal (in which case the
   target needs re-adding and #3340's HOLD on engine sandboxing needs revisiting), or has the
   DMG/Sparkle + TestFlight path superseded it for now? This spec currently describes three
   distribution outputs and doesn't mention MAS at all; not decided here.

## Rulings (design lead)

- **A same-day re-stamp gets ONE `RELEASE_NOTES.md` section, under the newer date.** When one
  calendar day ships twice (e.g. `2026.09.07` then `2026.09.08`, same build 3), the prose is one
  story: keep a single section for the newer date; the superseded date keeps only its GitHub release
  body. `CHANGELOG.md` is unaffected (it is per-day, not per-release).
- **`CHANGELOG.md` / `RELEASE_NOTES.md` are hand-resolved on merge, by union** — they hold authored
  content, not derived stamps, so they are *not* in the recreated-post-merge conflict-free set. A
  merge that touches both dates keeps both; the readiness gate (release lane, step 3) then confirms
  the shipping version's entries are present before anything is distributed.
