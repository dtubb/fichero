import AppKit

#if canImport(Sparkle)
import Sparkle
#endif

@MainActor
final class SparkleUpdater {
    static let shared = SparkleUpdater()

#if canImport(Sparkle)
    private let updaterController: SPUStandardUpdaterController
#endif

    private init() {
#if canImport(Sparkle)
        updaterController = SPUStandardUpdaterController(
            startingUpdater: true,
            updaterDelegate: nil,
            userDriverDelegate: nil
        )
#endif
    }

    func checkForUpdates() {
#if canImport(Sparkle)
        guard let feedURL = Bundle.main.object(forInfoDictionaryKey: "SUFeedURL") as? String,
              !feedURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            showMissingConfigurationAlert()
            return
        }

        updaterController.checkForUpdates(nil)
#else
        showMissingFrameworkAlert()
#endif
    }

    private func showMissingConfigurationAlert() {
        let alert = NSAlert()
        alert.messageText = "Updates Not Configured"
        alert.informativeText = "Set SUFeedURL (and SUPublicEDKey for release) in Info.plist to enable Sparkle updates."
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
