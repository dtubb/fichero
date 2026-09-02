//
//  ModeScopeFollowsSearchTests.swift
//  FicheroTests
//
//  "Scope follows the VISIBLE SURFACE" (Daniel, 2026-08-23) — the ruling
//  `selectAllIds` already encodes. Two families were still opting out while
//  search results were showing:
//
//   · the spatial boards (canvas / workspace / space) projected the pane's
//     raw `documents` INPUT, so the ⌘F filter, the Show-kind narrowing and a
//     search's relevance ORDER were all invisible on a board;
//   · Miller columns rendered `documentStore.collections` — the library ROOT
//     listing — in column 0, so a query left the columns browsing the folder
//     tree while every other mode showed the hits.
//
//  These are facts about where an expression sits, so the guard reads the
//  source, the instrument `ListRowPerRowWorkTests` uses for the same reason.
//

@testable import Fichero
import Foundation
import Testing

@Suite("Every view mode scopes to the visible surface")
struct ModeScopeFollowsSearchTests {

    private static func appSource(_ relativePath: String) throws -> String {
        let source = try AppSource.text(relativePath)
        #expect(!source.isEmpty, "\(relativePath) is empty — this guard measures nothing")
        return source
    }

    // MARK: - Canvas / workspace / space

    @Test("the spatial projection is built from the FILTERED documents")
    func projectionUsesFilteredDocuments() throws {
        let insets = try Self.appSource("Views/Library/LibraryView+Insets.swift")
        #expect(insets.contains("documents: filteredDocuments.map {"),
                "projecting the raw `documents` parameter ignores the quick filter, "
                    + "the Show kind, and a search's relevance order")
        #expect(!insets.contains("documents: documents.map {"),
                "the un-filtered projection is exactly the defect")
    }

    @Test("all three spatial modes go through that one projection")
    func allSpatialModesShareTheProjection() throws {
        let insets = try Self.appSource("Views/Library/LibraryView+Insets.swift")
        // If a mode is added to this switch without a renderer change, it
        // still gets the scoped node set for free — which is the point of
        // having one seam.
        #expect(insets.contains("case .canvas, .space, .workspace: return true"))

        let canvas = try Self.appSource("Views/Library/LibraryView+CanvasModes.swift")
        // 2D canvas (both engines), 3D space (both engines) — every renderer
        // takes its nodes from the projection, never from `documents`.
        #expect(canvas.components(separatedBy: "nodes: libraryProjection.nodes").count - 1 == 4)
        #expect(!canvas.contains("nodes: documents"))
    }

    @Test("the projection cannot drift from the filter that feeds it")
    func projectionRefreshesWhereverTheFilterDoes() throws {
        let filter = try Self.appSource("Views/Library/LibraryView+FilterAndBatch.swift")
        #expect(filter.contains("refreshLibraryProjection()"),
                """
                `recomputeFiltered()` must refresh the projection: four handlers \
                (folderId, the sort writers, the Show kind, the debounced ⌘F pass) \
                call it WITHOUT a paired refresh, so a hand-maintained pairing \
                leaves a board showing the previous filter.
                """)

        // …and the callers no longer repeat it, or every revision tick pays twice.
        let body = try Self.appSource("Views/Library/LibraryView+Body.swift")
        #expect(!body.contains("recomputeFiltered()\n                refreshLibraryProjection()"),
                "the paired call is redundant now that recomputeFiltered owns it")
        // The switch-INTO-a-board path still needs its own refresh: the display
        // mode changed, not the filter.
        #expect(body.contains(".onChange(of: displayMode) { _, _ in\n                refreshLibraryProjection()"))
    }

    // MARK: - Miller columns

    @Test("column 0 shows the hits while a search is up, not the browse root")
    func columnsScopeToSearchResults() throws {
        let root = try Self.appSource("Views/Library/ViewModes/Columns/LibraryView+ColumnsSeeding.swift")
        #expect(root.contains("var columnsRootDocuments: [Document]"))
        #expect(root.contains("if activeSearchQuery != nil { return filteredDocuments }"),
                "under a query there is no browse root — there is a result set")

        // The search branch must come BEFORE the root listing, or the roots
        // (non-empty in any real library) win and the fix is dead code.
        let searchBranch = try #require(root.range(of: "if activeSearchQuery != nil"))
        let rootBranch = try #require(root.range(of: "let roots = documentStore.collections"))
        #expect(searchBranch.lowerBound < rootBranch.lowerBound)

        // …and the column browser asks it, rather than keeping a second answer.
        let columns = try Self.appSource("Views/Library/ViewModes/Columns/LibraryView+ColumnsView.swift")
        #expect(columns.contains("guard depth > 0 else { return columnsRootDocuments }"))
        #expect(!columns.contains("documentStore.collections"),
                "one answer to 'what is column 0', in one place")
    }

    @Test("deeper columns still browse — drilling into a hit is browsing again")
    func deeperColumnsAreUnchanged() throws {
        let columns = try Self.appSource("Views/Library/ViewModes/Columns/LibraryView+ColumnsView.swift")
        #expect(columns.contains("return columnsChildren[path[depth - 1]] ?? []"),
                "a child column means that folder's children, search or no search")
    }

    // MARK: - The family that already got it right

    @Test("the dataset modes keep their own hit-id seam")
    func datasetModesStillScope() throws {
        let branches = try Self.appSource("Views/Library/LibraryView+ContentBranches.swift")
        #expect(branches.contains("searchHitIds: activeSearchQuery != nil ? documents.map(\\.id) : nil"),
                "the dataset renderers query the engine themselves, so they narrow by "
                    + "hit id rather than by the pane's row array — the reference for "
                    + "what 'scoped' means here")
    }
}
