//
//  LibraryMenuParityTests.swift
//  FicheroTests
//
//  Daniel, 2026-08-23: "make sure all library views are following the same code
//  paths, especially for contextual menus, menu-bar menus, and bottom-right
//  menus."
//
//  The defect class: N view modes each growing a private copy of a menu that
//  should be ONE shared implementation, until the same label does different
//  things depending on which mode you happen to be in. `SelectionSurfaceParity`
//  is the same idea for gestures; this is the table of MENUS.
//
//  **This file describes the surface as it IS**, including the divergences that
//  are filed findings rather than bugs to fix here. That is deliberate: a
//  consolidation is only provably behaviour-preserving if the guard was green
//  before it. A row that changes intentionally is edited in the same commit
//  that changes it, with the ruling cited — and `EXPECTED DIVERGENCE` marks the
//  rows that are waiting on Daniel, so the matrix is honest about them rather
//  than silent.
//

@testable import Fichero
import Foundation
import Testing

struct LibraryMenuParityTests {

    // MARK: - Reading the surface

    private func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    /// Source with comments stripped — a scan that reads prose fires on the
    /// very doc comment explaining the rule (the `CanvasPanInputParityTests`
    /// helper, and the lesson of 2026-08-22).
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

    // MARK: - The matrix

    /// One library surface and where its right-click menu comes from.
    private struct Surface {
        let mode: String
        let path: String
        /// A token that must appear in the file, proving the scan read the real
        /// thing — an empty or mis-pathed read satisfies every negative
        /// assertion otherwise.
        let anchor: String
    }

    /// BROWSE modes and both canvases: all route through the ONE shared
    /// builder, `documentContextMenu(for:)`. This is the parity that already
    /// holds and must not rot.
    private let sharedBuilderSurfaces = [
        Surface(mode: "Icon", path: "Views/Library/ViewModes/Icon/LibraryView+IconMode.swift",
                anchor: "LibraryIconCell"),
        Surface(mode: "List", path: "Views/Library/ViewModes/List/LibraryView+ListView.swift",
                anchor: "MailStyleRow"),
        Surface(mode: "Table", path: "Views/Library/ViewModes/Table/LibraryView+TableView.swift",
                anchor: "contextMenu(forSelectionType:"),
        Surface(mode: "Columns", path: "Views/Library/ViewModes/Columns/LibraryView+ColumnsView.swift",
                anchor: "MillerColumn"),
        Surface(mode: "Canvas 2D/3D", path: "Views/Library/LibraryView+CanvasModes.swift",
                anchor: "canvasContextMenu"),
    ]

    /// DATASET renderers: five private copies of a narrower menu. Consolidating
    /// them behind one builder is the job; this row set is what says whether
    /// that happened, and it is edited when it does.
    private let datasetSurfaces = [
        Surface(mode: "Dataset · Grid", path: "Views/Library/ViewModes/Dataset/Grid/DatasetGridView.swift",
                anchor: "DatasetGridView"),
        Surface(mode: "Dataset · Cards", path: "Views/Library/ViewModes/Dataset/Cards/DatasetCardsView.swift",
                anchor: "DatasetCardsView"),
        Surface(mode: "Dataset · Calendar", path: "Views/Library/ViewModes/Dataset/Calendar/DatasetCalendarView.swift",
                anchor: "DatasetCalendarView"),
        Surface(mode: "Dataset · Timeline", path: "Views/Library/ViewModes/Dataset/Timeline/DatasetTimelineView.swift",
                anchor: "DatasetTimelineView"),
        Surface(mode: "Dataset · Map", path: "Views/Library/ViewModes/Dataset/Map/DatasetMapView.swift",
                anchor: "DatasetMapView"),
    ]

    // MARK: - Context menus

    @Test("every browse mode and both canvases build their row menu from the ONE shared builder")
    func browseModesShareTheBuilder() throws {
        for surface in sharedBuilderSurfaces {
            let code = try code(at: surface.path)
            #expect(code.contains(surface.anchor), "\(surface.mode): scan read the wrong file")
            #expect(code.contains("documentContextMenu(for:"),
                    "\(surface.mode) hand-rolled a row menu instead of using documentContextMenu")
        }
    }

    @Test("the shared builder is the only place the row verbs are spelled")
    func rowVerbsLiveInOnePlace() throws {
        // If a mode ever spells these itself, the same label starts doing
        // different things in two modes — the worst class of this defect.
        let builder = try code(at: "Views/Library/LibraryView+ContextMenu.swift")
        for verb in ["Duplicate", "Make Alias", "New Folder", "Rename"] {
            #expect(builder.contains(verb), "the shared builder lost \(verb)")
        }
        for surface in sharedBuilderSurfaces where surface.mode != "Canvas 2D/3D" {
            let code = try code(at: surface.path)
            for verb in ["\"Duplicate\"", "\"Make Alias\"", "\"Rename\""] {
                #expect(!code.contains(verb), "\(surface.mode) spells \(verb) itself")
            }
        }
    }

    @Test("the canvases add exactly one verb of their own, and defer the rest")
    func canvasesExtendRatherThanFork() throws {
        let code = try code(at: "Views/Library/LibraryView+CanvasModes.swift")
        #expect(code.contains("Zoom to Card"))
        #expect(code.contains("documentContextMenu(for: doc)"))
    }

    // MARK: - EXPECTED DIVERGENCE: dataset menus are five private copies

    @Test("the dataset renderers still hand-roll their menus — filed, not fixed here")
    func datasetMenusAreStillPrivateCopies() throws {
        // The consolidation this audit exists to do. When a shared
        // `DatasetRowMenu` lands, this test is what has to be edited — and the
        // edit is the record that the copies are gone.
        for surface in datasetSurfaces {
            let code = try code(at: surface.path)
            #expect(code.contains(surface.anchor), "\(surface.mode): scan read the wrong file")
            #expect(!code.contains("documentContextMenu(for:"),
                    "\(surface.mode) now uses the browse builder — update this matrix row")
        }
    }

    @Test("Run Workflow is shared even where the menu around it is not")
    func runWorkflowSubmenuIsAlreadyShared() throws {
        // The one verb that was already consolidated, and the reason its
        // override test exists. Whatever else diverges, this must not.
        for path in ["Views/Library/LibraryView+ContextMenu.swift",
                     "Views/Library/ViewModes/Dataset/Grid/DatasetGridView.swift",
                     "Views/Library/ViewModes/Dataset/Cards/DatasetCardsView.swift"] {
            #expect(try code(at: path).contains("RunWorkflowSubmenuItems("),
                    "\(path) forked the workflow submenu")
        }
    }

    @Test("the run-scope preamble is stated before the click, wherever it appears")
    func runScopeIsAlwaysStated() throws {
        // "Runs on N entries" before the submenu — the 2026-08-15 ruling that
        // a batch must name its scope BEFORE it is invoked, not after.
        for path in ["Views/Library/ViewModes/Dataset/Grid/DatasetGridView.swift",
                     "Views/Library/ViewModes/Dataset/Cards/DatasetCardsView.swift"] {
            #expect(try code(at: path).contains("Runs on \\(targets.count) entries"),
                    "\(path) runs a batch without stating its scope")
        }
    }

    // MARK: - EXPECTED DIVERGENCE: Table builds its menu per render

    @Test("three of four browse modes defer menu construction to open time")
    func menuDeferralIsNotYetUniversal() throws {
        // #4544: building a menu per render costs on every row pass. Icon, List
        // and Columns defer; Table does not. Consolidating that is step 3 of
        // this audit, and this row changes when it lands.
        for path in ["Views/Library/ViewModes/Icon/LibraryView+IconMode.swift",
                     "Views/Library/ViewModes/List/LibraryView+ListView.swift",
                     "Views/Library/ViewModes/Columns/LibraryView+ColumnsView.swift"] {
            #expect(try code(at: path).contains("SidebarDeferredMenuContent"),
                    "\(path) stopped deferring its menu")
        }
        #expect(!(try code(at: "Views/Library/ViewModes/Table/LibraryView+TableView.swift"))
            .contains("SidebarDeferredMenuContent"),
                "Table now defers — update this matrix row")
    }

    // MARK: - EXPECTED DIVERGENCE (FILED, B1): the bar's target vs the visible surface

    @Test("the bottom bar acts on the BROWSER selection in every mode — filed finding B1")
    func bottomBarActsOnBrowserSelection() throws {
        // B1, for Daniel: `DatasetModeView` owns a private `selection`, so in
        // the five dataset modes the bar's Delete and Run Workflow target a
        // selection the user cannot see and did not make, while the context
        // menu two inches away targets the row they right-clicked. Same verb,
        // same screen, different set.
        //
        // Canvas is NOT affected: its selection IS `selection`, translated
        // (LibraryView.swift, "Canvas/spatial selection is NOT separate state").
        let bar = try code(at: "Views/Library/LibraryView+BottomActionBar.swift")
        #expect(bar.contains("selectedDocumentIdsForBatch = Array(selection)"))
        #expect(bar.contains("selection.isEmpty"))

        let dataset = try code(at: "Views/Library/ViewModes/Dataset/DatasetModeView.swift")
        #expect(dataset.contains("@State private var selection: Set<String> = []"),
                "dataset selection is no longer private — B1 may be resolved; update this row")
    }

    @Test("the bar renders in every mode, so its verbs are always reachable")
    func barIsNotGatedByMode() throws {
        // Not a defect on its own — it is what makes B1 matter, because the bar
        // is present precisely where its target is invisible.
        let insets = try code(at: "Views/Library/LibraryView+Insets.swift")
        #expect(insets.contains("libraryBottomActionBar"))
        #expect(!insets.contains("if displayMode.group != .dataset"))
    }

    // MARK: - EXPECTED DIVERGENCE (FILED, M1): two owners of ⌘A

    @Test("⌘A has two implementations — filed finding M1")
    func selectAllHasTwoOwners() throws {
        // M1, for Daniel: the menu command selects `filteredDocuments`;
        // CanvasKeyboardNav separately handles ⌘A over `nodeIds`. They disagree
        // whenever the board is truncated by the render caps, and which answers
        // depends on focus. One chord should have one owner.
        let menu = try code(at: "Views/Library/LibraryView+KeyboardShortcuts.swift")
        #expect(menu.contains("\\.librarySelectAll"))
        #expect(menu.contains("run: { selectAll() }"))

        let canvas = try code(at: "Views/Library/ViewModes/Canvas/CanvasKeyboardNav.swift")
        #expect(canvas.contains("SelectionGrammar.selectAll(in: nodeIds)"),
                "canvas ⌘A changed — M1 may be resolved; update this row")
    }

    @Test("menu-bar state is published once, for every mode alike")
    func focusedActionsArePublishedOnce() throws {
        // The half that is already right: one publish site, so no mode can
        // enable a command another mode leaves dead.
        let shortcuts = try code(at: "Views/Library/LibraryView+KeyboardShortcuts.swift")
        for key in ["\\.librarySelectAll", "\\.libraryDeleteSelection",
                    "\\.librarySortField", "\\.librarySortAscending"] {
            #expect(shortcuts.components(separatedBy: key).count - 1 == 1,
                    "\(key) is published from more than one site — two writers of one key")
        }
    }
}
