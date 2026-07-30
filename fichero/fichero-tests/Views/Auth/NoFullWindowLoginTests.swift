@testable import Fichero
import Foundation
import Testing

/// Guardrail (#4359): no full-window login view exists on macOS — ever again.
///
/// Daniel launched Dev Local (loopback, multi-user OFF) and got a full-window
/// "Sign In — Sign in to open your libraries" wall. The window had been handed
/// wholesale to `AuthGateView` whenever `isBackendRunning` flipped true while
/// the session phase was still `.checking` (heartbeat/failover recovery paths
/// marked ready without resolving the phase). The design fix is structural:
/// auth is CHROME — a modal sheet on macOS, an explicit full-screen cover on
/// iOS — and the window keeps its shell, sidebar and content unconditionally.
///
/// Source-level, like `MenuShortcutBoundaryTests` / `LaunchPathNoModalTests`:
/// the invariant is structural, costs nothing, and needs no engine.
struct NoFullWindowLoginTests {
    /// Root of the app target's sources (fichero/fichero).
    private static var appSourceRoot: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
    }

    /// Every Swift source in the app target.
    private static func appSources() throws -> [(path: String, source: String)] {
        let root = appSourceRoot
        guard let enumerator = FileManager.default.enumerator(
            at: root,
            includingPropertiesForKeys: nil
        ) else { return [] }
        var sources: [(String, String)] = []
        for case let url as URL in enumerator where url.pathExtension == "swift" {
            let source = try String(contentsOf: url, encoding: .utf8)
            let relative = url.path.replacingOccurrences(of: root.path + "/", with: "")
            sources.append((relative, source))
        }
        #expect(!sources.isEmpty, "app source enumeration found nothing — root path drifted")
        return sources
    }

    @Test("the deleted full-window AuthGateView cannot come back")
    func noAuthGateViewAnywhere() throws {
        for (path, source) in try Self.appSources() {
            #expect(
                !source.contains("struct AuthGateView"),
                "\(path) re-declares the full-window login takeover deleted in #4359"
            )
        }
    }

    @Test("the auth surface never frames itself as a window-filling wall")
    func authSurfaceIsNotAWall() throws {
        let sheet = try #require(
            try Self.appSources().first { $0.path.hasSuffix("Views/Auth/AuthSheetView.swift") },
            "the auth sheet moved — update this guardrail alongside it"
        )
        #expect(
            !sheet.source.contains("maxHeight: .infinity"),
            "AuthSheetView must size as a sheet card, never expand to fill the window"
        )
    }

    @Test("auth UI mounts only as presentation chrome, from ContentView")
    func authMountsOnlyAsChrome() throws {
        let referencingFiles = try Self.appSources()
            .filter { $0.source.contains("AuthSheetView(") }
            .map(\.path)
            .sorted()
        // Its own declaration + the single chrome mount in ContentView. Any new
        // reference must go through the same reviewed presentation decision.
        #expect(
            referencingFiles == [
                "Views/Auth/AuthSheetView.swift",
                "Views/Shell/ContentView/ContentView.swift"
            ],
            "AuthSheetView referenced from unexpected files: \(referencingFiles)"
        )
        let contentView = try #require(
            try Self.appSources().first { $0.path.hasSuffix("ContentView/ContentView.swift") }
        )
        // macOS: modal sheet. iOS: full-screen cover — the one platform where a
        // full-screen sign-in is idiomatic, decided EXPLICITLY in code (#4359).
        #expect(contentView.source.contains(".sheet(isPresented: authSheetPresented)"))
        #expect(contentView.source.contains(".fullScreenCover(isPresented: authSheetPresented)"))
        #expect(contentView.source.contains("#if os(macOS)"))
    }
}
