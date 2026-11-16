import Foundation
import SwiftUI

// MARK: - Table rows drag as ROWS (#6538)

extension LibraryItemDrag {
    /// What a library-table row drags out, or nil for a row that does not drag.
    ///
    /// The drag lives on the ROW (`TableRowContent.itemProvider`), never on a cell. A
    /// `.draggable` inside an `NSTableView` cell takes the mouse-down before the table sees
    /// it, so the Name column — the one cell that carried the drag — would not select its
    /// row on a click, ⇧-click or ⌘-click while every other column did (#6538). On the row,
    /// the table's own drag handling starts a drag only once the pointer moves, and a drag
    /// starts from any column.
    ///
    /// Entities, claims and proposed documents never dragged from the table; they still don't.
    static func forOutlineRow(_ node: LibraryOutlineNode, libraryId: UUID?) -> LibraryItemDrag? {
        switch node.kind {
        case .document:
            return forDocument(node.document, libraryId: libraryId)
        case .pageItem(let page):
            return forDocument(page, libraryId: libraryId)
        case .childGroup(let type):
            return LibraryItemDrag(
                kind: .group,
                id: node.id,
                documentId: node.document.id,
                text: type.groupLabel(count: node.count)
            )
        case .artifactItem(let artifact):
            return LibraryItemDrag(
                kind: .artifact,
                id: artifact.id,
                documentId: artifact.documentId,
                text: artifact.content?.isEmpty == false
                    ? artifact.content ?? artifact.artifactTypeDisplayName
                    : artifact.artifactTypeDisplayName
            )
        case .entityItem, .claimItem, .proposedDocument:
            return nil
        }
    }

    /// This payload as a table row's item provider, carrying every representation it declares
    /// (in-app JSON, file copy, text).
    func itemProvider() -> NSItemProvider {
        let provider = NSItemProvider()
        provider.register(self)
        return provider
    }
}

extension LibraryView {
    /// The item provider for one table row's drag (#6538): `LibraryItemDrag.forOutlineRow`,
    /// carrying every representation the payload declares (in-app JSON, file copy, text).
    func outlineRowDragProvider(for node: LibraryOutlineNode) -> NSItemProvider? {
        LibraryItemDrag.forOutlineRow(node, libraryId: windowState.libraryId)?.itemProvider()
    }
}
