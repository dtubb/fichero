import AppKit
import Foundation
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "AppInstaller")

/// Offers to move Fichero.app to /Applications on first launch from a DMG or Downloads folder.
enum AppInstaller {

    /// Returns true if the app is NOT in /Applications or ~/Applications.
    static func shouldOfferMoveToApplications() -> Bool {
        let bundlePath = Bundle.main.bundleURL.resolvingSymlinksInPath().path
        let homeApplications = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Applications").path
        return !bundlePath.hasPrefix("/Applications/") &&
            !bundlePath.hasPrefix("\(homeApplications)/")
    }

    /// Shows an alert offering to move the app. Returns true if move was initiated.
    @MainActor
    @discardableResult
    static func promptToMoveToApplicationsIfNeeded() -> Bool {
        guard shouldOfferMoveToApplications() else { return false }

        let sourcePath = Bundle.main.bundleURL.resolvingSymlinksInPath().path
        let targetURL = preferredInstallURL()

        let alert = NSAlert()
        alert.messageText = "Move Fichero to Applications?"
        alert.informativeText = """
        Fichero works best when installed in your Applications folder.

        Current location:
        \(sourcePath)

        Install to:
        \(targetURL.path)
        """
        alert.alertStyle = .informational
        alert.addButton(withTitle: "Move")
        alert.addButton(withTitle: "Not Now")

        guard alert.runModal() == .alertFirstButtonReturn else {
            logger.info("User declined move to Applications")
            return false
        }

        return moveCurrentAppToApplicationsAndRelaunch()
    }

    // MARK: - Private

    private static func preferredInstallURL() -> URL {
        let appName = Bundle.main.bundleURL.lastPathComponent
        if FileManager.default.isWritableFile(atPath: "/Applications") {
            return URL(fileURLWithPath: "/Applications").appendingPathComponent(appName)
        }
        let userApplications = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Applications", isDirectory: true)
        return userApplications.appendingPathComponent(appName)
    }

    private static func moveCurrentAppToApplicationsAndRelaunch() -> Bool {
        let fileManager = FileManager.default
        let sourceURL = Bundle.main.bundleURL.resolvingSymlinksInPath()
        let targetURL = preferredInstallURL()

        do {
            try fileManager.createDirectory(
                at: targetURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )

            if sourceURL.path == targetURL.path {
                return relaunchInstalledCopy(at: targetURL)
            }

            // Trash existing copy if present
            if fileManager.fileExists(atPath: targetURL.path) {
                _ = try? fileManager.trashItem(at: targetURL, resultingItemURL: nil)
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

    private static func showError(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "Installation Failed"
        alert.informativeText = message
        alert.alertStyle = .warning
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }
}
