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

        let projectURL = repoRoot
            .appendingPathComponent("fichero")
            .appendingPathComponent("fichero.xcodeproj")
            .appendingPathComponent("project.pbxproj")
        let updaterURL = repoRoot
            .appendingPathComponent("fichero")
            .appendingPathComponent("App")
            .appendingPathComponent("SparkleUpdater.swift")
        let appURL = repoRoot
            .appendingPathComponent("fichero")
            .appendingPathComponent("FicheroApp.swift")

        let projectText = try String(contentsOf: projectURL, encoding: .utf8)
        #expect(projectText.contains("Sparkle in Frameworks"))
        #expect(projectText.contains("platformFilters = (macos, );"))

        let updaterText = try String(contentsOf: updaterURL, encoding: .utf8)
        #expect(updaterText.contains("#if os(macOS)"))
        #expect(updaterText.contains("// iOS stub: Sparkle is macOS-only. Callers still compile; updates are a no-op."))

        let appText = try String(contentsOf: appURL, encoding: .utf8)
        #expect(appText.contains("#if os(macOS)"))
        #expect(appText.contains("SparkleUpdater.shared.checkForUpdates()"))
    }
}
