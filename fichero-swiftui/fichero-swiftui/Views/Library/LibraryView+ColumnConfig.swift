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
        ColumnDefinition(id: "size", title: "Size", defaultVisible: false, minWidth: 60, idealWidth: 80)
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
            default:             return false
            }
        }
    }

    // MARK: - Reset

    func resetColumns() {
        showName = true; showStatus = true; showProgress = true
        showOutput = true; showFileType = true; showPath = false
        showCreatedDate = true; showModifiedDate = false; showSize = false
    }

    // MARK: - Table Cell View

    @ViewBuilder
    // swiftlint:disable:next function_body_length cyclomatic_complexity
    func tableCellView(for columnId: String, document doc: Document) -> some View {
        switch columnId {
        case "name":
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
        case "status":
            StatusBadge(status: doc.status)
        case "progress":
            ProgressCell(document: doc)
        case "output":
            Text(doc.pageContent ?? "-")
                .font(.caption)
                .foregroundColor(.secondary)
                .lineLimit(1)
                .help(doc.pageContent ?? "")
        case "fileType":
            if doc.docType == .folder {
                Text("Folder").font(.caption).foregroundColor(.secondary)
            } else {
                Text(doc.fileType?.rawValue.capitalized ?? "-")
                    .font(.caption).foregroundColor(.secondary)
            }
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
        case "size":
            if let fileSize = doc.metadata["File_Size"]?.value as? Int {
                Text(ByteCountFormatter.string(fromByteCount: Int64(fileSize), countStyle: .file))
                    .font(.caption).foregroundColor(.secondary)
            } else {
                Text("-").font(.caption).foregroundColor(.secondary)
            }
        default:
            Text("-").foregroundColor(.secondary)
        }
    }
}
