import AppKit
import Foundation
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "AppInstaller")

/// Offers to move Fichero.app to /Applications on first launch from a DMG or Downloads folder.
enum AppInstaller {

    /// The real home directory, bypassing sandbox container redirection.
    private static var realHomeDirectory: String {
        // In a sandbox, NSHomeDirectory() returns the container path.
        // Use passwd to get the actual home directory.
        if let pw = getpwuid(getuid()), let home = pw.pointee.pw_dir {
            return String(cString: home)
        }
        return NSHomeDirectory()
    }

    /// Returns true if the app is NOT in /Applications or ~/Applications.
    static func shouldOfferMoveToApplications() -> Bool {
        let bundlePath = Bundle.main.bundleURL.resolvingSymlinksInPath().path
        let homeApplications = "\(realHomeDirectory)/Applications"
        return !bundlePath.hasPrefix("/Applications/") &&
            !bundlePath.hasPrefix("\(homeApplications)/")
    }

    /// Shows an alert offering to move the app. Returns true if move was initiated.
    @MainActor
    @discardableResult
    static func promptToMoveToApplicationsIfNeeded() -> Bool {
        guard shouldOfferMoveToApplications() else { return false }

        let sourcePath = Bundle.main.bundleURL.resolvingSymlinksInPath().path
        let targetPath = "/Applications/\(Bundle.main.bundleURL.lastPathComponent)"

        let alert = NSAlert()
        alert.messageText = "Fichero Is Not in Applications"
        alert.informativeText = """
        Fichero is not running from the Applications folder. \
        It will work best if installed there — updates, file associations, \
        and Spotlight integration all depend on it.

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

    private static func moveCurrentAppToApplicationsAndRelaunch() -> Bool {
        let sourceURL = Bundle.main.bundleURL.resolvingSymlinksInPath()
        let appName = sourceURL.lastPathComponent
        let targetPath = "/Applications/\(appName)"
        let targetURL = URL(fileURLWithPath: targetPath)

        // If already at target, just relaunch
        if sourceURL.path == targetURL.path {
            return relaunchInstalledCopy(at: targetURL)
        }

        // Trash existing copy if present
        if FileManager.default.fileExists(atPath: targetPath) {
            let trashResult = runProcess("/bin/rm", arguments: ["-rf", targetPath])
            if !trashResult {
                // Try with AppleScript authorization
                let script = """
                do shell script "rm -rf '\(targetPath)'" with administrator privileges
                """
                if let appleScript = NSAppleScript(source: script) {
                    var error: NSDictionary?
                    appleScript.executeAndReturnError(&error)
                    if let error = error {
                        logger.error("Failed to remove existing app: \(error)")
                        showError("Could not replace existing Fichero in Applications.\n\(error)")
                        return false
                    }
                }
            }
        }

        // Copy to /Applications
        let copySuccess = runProcess("/bin/cp", arguments: ["-R", sourceURL.path, targetPath])
        if !copySuccess {
            // Try with AppleScript authorization
            let script = """
            do shell script "cp -R '\(sourceURL.path)' '\(targetPath)'" with administrator privileges
            """
            if let appleScript = NSAppleScript(source: script) {
                var error: NSDictionary?
                appleScript.executeAndReturnError(&error)
                if let error = error {
                    logger.error("Failed to copy app: \(error)")
                    showError("Could not move Fichero to Applications.\n\(error)")
                    return false
                }
            }
        }

        logger.info("Copied app to \(targetPath)")
        return relaunchInstalledCopy(at: targetURL)
    }

    private static func runProcess(_ path: String, arguments: [String]) -> Bool {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: path)
        task.arguments = arguments
        task.standardOutput = FileHandle.nullDevice
        task.standardError = FileHandle.nullDevice
        do {
            try task.run()
            task.waitUntilExit()
            return task.terminationStatus == 0
        } catch {
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
