//
//  SelectAllVisibleSurfaceTests.swift
//  FicheroTests
//
//  Daniel, 2026-08-23: ⌘A selects all VISIBLE in the focused surface — "one
//  chord, one owner". The routing seam already existed (#4376,
//  `SelectAllRoutingPolicy`); what was missing was that the library's answer to
//  "what am I showing?" did not follow the mode.
//
//  Two defects this pins:
//   1. dataset modes filter by date and prototype in their OWN store, so ⌘A
//      selected the folder's documents rather than the rows on screen — the
//      same defect as B1, in a second costume;
//   2. the 3D board renders a bounded prefix of a large scope, so ⌘A reached
//      past the cap to cards that are not there.
//

@testable import Fichero
import Foundation
import Testing

struct SelectAllVisibleSurfaceTests {

    private func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    private static func code(of source: String) -> String {
        source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> Substring in
                guard let marker = line.range(of: "//") else { return line }
                return line[line.startIndex..<marker.lowerBound]
            }
            .joined(separator: "\n")
    }

    private func code(at relativePath: String) throws -> String {
        Self.code(of: try appSource(relativePath))
    }

    // MARK: - One owner

    @Test("⌘A is claimed in exactly ONE place")
    func oneChordOneOwner() throws {
        // The canvas used to handle ⌘A itself, over every node in scope. Which
        // answer the user got depended on where focus happened to be.
        let button = try code(at: "App/Menus/FocusedCommandButtons+SelectAll.swift")
        #expect(button.contains("struct SelectAllButton"))
        #expect(button.contains(".keyboardShortcut(\"a\", modifiers: .command)"))

        let canvasNav = try code(at: "Views/Library/ViewModes/Canvas/CanvasKeyboardNav.swift")
        #expect(canvasNav.contains("onKeyPress"), "scan read the wrong file")
        #expect(!canvasNav.contains("SelectionGrammar.selectAll("),
                "the canvas claimed ⌘A again — one chord, one owner")
    }

    @Test("the reader keeps falling through to WebKit — pinned, not implemented")
    func readerFallsThrough() throws {
        // The policy routes `.none` when neither a text editor nor library rows
        // hold focus, which DISABLES the item so the key equivalent reaches the
        // system Select All and the web view selects its own text. That IS
        // "reader → all text"; claiming ⌘A there and guessing would be the
        // #4354 bug in a new costume. This test exists so nobody "fixes" it.
        let policy = try code(at: "App/Menus/UndoRouting.swift")
        #expect(policy.contains("enum SelectAllRoutingPolicy"))
        #expect(policy.contains("return .none"))

        let button = try code(at: "App/Menus/FocusedCommandButtons+SelectAll.swift")
        #expect(button.contains(".disabled(route == .none)"))
    }

    // MARK: - The library's answer follows the visible surface

    @Test("every mode whose visible set differs from the document list says so")
    func selectAllIdsFollowsTheMode() throws {
        let source = try code(at: "Views/Library/LibraryView+DeleteActions.swift")
        #expect(source.contains("var selectAllIds: [String]"), "scan read the wrong file")
        // Dataset: its store's filters, not the folder's documents.
        #expect(source.contains("displayMode.group == .dataset"))
        #expect(source.contains("return datasetVisibleIds"))
        // Space: the rendered prefix, not the whole scope.
        #expect(source.contains("displayMode == .space"))
        #expect(source.contains("return renderedSpaceDocumentIds"))
    }

    @Test("the board's cap is read from the view that applies it")
    func capIsNotDuplicated() throws {
        // Two copies of a bound is how "visible" comes to mean two things.
        let library = try code(at: "Views/Library/LibraryView+DeleteActions.swift")
        #expect(library.contains("CanvasSpaceView.maxRenderedPlaceables"))
        #expect(!library.contains("10_000"), "the library hardcoded the render cap")

        let canvas = try code(at: "Views/Library/ViewModes/Canvas/3D/CanvasSpaceView.swift")
        #expect(canvas.contains("static let maxRenderedPlaceables = 10_000"))
        #expect(canvas.contains("prefix(Self.maxRenderedPlaceables)"),
                "the view stopped applying the bound it publishes")
    }

    @Test("the dataset publishes what it shows, in the order it shows it")
    func datasetPublishesVisibleIds() throws {
        let dataset = try code(at: "Views/Library/ViewModes/Dataset/DatasetModeView.swift")
        #expect(dataset.contains("var onVisibleIds: ([String]) -> Void"))
        #expect(dataset.contains("onVisibleIds(store.orderedVisibleRows.map(\\.id))"))
        // Status and the id list travel together — they answer the same
        // question, and drifting apart would put ⌘A and the status line on
        // different row sets.
        #expect(dataset.contains("reportSelectionStatus()"))
        let branch = try code(at: "Views/Library/LibraryView+ContentBranches.swift")
        #expect(branch.contains("onVisibleIds: { datasetVisibleIds = $0 }"))
    }

    @Test("the command is enabled by the SAME list it will act on")
    func enablementMatchesTheAction() throws {
        // Asking a different question when enabling than when acting is how a
        // command comes up live and then does nothing — or comes up dead over a
        // surface full of rows.
        let shortcuts = try code(at: "Views/Library/LibraryView+KeyboardShortcuts.swift")
        #expect(shortcuts.contains("isEnabled: !selectAllIds.isEmpty"))
        #expect(!shortcuts.contains("filteredDocuments.isEmpty"),
                "enablement asks a different question than selectAllIds answers")
    }
}
