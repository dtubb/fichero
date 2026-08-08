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
