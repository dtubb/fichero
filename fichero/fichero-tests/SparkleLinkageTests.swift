import Foundation
import Testing

struct SparkleLinkageTests {
    @Test("Sparkle is linked only for macOS and updater code is macOS-gated")
    func sparkleLinkageIsMacOnly() throws {
        func findRepoRoot(startingAt startURL: URL) -> URL {
            var current = startURL
            let fileManager = FileManager.default

            while true {
                let candidate = current.appendingPathComponent("fichero")
                let project = candidate.appendingPathComponent("fichero.xcodeproj")
                let pbxproj = project.appendingPathComponent("project.pbxproj")
                if fileManager.fileExists(atPath: pbxproj.path) {
                    return current
                }

                let next = current.deletingLastPathComponent()
                if next.path == current.path {
                    return startURL
                }
                current = next
            }
        }

        let fileURL = URL(fileURLWithPath: #filePath)
        let repoRoot = findRepoRoot(startingAt: fileURL.deletingLastPathComponent())

        // The app target lives at <repoRoot>/fichero/fichero/ (sources) beside
        // <repoRoot>/fichero/fichero.xcodeproj (project). The updater, app entry,
        // and Info.plist are under the nested sources dir — not repoRoot/fichero.
        let projectDir = repoRoot.appendingPathComponent("fichero")
        let sourceDir = projectDir.appendingPathComponent("fichero")

        let projectURL = projectDir
            .appendingPathComponent("fichero.xcodeproj")
            .appendingPathComponent("project.pbxproj")
        let updaterURL = sourceDir
            .appendingPathComponent("App")
            .appendingPathComponent("SparkleUpdater.swift")
        let appURL = sourceDir
            .appendingPathComponent("FicheroApp.swift")
        let infoPlistURL = sourceDir
            .appendingPathComponent("Info.plist")

        let projectText = try String(contentsOf: projectURL, encoding: .utf8)
        #expect(projectText.contains("Sparkle in Frameworks"))
        #expect(projectText.contains("platformFilters = (macos, );"))
        // Build settings that back the Info.plist $(...) references (#520 item 2):
        // the appcast URL and public key must be defined in the project.
        #expect(projectText.contains("SPARKLE_FEED_URL = "))
        #expect(projectText.contains("SPARKLE_PUBLIC_ED_KEY = "))

        let updaterText = try String(contentsOf: updaterURL, encoding: .utf8)
        #expect(updaterText.contains("#if os(macOS)"))
        #expect(updaterText.contains("// iOS stub: Sparkle is macOS-only. Callers still compile; updates are a no-op."))

        let appText = try String(contentsOf: appURL, encoding: .utf8)
        #expect(appText.contains("#if os(macOS)"))
        #expect(appText.contains("SparkleUpdater.shared.checkForUpdates()"))

        // Info.plist must wire Sparkle's feed + public key to build settings
        // (#520 item 2) so "Check for Updates" resolves the appcast URL.
        let infoPlistText = try String(contentsOf: infoPlistURL, encoding: .utf8)
        #expect(infoPlistText.contains("<key>SUFeedURL</key>"))
        #expect(infoPlistText.contains("$(SPARKLE_FEED_URL)"))
        #expect(infoPlistText.contains("<key>SUPublicEDKey</key>"))
        #expect(infoPlistText.contains("$(SPARKLE_PUBLIC_ED_KEY)"))
    }
}
