//
//  FolderAccessManagerSandboxGateTests.swift
//  FicheroTests
//
//  Pins the 2026-08-08 compile-gate fix: FolderAccessManager must decide
//  "are we sandboxed" at RUNTIME (SandboxEnvironment.isSandboxed), never via
//  the FICHERO_APP_STORE build flag. The flag was a proxy from when MAS was
//  the only sandboxed channel; that premise died on 2026-07-29, and the two
//  #if-gated grant methods silently compiled the engine handoff to a no-op
//  in every non-MAS build — zero POSTs to /api/sandbox/security-scoped-access
//  ever, every post-spawn library unreachable, folder-drop imports 403ing.
//  engineBookmarkPayload was fixed for the same class in 2026-08-04 and these
//  two were missed — hence a pin on the WHOLE FILE, not a site.
//

import Foundation
import Testing
@testable import Fichero

struct FolderAccessManagerSandboxGateTests {

    private func managerSource() throws -> String {
        let repoRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // drop the file → Services/
            .deletingLastPathComponent()  // fichero-tests/
            .deletingLastPathComponent()  // fichero/ (the product dir)
            .deletingLastPathComponent()  // repo root
        let source = repoRoot.appendingPathComponent(
            "fichero/fichero/Services/FolderAccessManager.swift"
        )
        let text = try String(contentsOf: source, encoding: .utf8)
        #expect(!text.isEmpty, "FolderAccessManager.swift is empty — this guard measures nothing")
        return text
    }

    @Test("FolderAccessManager never gates on the FICHERO_APP_STORE build flag")
    func noBuildFlagSandboxProxy() throws {
        let source = try managerSource()
        #expect(
            !source.contains("FICHERO_APP_STORE"),
            """
            FolderAccessManager must ask SandboxEnvironment.isSandboxed at runtime. \
            A FICHERO_APP_STORE gate here compiles the engine bookmark handoff to a \
            no-op in every non-MAS build — the 2026-08-08 zero-grants defect. If a \
            genuinely App-Store-only concern ever lands in this file, move it out.
            """
        )
    }

    @Test("Both grant methods carry the runtime sandbox guard")
    func grantMethodsUseRuntimeGuard() throws {
        let source = try managerSource()
        let guardCount = source.components(
            separatedBy: "guard SandboxEnvironment.isSandboxed else { return }"
        ).count - 1
        #expect(
            guardCount >= 2,
            "handOffToEngine and grantEngineAccess must each guard on the runtime "
                + "sandbox check; found \(guardCount) guard(s)."
        )
    }
}


/// The 2026-08-08 launch-grant race, pinned end to end: grants fired before
/// the engine authenticated, the engine refused all eleven, and nothing ever
/// re-sent them — every outside-container library stayed dead all session,
/// and both SSE streams sat in a "terminal" 403 forever.
struct PostReadyGrantSweepTests {

    private func source(_ repoRelative: String) throws -> String {
        let repoRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // Services/
            .deletingLastPathComponent()  // fichero-tests/
            .deletingLastPathComponent()  // fichero/ (product dir)
            .deletingLastPathComponent()  // repo root
        return try String(
            contentsOf: repoRoot.appendingPathComponent(repoRelative), encoding: .utf8
        )
    }

    @Test("first-authenticated-ready re-sends every persisted grant")
    func lifecycleRunsTheSweep() throws {
        let lifecycle = try source("fichero/fichero/Services/EngineLifecycleController.swift")
        #expect(
            lifecycle.contains("resendAllGrantsToEngine()"),
            "without the post-ready sweep, launch-time grant refusals are permanent"
        )
    }

    @Test("a successful grant announces that the engine's answer changed")
    func grantSuccessPostsTheNotification() throws {
        let manager = try source("fichero/fichero/Services/FolderAccessManager.swift")
        #expect(manager.contains("NotificationCenter.default.post(name: .ficheroEngineAccessChanged"))
    }

    @Test("both streams arm a revival when they hit the terminal 403")
    func deniedStreamsArmRevival() throws {
        for path in [
            "fichero/fichero/Services/ActivityStreamService.swift",
            "fichero/fichero/Services/LibraryChangeStream.swift",
        ] {
            let stream = try source(path)
            #expect(stream.contains("armRevivalOnAccessChange()"), "missing in \(path)")
            #expect(stream.contains(".ficheroEngineAccessChanged"), "missing in \(path)")
        }
    }
}
