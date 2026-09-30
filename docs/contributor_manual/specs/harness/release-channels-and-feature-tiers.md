# Release Channels & Feature Tiers — Design Spec (#5299)

> Milestone: release-channels
> Manual: TBD — the user manual must explain the Update channel choice in Settings › General: what
> each channel shows, what it receives, and that a channel change never installs an older build.
>
> Design-led. **Status: DRAFT — awaiting the design lead's rulings before tests or code.**
> Written 2026-09-30 from the files themselves (every claim in "How it works today" was read from
> the cited file that day). Companion to [`release-and-versioning.md`](release-and-versioning.md),
> which owns version stamps, the release lane's steps and `release.update.*`. This spec owns
> WHICH build a person runs, WHICH features it shows, and WHICH updates it is offered.
> SPEC issue #5299. Behaviors cite #5287, the defect that started this, until each gets its own.

## Intent (the design)

Today Fichero is built once per feature tier: a Dev build, an Alpha build, a Beta build, a Release
build, each a separate Xcode configuration, and two of them leave the lane as separate disk images.
The tier a person sees is decided when the binary is compiled. A tier nobody runs rots unseen:
#5287 is a Release build that shows a workflow bar and can never load a workflow.

The direction (design lead, 2026-09-30): **one app, and a choice inside it.** Settings › General
carries "Check for updates automatically" and an **Update channel** popup (Release, Beta, Alpha,
Dev), the way Jetty Pro and most Sparkle apps offer Release and Beta. The channel decides two
things together: which features the app shows, and which published builds it is offered. There is
one disk image to build, sign, notarize, test and publish.

The surface lives in `features.yaml` (the tier of each feature), `FeatureManager` (the rule),
`SparkleUpdater` (the channel), `GeneralSettingsView` (the control), the engine's tiered route
registration in `api/main.py`, and `scripts/release-all.sh` with its helpers.

## Prior art / best practices (don't invent from scratch)

- **Sparkle channels** are the established mechanism and are already in use here. An appcast item
  with no `<sparkle:channel>` is offered to everyone; an item tagged with a channel is offered only
  to apps whose `SPUUpdaterDelegate.allowedChannels(for:)` contains it. One feed, many channels.
  We adopt this unchanged and widen it from two channels to four.
- **Sparkle never installs an older build.** It compares `CFBundleVersion` and offers only a
  higher one. Moving to a more stable channel therefore waits for that channel to catch up. Every
  app with a Release/Beta popup behaves this way (Jetty Pro, Transmit, BBEdit previews, iTerm2
  "beta updates"). We adopt it, and it is also what protects a library: an older binary never
  opens a library a newer one has migrated.
- **Feature flags resolved at run time from one binary** is the ordinary practice (Chrome and
  Firefox channels ship one code base; Xcode and Safari Technology Preview are the counter-example
  of separate binaries). The Swift side here is already run-time: every feature's code is in every
  configuration; the tier is one string read from `Info.plist` at launch.
- **The Mac App Store and TestFlight are Apple's channels.** An App Store build may not carry a
  self-updater and cannot change where its updates come from. TestFlight is the App Store's beta.
  We do not reinvent a channel switch there.
- What we deliberately do differently: the channel also selects the visible feature set. Most
  apps' channels differ only in build freshness. Here the same build serves every channel, so
  the feature set is the main thing a channel changes.

## How it works today (2026-09-30)

### Builds

- One Mac app target, `Fichero`, bundle id `app.fichero.fichero` in every configuration. Five
  build configurations, each baking a tier into `Info.plist` key `FicheroFeatureTier`
  (`fichero/fichero/Info.plist:33`, from build setting `FICHERO_FEATURE_TIER`):

  | Scheme | Configuration | Tier | Sandbox | Engine | Optimised |
  |---|---|---|---|---|---|
  | Fichero (Dev Local) | Debug | dev | no | external | no |
  | Fichero (Dev Embedded) | Dev Embedded | dev | yes | embedded | no (`-Onone`) |
  | Fichero (Alpha Embedded) | Alpha Embedded | alpha | yes | embedded | yes |
  | Fichero (Beta Embedded) | Beta Embedded | beta | yes | embedded | yes |
  | Fichero (Release Embedded) | Release | release | yes | embedded | yes |

  The release scripts override optimisation for whatever they package (`scripts/build-release.sh`),
  so a shipped Dev disk image is optimised even though the Dev Embedded configuration is not.
- A sixth scheme, `Fichero (App Store)`, points at a target that is not in the project (#5121,
  #4912). `FicheroAppStore.entitlements` and `FicheroEngineAppStore.entitlements` exist and are
  referenced by nothing.
- No iOS scheme is checked in. `scripts/tier_build_map.sh` names iOS schemes and configurations
  (`Fichero (Release Local iOS)`, `Release Local`, `Beta`, `Alpha`) that do not exist in the project.

### Feature tiers

- `features.yaml` lists 54 features, each with one tier: dev (1), alpha (2), beta (3),
  release (4). `scripts/gen_feature_tiers.py` writes the Swift map, the Python map and
  `docs/reference_manual/features.md`. `scripts/check_features_freshness.py` holds them equal.
- **The rule:** a feature is visible when its tier's rank is at or above the build's
  (`FeatureManager.isVisible`, `FeatureManager+Accessors.swift:96`). A Dev build sees all 54; a
  Release build sees only the release-tier ones.
- **The build's tier is resolved once at launch:** `Info.plist`, then the environment variable
  `FICHERO_FEATURE_TIER` only if the plist value is unusable, then `release` (fail closed).
  `testTierOverride` is the only other seam and nothing in the app sets it.
- **There is no run-time or user-facing switch.** `allFeaturesEnabled` and the per-feature
  `fichero.features.*` defaults are ANDed with the tier and cannot raise it; no Settings control
  binds to either.
- **The engine has the same tiers.** The app passes its tier to the engine it spawns
  (`EmbeddedBackendService+Spawn.swift:331`). The engine registers its 21 gated route groups once,
  at import, for that tier, and answers a hidden group with 404 `feature_tier_gated`
  (`api/main.py`, `feature_tiers_generated.py`). Unset, the engine defaults to `release`; the
  developer start script defaults to `dev`.
- **What a Release build lacks.** The release tier holds library, reader, ingest, search,
  run-on-selection and the two canvas renderers. It does not hold workflows, providers, activity,
  batches, the workflow file tools, the knowledge graph, curation, or the Settings General tab.
  A Release build therefore cannot transcribe a page, and cannot show the pane this spec puts the
  channel control in.

### Updates

- Sparkle is linked into the one app target, so every configuration carries it. One feed:
  `https://tubb.ca/apps/fichero/appcast.xml`. One signing key.
- **One feed, two channels** (ruling of 2026-08-25): public items carry no channel; dev items carry
  `<sparkle:channel>dev</sparkle:channel>`. A Dev-tier build allows the `dev` channel; Alpha, Beta
  and Release builds allow none and see only the public items (`SparkleUpdater.swift:32`). The
  channel is captured once at launch from the baked tier.
- Settings › General already has a Software Update section: two toggles (check automatically,
  download and install automatically), the version, and Check Now. The File menu has Check for
  Updates. There is no channel control.

### The release lane

- `scripts/release-all.sh` with no tier flag builds **two disk images**: `Fichero-dev.dmg` (dev
  tier) and `Fichero.dmg` (alpha tier, the public download since 2026-09-04), and archives
  TestFlight at the dev tier. `--dev` or `--tier <t>` builds one.
- `scripts/tier_build_map.sh` maps a tier to a scheme and configuration. Each image is built,
  re-signed, notarized and stapled separately.
- `--github` publishes: the GitHub release, the Sparkle signature, the appcast items (public, and
  `dev` when the dev image exists) through `scripts/appcast_upsert.py`, then the site deploy.
- No default run builds a Beta or a Release image. Nothing anyone installs is at those tiers.

## Where the code and the write-ups disagree

Read from the files on 2026-09-30. Each line is a defect of its own; the ones this design
removes are marked (design).

**The tiers and what ships**
1. Workflows are `beta`; the Release configuration is `release`; the workflow bar is not gated, so
   a Release build shows an empty bar that blames the selection (#5287). (design)
2. `FeatureManager.resetToV001()` turns on 22 features that the tier then hides in a Release
   build (nine beta, twelve alpha, one dev). `AGENTS.md` says what ships is decided by
   `resetToV001()`; the code ANDs it with the tier. `FeatureManagerTests
   .testV001DefaultsDisableOffTierSurfaces` is skipped on exactly this (#3917, #252), and its skip
   message calls five surfaces beta when only one of them (batches) is. (design)
3. `docs/contributor_manual/feature-tiers.md` defines alpha as the maintainer's review queue, beta
   as tester-facing and release as publicly shipped. The lane's public download is alpha, and
   TestFlight is dev. The same page says the app defaults to `.dev` when the tier is
   unresolvable; the code returns `.release`. Its two line references are stale.
4. `scripts/release-all.sh` calls the public image alpha in three places and beta in three others;
   `build-release-dmg.sh` says beta; `create-github-release.sh` says alpha.
5. The release-size ratchet runs only when a beta or release image was built
   (`release-all.sh:496`). The default run builds dev and alpha, so the ratchet never runs in the
   lane. (design)
6. Comments in `api/main.py` say the knowledge-graph routes were promoted to core and that
   research, integrations, MCP servers, schedules, triggers and IIIF were promoted to release. The
   generated map has them at beta, dev and alpha.
7. `architecture/fichero-server/overview.md` and `architecture-overview.md` describe two tiers.
   There are four.

**Targets, schemes, scripts**
8. The App Store scheme has no target (#5121). `tier_build_map.sh` and `release-all.sh` depend on
   it for Mac TestFlight, and `tier_build_map.sh` picks Dev/Alpha/Beta Embedded configurations for
   a scheme whose every action uses Release.
9. The iOS schemes and configurations `tier_build_map.sh` names do not exist.
10. `release-all.sh` calls `scripts/wait-testflight-processing.py`; the file does not exist.
11. Two names for one compile flag: `FicheroApp.swift` hides Check for Updates behind
    `!APP_STORE`; the engine code and both guards use `FICHERO_APP_STORE`. The project defines
    neither.
12. `create-github-release.sh`, `nightly-release.sh` and `smoke-release-embedded-backend.sh`
    hard-code `Products/Release/Fichero.app`; the default lane builds under `Dev Embedded` and
    `Alpha Embedded`. (design)
13. `create-github-release.sh` says the appcast step only commits and that pushing the site is the
    maintainer's step; `release-all.sh --github` then runs `deploy-site.sh`, which pushes.
    `release-and-versioning.md` says the lane does not self-publish.

**Sparkle**
14. `SparkleUpdater.swift` and `GeneralSettingsView.swift` say Xcode runs carry no feed. Debug and
    Dev Embedded both set the feed URL, so the Software Update section shows in them.
15. `SparkleLinkageTests` is titled as proving Sparkle is linked only where it should be; it does
    not check the App Store exclusion the guard requires.

**Docs of the lane**
16. `release/release-lane.md` and `AGENTS.md` describe one disk image and never mention the second
    image, `--dev` or `--tier`. (design)
17. `AGENTS.md` and `guide/17-the-release-lane.md` say the image build stamps a `-beta` version;
    it does so only when `FICHERO_RELEASE_BETA=1`.
18. `specs/testing/xcode-build-configs.md` (APPROVED) lists three scheme rows; there are five Mac
    schemes. `check_xcode_config_invariants.py` says it checks App Store configurations and
    does not.
19. Three entitlements files carry comments that are no longer true of the files they describe.

## Behaviors (the proposal)

Tags: [OK] built · [PARTIAL] partly built · [MISSING] not built. Nothing below is approved.

### One app

- `channel.one-shipping-binary` [MISSING] (#5287) — the lane builds ONE Mac disk image,
  `Fichero.dmg`. It is optimised, sandboxed and signed the same way whatever channel it is
  published to. `Fichero-dev.dmg` and the per-tier Embedded configurations retire; `Debug`
  (Dev Local) stays for development and is never shipped.
- `channel.the-build-carries-a-default-channel` [PARTIAL] (#5287) — the binary's `Info.plist`
  names the channel a fresh install starts on. Today that key is the whole tier; it becomes only
  the default. The public download's default is Alpha until the design lead moves it.
- `channel.the-choice-is-in-settings` [MISSING] (#5287) — Settings › General › Software Update
  has an **Update channel** popup: Release, Beta, Alpha, Dev, in that order, under "Check for
  updates automatically". One line beneath says what the chosen channel is in plain words.
- `channel.the-choice-persists` [MISSING] (#5287) — the chosen channel is stored per user and
  survives updates. A stored value that is not one of the four falls back to the binary's default.
- `channel.the-settings-pane-is-in-every-channel` [MISSING] (#5287) — the General pane and the
  Software Update section are visible on every channel. A person on Release can always reach the
  control that changes it. (Today the General tab is a beta feature.)

### What a channel shows

- `channel.features-follow-the-channel` [MISSING] (#5287) — the visible feature set is
  `features.yaml` read against the chosen channel, by the existing rank rule. No second rule.
- `channel.a-change-takes-effect-on-relaunch` [MISSING] (#5287) — changing the channel does not
  re-draw the running app or restart a running engine. The pane says the change applies when
  Fichero next opens and offers Relaunch Now. Running work is never interrupted by a channel
  change. (Why: the tier is read on hot paths and resolved once; the engine registers its routes
  once at start.)
- `channel.the-engine-runs-at-the-apps-channel` [OK] — the app hands its tier to the engine it
  spawns. Unchanged, except that the value now comes from the chosen channel.
- `channel.release-is-a-whole-app` [MISSING] (#5287, #3917) — on the Release channel a person can
  import, transcribe, search and read, and can reach Settings. `features.yaml` is re-graded so
  that holds. Which features move is a ruling (open question 1).
- `channel.an-empty-surface-names-the-channel` [PARTIAL] (#5287) — a surface that is present but
  empty because of the channel says so and names the channel that has it. The workflow bar's
  interim text is "Workflows are not in this build" (in the working tree, uncommitted).

### What a channel receives

- `channel.one-feed-four-channels` [PARTIAL] (#5287) — one appcast. A published build's item
  carries the least stable channel it has reached: `dev`, `alpha`, `beta`, or no tag for Release.
  Today only `dev` and no-tag exist.
- `channel.each-channel-sees-itself-and-the-more-stable` [MISSING] (#5287) — Release allows no
  channel; Beta allows `beta`; Alpha allows `alpha` and `beta`; Dev allows `dev`, `alpha` and
  `beta`. Everyone sees untagged (Release) builds.
- `channel.a-build-is-promoted-not-rebuilt` [MISSING] (#5287) — moving a build to a more stable
  channel re-tags its one appcast item. The bytes, the build number and the signature do not
  change. A build has one item, never one per channel.
- `channel.no-downgrade` [OK] — a channel change never installs a lower build number. Moving to a
  more stable channel keeps the installed build and hides the features; the next update is the
  first build on that channel with a higher number. (Sparkle's own rule; the spec relies on it
  and the pane says it.)
- `channel.a-less-stable-channel-checks-at-once` [MISSING] (#5287) — after a move to a less
  stable channel, the next update check uses the new channel without a relaunch.
- `channel.installed-builds-carry-over` [MISSING] (#5287) — the alpha and dev builds already
  installed only see untagged and `dev` items. The first single build is published once untagged
  so both can reach it; after that update each install is on its binary's default channel.

### App Store, TestFlight, iOS

- `channel.app-store-has-no-channel` [MISSING] (#5121) — the Mac App Store build links no Sparkle,
  shows no Software Update section and no channel popup, and ignores a stored channel. Its
  features are its baked tier. Apple delivers its updates; TestFlight is its beta.
- `channel.ios-is-baked` [PARTIAL] (#5287) — iPhone and iPad builds have no updater and no popup.
  Their tier is the one baked at archive time.

### The lane

- `channel.the-lane-publishes-to-a-channel` [MISSING] (#5287) — `release-all.sh` builds the one
  image and, when told to publish, takes the channel to publish to. The standing rule holds: the
  notarized image goes to the maintainer first, and publishing is a separate step after his verdict.
- `channel.promotion-is-one-command` [MISSING] (#5287) — promoting a published build to a more
  stable channel is one script that edits the appcast item and nothing else.
- `channel.the-size-ratchet-runs-on-the-one-image` [MISSING] (#5287) — the release-size ratchet
  measures the image the lane built, on every run.

## Alternative considered: a binary per channel behind one feed

Keep separate builds (today's shape) and let the popup choose which one Sparkle fetches.

- For: a Release binary cannot be switched to show unfinished features; each binary could differ
  in more than features.
- Against: four builds to notarize and test where there is time for one; on the 8 GB development
  Mac one clean build took 21 minutes. A channel change would replace the binary, which is a
  downgrade whenever the target channel is behind, and Sparkle does not do that. The tier
  nobody runs rots, which is how #5287 happened. The binaries do not in fact differ: all feature
  code is in all of them.

Recommendation: one binary.

## Test matrix

Tests are written after the rulings. This is what would pin the design.

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | stored channel beats the binary's default; an unknown value falls back; App Store ignores it; fail closed is still Release | `fichero/Tests/Unit/general/Models/UpdateChannelTests.swift` |
| Pure rule (Swift) | y | the allowed Sparkle channels for each of the four | same |
| Pure rule (Swift) | y | Release is a whole app: the named core features are visible on Release | `FeatureManagerTests.swift` (un-skip `testV001DefaultsDisableOffTierSurfaces`) |
| Availability (Swift) | y | the popup exists when Sparkle is available and not otherwise; General is reachable on every channel | `fichero/Tests/Unit/general/Views/Settings/…` hosting the real pane |
| Backend (pytest) | y | the engine's route set per tier after the re-grade | `fichero-server/tests/unit/api/test_feature_tier_routing.py` |
| Backend (pytest) | y | appcast promotion re-tags one item; four channels are not duplicates; build numbers stay monotonic | `tests/unit/scripts/test_appcast_upsert.py`, `test_check_sparkle_update_ready.py` |
| Backend (pytest) | y | the lane builds one image; the ratchet runs on it | `tests/unit/scripts/test_release_scripts.py` |
| MCP | n | | |
| CLI | n | | |
| Click-around (XCUITest, Mac) | y | choose a channel, relaunch, a gated feature appears | `fichero/Tests/UI/…` |
| iPhone (iOS) | n | no control on iOS | |
| iPad | n | no control on iPad | |
| Load (#4634) | n | | |

Guards to change with it: `check_xcode_config_invariants.py` (one shipping configuration),
`check_mac_app_store_target.py` (unchanged in intent, still red until #5121),
`check_features_freshness.py` (unchanged).

## Documentation matrix

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual + screenshot | y | the maintainer's manual: Settings › General, Update channel |
| Contributor | developer docs | y | `feature-tiers.md`, `guide/03-feature-tiers.md`, `guide/17-the-release-lane.md`, `release/release-lane.md`, `AGENTS.md`, this spec |
| AI / agent | MCP tool description | n | |
| Scripter | CLI `--help` | n | |
| Reference | capability/endpoint reference | y | `docs/reference_manual/features.md` (generated) |

## Preview harness

`UpdateChannelSettingsPreview`, beside the pure channel model: the Software Update section drawn
for each of the four channels and for the App Store case (section absent), from data, with no
updater running.

## Accessibility identifiers

- `settings.general.updateChannel` — the popup
- `settings.general.updateChannel.<release|beta|alpha|dev>` — each choice
- `settings.general.updateChannel.relaunch` — Relaunch Now
- `settings.general.checkForUpdatesAutomatically` — the existing toggle

## UX completeness

| Control (a11y id) | Label | Tooltip/help text | Localized key | Verified by |
|---|---|---|---|---|
| `settings.general.updateChannel` | Update channel | Which builds Fichero is offered, and which features it shows | [MISSING] | [MISSING] |
| `settings.general.updateChannel.relaunch` | Relaunch Now | Reopen Fichero on the chosen channel | [MISSING] | [MISSING] |

## Open questions for the creative director

1. **What is in Release?** Recommended: move workflows, providers, activity, batches, the
   workflow file tools, the Settings General tab and the library and search advanced views to
   release; leave the knowledge graph, curation and workflow chains at beta. (#3917 is this
   question.)
2. **The public download's default channel.** Recommended: Alpha now, as today; move it when the
   first build is called a release.
3. **Is Dev offered to everyone?** The direction names all four. The alternative is to show Dev
   only when the binary's default is Dev or a hidden default is set. Recommended: all four.
4. **Relaunch.** Recommended: never forced; the change applies at the next launch, with a
   Relaunch Now button.
5. **Two things or one?** One popup sets both features and updates. The alternative is a second
   control so a person can take early builds without early features. Recommended: one.
6. **App Store and TestFlight tiers.** Recommended: App Store is Release, fixed; TestFlight
   stays at the tier baked at archive (Dev today), with no switch.
7. **A shared or remote engine.** An iPhone, or a second Mac, connected to another Mac's engine
   gets that engine's routes. Should a client on a less stable channel hide what the host's
   channel does not serve, or show it and report the 404? Not designed here.
8. **The per-feature defaults** (`resetToV001`, `fichero.features.*`). With the channel as the
   one gate a person sees, do these stay as an internal second gate, or go?

## Rulings (design lead)

- 2026-09-30 — Workflows are part of the public release; a release without them is not the
  product. The builds handed out today are alpha, and testing is on the Dev build.
- 2026-09-30 — Direction: one release with the channel chosen in Settings, rather than a build
  per tier. To be designed in this spec before anything is built.
