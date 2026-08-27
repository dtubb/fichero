#if os(macOS)
import AppKit

#if canImport(Sparkle)
import Sparkle
#endif

#if canImport(Sparkle)
/// Opts dev builds into the `dev` Sparkle channel (one feed, two channels —
/// Daniel's 2026-08-25 ruling). Beta/release builds see only channel-less
/// items (Fichero.dmg); dev builds also see `<sparkle:channel>dev</sparkle:channel>`
/// items (Fichero-dev.dmg). The tier is baked per build, so it is captured
/// once at init — Sparkle may call this off the main actor.
private final class SparkleChannelDelegate: NSObject, SPUUpdaterDelegate {
    private let channels: Set<String>
    init(channels: Set<String>) { self.channels = channels }
    func allowedChannels(for updater: SPUUpdater) -> Set<String> { channels }
}
#endif

@MainActor
final class SparkleUpdater {
    static let shared = SparkleUpdater()

    #if canImport(Sparkle)
    private let updaterController: SPUStandardUpdaterController
    private let channelDelegate: SparkleChannelDelegate
    #endif

    private init() {
        #if canImport(Sparkle)
        channelDelegate = SparkleChannelDelegate(
            channels: FeatureManager.shared.activeBuildTier == .dev ? ["dev"] : []
        )
        updaterController = SPUStandardUpdaterController(
            startingUpdater: true,
            updaterDelegate: channelDelegate,
            userDriverDelegate: nil
        )
        #endif
    }

    func checkForUpdates() {
        #if canImport(Sparkle)
        guard let feedURLString = Bundle.main.object(forInfoDictionaryKey: "SUFeedURL") as? String else {
            showMissingConfigurationAlert()
            return
        }
        let trimmedFeedURL = feedURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedFeedURL.isEmpty, URL(string: trimmedFeedURL) != nil else {
            showMissingConfigurationAlert()
            return
        }

        if requiresSignedUpdates {
            let publicKey = (
                Bundle.main.object(forInfoDictionaryKey: "SUPublicEDKey") as? String ?? ""
            ).trimmingCharacters(in: .whitespacesAndNewlines)
            guard !publicKey.isEmpty else {
                showMissingReleaseKeyAlert()
                return
            }
        }

        updaterController.checkForUpdates(nil)
        #else
        showMissingFrameworkAlert()
        #endif
    }

    private var requiresSignedUpdates: Bool {
        #if DEBUG
        return false
        #else
        return true
        #endif
    }

    private func showMissingConfigurationAlert() {
        let alert = NSAlert()
        alert.messageText = "Updates Not Configured"
        alert.informativeText = "Set SUFeedURL (and SUPublicEDKey for release) in Info.plist to enable Sparkle updates."
        alert.alertStyle = .informational
        alert.runModal()
    }

    private func showMissingReleaseKeyAlert() {
        let alert = NSAlert()
        alert.messageText = "Release Updates Not Configured"
        alert.informativeText = "Set SUPublicEDKey in Info.plist for release Sparkle updates."
        alert.alertStyle = .informational
        alert.runModal()
    }

    private func showMissingFrameworkAlert() {
        let alert = NSAlert()
        alert.messageText = "Updates Unavailable"
        alert.informativeText = "Sparkle framework is not linked in this build."
        alert.alertStyle = .informational
        alert.runModal()
    }
}

#else

// iOS stub: Sparkle is macOS-only. Callers still compile; updates are a no-op.
@MainActor
final class SparkleUpdater {
    static let shared = SparkleUpdater()
    private init() {}
    func checkForUpdates() {}
}

#endif
