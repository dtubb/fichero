//
//  SidebarItemRowSlimmingTests.swift
//  FicheroTests
//
//  Pins the #4545 row-slimming fix: SidebarItemRow resolves rows through an
//  O(1) id-lookup closure, never by storing the whole cached forest. The
//  aug4 profile measured ~740 main-thread samples just copying row structs;
//  re-adding an `allCachedItems: [SidebarItem]` stored property makes every
//  row carry (and copy) the forest again AND invalidates every row whenever
//  any row changes.
//

import Foundation
import Testing
@testable import Fichero

struct SidebarItemRowSlimmingTests {

    private func rowSource() throws -> String {
        let repoRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // drop the file → Sidebar/
            .deletingLastPathComponent()  // Views/
            .deletingLastPathComponent()  // fichero-tests/
            .deletingLastPathComponent()  // fichero/ (the product dir)
            .deletingLastPathComponent()  // repo root
        let source = repoRoot.appendingPathComponent(
            "fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow.swift"
        )
        return try String(contentsOf: source, encoding: .utf8)
    }

    @Test("SidebarItemRow stores a lookup closure, not the forest (#4545)")
    func rowStoresLookupNotForest() throws {
        let source = try rowSource()
        #expect(
            !source.contains("let allCachedItems"),
            """
            SidebarItemRow must not store the cached forest — every row copies \
            its stored properties on each SwiftUI diff (~740 samples in \
            aug4.trace). Resolve rows via the lookupItem closure instead.
            """
        )
        #expect(source.contains("let lookupItem: (String) -> SidebarItem?"))
    }
}
