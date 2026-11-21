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

## The lane runs unattended (owner, 2026-11-14)

The 2026.11.14 release needed the manager by hand at eight points; each is now the lane's job.
The logic lives in `scripts/release_guard.py` (one subcommand per point) so it is tested;
`release-all.sh` only calls it.

- `release.lane.disk-checked-before-heavy-stages` — **[OK]** before the engine build, each DMG,
  each TestFlight archive and each export, free space is checked against
  `FICHERO_RELEASE_MIN_FREE_GB` (default 15). Short, it thins Time Machine local snapshots once
  (`tmutil thinlocalsnapshots / 40000000000 4`) and re-checks; still short, it refuses with the
  stage and the numbers. It never deletes DerivedData, DMGs or any other file. (Deleting a published release's local files is `release.build.local-artifacts-deleted-once-published`, after the publish, never here.) Was: default 20 GB; the owner set 15 GB on 2026-11-14 (#6590). *Test:* `fichero-server/tests/unit/scripts/test_release_guard.py`.
- `release.update.build-number-bumped-and-above-published` — **[OK]** a run that builds a DMG
  always stamps a new build number, pinned `FICHERO_RELEASE_VERSION` or not: one above both the
  local `CURRENT_PROJECT_VERSION` and every published build (the live appcast's
  `sparkle:version` values and the `(build N)` in each release tag's annotation). Before
  anything is built it refuses a build number not above every published one, and refuses when
  the live appcast cannot be read (blind is not green). A TestFlight-only or publish-only run
  keeps the build number of the DMG it goes with. *Test:* `fichero-server/tests/unit/scripts/test_release_guard.py`.
- `release.lane.ios-compile-preflight` — **[OK]** when iOS TestFlight is in the run, the
  preflight builds the iOS scheme for `generic/platform=iOS` with signing off, and refuses with
  the compiler's `error:` lines if it fails, before the engine or any DMG is built. *Test:* `fichero-server/tests/unit/scripts/test_release_guard.py`.
- `release.lane.upload-watchdog-continues` — **[OK]** each TestFlight export/upload runs under a
  watchdog: no output for `FICHERO_UPLOAD_IDLE_MINUTES` (default 30) kills it. A failed or
  killed TestFlight part is marked FAILED and the run goes on to the remaining parts (the other
  TestFlight, then the publish if requested); the run still exits non-zero. *Test:* `fichero-server/tests/unit/scripts/test_release_guard.py`.
- `release.lane.asc-key-materialised` — **[OK]** the preflight refuses an App Store Connect
  `.p8` that is missing; one that is an iCloud dataless placeholder is read once to download it
  and re-checked. *Test:* `fichero-server/tests/unit/scripts/test_release_guard.py`.
- `release.lane.smoke-before-publish` — **[OK]** before the GitHub release, each DMG to ship is
  checked: `xcrun stapler validate`, mounted read-only, `codesign --verify --deep --strict` and
  `spctl -a` on the app, and its `CFBundleShortVersionString`/`CFBundleVersion` equal the stamp.
  Any failure refuses the publish. *Test:* `fichero-server/tests/unit/scripts/test_release_guard.py`.
- `release.lane.notify-owner` — **[OK]** when a part goes live (the publish: GitHub release,
  appcast and site; Mac TestFlight; iOS TestFlight) and when any part fails, the owner is texted
  through Messages at the handle in `FICHERO_NOTIFY_IMESSAGE` (unset: no text). `osascript` runs
  in the background `with timeout of 30 seconds`, reading the message as UTF-8 from a file, so
  an AppleEvent timeout never blocks the lane. No handle is committed. *Test:* `fichero-server/tests/unit/scripts/test_release_guard.py`.
- `release.lane.summary-table` — **[OK]** however the run ends, it prints one line per part
  (Preflight, DMG, Mac TestFlight, iOS TestFlight, Publish; Engine when it fails) with
  OK, FAILED or SKIPPED and the reason; a part the run never reached shows SKIPPED, not reached. *Test:* `fichero-server/tests/unit/scripts/test_release_guard.py`.
- `release.lane.morning-release-token-free` — **[PARTIAL]** (#6585; owner 2026-11-14: "a token-free
  release each morning") a launchd LaunchAgent runs `scripts/morning-release.sh` at a set time
  (default 06:00 local; the plist template is `scripts/launchd/app.fichero.morning-release.plist`,
  installed by `scripts/install-morning-release.sh`, which nothing runs for the owner). No model
  or AI call is in it. It takes a lock (a second run while one is live exits at once), logs to
  `~/Library/Logs/Fichero/morning-release-<date>.log`, fetches origin, and when
  `origin/integration` has no commits since the newest `v*` release tag it texts "nothing new"
  and stops. Otherwise it cuts `release/<date>` from `origin/integration` in its own worktree,
  runs `release-all.sh` (date stamp, build bump and every guard above), and publishes only when
  the DMG part is OK and every DMG passes the smoke check; a failed DMG or smoke texts which
  part failed and stops before publishing. It publishes with `publish-release.sh` (pushes
  `release/<date>`, never `main`), opens the `release/<date>` → `main` PR with `gh`, and texts
  the summary table. The release-docs preflight still applies: a morning with no
  `RELEASE_NOTES.md` section for the day stops there and texts the failure. *Test:* `fichero-server/tests/unit/scripts/test_release_guard.py` covers the lock, the commit count, the publish gate, the publish hand-off (`guard publish` records Publish from `publish-release.sh`'s exit status) and, running the script itself against a stub guard, a count that fails stopping the run with a text. Not yet tested: the PR step, the preflight stop, the lock taken before its trap.

- `release.nightly.reliable-publish` — **[GAP]** (#6726; owner 2026-11-19) every night a dev DMG (GitHub, Sparkle, the site) and an iOS
  TestFlight build publish, and a Mac TestFlight build once signing is set up on the DMG host, run by a launchd job calling the
  builder's deterministic release-all and daily-builds, with no model tokens; a model is brought in only when a stage is red,
  and then a text says what is red. Stages, in order: (1) before the freeze, check every build machine (reachable, awake, free
  disk at or above the floor), pick one, and text the owner at 22:00 if none can run; (2) a per-machine sweep before the build
  frees space (DerivedData untouched for 7 days, build trees of commits already landed, device-support folders for iOS versions
  older than the newest two, old DMGs except the newest published and the last two, package caches past their size cap, and
  local Time Machine snapshots after files are removed), never the release's own DerivedData or the newest DMGs, keeps a floor
  (40 GB proposed), and texts when it cannot reach it; the release's disk check counts snapshots; (3) the verify stage runs
  with the engine importable and from the release candidate, not the live builder checkout; (4) a red stage texts what is red
  at once, and an unpublished DMG is never silent; (5) the red goes to the manager, who fixes it, and the nightly resumes from
  the failed stage instead of starting over. Cheaper runs: the Mac DMG and the iOS archive build in parallel on two Macs and
  publish when both are green; the separate iOS compile preflight is skipped when the same run archives iOS; the engine bundle
  is reused when the lock file and engine sources are unchanged since the last good build; Xcode builds incrementally in a kept
  DerivedData on the build Mac; one notarization covers the DMG with the app inside. Also open: the main branch's pull
  request and merge scripted. Test owed per stage.

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

- `release.update.feed-is-current` — **[PARTIAL]** (#4901) the public appcast
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
  **Re-tagged PARTIAL, 2026-09-27.** The first half of that cause is fixed, the second is not.
  `create-github-release.sh:165` now runs `check_sparkle_update_ready.py` as a BLOCKING
  pre-publish step under `set -e`, before signing or publishing anything, so a build that cannot
  actually reach a user — already in the feed, not strictly above the feed's maximum, a feed-URL
  or enclosure mismatch, an unreachable feed — fails the release instead of shipping; and
  `release-all.sh:811` runs `deploy-site.sh` by default straight after the GitHub step, so the
  publish is no longer a step someone has to remember. Pinned by
  `fichero-server/tests/unit/scripts/test_check_sparkle_update_ready.py`
  (`test_feed_url_mismatch_fails`, `test_enclosure_length_mismatch_fails`,
  `test_unreachable_feed_fails`, `test_exit_code_follows_the_verdict_not_ready`). NOT yet [OK]:
  `FICHERO_SKIP_SITE=1` still opts the deploy out, the check runs only on the releasing machine
  and never in CI, and nothing re-reads the live feed AFTER the deploy to confirm it landed. The
  check is a pre-flight, not a receipt.
- `release.update.build-number-strictly-increases` — **[PARTIAL]** (#4901) Sparkle
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
  **Re-tagged PARTIAL, 2026-09-27.** Forward monotonicity IS now enforced against the live feed:
  `check_build_number_increases` fails a build equal to or below the feed's maximum, and the
  per-channel subtlety above was honoured — `test_fail_gate_uses_the_global_maximum_across_every_
  channel` and `test_a_public_dev_pair_is_not_reported_as_a_duplicate_or_a_collision` pin both
  halves, so the intentional public/dev pair does not false-positive. What stays imperfect is
  historical and permanent: the `2026.09.04`/`2026.09.05` collision already sits in the feed and
  cannot be un-shipped, so by design it is reported as a WARNING and never fails a release
  (`test_real_collision_between_two_releases_warns_and_does_not_fail`).
- `release.update.signature-made-after-stapling` — **[PARTIAL]** (#4901) an EdDSA signature must
  be computed AFTER `xcrun stapler staple`, since stapling modifies the file and a
  pre-staple signature would no longer verify. Verified BY READING, not by a test or script
  check: `release-all.sh` runs `build-release-dmg.sh` → `notarize.sh "$DMG_PATH"` (which staples
  the DMG itself) → only then `create-github-release.sh` (which calls `sign_update` on that same,
  already-stapled `$DMG_PATH`) — the correct order, today, in the scripts as checked in. PARTIAL,
  not OK, because no automated check pins this order; a future edit could reorder these steps (or
  a manual/partial release run could skip `notarize.sh`) with nothing to catch it before a
  broken signature ships.
- `release.update.appcast-item-insert-is-idempotent` — **[PARTIAL]** (#4901) re-running the appcast
  step for the SAME release must not append a duplicate item. An item's true identity is the
  triple (`sparkle:version`, `sparkle:shortVersionString`, channel) — NOT version+build alone,
  because every release legitimately produces TWO items sharing the same version and build
  number: a channel-less public item and a `<sparkle:channel>dev</sparkle:channel>` item
  (`SparkleChannelDelegate` scopes the dev item to dev builds only). A first fix attempt keyed on
  version+build only was considered and REJECTED before it was ever committed, because a re-run
  would have matched and replaced the WRONG item — overwriting the public item with the dev
  item's enclosure/signature, or vice versa, silently pointing one channel's users at the other
  channel's DMG. **Read from the code, not the tag, 2026-09-27:** this line was stale — the fix
  landed. `create-github-release.sh` now calls `scripts/appcast_upsert.py`'s `upsert_item()`,
  keyed on the (version, short_version, channel) triple, for both the public and dev calls in its
  appcast-update step. `upsert_item()` is proven idempotent against the real public-then-dev
  sequence, including a rerun producing byte-identical output and each channel never touching the
  other's item
  (`fichero-server/tests/unit/scripts/test_appcast_upsert.py::test_the_real_public_then_dev_sequence_yields_two_items_public_still_present`,
  `::test_rerunning_the_real_sequence_yields_the_same_two_items_byte_identical`). Stays
  `[PARTIAL]` rather than `[OK]`: `create-github-release.sh` itself is never run in CI (per that
  test file's own header), so this is proven at the pure-function level, not end-to-end against
  the real script.
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
- `release.update.an-update-is-proven-to-install-before-publishing` — **[GAP]** (#2582, #4901) no
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

## Release scope (owner ruling 2026-10-20)

The next release is about three things, in this order; lane work is sorted by it:

1. **Recipes with cloud AND local models.** Set Up recommends a reader wisely, weighing frontier models (Claude,
   Gemini) with local ones on the project's own Try pages, with cost per page and per set
   (`source.recipe.reader-tiers.frontier-on-the-try-pages`, #5922); the bake-off is the first evidence.
2. **Sharing**, between the owner's own Macs and with other people (the bar below, #5910).
3. **Tahoe (macOS 26)**: APIs that exist only on macOS 27 are availability-gated, and the app launches and runs on
   26 (#5730).

After the release, in this order: the ACENet cluster and Hugging Face training working end to end, then the iPhone.

- `release.scope.three-goals` — **[GAP]** (#5910, #5922, #5730) the release ships when goals 1-3 are met;
  goal 2 is met by the sharing release bar below.

## Release bar: sharing (owner ruling 2026-10-20, #5910)

The next release ships only when sharing works solidly. Every item below needs all three before it
is ticked: (1) a spec line in the sharing specs, (2) an automated test with two engines (a host on a
test listen port and a guest, both on throwaway libraries; the harness is #5911, not built yet), and
(3) one live two-Mac try by the owner, recorded with its date. The release lane refuses to publish
while any box is open.

- `release.bar.sharing` — **[GAP]** (#5910; harness #5911)
  - [ ] Own Mac pairs over `.local` (spec: `sharing.mac-pairs`, `sharing.listener`, #5049, #5736, #5897)
  - [ ] Own Mac pairs over Tailscale (spec: `sharing.tailscale-serve`, #5902)
  - [ ] The M4 connects and renames sync both ways (spec: `sharing.two-macs-end-to-end`, `sharing.edits-both-ways`, #5049)
  - [ ] Remove works: a removed device is refused at once (spec: `sharing.revoke`, `sharing.revoke-cascades`, #5351)
  - [ ] Turning Multi-user on asks for the owner's password first (spec: `multiuser.turning-on-needs-an-owner-password`, lands with m-bugs-pairing-proper; #5908)
  - [ ] Two named people pair as themselves through person-bound invites (spec: `sharing.invite`, `multiuser.invite-registers-public-key`, #2403)
  - [ ] Activity reconnects after a Sharing switch (spec: `sharing.toggle-restarts-engine`, #5912)
  - [ ] No engine death on any Sharing or Multi-user switch (spec: `sharing.toggle-restarts-engine`, #5909)
  - [ ] Another person sees only what the owner shared with them: a project or a folder in it, chosen on its Share… sheet (spec: `sharing.share-sheet-chooses-what`, #5967; owner ruling 2026-10-20)
- `release.scope.next-release` — **[CONVENTION]** (#5910; owner ruling 2026-10-20) the next release is (1) recipes with cloud and local models, (2) sharing between the owner's own Macs and with other people (the bar above, #5910), and (3) Tahoe: macOS 26.0 is the floor, APIs only macOS 27 has are availability-gated, and the first launch on macOS 26 is on a Tahoe Mac after the release (no Mac here runs Tahoe). After it, in this order: local models working properly (Kraken, MLX, spaCy), then Hugging Face, then ACENet (Canadians and the owner), then the iPhone. Test: n/a (a plan; the release lane checks the bar above).

## Open questions

1. Which build was "the last release" the maintainer means — the one that shipped and then
   failed to update, on which machine? `~/Library/Logs/Autoupdate.log` on THAT machine names the
   actual cause; nothing in this repository can substitute for it.
2. ~~**For the maintainer (#4912):** is Mac App Store distribution still wanted?~~ **Answered
   2026-10-04** (#4988, #5068): yes, the target is restored. See Rulings and
   `release-channels-and-feature-tiers.md` (`channel.app-store-target-builds`).

## Rulings (design lead)

- **A same-day re-stamp gets ONE `RELEASE_NOTES.md` section, under the newer date.** When one
  calendar day ships twice (e.g. `2026.09.07` then `2026.09.08`, same build 3), the prose is one
  story: keep a single section for the newer date; the superseded date keeps only its GitHub release
  body. `CHANGELOG.md` is unaffected (it is per-day, not per-release).
- **`CHANGELOG.md` / `RELEASE_NOTES.md` are hand-resolved on merge, by union** — they hold authored
  content, not derived stamps, so they are *not* in the recreated-post-merge conflict-free set. A
  merge that touches both dates keeps both; the readiness gate (release lane, step 3) then confirms
  the shipping version's entries are present before anything is distributed.
- **2026-10-04 (maintainer, #4912, #4988, #5068): the Mac App Store target is restored.** The
  `Fichero (App Store)` scheme builds again and its guardrails (`check_mac_app_store_target`)
  stay; the Mac App Store is a distribution output again (`release.mas.sandboxed-build`).

### Release defaults (owner, 2026-11-14, #6590)

- `release.lane.notes-auto-generated` — **[OK]** when `RELEASE_NOTES.md` has no `## <version>` section, or `CHANGELOG.md` no entry for the day, `release_guard.py auto-notes` writes them (#6728) from the record since the newest `v*` tag that is not `v<version>`, with an intro that says "since <that last release>", grouped by milestone (the sections are specified in `release-channels-and-feature-tiers.md`, "Release notes"); `release-all.sh` runs it before the stamp and before the release-docs preflight, with the version from `set-release-version.sh --print-version`. The stamp only checks that `RELEASE_NOTES.md` has a `## <version>` section and fails when it does not; it never retitles another section. A hand-written section is never touched, and a hand-written `## Unreleased` in `CHANGELOG.md` becomes the day's entry. *Test:* `fichero-server/tests/unit/scripts/test_release_guard.py`.
- `release.lane.daily-builds-dev-dmg-only` — **[OK]** the morning release runs `release-all.sh --dev` and builds one DMG, the dev tier, named `Fichero.dmg` (a single-tier run always names its DMG `Fichero.dmg`); the two-DMG default stays for a hand run. That DMG is published on the `dev` Sparkle channel only (`FICHERO_RELEASE_CHANNEL=dev`: its appcast item carries `<sparkle:channel>dev</sparkle:channel>`, no channel-less item is written), so Alpha, Beta and Release installs are never offered it (`release-channels-and-feature-tiers.md`, "One feed, two channels"). `FICHERO_MORNING_ARGS` can change the flags. *Test:* `fichero-server/tests/unit/scripts/test_release_guard.py`.
- `release.queue.two-workers` — **[OK]** `harness.toml` `[queue] workers = 2`. *Test:* `fichero-server/tests/unit/scripts/test_release_guard.py`.
- `release.lane.site-deploy-triggers-netlify` — **[OK]** `deploy-site.sh` posts to the Netlify build hook in `FICHERO_NETLIFY_BUILD_HOOK` after the push (unset: it says so and relies on the push). *Test:* `fichero-server/tests/unit/scripts/test_release_guard.py`.
- `release.lane.live-appcast-verified` — **[OK]** the run texts success for the publish only after `release_guard.py verify-appcast` finds the new build in the live appcast (retried for `FICHERO_APPCAST_WAIT_MINUTES`, default 10); if it never appears, Publish is FAILED. *Test:* `fichero-server/tests/unit/scripts/test_release_guard.py`.
- `release.lane.notarize-poll-failed-call-not-in-progress` — **[OK]** in `notarize.sh` a `notarytool info` call that fails or returns no status is never read as "In Progress": the poll switches to the App Store Connect API key, and gives up after 5 failed calls in a row. Test: `fichero-server/tests/unit/scripts/test_notarize_poll.py`.

### Builds and disk (owner, 2026-11-19 and 2026-11-20, #6589)

A full disk stopped the night of 2026-11-19 more than once: each lane's checkout held its own app build and its own
engine build, and every release left its DMGs, archives and staging folders behind. The rulings below (paraphrased)
make the nightly the only build and give every byte it writes an owner that deletes it. Here "build" means a packaged
app (a DMG or an archive); the compile rung of a check (`dev-workflows.run.build-incremental`) is a check and stays.
Spec-change: owner 2026-11-20.

- `release.build.nightly-is-the-only-build` — **[PARTIAL]** (#6589) the one packaged build is the nightly dev release
  (`dev-workflows.run.nightly-build`, `dev-workflows.run.release-stages`). The builder never makes a dev build for a
  lane or for a landing. A dev build made by hand on request stays (`builder build --dev`, `dev-workflows.tool.build`).
  Built: the loop starts no dev build after a landing (`fichero-builder/fichero_builder/queue.py`; the nightly replaced
  it). Left: no test holds it, the console still offers a build action
  (`fichero-builder/fichero_builder/console.py`), and `builder verify-all` builds a dev DMG after a green verify when
  asked to. Acceptance: no loop tick and no lane verb starts `release-all.sh` or `builder build`; only the nightly
  agent and a person's own command do.
- `release.build.release-holds-the-heavy-lock` — **[GAP]** (#6589) a release takes the heavy lock
  (`dev-workflows.run.heavy-lock`) on each Mac it builds on, for the whole of its build stages, and does not yield it:
  no check's compile, no dev build and no second release builds through it. Today the stages in
  `fichero-builder/fichero_builder/release_run.py` call `scripts/release-all.sh` with no heavy lock, and
  `builder build --dev` holds it for the compile only and yields to a waiting check. The release's own lock (a second
  release run exits at once) stays. Acceptance: with a release stage running, a check that needs the compile waits and
  its row names the release; a release that finds the lock held waits, with a row, and does not build beside it.
- `release.build.local-artifacts-deleted-once-published` — **[GAP]** (#6589) once a release is verified on GitHub (the
  asset is there and `release.lane.live-appcast-verified` is green), its local DMGs, archives, export folders and
  staging are deleted, and so are those of every older release, on every Mac that built or smoked it. GitHub is the
  copy. Nothing is deleted before the verify, and a failed publish deletes nothing. Was: releases never deleted a DMG
  (owner 2026-11-13); the disk check of `release.lane.disk-checked-before-heavy-stages` still deletes none. Today
  `release-all.sh` removes an archive or export folder only just before it writes the same one again, and the `sweep`
  stage removes its own clone folders. Acceptance: after a green publish no DMG, archive or export folder of this or
  an older release is left under the build folders of any release Mac, and a `release` row lists what was removed and
  the space freed; after a red publish every file is still there.
- `release.build.one-engine-build-per-mac` — **[GAP]** (#6589) each Mac keeps one engine (Briefcase) build, shared by every
  checkout on it and keyed by the engine's sources and lock file, in place of a copy in every checkout. A checkout
  whose key matches uses it; one writer at a time rebuilds it. Today each checkout builds and keeps its own
  (`scripts/release-all.sh`, `scripts/build-release.sh`). Acceptance: two checkouts at the same engine sources build
  the engine once and the second reuses it; a changed lock file rebuilds it once.
- `release.build.disk-floor-before-a-lane-and-a-stage` — **[PARTIAL]** (#6589) free disk is checked against a floor before
  a lane starts and before each release stage. Built: the release stages
  (`release.lane.disk-checked-before-heavy-stages`), the nightly's choice of a Mac over `--floor-gb`
  (`fichero-builder/fichero_builder/release_run.py`), and a check runner under its floor is skipped
  (`fichero-builder/fichero_builder/measure.py`). Left: the loop starts a lane, and makes its worktree, without reading
  free disk. Acceptance: under the floor a lane's step stays `queued` with one row that names the free space and the
  floor; it starts by itself when the disk is back over it.
- `release.build.snapshots-thinned-before-refusing` — **[PARTIAL]** (#6589) on a full Mac, Time Machine local snapshots
  keep deleted files on disk, so deleting frees nothing until they are thinned. A floor check that falls short thins
  them once and reads free space again before it refuses. Built: the release disk check and the `sweep` stage on the
  Mac that runs it. Left: the lane floor above, and the other Macs of a release. Acceptance: as for
  `release.lane.disk-checked-before-heavy-stages`, for the lane floor and on each release Mac.
- `release.build.indexes-and-caches-pruned` — **[GAP]** (#6589) what a worktree leaves outside itself is removed with it:
  its code index, its derived build data and its entry in any tool's per-folder cache. Package caches (the Python and
  Swift package caches) are pruned nightly to what the current lock files name. Today
  `dev-workflows.run.loop-cleanup` removes the worktree and its branch only. Acceptance: after a lane's tree is
  removed no index or build folder names its path; the nightly prune is a row with the space freed.
- `release.build.nightly-report-lists-build-folders` — **[GAP]** (#6589) the nightly report lists, per Mac, free disk and
  the size of each build folder (derived data, engine build, release staging, DMGs, check trees, worktrees), largest
  first, so growth is seen the morning it starts. Acceptance: the report of a night has one size line per build
  folder per reachable Mac, and an unreachable Mac is named as not read.

## Triaged from the backlog (2026-10-04)
- `release.license-hygiene` — **[GAP]** (#4610) zeroconf LGPL, pillow-heif codec wheels, PythonKit branch pin, undeclared whisper and the NOTICE inventory are resolved so the SBOM is accurate.
- `release.dmg-container-signed` — **[GAP]** (#4704) release-all codesigns the DMG with the Developer ID Application identity before notarization so spctl accepts the disk image.
- `release.lane.github-before-testflight` — **[OK]** (#4272) the GitHub release (tag, notes, DMG, appcast) publishes as soon as the DMG staples, before the App Store/TestFlight leg. Built (#6590, owner 2026-11-14): `release-all.sh` runs the publish part right after the DMG is built and smoked, then the Mac and iOS TestFlight parts; a failed publish is marked FAILED and TestFlight still runs; the morning release publishes first and runs TestFlight in a second `--skip-dmg` pass. *Test:* `fichero-server/tests/unit/scripts/test_release_guard.py`.
- `release.gate.ready-for-first-real-user` — **[GAP]** (#4421) the Ann gate checklist (no data loss, no 'what on earth' moments, ...) is a named release gate with its evidence.
- `release.update.announces-in-app-not-a-window` — **[GAP]** (#4433) an available update shows as a quiet in-app indicator, never a modal over the user's work (SparkleUpdater.swift uses the standard driver, no gentle reminders).
- `release.verify-embedded-launch-local-signing` — **[GAP]** (#4333) scripts/verify_embedded_launch.sh packages the engine with ad-hoc signing (or a resolvable identity) instead of failing on a UUID-form identity's Team ID.
- `release.mas.sandboxed-build` — **[GAP]** (#3340) a Mac App Store build is sandboxed on the app and the embedded engine with Sparkle stripped; only the entitlements foundation has landed, the MAS target and sandboxed-engine check are not wired.

## Future (ideas, not scheduled)
- (#4255) Trademark notice is in LICENSING.md:20; formal wordmark registration is an external legal step, not code.
- (#4273) Release speed pass (shared SPM derived data, parallel Apple round-trips); optimisation, not behaviour.
- (#2584) Split local-ML deps into an optional plugin pack to slim the bundle; optimization, not scheduled
- (#2663) Replace Python image/PDF deps with native Apple APIs to shrink the embedded engine; bundle-size optimization
- (#2865) In-process CPython embedding on iOS/iPad (PEP 730) needs wheels for lancedb/duckdb; a future epic, blocked on dependencies.
- (#2878) tvOS target with focus-based UX; depends on iOS embedding (#2865), future milestone.
