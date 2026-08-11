//
//  PreviewHostGuardTests.swift
//  FicheroTests
//
//  Pins the 2026-08-08 preview-host guard: Xcode Previews launch the REAL
//  Fichero.app to render one view. Before the guard, the app delegate spawned
//  a real embedded engine inside the preview host — which fought the live ⌘R
//  instance over the container socket and blew the preview's 30s launch
//  window ("Failed to launch app 'Fichero.app' in reasonable time"), so the
//  SidebarPreviewCatalog never rendered. Previews are pure SwiftUI over
//  fixtures; the delegate must bail exactly like it does for XCTest (#3902).
//

import Foundation
import Testing
@testable import Fichero

struct PreviewHostGuardTests {

    private func appSource() throws -> String {
        let repoRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // Services/
            .deletingLastPathComponent()  // fichero-tests/
            .deletingLastPathComponent()  // fichero/ (product dir)
            .deletingLastPathComponent()  // repo root
        let source = repoRoot.appendingPathComponent("fichero/fichero/FicheroApp.swift")
        let text = try String(contentsOf: source, encoding: .utf8)
        #expect(!text.isEmpty, "FicheroApp.swift is empty — this guard measures nothing")
        return text
    }

    @Test("the app delegate never starts an engine inside the Xcode Previews host")
    func delegateGuardsPreviewHost() throws {
        let source = try appSource()
        // The delegate half of the guard — FicheroApp.init's skip covers only
        // installer/restore; the engine spawn lives in
        // applicationDidFinishLaunching and needs its own bail-out.
        let didFinish = source.range(of: "func applicationDidFinishLaunching")
        let controllerStart = source.range(of: "controller.start()")
        let previewGuard = source.range(
            of: "guard ProcessInfo.processInfo.environment[\"XCODE_RUNNING_FOR_PREVIEWS\"] != \"1\" else { return }"
        )
        #expect(didFinish != nil, "applicationDidFinishLaunching moved — repoint this pin")
        #expect(controllerStart != nil, "engine start moved — repoint this pin")
        #expect(previewGuard != nil, "the preview-host guard is gone")
        if let didFinish, let controllerStart, let previewGuard {
            #expect(
                didFinish.lowerBound < previewGuard.lowerBound
                    && previewGuard.lowerBound < controllerStart.lowerBound,
                "the preview guard must sit between the delegate entry and the engine start"
            )
        }
    }
}
