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
        let button = try code(at: "App/Menus/FocusedCommands/FocusedCommandButtons+SelectAll.swift")
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

        let button = try code(at: "App/Menus/FocusedCommands/FocusedCommandButtons+SelectAll.swift")
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
        // `selectAllIds` is computed ONCE into `rowIds` and used for both the
        // enablement and the action's identity (2026-09-01: the stale-closure
        // fix) — one answer to one question.
        #expect(shortcuts.contains("let rowIds = selectAllIds"))
        #expect(shortcuts.contains("isEnabled: !rowIds.isEmpty"))
        #expect(!shortcuts.contains("filteredDocuments.isEmpty"),
                "enablement asks a different question than selectAllIds answers")
    }

    // MARK: - Slice C: the policy widened without touching the fall-through

    @Test("precedence comes from FOCUS, not from who published")
    func precedenceComesFromFocus() throws {
        // The publications are scene-scoped, so the library's is live whenever
        // a library pane is on screen — including while the inspector has
        // focus. Deciding by "who published" would hand every ⌘A to the
        // library forever.
        let button = try code(at: "App/Menus/FocusedCommands/FocusedCommandButtons+SelectAll.swift")
        #expect(button.contains("@FocusedValue(\\.focusedPaneKind)"))
        #expect(button.contains("private var focusedSurface: SelectAllSurface?"))
        #expect(button.contains("case .inspector:"))

        let shell = try code(at: "Views/Shell/ContentView/Layout/ContentView+RootLayout.swift")
        #expect(shell.contains("focusedSceneValue(\\.focusedPaneKind, focusedPane ?? paneFocusHint)"),
                "the shell stopped publishing which pane has focus")
    }

    @Test("the library stays the default owner when no pane hint exists")
    func libraryRemainsTheDefault() throws {
        // The widening must not change a plain library window's behaviour: no
        // hint at all still routes to the library.
        let button = try code(at: "App/Menus/FocusedCommands/FocusedCommandButtons+SelectAll.swift")
        let tail = try #require(button.components(separatedBy: "private var focusedSurface").last)
        let body = try #require(tail.components(separatedBy: "\n    }").first)
        #expect(body.contains("default:"))
        #expect(body.contains("librarySelectAll?.isEnabled == true ? .libraryRows : nil"))
    }

    // MARK: - Slice D: what publishes, and what deliberately does not

    @Test("the inspector's entity list publishes a select-all")
    func inspectorListPublishes() throws {
        let tab = try code(at: "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab.swift")
        #expect(tab.contains("\\.inspectorSelectAll"))
        // Through the grammar, so ⌘A leaves a usable anchor (#4377) — the same
        // rule the library follows.
        #expect(tab.contains("SelectionGrammar.selectAll("))
        #expect(tab.contains("entitySelectionAnchor = all.anchor"))
        // Published, not handled: a local .onKeyPress here would be the
        // canvas's mistake in a new pane.
        #expect(!tab.contains("onKeyPress(.init(\"a\")"))
    }

    // MARK: - The three live bugs, 2026-08-23

    @Test("the Edit menu carries exactly ONE Select All row")
    func oneSelectAllRow() throws {
        // It showed two: ours with the shortcut, and the system's disabled
        // beneath it. `after: .pasteboard` ADDS beside the system group;
        // `replacing: .textEditing` takes over the group that carries Select
        // All, which is the only way to have one row.
        let app = try code(at: "FicheroApp.swift")
        #expect(app.contains("CommandGroup(replacing: .textEditing)"))
        #expect(!app.contains("CommandGroup(after: .pasteboard)"),
                "the system Select All is back beside ours")
        #expect(app.components(separatedBy: "SelectAllButton()").count - 1 == 1,
                "more than one Select All row is declared")
    }

    @Test("every pane claims focus when clicked, so ⌘A can follow it")
    func everyPaneClaimsFocus() throws {
        // Preview and reading carried no focus gesture, so the hint never left
        // .content and ⌘A over a clicked preview still went to the library.
        let spec = try code(at: "Views/Shell/ContentView/Layout/PaneSpec.swift")
        for pane in [".content", ".chat", ".preview", ".reading"] {
            #expect(spec.contains("focusedPane = \(pane); paneFocusHint = \(pane)"),
                    "the \(pane) pane does not claim focus on click")
        }
    }

    @Test("the reader declines EXPLICITLY, rather than by accident")
    func readerDeclinesOnPurpose() throws {
        // It routed correctly before only because the library's enablement
        // happened to be false — an accident, not a decision. Now `.reading`
        // returns nil in its own branch, with the reason at the site.
        let button = try code(at: "App/Menus/FocusedCommands/FocusedCommandButtons+SelectAll.swift")
        let tail = try #require(button.components(separatedBy: "case .reading:").last)
        let branch = try #require(tail.components(separatedBy: "default:").first)
        #expect(branch.contains("return nil"))
    }

    // MARK: - What each surface answers with

    @Test("the preview selects the WHOLE image, through the marquee it already has")
    func previewSelectsTheWholeImage() throws {
        // My earlier audit recorded "the image editor has no selection concept"
        // — that was WRONG, and worth saying plainly: the concept lives in
        // ImageMarqueeOverlay (a normalized 0…1 rect), not in the canvas file I
        // scanned. So ⌘A needed no new concept, only its full extent.
        let editor = try code(at: "Views/Preview/ImageEditor/ImageEditorView.swift")
        #expect(editor.contains("\\.previewSelectAll"))
        #expect(editor.contains("CGRect(x: 0, y: 0, width: 1, height: 1)"))
        #expect(editor.contains("isEnabled: model.preview != nil"),
                "the preview claims ⌘A with no image shown")
    }

    @Test("the sidebar selects the CURRENT library's visible rows, never across libraries")
    func sidebarSelectsOneLibrary() throws {
        // Daniel's ruling. Several libraries open at once is the normal state,
        // and a chord reaching all of them would select things the user cannot
        // see and did not open.
        let sections = try code(at: "Views/Sidebar/Sections/SidebarView+UnifiedLibrarySections.swift")
        #expect(sections.contains("var currentLibraryVisibleDestinations: [SidebarDestination]"))
        #expect(sections.contains("libraryManager.currentLibraryId"))
        // VISIBLE has two halves: the group is expanded, and the rows are the
        // ones the view actually renders.
        #expect(sections.contains("sidebarState.isLibraryExpanded(libraryId)"))
        #expect(sections.contains("flattenedLibraryItems(libraryId: libraryId, buckets: buckets)"))

        let components = try code(at: "Views/Sidebar/Sections/SidebarView+ViewComponents.swift")
        #expect(components.contains("\\.sidebarSelectAll"))
        // Through the same commit seam a click uses, so a select-all cannot
        // bypass the resilience filter and primary derivation.
        #expect(components.contains("applySidebarSelectionProposal(Set(currentLibraryVisibleDestinations))"))
    }
}