@testable import Fichero
import Foundation
import Testing

/// #5276 / #5279: the library Table's rows drew tall, then shrank, as content arrived; Created
/// text was drawn over the Output chips; a Completed pill sat on every row. These pin the layout
/// rules. Whether the rows LOOK right needs the app on screen; these stop the wiring regressing.
struct LibraryTableColumnsLayoutTests {
    private func source(_ path: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(path), encoding: .utf8)
    }

    @Test("Status is the first column, untitled, and a finished row shows no badge")
    func statusIsALeadingIcon() throws {
        let columns = try source("Views/Library/ViewModes/Table/LibraryView+TableColumns.swift")
        let status = try #require(columns.range(of: "TableColumn(\"\", value: \\.document.status.rawValue)"))
        let name = try #require(columns.range(of: "TableColumn(\"Name\""))
        #expect(status.lowerBound < name.lowerBound)
        let config = try source("Views/Library/ViewModes/LibraryView+ColumnConfig.swift")
        #expect(config.contains("LibraryTableStatusIcon(status: doc.status)"))
        #expect(!config.contains("StatusBadge(status: doc.status)"))
    }

    @Test("Content is text only, in the Metadata menu's reserved lines, so a load cannot resize the row")
    func contentReservesItsLines() throws {
        let config = try source("Views/Library/ViewModes/LibraryView+ColumnConfig.swift")
        let body = try #require(config.range(of: "private func outputCell(for doc: Document)"))
        let cell = String(config[body.lowerBound...].prefix(900))
        #expect(cell.contains("lineLimit(LibraryRowContentLines.resolve(rowContentLinesRaw).rawValue, reservesSpace: true)"))
        #expect(!cell.contains("ArtifactEntitiesView"), "entities have their own columns")
        #expect(try source("Views/Library/ViewModes/Table/LibraryView+TableColumns.swift")
            .contains("TableColumn(\"Content\")"))
    }

    @Test("every table cell is top-aligned")
    func cellsAreTopAligned() throws {
        let columns = try source("Views/Library/ViewModes/Table/LibraryView+TableColumns.swift")
        let aligned = columns.components(separatedBy: ".frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)").count - 1
        #expect(aligned == 2, "the name cell and the shared column cell")
    }
}
