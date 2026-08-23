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

    // MARK: - Dataset menus: consolidated behind ONE builder

    @Test("every dataset renderer builds its menu from the ONE shared DatasetRowMenu")
    func datasetRenderersShareTheirBuilder() throws {
        // Was five private copies offering four different menus. Consolidated
        // 2026-08-23; the row that used to assert the copies is this one.
        for surface in datasetSurfaces {
            let code = try code(at: surface.path)
            #expect(code.contains(surface.anchor), "\(surface.mode): scan read the wrong file")
            #expect(code.contains("DatasetRowMenu("),
                    "\(surface.mode) hand-rolled a row menu again")
        }
    }

    @Test("the dataset verbs are spelled in the shared builder and nowhere else")
    func datasetVerbsLiveInOnePlace() throws {
        let builder = try code(at: "Views/Library/ViewModes/Dataset/DatasetRowMenu.swift")
        for verb in ["\"Show Source Page\"", "\"Edit Date…\"", "\"Exclude from Processing\"",
                     "\"Exclude from Search\"", "\"Include Everywhere\"", "\"Run Workflow\""] {
            #expect(builder.contains(verb), "the shared dataset builder lost \(verb)")
        }
        for surface in datasetSurfaces {
            let code = try code(at: surface.path)
            for verb in ["\"Show Source Page\"", "\"Exclude from Processing\"", "\"Run Workflow\""] {
                #expect(!code.contains(verb), "\(surface.mode) spells \(verb) itself again")
            }
        }
    }

    @Test("dataset rows keep the narrower vocabulary — this is not the browse menu")
    func datasetMenuStaysNarrow() throws {
        // Deliberate (ruling, 2026-08-23): a dataset row's menu is narrower
        // than a browse row's — Edit Date belongs, duplicate/alias do not.
        // Widening it is a product decision, so it must not happen by drift.
        let builder = try code(at: "Views/Library/ViewModes/Dataset/DatasetRowMenu.swift")
        for verb in ["\"Duplicate\"", "\"Make Alias\"", "\"Rename\"", "\"New Folder\""] {
            #expect(!builder.contains(verb), "the dataset menu grew \(verb) without a ruling")
        }
    }

    @Test("Run Workflow is shared even where the menu around it is not")
    func runWorkflowSubmenuIsAlreadyShared() throws {
        // The one verb that was already consolidated, and the reason its
        // override test exists. Whatever else diverges, this must not.
        for path in ["Views/Library/LibraryView+ContextMenu.swift",
                     "Views/Library/ViewModes/Dataset/DatasetRowMenu.swift"] {
            #expect(try code(at: path).contains("RunWorkflowSubmenuItems("),
                    "\(path) forked the workflow submenu")
        }
    }

    @Test("the run-scope preamble is stated before the click, wherever it appears")
    func runScopeIsAlwaysStated() throws {
        // "Runs on N entries" before the submenu — the 2026-08-15 ruling that
        // a batch must name its scope BEFORE it is invoked, not after.
        // In ONE place now, which is the point: the preamble was copy-pasted
        // into Grid and Cards and absent from the other three.
        #expect(try code(at: "Views/Library/ViewModes/Dataset/DatasetRowMenu.swift")
            .contains("Runs on \\(targets.count) entries"))
    }

    // MARK: - EXPECTED DIVERGENCE: Table builds its menu per render

    @Test("every browse mode defers menu construction to open time")
    func menuDeferralIsUniversal() throws {
        // #4544: building a menu per render costs on every row pass. Table was
        // the last mode still doing it; consolidated 2026-08-23.
        for path in ["Views/Library/ViewModes/Icon/LibraryView+IconMode.swift",
                     "Views/Library/ViewModes/List/LibraryView+ListView.swift",
                     "Views/Library/ViewModes/Columns/LibraryView+ColumnsView.swift",
                     "Views/Library/ViewModes/Table/LibraryView+TableView.swift"] {
            #expect(try code(at: path).contains("SidebarDeferredMenuContent"),
                    "\(path) stopped deferring its menu")
        }
    }

    // MARK: - B1 RESOLVED: every surface acts on the selection you can SEE

    @Test("the bar acts on the visible surface's selection, in every mode")
    func everySurfacePublishesItsSelection() throws {
        // Daniel's ruling, 2026-08-23: "visible surface, always". The bar and
        // the menu bar act on `selection`; every mode now WRITES that
        // selection, so the verb and the thing it targets are the same in all
        // of them. Dataset was the exception — it owned a private @State.
        let bar = try code(at: "Views/Library/LibraryView+BottomActionBar.swift")
        #expect(bar.contains("selectedDocumentIdsForBatch = Array(selection)"))

        let dataset = try code(at: "Views/Library/ViewModes/Dataset/DatasetModeView.swift")
        #expect(dataset.contains("@Binding var selection: Set<String>"),
                "dataset owns its selection again — the bar would target rows the user cannot see")
        #expect(!dataset.contains("@State private var selection"))
        #expect(try code(at: "Views/Library/LibraryView+ContentBranches.swift")
            .contains("selection: $selection"), "the dataset branch stopped binding the selection")
    }

    @Test("a single dataset selection still routes the other panes")
    func datasetSelectionDrivesThePreview() throws {
        // The other half of the ruling ("if card suggests showing full page
        // great, if bbox great"): one chosen row opens the document, which is
        // what drives preview / reader / inspector. Sharing the selection
        // upward must not cost that router.
        let dataset = try code(at: "Views/Library/ViewModes/Dataset/DatasetModeView.swift")
        #expect(dataset.contains(".onChange(of: selection)"))
        #expect(dataset.contains("onOpen(row)"))
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
