import SwiftUI
import UniformTypeIdentifiers

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

/// Grid/List/Table/Map view of documents
struct LibraryView: View {
    let documents: [Document]
    @Binding var selection: Set<String>
    @Binding var detailDocument: Document?
    @Binding var viewMode: LibraryLayout

    @State private var searchText: String = ""
    @State private var sortOrder: [KeyPathComparator<Document>] = [
        .init(\.name, order: .forward)
    ]

    // Column visibility for Table view
    @AppStorage("column_name") private var showName = true
    @AppStorage("column_status") private var showStatus = true
    @AppStorage("column_progress") private var showProgress = true
    @AppStorage("column_output") private var showOutput = true
    @AppStorage("column_fileType") private var showFileType = true
    @AppStorage("column_path") private var showPath = false
    @AppStorage("column_createdDate") private var showCreatedDate = true
    @AppStorage("column_modifiedDate") private var showModifiedDate = false
    @AppStorage("column_size") private var showSize = false

    // Map view positions
    @State private var mapPositions: [String: CGPoint] = [:]

    private var visibleColumns: [ColumnDefinition] {
        ColumnDefinition.allColumns.filter { col in
            switch col.id {
            case "name": return showName
            case "status": return showStatus
            case "progress": return showProgress
            case "output": return showOutput
            case "fileType": return showFileType
            case "path": return showPath
            case "createdDate": return showCreatedDate
            case "modifiedDate": return showModifiedDate
            case "size": return showSize
            default: return false
            }
        }
    }

    private var filteredDocuments: [Document] {
        var docs = documents.filter { $0.docType == .file }

        if !searchText.isEmpty {
            docs = docs.filter {
                $0.name.localizedCaseInsensitiveContains(searchText) ||
                ($0.pageContent?.localizedCaseInsensitiveContains(searchText) ?? false) ||
                $0.status.rawValue.localizedCaseInsensitiveContains(searchText)
            }
        }

        return docs.sorted(using: sortOrder)
    }

    var body: some View {
        VStack(spacing: 0) {
            // View-specific toolbar at top
            LibraryViewToolbar(
                viewMode: $viewMode,
                showColumnConfig: true,
                showName: $showName,
                showStatus: $showStatus,
                showProgress: $showProgress,
                showOutput: $showOutput,
                showFileType: $showFileType,
                showPath: $showPath,
                showCreatedDate: $showCreatedDate,
                showModifiedDate: $showModifiedDate,
                showSize: $showSize,
                onResetColumns: resetColumns
            )

            // Main content
            if filteredDocuments.isEmpty {
                emptyState
            } else {
                switch viewMode {
                case .icons:
                    iconsView
                case .list:
                    listView
                case .table:
                    tableView
                case .map:
                    mapView
                }
            }
        }
        .frame(minWidth: 400)
        .searchable(text: $searchText, prompt: "Search documents")
    }
}

// MARK: - View Components & Helpers

extension LibraryView {
    // MARK: - Column Management

    func resetColumns() {
        showName = true
        showStatus = true
        showProgress = true
        showOutput = true
        showFileType = true
        showPath = false
        showCreatedDate = true
        showModifiedDate = false
        showSize = false
    }

    // MARK: - Old Toolbar (being removed)
    //
    // The toolbar content has been moved to LibraryViewToolbar.swift
    // This section can be deleted - keeping temporarily for reference
    //
    // @ToolbarContentBuilder
    // private var toolbarContent: some ToolbarContent {
    //     ToolbarItem(placement: .automatic) {
    //         if viewMode == .table {
    //             Menu {
    //                 Text("Show Columns")
    //
    //                 Divider()
    //
    //                 Toggle("Name", isOn: $showName)
    //                 ...
    //                     resetColumnVisibility()
    //                 }
    //             } label: {
    //                 Image(systemName: "slider.horizontal.3")
    //             }
    //             .help("Configure Columns")
    //         }
    //     }
    // }

    // MARK: - Icons View (Grid)

    private var iconsView: some View {
        ScrollView {
            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 100, maximum: 140))],
                spacing: 16
            ) {
                ForEach(filteredDocuments) { doc in
                    DocumentThumbnailView(
                        document: doc,
                        isSelected: selection.contains(doc.id)
                    )
                    .draggable(doc.id)
                    .onTapGesture {
                        handleTap(doc)
                    }
                    .onTapGesture(count: 2) {
                        detailDocument = doc
                    }
                }
            }
            .padding()
        }
    }

    // MARK: - List View (Mail-style compact rows)

    private var listView: some View {
        List(selection: $selection) {
            ForEach(filteredDocuments) { doc in
                MailStyleRow(document: doc, isSelected: selection.contains(doc.id))
                    .tag(doc.id)
                    .draggable(doc.id)
                    .listRowInsets(EdgeInsets(top: 8, leading: 12, bottom: 8, trailing: 12))
                    .onTapGesture(count: 2) {
                        detailDocument = doc
                    }
            }
        }
        .listStyle(.plain)
    }

    // MARK: - Table View (Sortable columns)

    private var tableView: some View {
        Table(filteredDocuments, selection: $selection, sortOrder: $sortOrder) {
            TableColumnForEach(visibleColumns) { col in
                TableColumn(col.title) { doc in
                    tableCellView(for: col.id, document: doc)
                }
                .width(min: col.minWidth, ideal: col.idealWidth)
            }
        }
        .tableStyle(.inset)
        .onTapGesture(count: 2) {
            if let firstId = selection.first,
               let doc = filteredDocuments.first(where: { $0.id == firstId }) {
                detailDocument = doc
            }
        }
    }

    // MARK: - Map View (Tinderbox-style canvas)

    private var mapView: some View {
        GeometryReader { geometry in
            ZStack {
                // Grid background
                MapGridBackground()

                // Document cards
                ForEach(filteredDocuments) { doc in
                    MapCard(
                        document: doc,
                        isSelected: selection.contains(doc.id),
                        position: mapPositions[doc.id] ?? randomPosition(for: doc, in: geometry.size)
                    )
                    .onTapGesture {
                        handleTap(doc)
                    }
                    .onTapGesture(count: 2) {
                        detailDocument = doc
                    }
                    .gesture(
                        DragGesture()
                            .onChanged { value in
                                mapPositions[doc.id] = value.location
                            }
                    )
                }
            }
        }
        .background(Color(.textBackgroundColor))
        .onAppear {
            initializeMapPositions()
        }
    }

    private func initializeMapPositions() {
        // Only initialize if not already set
        for (index, doc) in filteredDocuments.enumerated() where mapPositions[doc.id] == nil {
            let row = index / 4
            let col = index % 4
            mapPositions[doc.id] = CGPoint(
                x: 100 + CGFloat(col) * 200,
                y: 100 + CGFloat(row) * 150
            )
        }
    }

    private func randomPosition(for doc: Document, in size: CGSize) -> CGPoint {
        // Generate consistent position based on document id hash
        let hash = doc.id.hashValue
        let xPos = CGFloat(abs(hash % 1000)) / 1000 * (size.width - 200) + 100
        let yPos = CGFloat(abs((hash / 1000) % 1000)) / 1000 * (size.height - 150) + 75
        return CGPoint(x: xPos, y: yPos)
    }

    // MARK: - Table Cell View

    @ViewBuilder
    private func tableCellView(for columnId: String, document doc: Document) -> some View {
        switch columnId {
        case "name":
            HStack(spacing: 8) {
                Image(systemName: doc.fileType?.icon ?? "doc")
                    .foregroundColor(.secondary)
                    .frame(width: 16)
                Text(doc.name)
                    .lineLimit(1)
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
            Text(doc.fileType?.rawValue.capitalized ?? "-")
                .font(.caption)
                .foregroundColor(.secondary)
        case "path":
            Text(doc.path ?? "-")
                .font(.caption)
                .foregroundColor(.secondary)
                .lineLimit(1)
                .help(doc.path ?? "")
        case "createdDate":
            Text(doc.createdAt, style: .date)
                .font(.caption)
                .foregroundColor(.secondary)
        case "modifiedDate":
            Text(doc.updatedAt, style: .date)
                .font(.caption)
                .foregroundColor(.secondary)
        case "size":
            Text("-")
                .font(.caption)
                .foregroundColor(.secondary)
        default:
            Text("-")
                .foregroundColor(.secondary)
        }
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 48))
                .foregroundColor(.secondary)

            Text("No Documents")
                .font(.headline)

            if !searchText.isEmpty {
                Text("No results for \"\(searchText)\"")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            } else {
                Text("Select a collection to view documents")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Helpers

    private func handleTap(_ doc: Document) {
        if NSEvent.modifierFlags.contains(.command) {
            if selection.contains(doc.id) {
                selection.remove(doc.id)
            } else {
                selection.insert(doc.id)
            }
        } else {
            selection = [doc.id]
        }
    }

    private func resetColumnVisibility() {
        showName = true
        showStatus = true
        showProgress = true
        showOutput = true
        showFileType = true
        showPath = false
        showCreatedDate = true
        showModifiedDate = false
        showSize = false
    }
}

// MARK: - Mail-Style Row (like Apple Mail)

struct MailStyleRow: View {
    let document: Document
    let isSelected: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // Status indicator dot
            Circle()
                .fill(statusColor)
                .frame(width: 10, height: 10)
                .padding(.top, 5)

            // Content
            VStack(alignment: .leading, spacing: 4) {
                // Title row
                HStack {
                    Text(document.name)
                        .font(.headline)
                        .lineLimit(1)

                    Spacer()

                    Text(document.createdAt, style: .date)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                // Status + Type row
                HStack(spacing: 8) {
                    StatusBadge(status: document.status)

                    if let fileType = document.fileType {
                        Text(fileType.rawValue.capitalized)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }

                // Summary/Output preview (2-3 lines)
                if let content = document.pageContent, !content.isEmpty {
                    Text(content)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
    }

    private var statusColor: Color {
        switch document.status {
        case .pending: return .gray
        case .processing: return .blue
        case .completed: return .green
        case .failed: return .red
        }
    }
}

// MARK: - Map Card (Tinderbox-style with thumbnail)

struct MapCard: View {
    let document: Document
    let isSelected: Bool
    let position: CGPoint

    var body: some View {
        VStack(spacing: 6) {
            // Thumbnail area
            ZStack {
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color(.windowBackgroundColor))

                // Load thumbnail from backend API with library path header
                LibraryImageView(documentId: document.id, imageType: .thumbnail)
                    .aspectRatio(contentMode: .fill)
                    .clipped()

                // Status indicator overlay
                VStack {
                    Spacer()
                    HStack {
                        Spacer()
                        Circle()
                            .fill(statusColor)
                            .frame(width: 12, height: 12)
                            .overlay(
                                Circle()
                                    .stroke(Color.white, lineWidth: 1.5)
                            )
                            .padding(4)
                    }
                }
            }
            .frame(width: 80, height: 80)
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(isSelected ? Color.accentColor : Color.gray.opacity(0.2), lineWidth: isSelected ? 2 : 1)
            )

            // Name label
            Text(document.name)
                .font(.caption)
                .lineLimit(2)
                .multilineTextAlignment(.center)
                .frame(width: 90)
        }
        .padding(6)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isSelected ? Color.accentColor.opacity(0.15) : Color.clear)
        )
        .shadow(color: .black.opacity(isSelected ? 0.15 : 0.05), radius: isSelected ? 4 : 2, x: 0, y: 1)
        .position(position)
    }

    private var statusColor: Color {
        switch document.status {
        case .pending: return .gray
        case .processing: return .blue
        case .completed: return .green
        case .failed: return .red
        }
    }
}

// MARK: - Map Grid Background

struct MapGridBackground: View {
    let gridSpacing: CGFloat = 40

    var body: some View {
        Canvas { context, size in
            // Draw grid
            let path = Path { path in
                // Vertical lines
                var xPos: CGFloat = 0
                while xPos < size.width {
                    path.move(to: CGPoint(x: xPos, y: 0))
                    path.addLine(to: CGPoint(x: xPos, y: size.height))
                    xPos += gridSpacing
                }

                // Horizontal lines
                var yPos: CGFloat = 0
                while yPos < size.height {
                    path.move(to: CGPoint(x: 0, y: yPos))
                    path.addLine(to: CGPoint(x: size.width, y: yPos))
                    yPos += gridSpacing
                }
            }

            context.stroke(path, with: .color(.gray.opacity(0.15)), lineWidth: 0.5)
        }
    }
}

// MARK: - Progress Cell

struct ProgressCell: View {
    let document: Document

    var body: some View {
        switch document.status {
        case .processing:
            HStack(spacing: 6) {
                ProgressView()
                    .scaleEffect(0.6)
                Text("...")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        case .completed:
            HStack(spacing: 4) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(.green)
                    .font(.caption)
                Text("100%")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        case .failed:
            HStack(spacing: 4) {
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(.red)
                    .font(.caption)
                Text("Failed")
                    .font(.caption)
                    .foregroundColor(.red)
            }
        case .pending:
            Text("Pending")
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }
}

// MARK: - Document Thumbnail View

struct DocumentThumbnailView: View {
    let document: Document
    let isSelected: Bool

    var body: some View {
        VStack(spacing: 6) {
            ZStack {
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color(.windowBackgroundColor))
                    .aspectRatio(1, contentMode: .fit)

                // Load thumbnail from backend API with library path header
                LibraryImageView(documentId: document.id, imageType: .thumbnail)
                    .aspectRatio(contentMode: .fill)
                    .clipped()

                VStack {
                    Spacer()
                    HStack {
                        Spacer()
                        statusIndicator
                            .padding(4)
                    }
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(isSelected ? Color.accentColor : Color.clear, lineWidth: 2)
            )

            Text(document.name)
                .font(.caption)
                .lineLimit(2)
                .multilineTextAlignment(.center)
                .foregroundColor(isSelected ? .accentColor : .primary)
        }
        .frame(width: 100)
        .padding(6)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isSelected ? Color.accentColor.opacity(0.1) : Color.clear)
        )
    }

    @ViewBuilder
    private var statusIndicator: some View {
        switch document.status {
        case .processing:
            ProgressView()
                .scaleEffect(0.5)
                .background(.ultraThinMaterial)
                .cornerRadius(4)
        case .completed:
            Image(systemName: "checkmark.circle.fill")
                .foregroundColor(.green)
                .font(.caption)
        case .failed:
            Image(systemName: "xmark.circle.fill")
                .foregroundColor(.red)
                .font(.caption)
        case .pending:
            EmptyView()
        }
    }
}

// MARK: - Previews

#Preview("Empty") {
    LibraryView(
        documents: [],
        selection: .constant(Set<String>()),
        detailDocument: .constant(nil),
        viewMode: .constant(.icons)
    )
    .frame(width: 600, height: 500)
}
