#if canImport(AppKit)
import AppKit
#endif
import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "AppInstaller")

/// Offers to move Fichero.app to /Applications on first launch from a DMG or Downloads folder.
enum AppInstaller {

    /// Returns true if the app is NOT in /Applications or ~/Applications.
    /// Always returns false for debug builds (running from Xcode).
    static func shouldOfferMoveToApplications() -> Bool {
        #if DEBUG
        return false
        #else
        let bundlePath = Bundle.main.bundleURL.resolvingSymlinksInPath().path
        // A dev build run from Xcode lives under DerivedData / Build/Products even
        // in a Release configuration (so #if DEBUG doesn't catch it). Never prompt
        // — and never try the move, which fails with a permissions error (#2860).
        if bundlePath.contains("/DerivedData/") || bundlePath.contains("/Build/Products/") {
            return false
        }
        let homeApplications = URL(fileURLWithPath: NSHomeDirectory())
            .appendingPathComponent("Applications").path
        return !bundlePath.hasPrefix("/Applications/") &&
            !bundlePath.hasPrefix("\(homeApplications)/")
        #endif
    }

    /// Shows an alert offering to move the app. Returns true if move was initiated.
    @MainActor
    @discardableResult
    static func promptToMoveToApplicationsIfNeeded() -> Bool {
        #if !os(macOS)
        return false
        #else
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
        #endif
    }

    // MARK: - Private

    #if os(macOS)
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

        // Kill any embedded "Fichero Engine" subprocess before launching the
        // moved copy. Without this, the new instance's engine fails with
        // "Port 8765 already in use" because our orphan engine still holds it
        // (#757). pgrep matches any engine started from this app's bundle.
        terminateEmbeddedEngines()
        waitForPortToClear(8765, timeout: 3.0)

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

    private static func terminateEmbeddedEngines() {
        let pgrep = Process()
        pgrep.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
        pgrep.arguments = ["-f", "Fichero Engine.app/Contents/MacOS"]
        let pipe = Pipe()
        pgrep.standardOutput = pipe
        pgrep.standardError = FileHandle.nullDevice
        do {
            try pgrep.run()
            pgrep.waitUntilExit()
            let data = (try? pipe.fileHandleForReading.readToEnd()) ?? Data()
            guard let output = String(data: data, encoding: .utf8) else { return }
            for line in output.split(separator: "\n") {
                if let pid = pid_t(line.trimmingCharacters(in: .whitespaces)) {
                    logger.info("SIGTERM engine PID \(pid) before relaunch")
                    kill(pid, SIGTERM)
                }
            }
        } catch {
            logger.warning("Could not enumerate engine processes: \(error.localizedDescription)")
        }
    }

    private static func waitForPortToClear(_ port: UInt16, timeout: TimeInterval) {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if !portInUse(port) { return }
            Thread.sleep(forTimeInterval: 0.1)
        }
        logger.warning("Port \(port) still in use after \(timeout)s, proceeding anyway")
    }

    private static func portInUse(_ port: UInt16) -> Bool {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/sbin/lsof")
        task.arguments = ["-i", ":\(port)", "-sTCP:LISTEN", "-t"]
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = FileHandle.nullDevice
        do {
            try task.run()
            task.waitUntilExit()
            let data = (try? pipe.fileHandleForReading.readToEnd()) ?? Data()
            return !data.isEmpty
        } catch {
            return false
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
    #endif
}
