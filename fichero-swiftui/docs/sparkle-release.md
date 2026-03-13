# Sparkle Release Setup (0.0.1)

This project uses Sparkle for app updates via the **Check for Updates...** menu item.

## Required Info.plist Keys

`Info.plist` now reads Sparkle values from build settings:

- `SUFeedURL` -> `$(SPARKLE_FEED_URL)`
- `SUPublicEDKey` -> `$(SPARKLE_PUBLIC_ED_KEY)`

Default build settings in the app target:

- Debug:
  - `SPARKLE_FEED_URL=https://raw.githubusercontent.com/dtubb/fichero/main/fichero-swiftui/appcast.xml`
  - `SPARKLE_PUBLIC_ED_KEY=DEBUG_SPARKLE_KEY_NOT_REQUIRED`
- Release:
  - `SPARKLE_FEED_URL=https://raw.githubusercontent.com/dtubb/fichero/main/fichero-swiftui/appcast.xml`
  - `SPARKLE_PUBLIC_ED_KEY=SET_RELEASE_SPARKLE_PUBLIC_ED_KEY`

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
