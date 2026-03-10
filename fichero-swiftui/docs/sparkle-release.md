# Sparkle Release Setup (0.0.1)

This project uses Sparkle for app updates via the **Check for Updates...** menu item.

## Required Info.plist Keys

- `SUFeedURL`
  - Current value points to:
    - `https://raw.githubusercontent.com/dtubb/fichero/main/fichero-swiftui/appcast.xml`
- `SUPublicEDKey`
  - Must be set for signed release update channels.

## Local Development

- Debug builds allow update checks with `SUFeedURL` only.
- If `SUFeedURL` is missing or invalid, the app shows an updater configuration alert.

## Release Builds

- Release builds require both:
  - valid `SUFeedURL`
  - non-empty `SUPublicEDKey`
- If `SUPublicEDKey` is empty in release, the app shows a release-configuration alert.

## Minimal Release Flow

1. Build and archive the release app.
2. Generate Sparkle update metadata/signature for the release artifact.
3. Publish release artifact and update `appcast.xml` with the new enclosure metadata.
4. Confirm `SUFeedURL` resolves from a clean machine.
5. Launch app and run **Check for Updates...** to verify updater discovery.
