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
