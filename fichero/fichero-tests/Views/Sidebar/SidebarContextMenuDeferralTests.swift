//
//  SidebarContextMenuDeferralTests.swift
//  FicheroTests
//
//  Pins the #4544 fix: sidebar row context menus are built at MENU OPEN via
//  SidebarDeferredMenuContent, never eagerly per row render. A bare
//  `.contextMenu { rowContextMenu }` re-introduces the 506-sample-per-profile
//  render cost this removed, so the pin reads the source and fails on it.
//

import Foundation
import SwiftUI
import Testing
@testable import Fichero

struct SidebarContextMenuDeferralTests {

    private func presentationBodySource() throws -> String {
        // Repo-root-relative resolution, same pattern as the other
        // source-pin tests (ReaderPageActivationTests).
        let thisFile = URL(fileURLWithPath: #filePath)
        let repoRoot = thisFile
            .deletingLastPathComponent()  // drop the file → Sidebar/
            .deletingLastPathComponent()  // Views/
            .deletingLastPathComponent()  // fichero-tests/
            .deletingLastPathComponent()  // fichero/ (the product dir)
            .deletingLastPathComponent()  // repo root
        let source = repoRoot.appendingPathComponent(
            "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+Presentation+Body.swift"
        )
        return try String(contentsOf: source, encoding: .utf8)
    }

    @Test("Every row context menu defers construction to menu open (#4544)")
    func allContextMenusAreDeferred() throws {
        let source = try presentationBodySource()

        let deferred = source.components(
            separatedBy: ".contextMenu { SidebarDeferredMenuContent { rowContextMenu } }"
        ).count - 1
        #expect(
            deferred == 3,
            "Expected the 3 row shapes (disclosure, folder, leaf) to defer; found \(deferred)."
        )

        #expect(
            !source.contains(".contextMenu { rowContextMenu }"),
            """
            A bare `.contextMenu { rowContextMenu }` builds the whole menu tree \
            on every row render (506 main-thread samples in aug4.trace). Wrap \
            it in SidebarDeferredMenuContent.
            """
        )
    }

    @Test("Deferred wrapper evaluates its content only in body")
    func wrapperDefersEvaluation() {
        var evaluated = 0
        _ = SidebarDeferredMenuContent {
            evaluated += 1
            return Text("menu item")
        }
        // Constructing the wrapper (what a row render now pays) must not
        // evaluate the content closure — that is the entire point.
        #expect(evaluated == 0)
    }
}
