import SwiftUI

// MARK: - Column Definition

/// Column definition for table view
struct ColumnDefinition: Identifiable, Hashable {
    let id: String
    let title: String
    let defaultVisible: Bool
    let minWidth: CGFloat
    let idealWidth: CGFloat

    static let allColumns: [ColumnDefinition] = [
        ColumnDefinition(id: "name", title: "Name", defaultVisible: true, minWidth: 150, idealWidth: 200),
        ColumnDefinition(id: "status", title: "Status", defaultVisible: true, minWidth: 80, idealWidth: 100),
        ColumnDefinition(id: "progress", title: "Progress", defaultVisible: true, minWidth: 80, idealWidth: 100),
        ColumnDefinition(id: "output", title: "Output", defaultVisible: true, minWidth: 150, idealWidth: 250),
        ColumnDefinition(id: "fileType", title: "Type", defaultVisible: true, minWidth: 60, idealWidth: 80),
        ColumnDefinition(id: "path", title: "Path", defaultVisible: false, minWidth: 100, idealWidth: 150),
        ColumnDefinition(id: "createdDate", title: "Created", defaultVisible: true, minWidth: 80, idealWidth: 100),
        ColumnDefinition(id: "modifiedDate", title: "Modified", defaultVisible: false, minWidth: 80, idealWidth: 100),
        ColumnDefinition(id: "size", title: "Size", defaultVisible: false, minWidth: 60, idealWidth: 80),
        ColumnDefinition(id: "artifacts", title: "Artifacts", defaultVisible: false, minWidth: 100, idealWidth: 120)
    ]
}

// MARK: - Column Configuration Extension

extension LibraryView {

    // MARK: - Visible Columns

    var visibleColumns: [ColumnDefinition] {
        ColumnDefinition.allColumns.filter { col in
            switch col.id {
            case "name":         return showName
            case "status":       return showStatus
            case "progress":     return showProgress
            case "output":       return showOutput
            case "fileType":     return showFileType
            case "path":         return showPath
            case "createdDate":  return showCreatedDate
            case "modifiedDate": return showModifiedDate
            case "size":         return showSize
            case "artifacts":    return showArtifacts
            default:             return false
            }
        }
    }

    // MARK: - Reset

    func resetColumns() {
        showName = true; showStatus = true; showProgress = true
        showOutput = true; showFileType = true; showPath = false
        showCreatedDate = true; showModifiedDate = false
        showSize = false; showArtifacts = false
    }

    // MARK: - Table Cell View

    @ViewBuilder
    func tableCellView(for columnId: String, document doc: Document) -> some View {
        switch columnId {
        case "name":
            nameCell(for: doc)
        case "status":
            StatusBadge(status: doc.status)
        case "progress":
            ProgressCell(document: doc)
        case "output":
            outputCell(for: doc)
        case "fileType":
            fileTypeCell(for: doc)
        case "size":
            sizeCell(for: doc)
        default:
            metadataCellView(for: columnId, document: doc)
        }
    }

    /// The remaining, mostly single-line, metadata columns — split out from
    /// `tableCellView` purely to keep that switch's branch count down.
    @ViewBuilder
    private func metadataCellView(for columnId: String, document doc: Document) -> some View {
        switch columnId {
        case "path":
            Text(doc.path ?? "-")
                .font(.caption).foregroundColor(.secondary)
                .lineLimit(1).help(doc.path ?? "")
        case "createdDate":
            Text(doc.createdAt, style: .date)
                .font(.caption).foregroundColor(.secondary)
        case "modifiedDate":
            Text(doc.updatedAt, style: .date)
                .font(.caption).foregroundColor(.secondary)
        case "artifacts":
            ArtifactEntitiesView(documentId: doc.id, style: .singleLine)
        case "people", "places", "organizations", "events", "dates", "keywords":
            ArtifactEntityCell(documentId: doc.id, entityType: columnId)
        default:
            Text("-").foregroundColor(.secondary)
        }
    }

    @ViewBuilder
    private func nameCell(for doc: Document) -> some View {
        HStack(spacing: 8) {
            if doc.docType == .folder {
                Image(systemName: "folder.fill")
                    .foregroundColor(.accentColor)
                    .frame(width: 16)
            } else {
                Image(systemName: doc.fileType?.icon ?? "doc")
                    .foregroundColor(.secondary)
                    .frame(width: 16)
            }
            EditableDocumentName(
                document: doc,
                isRenaming: renamingDocumentId == doc.id,
                editingName: $editingName,
                onCommit: commitRename,
                onCancel: cancelRename
            )
        }
    }

    @ViewBuilder
    private func outputCell(for doc: Document) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(doc.pageContent ?? "-")
                .font(.caption)
                .foregroundColor(.secondary)
                .lineLimit(2)
                .help(doc.pageContent ?? "")

            ArtifactEntitiesView(
                documentId: doc.id,
                style: .multiLine,
                visibleTypes: listVisibleEntityTypes
            )
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private func fileTypeCell(for doc: Document) -> some View {
        if doc.docType == .folder {
            Text("Folder").font(.caption).foregroundColor(.secondary)
        } else {
            Text(doc.fileType?.rawValue.capitalized ?? "-")
                .font(.caption).foregroundColor(.secondary)
        }
    }

    @ViewBuilder
    private func sizeCell(for doc: Document) -> some View {
        if let fileSize = fileSizeInBytes(for: doc) {
            Text(ByteCountFormatter.string(fromByteCount: fileSize, countStyle: .file))
                .font(.caption)
                .foregroundColor(.secondary)
        } else {
            Text("-").font(.caption).foregroundColor(.secondary)
        }
    }

    // (The actual Artifacts TableColumn is wired inline in
    // LibraryView+DisplayModes.swift's tableView; trying to factor it
    // into an `@ViewBuilder var artifactsColumn: some View` doesn't
    // type-check because TableColumn conforms to TableColumnContent,
    // not View. SwiftUI's TableColumnBuilder is the right macro for
    // composing TableColumns, but inlining keeps the column list in
    // one place — preferred.) #519

    private func fileSizeInBytes(for doc: Document) -> Int64? {
        let metadataKeys = ["File_Size", "file_size", "size"]

        for key in metadataKeys {
            guard let value = doc.metadata[key]?.value else { continue }

            switch value {
            case let intValue as Int:
                return Int64(intValue)
            case let intValue as Int64:
                return intValue
            case let doubleValue as Double:
                return Int64(doubleValue)
            case let numberValue as NSNumber:
                return numberValue.int64Value
            case let stringValue as String:
                if let parsed = Int64(stringValue) {
                    return parsed
                }
            default:
                continue
            }
        }

        return nil
    }
}
