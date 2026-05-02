import AppKit
import Foundation
import OSLog

private let logger = Logger(subsystem: "com.fichero.fichero", category: "AppInstaller")

/// Offers to move Fichero.app to /Applications on first launch from a DMG or Downloads folder.
enum AppInstaller {

    /// Returns true if the app is NOT in /Applications or ~/Applications.
    /// Always returns false for debug builds (running from Xcode).
    static func shouldOfferMoveToApplications() -> Bool {
        #if DEBUG
        return false
        #else
        let bundlePath = Bundle.main.bundleURL.resolvingSymlinksInPath().path
        let homeApplications = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Applications").path
        return !bundlePath.hasPrefix("/Applications/") &&
            !bundlePath.hasPrefix("\(homeApplications)/")
        #endif
    }

    /// Shows an alert offering to move the app. Returns true if move was initiated.
    @MainActor
    @discardableResult
    static func promptToMoveToApplicationsIfNeeded() -> Bool {
        guard shouldOfferMoveToApplications() else { return false }

        let targetPath = "/Applications/\(Bundle.main.bundleURL.lastPathComponent)"

        let alert = NSAlert()
        alert.messageText = "Fichero Is Not in Applications"
        alert.informativeText = """
        Fichero is not running from the Applications folder. \
        It will work best there.

        Move to \(targetPath)?
        """
        alert.alertStyle = .informational
        alert.addButton(withTitle: "Move to Applications")
        alert.addButton(withTitle: "Not Now")

        guard alert.runModal() == .alertFirstButtonReturn else {
            logger.info("User declined move to Applications")
            return false
        }

        return moveCurrentAppToApplicationsAndRelaunch()
    }

    // MARK: - Private

    @MainActor
    private static func moveCurrentAppToApplicationsAndRelaunch() -> Bool {
        let fileManager = FileManager.default
        let sourceURL = Bundle.main.bundleURL.resolvingSymlinksInPath()
        let appName = sourceURL.lastPathComponent
        let targetURL = URL(fileURLWithPath: "/Applications/\(appName)")

        if sourceURL.path == targetURL.path {
            return relaunchInstalledCopy(at: targetURL)
        }

        do {
            // Trash existing copy if present
            if fileManager.fileExists(atPath: targetURL.path) {
                try fileManager.trashItem(at: targetURL, resultingItemURL: nil)
            }

            try fileManager.copyItem(at: sourceURL, to: targetURL)
            logger.info("Copied app to \(targetURL.path)")
            return relaunchInstalledCopy(at: targetURL)
        } catch {
            logger.error("Failed to move app: \(error.localizedDescription)")
            showError("Could not move Fichero to Applications:\n\(error.localizedDescription)")
            return false
        }
    }

    @MainActor
    private static func relaunchInstalledCopy(at targetURL: URL) -> Bool {
        terminateOtherRunningInstances()

        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        task.arguments = ["-n", targetURL.path]

        do {
            try task.run()
            task.waitUntilExit()
            guard task.terminationStatus == 0 else {
                showError("Could not open the installed copy at:\n\(targetURL.path)")
                return false
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                NSApp.terminate(nil)
            }
            return true
        } catch {
            showError("Could not open the installed copy:\n\(error.localizedDescription)")
            return false
        }
    }

    private static func terminateOtherRunningInstances() {
        guard let bundleID = Bundle.main.bundleIdentifier else { return }
        let currentPID = ProcessInfo.processInfo.processIdentifier
        for app in NSRunningApplication.runningApplications(withBundleIdentifier: bundleID)
        where app.processIdentifier != currentPID {
            _ = app.terminate()
        }
    }

    @MainActor
    private static func showError(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "Installation Failed"
        alert.informativeText = message
        alert.alertStyle = .warning
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }
}
