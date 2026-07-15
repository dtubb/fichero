#!/usr/bin/env bash
# tier_build_map.sh -- sourced (never executed) by the release/build scripts to
# resolve the (scheme, configuration) pair for each platform from
# FICHERO_RELEASE_TIER. Schemes are the strict (Tier, Mode) names from #3345;
# each scheme's build actions bake FICHERO_FEATURE_TIER + FICHERO_EMBED_ENGINE
# via its config, so the scheme alone drives tier/embed. The -configuration flag
# is kept only to pin the Products/$CONFIG output directory the packaging
# scripts look for.
#
#   FICHERO_RELEASE_TIER   Mac (Embedded)                        iOS (Local; no engine)
#   release (default)      Fichero (Release Embedded)/Release    Fichero (Release Local iOS)/Release Local
#   beta                   Fichero (Beta Embedded)/Beta Embedded Fichero (Beta Local iOS)/Beta
#   alpha                  Fichero (Alpha Embedded)/Alpha Embedded  Fichero (Alpha Local iOS)/Alpha
#   dev                    Fichero (Dev Embedded)/Dev Embedded   Fichero (Dev Local iOS)/Debug
#
# Unknown values fall back to release (release-safe). iOS is always Local -- the
# Python engine cannot run on-device, so there is no iOS Embedded variant.

TIER="${FICHERO_RELEASE_TIER:-release}"
case "$TIER" in
  release)
    MAC_SCHEME="Fichero (Release Embedded)";  MAC_CONFIG="Release"
    IOS_SCHEME="Fichero (Release Local iOS)"; IOS_CONFIG="Release Local"
    ;;
  beta)
    MAC_SCHEME="Fichero (Beta Embedded)";     MAC_CONFIG="Beta Embedded"
    IOS_SCHEME="Fichero (Beta Local iOS)";    IOS_CONFIG="Beta"
    ;;
  alpha)
    MAC_SCHEME="Fichero (Alpha Embedded)";    MAC_CONFIG="Alpha Embedded"
    IOS_SCHEME="Fichero (Alpha Local iOS)";   IOS_CONFIG="Alpha"
    ;;
  dev)
    MAC_SCHEME="Fichero (Dev Embedded)";      MAC_CONFIG="Dev Embedded"
    IOS_SCHEME="Fichero (Dev Local iOS)";     IOS_CONFIG="Debug"
    ;;
  *)
    echo "tier_build_map: unknown FICHERO_RELEASE_TIER='$TIER' -- defaulting to release" >&2
    MAC_SCHEME="Fichero (Release Embedded)";  MAC_CONFIG="Release"
    IOS_SCHEME="Fichero (Release Local iOS)"; IOS_CONFIG="Release Local"
    ;;
esac
# TestFlight uses the sandboxed App Store target. Its configuration must retain
# the requested tier so an internal Dev archive exposes the Dev surface.
MAC_APP_STORE_SCHEME="Fichero (App Store)"
case "$TIER" in
  dev) MAC_APP_STORE_CONFIG="Dev Embedded" ;;
  alpha) MAC_APP_STORE_CONFIG="Alpha Embedded" ;;
  beta) MAC_APP_STORE_CONFIG="Beta Embedded" ;;
  *) MAC_APP_STORE_CONFIG="Release" ;;
esac
export FICHERO_RELEASE_TIER="$TIER" MAC_SCHEME MAC_CONFIG IOS_SCHEME IOS_CONFIG \
  MAC_APP_STORE_SCHEME MAC_APP_STORE_CONFIG
