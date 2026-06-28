> **HISTORICAL SETUP NOTE.** This page describes an older Sparkle setup pass and
> still contains the retired `fichero-releases` feed URL. Do not use it as the
> current release procedure; use [release-lane.md](./release-lane.md) for the
> shipped DMG/Sparkle path.

# Sparkle Release Setup (historical 0.0.1-era note)

This project uses Sparkle for app updates via the **Check for Updates...** menu item.

## Required Info.plist Keys

`Info.plist` now reads Sparkle values from build settings:

- `SUFeedURL` -> `$(SPARKLE_FEED_URL)`
- `SUPublicEDKey` -> `$(SPARKLE_PUBLIC_ED_KEY)`

Default build settings in the app target:

- `SPARKLE_FEED_URL=https://raw.githubusercontent.com/dtubb/fichero-releases/main/appcast.xml`
- `SPARKLE_PUBLIC_ED_KEY="z3UPbmGi74NGSqTQL25E2WFD1yulIzYRvtDitbIZvNY="`

The matching EdDSA private key must be stored securely outside the repo.
**Critical**: this key must never be lost. If it is lost, every shipped
Fichero install becomes update-stuck; recovery requires reinstalling a fresh
build with a new public key.

## Local Development

- Debug builds allow update checks with `SUFeedURL` only.
- If `SUFeedURL` is missing or invalid, the app shows an updater configuration alert.

## Release Builds

- Release builds require both:
  - valid `SPARKLE_FEED_URL`
  - production `SPARKLE_PUBLIC_ED_KEY`
- Replace placeholder `SET_RELEASE_SPARKLE_PUBLIC_ED_KEY` in release pipeline/local Release config before shipping.

## Minimal Release Flow

1. Build and archive the release app.
2. Generate Sparkle update metadata/signature for the release artifact.
3. Publish release artifact and update `appcast.xml` with the new enclosure metadata.
4. Confirm `SPARKLE_FEED_URL` resolves from a clean machine.
5. Launch app and run **Check for Updates...** to verify updater discovery.
