@testable import Fichero
import Foundation
import Testing

/// Launch-cost regressions are silent: every one this week (#3928, #3936, #3945)
/// shipped without an error, a log line, or a failing test, and was found by hand.
/// #3946's fix is to **assert on the WORK, not the clock** — a wall-clock budget on
/// a dev Mac flakes and gets `@skip`ed, but the deterministic shape of the launch
/// path does not. Each assertion here names a real regression the codebase already
/// paid for, and costs nothing: it reads source, needs no engine, cannot flake.
///
/// Source-level (mirroring `LaunchPathNoModalTests`) because these invariants are
/// structural. Watching them at runtime would mean launching the real app and the
/// 1 GB engine — the exact thing #3968 shows the UI harness cannot reliably do.
struct StartupWorkGateTests {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// Assert `needle` appears within `window` characters *before* the first
    /// occurrence of `anchor` — i.e. `anchor` is lexically enclosed by `needle`.
    /// A cheap "B is wrapped by A" check that survives whitespace/formatting churn.
    private static func expectEnclosedBy(
        _ source: String,
        anchor: String,
        by needle: String,
        within window: Int = 400,
        _ comment: Comment
    ) throws {
        let anchorRange = try #require(
            source.range(of: anchor), "expected to find \(anchor) in source"
        )
        let start = source.index(
            anchorRange.lowerBound,
            offsetBy: -window,
            limitedBy: source.startIndex
        ) ?? source.startIndex
        let preface = source[start..<anchorRange.lowerBound]
        #expect(preface.contains(needle), comment)
    }

    /// Return the brace-balanced body of the first function whose declaration
    /// contains `declaration`. Lets a test assert "X happens *inside* this
    /// function" without a fragile character window that breaks as the body grows.
    private static func functionBody(containing declaration: String, in source: String) throws -> Substring {
        let declRange = try #require(
            source.range(of: declaration), "expected to find \(declaration) in source"
        )
        let openBrace = try #require(
            source.range(of: "{", range: declRange.upperBound..<source.endIndex),
            "expected an opening brace after \(declaration)"
        )
        var depth = 0
        var index = openBrace.lowerBound
        while index < source.endIndex {
            let character = source[index]
            if character == "{" { depth += 1 }
            if character == "}" {
                depth -= 1
                if depth == 0 {
                    return source[openBrace.upperBound..<index]
                }
            }
            index = source.index(after: index)
        }
        Issue.record("unbalanced braces after \(declaration)")
        return source[openBrace.upperBound..<source.endIndex]
    }

    /// #3945: the engine spawn is an APP event, owned by the AppDelegate's
    /// `applicationDidFinishLaunching`, not a window's `.task`. A window is not an
    /// engine, so opening one must not be what starts (or fails to start) it — the
    /// symptom behind #3968, where no window materialised and nothing ever spawned.
    @Test("engine spawn is triggered from the AppDelegate, not a window .task")
    func engineSpawnIsAppScoped() throws {
        let source = try Self.appSource("FicheroApp.swift")
        #expect(
            source.contains("func applicationDidFinishLaunching"),
            "the app-level launch hook must exist to own the spawn"
        )
        try Self.expectEnclosedBy(
            source,
            anchor: "controller.start()",
            by: "applicationDidFinishLaunching",
            within: 600,
            "the engine start must live in applicationDidFinishLaunching (#3945)"
        )
        // The pre-#3945 shape hung the spawn off a window's `.task { await
        // backendService.start() }`. If that call reappears in the App/Scene
        // source, the spawn is window-gated again.
        #expect(
            !source.contains("backendService.start"),
            "the window must not start the engine; the app-scoped controller does (#3945)"
        )
    }

    /// #3936: the TLS-prep subprocess spawns the ~1 GB engine and blocks on
    /// `waitUntilExit()` for ~2.7s on every first/dev launch. It must run OFF the
    /// main actor — the cache lookup stays on main, the subprocess is `Task.detached`.
    @Test("the TLS-prep subprocess is dispatched off the main actor")
    func tlsPrepRunsOffMainActor() throws {
        let source = try Self.appSource("Services/EmbeddedBackendService.swift")
        try Self.expectEnclosedBy(
            source,
            anchor: "runEngineTLSPrep(",
            by: "Task.detached",
            "the TLS subprocess must be spawned in a detached task, not on @MainActor (#3936)"
        )
    }

    /// #3936/#3928: the blocking `process.waitUntilExit()` on the TLS path is only
    /// safe because its owner is `nonisolated` — a plain method on this @MainActor
    /// class would run the 2.7s wait on the main actor and freeze first frame.
    /// This pins the isolation, so demoting it back to main-actor fails loudly.
    @Test("the launch TLS-prep function is nonisolated, keeping its blocking wait off-main")
    func tlsPrepBlockingWaitIsOffMain() throws {
        let source = try Self.appSource("Services/EmbeddedBackendService.swift")
        #expect(
            source.contains("nonisolated private static func runEngineTLSPrep"),
            "runEngineTLSPrep must stay nonisolated so its waitUntilExit() cannot run on @MainActor (#3936)"
        )
        // The blocking wait must live INSIDE that nonisolated function — not have
        // been hoisted onto a @MainActor caller. `EmbeddedBackendService` is a
        // @MainActor class, so any waitUntilExit() outside a nonisolated member
        // blocks first frame.
        let body = try Self.functionBody(
            containing: "nonisolated private static func runEngineTLSPrep", in: source
        )
        #expect(
            body.contains("process.waitUntilExit()"),
            "the TLS subprocess wait must stay inside the nonisolated function (#3928/#3936)"
        )
    }
}
