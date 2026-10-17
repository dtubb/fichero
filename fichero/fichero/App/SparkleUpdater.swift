#if os(macOS)
import AppKit

import Sparkle

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

@MainActor
final class SparkleUpdater {
    static let shared = SparkleUpdater()

    // Sparkle is weak-linked and the App Store configuration deletes the
    // framework from its bundle (#5730), so "is Sparkle here" is a RUNTIME
    // question — the class is absent exactly when the framework is. Nothing
    // below touches a Sparkle symbol unless this is true.
    private static let hasSparkle = NSClassFromString("SPUStandardUpdaterController") != nil

    private let updaterController: SPUStandardUpdaterController?
    private let channelDelegate: SparkleChannelDelegate?

    private init() {
        guard Self.hasSparkle else {
            channelDelegate = nil
            updaterController = nil
            return
        }
        let delegate = SparkleChannelDelegate(
            channels: FeatureManager.shared.activeBuildTier == .dev ? ["dev"] : []
        )
        channelDelegate = delegate
        let controller = SPUStandardUpdaterController(
            startingUpdater: true,
            updaterDelegate: delegate,
            userDriverDelegate: nil
        )
        updaterController = controller
        // Automatic download-and-install defaults ON (Daniel, 2026-09-04):
        // an archive tool's updates carry fixes to the data path, and waiting
        // for a manual check is how a known bug stays on a machine for weeks.
        // FIRST LAUNCH ONLY — Sparkle persists both flags in UserDefaults
        // (SUEnableAutomaticChecks / SUAutomaticallyUpdate), so seed the
        // default solely while the user has never touched it; a deliberate
        // opt-out in Settings then sticks forever.
        let defaults = UserDefaults.standard
        if defaults.object(forKey: "SUAutomaticallyUpdate") == nil {
            controller.updater.automaticallyDownloadsUpdates = true
        }
        if defaults.object(forKey: "SUEnableAutomaticChecks") == nil {
            controller.updater.automaticallyChecksForUpdates = true
        }
    }

    /// Settings seam (General ▸ Software Update). Straight passthroughs to
    /// Sparkle's own persisted preferences — no shadow copy to drift.
    var automaticallyChecksForUpdates: Bool {
        get { updaterController?.updater.automaticallyChecksForUpdates ?? false }
        set { updaterController?.updater.automaticallyChecksForUpdates = newValue }
    }

    var automaticallyDownloadsUpdates: Bool {
        get { updaterController?.updater.automaticallyDownloadsUpdates ?? false }
        set { updaterController?.updater.automaticallyDownloadsUpdates = newValue }
    }

    /// True when this build carries Sparkle at all (DMG channel; MAS and dev
    /// Xcode runs do not) — Settings hides the section rather than showing
    /// dead toggles.
    var isAvailable: Bool {
        guard updaterController != nil else { return false }
        return (Bundle.main.object(forInfoDictionaryKey: "SUFeedURL") as? String)
            .map { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty } ?? false
    }

    func checkForUpdates() {
        guard let updaterController else {
            showMissingFrameworkAlert()
            return
        }
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
