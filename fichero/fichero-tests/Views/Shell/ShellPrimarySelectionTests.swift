//
//  ShellPrimarySelectionTests.swift
//  FicheroTests
//
//  Pins the 2026-08-09 selection-identity fix: the shell's browserSelection
//  handler drew `Set.first` THREE times (entity focus, preview promotion,
//  stale-fetch guard) — hash order, so each draw could name a DIFFERENT
//  element of the same multi-selection, and actions could target a row the
//  user never considered primary. One helper now answers in DOCUMENT ORDER
//  (what the user sees), with a stable lexical fallback for unloaded ids.
//

@testable import Fichero
import Foundation
import Testing

struct ShellPrimarySelectionTests {

    private func doc(_ id: String) -> Document {
        Document(id: id, docType: .file, name: id)
    }

    @Test("primary follows the visible document order, not set hash order")
    func documentOrderWins() {
        let docs = [doc("c"), doc("a"), doc("b")]
        #expect(shellPrimarySelectionId(in: ["a", "b"], orderedBy: docs) == "a")
        #expect(shellPrimarySelectionId(in: ["b", "c"], orderedBy: docs) == "c")
    }

    @Test("ids not in the loaded list fall back to the stable lexical minimum")
    func unloadedFallsBackStably() {
        #expect(shellPrimarySelectionId(in: ["z-late", "m-mid"], orderedBy: []) == "m-mid")
        // Deterministic across calls — the property Set.first lacks.
        for _ in 0..<10 {
            #expect(shellPrimarySelectionId(in: ["z", "y", "x"], orderedBy: []) == "x")
        }
    }

    @Test("empty selection has no primary")
    func emptyIsNil() {
        #expect(shellPrimarySelectionId(in: [], orderedBy: [doc("a")]) == nil)
    }

    @Test("a partially-loaded selection still prefers the visible member")
    func partiallyLoadedPrefersVisible() {
        // "z-visible" is on screen; "a-unloaded" would win the lexical
        // fallback — visibility must win over lexical order.
        #expect(
            shellPrimarySelectionId(in: ["a-unloaded", "z-visible"], orderedBy: [doc("z-visible")])
                == "z-visible"
        )
    }
}

/// F2 (page-1 snapback) and F4 (right-click targeting) shipped without
/// tests; both fix symptoms Daniel reported personally, so a silent
/// regression is indistinguishable from the original bug. Source pins —
/// the F2 handler mutates @State and the F4 resolver is private, so the
/// RULE is pinned where it lives.
struct ReportedSymptomRegressionPins {

    private func source(_ repoRelative: String) throws -> String {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // Shell/
            .deletingLastPathComponent()  // Views/
            .deletingLastPathComponent()  // fichero-tests/
            .deletingLastPathComponent()  // fichero/ (product dir)
        return try String(contentsOf: root.appendingPathComponent(repoRelative), encoding: .utf8)
    }

    @Test("F2: page focus clears only when the document IDENTITY changes")
    func pageFocusClearIsIdentityGated() throws {
        let events = try source("fichero/Views/Shell/ContentView/ContentView+StateEvents.swift")
        #expect(
            events.contains("if oldDoc?.id != newDoc?.id {"),
            "the unconditional pageFocusDocument clear is back — every background refresh snaps the reader to page 1 (#4558)"
        )
        #expect(events.contains("func handleDetailDocumentChange(from oldDoc: Document?, to newDoc: Document?)"))
    }

    @Test("F4: right-click targets follow the clicked-row rule")
    func rightClickTargetsClickedRow() throws {
        let menu = try source("fichero/Views/Library/LibraryView+ContextMenu.swift")
        #expect(
            menu.contains("selection.contains(document.id) ? Array(selection) : [document.id]"),
            "excludeToggleTargets reverted to selection-wins — right-click acts on rows the user never pointed at"
        )
        #expect(
            !menu.contains("selection.isEmpty ? [document.id] : Array(selection)"),
            "the inverted (selection-wins) form is back"
        )
    }

    @Test("F3: no shell surface draws a primary from Set.first any more")
    func noPrimaryDrawsRemain() throws {
        for path in [
            "fichero/Views/Shell/ContentView/ContentView+StatePreview.swift",
            "fichero/Views/Shell/ContentView/ContentView+StateSelection.swift",
            "fichero/Views/Shell/ContentView/Layout/ContentView+CompactReader.swift",
            "fichero/Models/LayoutMode.swift"
        ] {
            let text = try source(path)
            #expect(!text.contains("browserSelection.first"), "hash-order draw back in \(path)")
            #expect(!text.contains("selectedDocumentIds.first"), "hash-order draw back in \(path)")
        }
    }
}
