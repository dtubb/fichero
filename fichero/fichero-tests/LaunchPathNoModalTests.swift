@testable import Fichero
import Foundation
import Testing

/// The launch path must reach the interface on its own — no modal, no decision,
/// no blocking prompt between the user double-clicking Fichero and the window.
///
/// A modal here is uniquely bad: `NSAlert.runModal()` runs a nested run loop on
/// the main thread during `FicheroApp.init()`, before the scene graph exists.
/// The move-to-Applications prompt did exactly that, and its dev-build guard
/// missed (it matched the literal "/Build/Products/" against a real path of
/// `build/xcode/Products/`), so it fired on developer builds and stalled the
/// launch on a dialog nobody wanted.
///
/// Source-level because the invariant is structural — it costs nothing and needs
/// no engine, unlike launching the real app to watch a dialog not appear.
struct LaunchPathNoModalTests {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// `runModal` is the load-bearing token: every blocking AppKit prompt goes
    /// through it. Modal-free legitimate uses (Sparkle, menu commands, save
    /// panels) live in their own files and are user-initiated — this pins only
    /// the launch path.
    @Test("the launch path presents no modal")
    func launchPathPresentsNoModal() throws {
        let source = try Self.appSource("FicheroApp.swift")
        #expect(!source.contains("runModal"), "a modal on the launch path blocks the app from opening")
    }

    /// The move-to-Applications flow is gone, not merely bypassed: a guard that
    /// returns false on today's paths would break again the moment the build
    /// directory moves.
    @Test("no move-to-Applications flow on the launch path")
    func noMoveToApplicationsFlow() throws {
        let source = try Self.appSource("FicheroApp.swift")
        #expect(!source.contains("AppInstaller"))
        #expect(!source.contains("promptToMoveToApplications"))
    }

    /// The other half of "it launches": having removed the blocker, the launch
    /// path must still reach the engine spawn.
    @Test("launch proceeds to the engine spawn")
    func launchProceedsToEngineSpawn() throws {
        let source = try Self.appSource("FicheroApp.swift")
        #expect(source.contains("try await backendService.start()"))
    }
}
