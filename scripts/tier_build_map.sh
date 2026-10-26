#!/usr/bin/env bash
# tier_build_map.sh -- sourced (never executed) by the release/build scripts to
# resolve the (scheme, configuration) pair for each platform from
# FICHERO_RELEASE_TIER. Schemes are the strict (Tier, Mode) names from #3345;
# each scheme's build actions bake FICHERO_FEATURE_TIER + FICHERO_EMBED_ENGINE
# via its config, so the scheme alone drives tier/embed. The -configuration flag
# is kept only to pin the Products/$CONFIG output directory the packaging
# scripts look for.
#
#   FICHERO_RELEASE_TIER   Mac (Embedded)                        iOS (no engine)
#   release (default)      Fichero (Release Embedded)/Release    Fichero (App Store)/App Store
#   beta                   Fichero (Beta Embedded)/Beta Embedded Fichero (App Store)/App Store
#   alpha                  Fichero (Alpha Embedded)/Alpha Embedded  Fichero (App Store)/App Store
#   dev                    Fichero (Dev Embedded)/Dev Embedded   Fichero (App Store)/App Store
#
# iOS archives the one Fichero target's App Store configuration (#5730 retired the
# per-tier "Local iOS" schemes); the tier reaches it as FICHERO_FEATURE_TIER
# (IOS_ARCHIVE_FEATURE_TIER below), and the engine embed skips non-macOS platforms.
#
# Unknown values fall back to release (release-safe). iOS is always Local -- the
# Python engine cannot run on-device, so there is no iOS Embedded variant.

TIER="${FICHERO_RELEASE_TIER:-release}"
case "$TIER" in
  release)
    MAC_SCHEME="Fichero (Release Embedded)";  MAC_CONFIG="Release"
    IOS_SCHEME="Fichero (App Store)"; IOS_CONFIG="App Store"
    ;;
  beta)
    MAC_SCHEME="Fichero (Beta Embedded)";     MAC_CONFIG="Beta Embedded"
    IOS_SCHEME="Fichero (App Store)"; IOS_CONFIG="App Store"
    ;;
  alpha)
    MAC_SCHEME="Fichero (Alpha Embedded)";    MAC_CONFIG="Alpha Embedded"
    IOS_SCHEME="Fichero (App Store)"; IOS_CONFIG="App Store"
    ;;
  dev)
    MAC_SCHEME="Fichero (Dev Embedded)";      MAC_CONFIG="Dev Embedded"
    # TestFlight rejects Debug archives: archive App Store and override only
    # FICHERO_FEATURE_TIER below for internal Dev.
    IOS_SCHEME="Fichero (App Store)"; IOS_CONFIG="App Store"
    ;;
  *)
    echo "tier_build_map: unknown FICHERO_RELEASE_TIER='$TIER' -- defaulting to release" >&2
    MAC_SCHEME="Fichero (Release Embedded)";  MAC_CONFIG="Release"
    IOS_SCHEME="Fichero (App Store)"; IOS_CONFIG="App Store"
    ;;
esac
# TestFlight archives the sandboxed App Store target in its App Store configuration:
# only that config embeds the engine in Contents/Helpers (the tier configs put it in
# Contents/Resources for the DMG, and the MAS resign/validate scripts reject that, #6112).
# The tier reaches the archive as FICHERO_FEATURE_TIER (MAC_ARCHIVE_FEATURE_TIER), like iOS.
MAC_APP_STORE_SCHEME="Fichero (App Store)"
MAC_APP_STORE_CONFIG="App Store"
MAC_ARCHIVE_FEATURE_TIER="$TIER"
IOS_ARCHIVE_FEATURE_TIER="$TIER"
export FICHERO_RELEASE_TIER="$TIER" IOS_ARCHIVE_FEATURE_TIER MAC_SCHEME MAC_CONFIG IOS_SCHEME IOS_CONFIG \
  MAC_APP_STORE_SCHEME MAC_APP_STORE_CONFIG MAC_ARCHIVE_FEATURE_TIER
