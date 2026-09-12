# Release & Versioning — Design Spec (#TBD)

> Milestone: release-and-versioning
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
| OpenAPI schema version | all **three** `openapi.json` copies → `info.version` | = the engine version | Kept in sync by `fichero-server/scripts/sync_openapi_schema.sh`; agreement checked by `check_openapi_shadow_types.py`. |

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
- `scripts/check_openapi_shadow_types.py` — the three OpenAPI copies agree.

## The release lane (process)

Detail lives in [`../../release/release-lane.md`](../../release/release-lane.md) (the runbook) and
[`../../architecture/release-process.md`](../../architecture/release-process.md) (the feature→ship
sequence); [`../../release/sparkle-release.md`](../../release/sparkle-release.md) covers Sparkle, and
[`../../release/release-readiness.md`](../../release/release-readiness.md) is a point-in-time
readiness snapshot. Shape:

1. **Integrate + gate.** Multi-lane work lands on `integration` and is gated there (`verify_all`,
   0 failed) — see [`git-worktree-workflow.md`](git-worktree-workflow.md).
2. **Merge to main.** `scripts/merge-integration-to-main.sh` fast-forwards `integration` into `main`
   (refuses anything but a clean fast-forward) as the pre-step; `release-all.sh` builds from the
   `main` checkout. It stamps the version *after* the merge, so the dated stamps are not a merge
   conflict source.
3. **Build + sign + ship.** `scripts/release-all.sh` runs the lane **unattended**: builds the
   embedded engine once, then DMG (Developer ID → notarize → staple → Sparkle-sign → GitHub release
   via `create-github-release.sh`) + Mac TestFlight + iOS TestFlight. iOS is remote-only (no embedded
   engine, no Sparkle).
4. **Tag.** `vYYYY.MM.DD[.N]` on the shipped commit; the GitHub release carries that version's notes.

**Tested before published.** Releases are notarized/verified and the design lead gives the verdict
*before* anything goes public (GitHub, TestFlight, the site). The lane does not self-publish on a
green build.

## Release notes — two artifacts, different owners

| Artifact | What | Who | How |
|----------|------|-----|-----|
| `CHANGELOG.md` | The commit-level, day-by-day record. Bare dated `## YYYY.MM.DD` headings — **every shipped release date gets one**, including a same-day re-stamp. | Agents (the record). | `scripts/release-notes-gen.sh` backfills history from git + closed issues via a local model (zero Claude cost); it only walks backward, never adds today. |
| `RELEASE_NOTES.md` | The human prose — one section per shipped release, the story for users. | The **maintainer** owns this prose (user-facing). | Written by hand. `scripts/gen_site_releases.py` slices the newest section onto the landing page. |

The GitHub release body holds each version's own notes independently of these files, so a version's
notes survive even if a later re-date reshuffles the local files.

## Open questions for the design lead

- **Does a same-day re-stamp deserve its own `RELEASE_NOTES.md` section?** When one calendar day
  ships twice (e.g. `2026.09.07` then `2026.09.08` for the same build 3), `CHANGELOG.md` gets both
  headings but the prose is usually one story. Current practice: one `RELEASE_NOTES.md` section for
  the newer date; the superseded date keeps only its GitHub release body. Confirm that's the rule, or
  say both dates should carry a prose section.
- **Should `CHANGELOG.md`/`RELEASE_NOTES.md` be part of the merge-conflict-free set** the way the
  dated stamps are (recreated post-merge), rather than hand-resolved on every integration merge?
