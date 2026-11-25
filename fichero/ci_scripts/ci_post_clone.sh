#!/bin/sh
# Xcode Cloud post-clone (ci.xcode-cloud-swift-only, docs/contributor_manual/specs/harness/github-ci.md).
# Xcode Cloud builds and tests Swift only. It never runs the Python engine: no engine tests, no guards, no Briefcase build.
# The schemes that embed the engine (any "Embedded" or "App Store" scheme) need that build, so they are refused here, named,
# instead of failing later at the Embed Fichero Server phase.
set -eu

case "${CI_XCODE_SCHEME:-}" in
  *Embedded*|*"App Store"*)
    echo "error: Xcode Cloud builds Swift only; scheme '${CI_XCODE_SCHEME}' embeds the engine, which is built on the Macs" >&2
    exit 1
    ;;
esac

# The project's Swift packages use plugins and macros; a fresh Xcode Cloud host has never trusted them.
defaults write com.apple.dt.Xcode IDESkipPackagePluginFingerprintValidatation -bool YES
defaults write com.apple.dt.Xcode IDESkipMacroFingerprintValidation -bool YES

echo "Xcode Cloud: scheme '${CI_XCODE_SCHEME:-?}', Swift only; the engine is not built here"
