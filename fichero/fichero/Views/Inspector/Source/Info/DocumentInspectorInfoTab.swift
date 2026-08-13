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
    @State private var selectedAttribute: InspectorAttribute?
    /// The per-prototype chooser's answers (#4481). Observed, not copied, so a
    /// choice made here is the same choice in every other open inspector.
    let choiceStore = InspectorAttributeChoiceStore.shared
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
                identitySections
                fileAndContentSections
                provenanceSections
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

    // MARK: - Body groups
    //
    // A `ViewBuilder` block takes at most TEN children, and this stack was at
    // exactly ten — the next row anyone added would have overflowed it. SwiftUI
    // reports that overflow as "unable to type-check this expression in
    // reasonable time", which reads as a performance problem rather than the
    // hard limit it is; `LibraryWindow` cost this project real time to that
    // misdiagnosis and was fixed this same way. These three groups exist to
    // leave headroom: add new sections INSIDE one of them, not back into `body`.

    /// Who and what this document is: the chooser that gates everything, then
    /// state, class, sharing, and (for workspaces) its curated items.
    @ViewBuilder
    private var identitySections: some View {
        // Unconditional, and first: the only way any of the sections
        // below can ever appear (#4481).
        attributesChooser

        statusSection
        classSection

        // Prototype-declared attributes (datasets Stage 1). Not gated by the
        // chooser: these rows ARE the assigned prototype's declared set, and
        // the section hides itself when there is nothing to show.
        DocumentAttributesSection(
            documentId: document.id,
            entityService: currentLibrary?.entityService
        )

        sharingSection

        // Workspace curated items + per-item node class (#1570 Phase 1).
        if document.isWorkspace {
            infoSection("Curated Items") {
                WorkspaceCuratedItemsSection(folderId: document.id)
            }
        }
    }

    /// The bytes and what the engine read out of them.
    @ViewBuilder
    private var fileAndContentSections: some View {
        fileSection
        contentSection

        if !geoPoints.isEmpty {
            infoSection("Locations") {
                locationsView
            }
        }
    }

    /// Where this document sits in the knowledge graph and what has been run
    /// over it.
    ///
    /// Citations + Bibliography moved to dedicated inspector tabs (#2004 /
    /// #2005) — List + detachable detail, replacing the stacked
    /// CitationGraphPanel / DocumentBibliographyPanel that were cramped inside
    /// this Info list.
    @ViewBuilder
    private var provenanceSections: some View {
        infoSection("Related Claims") {
            RelatedClaimsPanel(documentId: document.id, library: currentLibrary)
        }

        infoSection("Workflow History") {
            WorkflowProvenancePanel(documentId: document.id)
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
        attributeSection("Status", attributes: [.state]) {
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
        attributeSection("Class", attributes: [.documentClass]) {
            attributeRow(
                name: "Class",
                summary: document.prototypeKey ?? "Default",
                attribute: .documentClass
            ) {
                DocumentPrototypePicker(
                    documentId: document.id,
                    initialKey: document.prototypeKey,
                    entityService: currentLibrary?.entityService
                )
            }
        }
    }

    @ViewBuilder
    private var fileSection: some View {
        attributeSection("File", attributes: [.kind, .fileType, .format, .fileSize]) {
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

            // `Ingest Mode` and `Path` are DELETED, not hidden (#4422). They
            // describe how the app filed the bytes, not the document, and the
            // path exposes the generated storage filename — the same value that
            // is wrong in the island (#4416). There is no configuration in
            // which showing them is right, so they are not offerable at all:
            // `InspectorAttribute` has no case for either.
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
            attributeSection("Content", attributes: [.pageCount, .dimensions]) {
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

    /// A section whose entire content is attribute rows (#4422).
    ///
    /// With the default visible set empty, every row inside gates off — and
    /// `infoSection` renders its heading unconditionally, so the user would be
    /// left with bare "Status" / "File" / "Class" headings above nothing. That
    /// is worse than the strip it replaced, and exactly the half-working
    /// affordance the release gate forbids. The heading follows its rows.
    @ViewBuilder
    func attributeSection<Content: View>(
        _ title: String,
        attributes: [InspectorAttribute],
        @ViewBuilder content: () -> Content
    ) -> some View {
        if attributes.contains(where: visibleAttributes.contains) {
            infoSection(title, content: content)
        }
    }

    /// Wraps the existing `InfoAttributeRow` with tap-to-select behaviour,
    /// replacing the `List(selection:)` driver that no longer applies.
    @ViewBuilder
    private func attributeRow<Detail: View>(
        name: String,
        summary: String,
        attribute: InspectorAttribute,
        @ViewBuilder detail: @escaping () -> Detail
    ) -> some View {
        // ONE gate for every attribute row (#4422). They all funnel through
        // here, so the visible set is enforced in a single place rather than by
        // fifteen `if`s that could drift. Default is nothing;
        // `InspectorAttributeVisibility` is where a per-prototype resolver will
        // later decide differently.
        if visibleAttributes.contains(attribute) {
            InfoAttributeRow(
                name: name,
                summary: summary,
                isSelected: selectedAttribute == attribute,
                detail: detail
            )
            // #4386: full-width row target, not the label's intrinsic width.
            .inspectorListRowTarget()
            .onTapGesture {
                selectedAttribute = (selectedAttribute == attribute) ? nil : attribute
            }
        }
    }

    /// The attributes this document shows, resolved as data (#4422) from the
    /// prototype's chosen set (#4481).
    ///
    /// `chosen:` had no caller until now, so the resolver took its `nil` branch
    /// — `defaultVisible`, which is empty — for every document that ever
    /// existed. The default is unchanged and still nothing; what changed is
    /// that a user can now answer.
    var visibleAttributes: [InspectorAttribute] {
        InspectorAttributeVisibility.visibleAttributes(
            for: document,
            chosen: choiceStore.chosen(forPrototype: document.prototypeKey)
        )
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

// `InspectorAttribute` moved to `InspectorAttributeVisibility.swift` as
// `InspectorAttribute` (#4422): the visible set is DATA now, so the type that
// names the keys has to be reachable from the resolver and its tests.

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
