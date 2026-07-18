import FicheroAPIClient
import SwiftUI

/// Info tab — two-step progressive disclosure: attribute name + summary, select to reveal detail / edit.
struct DocumentInspectorInfoTab: View {
    let document: Document

    @Environment(LibraryManager.self) var libraryManager
    @Environment(WindowState.self) var windowState
    @Environment(DocumentStore.self) private var documentStore: DocumentStore
    @State var isUpdatingExclude = false
    @State var excludeFromProcessingOverride: Bool?
    @State var libraryAuthzSnapshot: Components.Schemas.LibraryAuthzSnapshot?
    @State var libraryAuthzError: String?
    @State var isLoadingLibraryAuthz = false
    @State private var selectedAttribute: InfoAttribute?
    /// Geo points the engine derived for this document (#3055) — shown only when present.
    @State private var geoPoints: [Components.Schemas.DocGeoPoint] = []

    var isExcludedFromProcessing: Bool {
        excludeFromProcessingOverride ?? document.excludeFromProcessing
    }

    var body: some View {
        // NOTE: this view is hosted inside a parent `ScrollView` (see
        // `DocumentInspector.infoTab(for:)`). A SwiftUI `List` collapses to
        // zero height inside a `ScrollView`, which is why only the header used
        // to render and the whole attribute body was invisible (#2107). We
        // keep the exact same `InfoAttributeRow` progressive-disclosure UI but
        // lay the sections out with plain stacks so they survive the enclosing
        // scroll view. Selection is driven by a tap on each row rather than
        // `List(selection:)`.
        VStack(alignment: .center, spacing: 0) {
            headerSection
                .padding(.bottom, 8)

            VStack(alignment: .leading, spacing: 16) {
                statusSection
                classSection
                sharingSection

                // Workspace curated items + per-item node class (#1570 Phase 1).
                if document.isWorkspace {
                    infoSection("Curated Items") {
                        WorkspaceCuratedItemsSection(folderId: document.id)
                    }
                }

                fileSection
                contentSection

                if !geoPoints.isEmpty {
                    infoSection("Locations") {
                        locationsView
                    }
                }

                infoSection("Related Claims") {
                    RelatedClaimsPanel(documentId: document.id)
                }

                // Citations + Bibliography moved to dedicated inspector tabs
                // (#2004 / #2005) — List + detachable detail, replacing the
                // stacked CitationGraphPanel / DocumentBibliographyPanel that
                // were cramped inside this Info list.

                infoSection("Workflow History") {
                    WorkflowProvenancePanel(documentId: document.id)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .onChange(of: document.id) { _, _ in
            excludeFromProcessingOverride = nil
            selectedAttribute = nil
        }
        .task(id: authzLoadKey) {
            await loadLibraryAuthzSnapshot()
        }
        .task(id: document.id) {
            await loadGeoPoints()
        }
    }

    // MARK: - Locations (#3055)

    /// Fetch this document's geo points through the generated client wrapper.
    /// Failures are non-fatal — the section simply stays hidden (empty points).
    private func loadGeoPoints() async {
        geoPoints = []
        guard let service = libraryManager.getLibrary(id: windowState.libraryId)?
            .documentService else { return }
        geoPoints = (try? await service.documentGeoPoints(document.id)) ?? []
    }

    private var locationsView: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(geoPoints.enumerated()), id: \.offset) { _, point in
                HStack(alignment: .top, spacing: 6) {
                    Image(systemName: "mappin.and.ellipse")
                        .foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 1) {
                        if let place = point.placeName, !place.isEmpty {
                            Text(place)
                                .font(.callout)
                            Text(String(format: "%.4f, %.4f", point.lat, point.lon))
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        } else {
                            Text(String(format: "%.4f, %.4f", point.lat, point.lon))
                                .font(.callout)
                        }
                    }
                    Spacer(minLength: 0)
                }
                .textSelection(.enabled)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - Sections

    @ViewBuilder
    private var statusSection: some View {
        infoSection("Status") {
            attributeRow(
                name: "State",
                summary: document.status.rawValue.capitalized,
                attribute: .state
            ) {
                HStack(spacing: 6) {
                    StatusBadge(status: document.status)
                    if document.status == .processing {
                        ProgressView().scaleEffect(0.7)
                    }
                }
            }

            attributeRow(
                name: "Ingest Mode",
                summary: document.ingestMode.rawValue.capitalized,
                attribute: .ingestMode
            ) {
                Text(document.ingestMode.rawValue.capitalized)
                    .foregroundStyle(.secondary)
            }

            attributeRow(
                name: "Created",
                summary: document.createdAt.formatted(date: .abbreviated, time: .omitted),
                attribute: .created
            ) {
                Text(document.createdAt, format: .dateTime)
                    .foregroundStyle(.secondary)
            }

            attributeRow(
                name: "Modified",
                summary: document.updatedAt.formatted(.relative(presentation: .named)),
                attribute: .modified
            ) {
                Text(document.updatedAt, format: .dateTime)
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private var classSection: some View {
        infoSection("Class") {
            attributeRow(
                name: "Class",
                summary: document.prototypeKey ?? "Default",
                attribute: .documentClass
            ) {
                DocumentPrototypePicker(
                    documentId: document.id,
                    initialKey: document.prototypeKey
                )
            }
        }
    }

    @ViewBuilder
    private var fileSection: some View {
        infoSection("File") {
            attributeRow(
                name: "Kind",
                summary: document.docType.rawValue.capitalized,
                attribute: .kind
            ) {
                Text(document.docType.rawValue.capitalized)
                    .foregroundStyle(.secondary)
            }

            if let fileType = document.fileType {
                attributeRow(
                    name: "Type",
                    summary: fileType.rawValue.capitalized,
                    attribute: .fileType
                ) {
                    Text(fileType.rawValue.capitalized)
                        .foregroundStyle(.secondary)
                }
            }

            if let format = stringMetadata("mime_type") ?? stringMetadata("format") {
                attributeRow(name: "Format", summary: format, attribute: .format) {
                    Text(format).foregroundStyle(.secondary)
                }
            }

            if let fileSize = intMetadata("file_size") {
                let formatted = ByteCountFormatter.string(fromByteCount: Int64(fileSize), countStyle: .file)
                attributeRow(name: "Size", summary: formatted, attribute: .fileSize) {
                    Text(formatted).foregroundStyle(.secondary)
                }
            }

            if let path = document.path {
                attributeRow(name: "Path", summary: path, attribute: .path) {
                    Text(path)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
            }
        }
    }

    /// Format-specific structural facts — page count for PDFs, pixel
    /// dimensions for images. Only renders when at least one value exists.
    @ViewBuilder
    private var contentSection: some View {
        let pageCount = intMetadata("page_count")
        let width = intMetadata("width")
        let height = intMetadata("height")

        if pageCount != nil || (width != nil && height != nil) {
            infoSection("Content") {
                if let pageCount {
                    let summary = "\(pageCount) page\(pageCount == 1 ? "" : "s")"
                    attributeRow(name: "Pages", summary: summary, attribute: .pageCount) {
                        Text(summary).foregroundStyle(.secondary)
                    }
                }

                if let width, let height {
                    let summary = "\(width) × \(height) px"
                    attributeRow(name: "Dimensions", summary: summary, attribute: .dimensions) {
                        Text(summary).foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    // MARK: - Section + row builders

    /// A titled section: small caps header + the same row stack the inspector
    /// already uses. Replaces `List`'s `Section` so the body renders inside the
    /// enclosing `ScrollView`.
    @ViewBuilder
    func infoSection<Content: View>(
        _ title: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
            content()
        }
    }

    /// Wraps the existing `InfoAttributeRow` with tap-to-select behaviour,
    /// replacing the `List(selection:)` driver that no longer applies.
    @ViewBuilder
    private func attributeRow<Detail: View>(
        name: String,
        summary: String,
        attribute: InfoAttribute,
        @ViewBuilder detail: @escaping () -> Detail
    ) -> some View {
        InfoAttributeRow(
            name: name,
            summary: summary,
            isSelected: selectedAttribute == attribute,
            detail: detail
        )
        .contentShape(Rectangle())
        .onTapGesture {
            selectedAttribute = (selectedAttribute == attribute) ? nil : attribute
        }
    }

    // MARK: - Metadata helpers

    /// Reads an integer from `source_metadata`, tolerating values the backend
    /// may serialise as Double or numeric String.
    private func intMetadata(_ key: String) -> Int? {
        guard let value = document.metadata[key]?.value else { return nil }
        if let int = value as? Int { return int }
        if let double = value as? Double { return Int(double) }
        if let string = value as? String { return Int(string) }
        return nil
    }

    /// Reads a non-empty string from `source_metadata`.
    private func stringMetadata(_ key: String) -> String? {
        guard let string = document.metadata[key]?.value as? String,
              !string.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else { return nil }
        return string
    }

    @MainActor
    func toggleExcludeFromProcessing() async {
        guard let library = currentLibrary else { return }

        isUpdatingExclude = true
        defer { isUpdatingExclude = false }

        do {
            let refreshed = try await library.documentService.batchExclude(
                documentIds: [document.id],
                excluded: !isExcludedFromProcessing
            )
            for updated in refreshed {
                documentStore.refreshLocalContent(updated)
                if updated.id == document.id {
                    excludeFromProcessingOverride = updated.excludeFromProcessing
                }
            }
        } catch {
            documentStore.error = error
        }
    }

    var currentLibrary: LibraryManager.LibraryReference? {
        if let library = libraryManager.getLibrary(id: windowState.libraryId) {
            return library
        }
        return libraryManager.globalLibrary
    }
}

// MARK: - Supporting types

private enum InfoAttribute: Hashable {
    case state, ingestMode, created, modified
    case kind, fileType, format, fileSize, path
    case pageCount, dimensions
    case documentClass
}

private struct InfoAttributeRow<Detail: View>: View {
    let name: String
    let summary: String
    let isSelected: Bool
    private let detail: () -> Detail

    init(name: String, summary: String, isSelected: Bool, @ViewBuilder detail: @escaping () -> Detail) {
        self.name = name
        self.summary = summary
        self.isSelected = isSelected
        self.detail = detail
    }

    var body: some View {
        VStack(alignment: .leading, spacing: isSelected ? 6 : 0) {
            HStack(alignment: .firstTextBaseline) {
                Text(name)
                    .fontWeight(.medium)
                Spacer()
                if !isSelected {
                    Text(summary)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            if isSelected {
                detail()
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 6))
            }
        }
        .padding(.vertical, 2)
        .animation(.easeInOut(duration: 0.15), value: isSelected)
    }
}
