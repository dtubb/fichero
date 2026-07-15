import FicheroAPIClient
import SwiftUI

// swiftlint:disable file_length

/// V2 inspector Content tab. Tinderbox-style layout:
///   - DisplayAttributesStrip at top (compact key-value).
///   - One ArtifactPanel per artifact below.
///   - The document's `page_content` (if any) renders as one final panel
///     so existing data is visible without a migration.
///
/// Phase 1: read-only. No save logic, no caching, no signature dance —
/// we re-fetch artifacts when the document selection or workflow events
/// change, full stop. See docs/contributor/architecture/swiftui/inspector_redesign.md.
struct DocumentInspectorContentV2: View {
    /// Which panels to render. The Content tab shows only the document's
    /// page content (the source text), Artifacts shows only the generated
    /// artifacts. `.all` keeps the original combined behaviour for any
    /// caller that still wants both.
    enum Mode {
        case all
        case pageContentOnly
        case artifactsOnly
    }

    let document: Document
    var mode: Mode = .all

    @Environment(ArtifactStore.self) private var artifactStore
    @Environment(DocumentServiceGenerated.self) private var documentService
    @Environment(DocumentStore.self) private var documentStore: DocumentStore
    @Environment(WorkflowExecutionObserver.self) private var executionObserver

    @State private var actionError: String?

    private var liveDocument: Document {
        Self.refreshedDocument(document, in: documentStore.currentDocuments)
    }

    private var artifacts: [Artifact] {
        artifactStore.items
    }

    private var isLoading: Bool {
        artifactStore.isLoading
    }

    private var loadError: String? {
        artifactStore.loadError
    }

    var body: some View {
        // Two layout modes:
        //
        // .pageContentOnly — exactly one panel (Page Content). Use a
        // direct flex layout so the editor expands to fill the inspector
        // pane height. No ScrollView (the editor manages its own scroll).
        //
        // .all / .artifactsOnly — many panels (transcription, catalogue,
        // people, places, etc.). Each panel reserves at least 100pt; with
        // 13+ panels the stack overflows the inspector — wrap in
        // ScrollView so the user can scroll through them. Without the
        // wrapper the overflow pushed sibling chrome (the inspector's
        // own tab bar) offscreen.
        Group {
            if mode == .pageContentOnly {
                panelStack(spacing: 8)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            } else {
                ScrollView {
                    panelStack(spacing: 8)
                        .frame(maxWidth: .infinity, alignment: .top)
                }
            }
        }
        .task(id: document.id) {
            await syncArtifactScope(force: true)
        }
        .onChange(of: executionObserver.fileCompletedCount) { _, _ in
            Task { await refreshVisibleDocument() }
            Task { await syncArtifactScope(force: true) }
        }
        .onChange(of: executionObserver.workflowCompletedCount) { _, _ in
            Task { await refreshVisibleDocument() }
            Task { await syncArtifactScope(force: true) }
        }
    }

    // MARK: - Subviews

    @ViewBuilder
    private func panelStack(spacing: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: spacing) {
            if let loadError {
                errorBox(loadError)
            }
            if let actionError {
                errorBox(actionError)
            }

            // Page Content panel — only when the mode wants it. The Content
            // tab shows just this so the user can edit / type notes against
            // the source text without artifact noise; the Artifacts tab
            // suppresses it so the panel list is purely workflow output.
            if mode != .artifactsOnly {
                ArtifactPanel(
                    kind: .pageContent(text: liveDocument.pageContent ?? ""),
                    // In pageContentOnly there's no outer ScrollView, so the
                    // editor fills the pane top-down instead of centring (#1286).
                    fillsHeight: mode == .pageContentOnly,
                    // Hand the store the page editor's flush so image prev/next
                    // and inspector tab switches persist the in-flight edit
                    // before the focused document changes (#2476).
                    documentStore: documentStore,
                    onSave: { newContent in
                        await savePageContent(newContent)
                    }
                )
                // In pageContentOnly mode there's no outer ScrollView, so
                // the panel can safely claim all remaining inspector height.
                // Top alignment keeps the content pinned just below the
                // attribute strip rather than floating centred (#1062, #1286).
                .frame(
                    maxWidth: .infinity,
                    maxHeight: mode == .pageContentOnly ? .infinity : nil,
                    alignment: .top
                )
            }

            // Generated artifacts — only when the mode wants them. Each one
            // is editable (RTF round-trips, auto-save) and deletable.
            if mode != .pageContentOnly {
                ForEach(sortedArtifacts) { artifact in
                    artifactPanel(for: artifact)
                }

                // Hint shown when no generated artifacts exist.
                if !isLoading && sortedArtifacts.isEmpty && loadError == nil {
                    emptyState
                }
            }

            if isLoading && artifacts.isEmpty {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Loading artifacts…").font(.caption).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "sparkles")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No content yet")
                .font(.callout)
            Text("Run a workflow to generate transcriptions, catalogues, or summaries.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 32)
    }

    @ViewBuilder
    private func errorBox(_ message: String) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Button("Retry") {
                Task { await syncArtifactScope(force: true) }
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.orange.opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .padding(.horizontal, 8)
    }

    // MARK: - Data

    private var sortedArtifacts: [Artifact] {
        // Group raw + cleaned pairs together (people / people_clean,
        // keywords / keywords_clean) by base type, with the *_clean entry
        // first within each pair (the cleaned canonical view is the
        // authoritative one; raw is the per-page substrate that
        // generated it). Within the same exact type, newer first —
        // useful when multiple model runs of the same type exist.
        artifacts.sorted {
            let aBase = baseType(of: $0.artifactType)
            let bBase = baseType(of: $1.artifactType)
            if aBase != bBase { return aBase < bBase }
            let aClean = $0.artifactType.hasSuffix("_clean")
            let bClean = $1.artifactType.hasSuffix("_clean")
            if aClean != bClean { return aClean }
            return $0.createdAt > $1.createdAt
        }
    }

    private func baseType(of artifactType: String) -> String {
        artifactType.hasSuffix("_clean")
            ? String(artifactType.dropLast("_clean".count))
            : artifactType
    }

    private var panelCount: Int {
        var count = sortedArtifacts.count
        if let pageContent = liveDocument.pageContent, !pageContent.isEmpty { count += 1 }
        return count
    }

    private func syncArtifactScope(force: Bool) async {
        // The page-content-only tab never renders artifacts (the artifact list
        // is gated by `mode != .pageContentOnly`), so fetching them on every
        // document selection is wasted work — and it flashed a stray "Loading
        // artifacts…" spinner over the page editor (#3186).
        guard mode != .pageContentOnly else { return }
        await artifactStore.setScope(
            documentId: document.id,
            includeDescendants: Self.shouldIncludeDescendantArtifacts(
                for: document,
                mode: mode
            ),
            force: force
        )
    }

    private func deleteArtifact(_ artifact: Artifact) async {
        let failedDeletes = await artifactStore.delete([artifact])
        if failedDeletes == 0 {
            actionError = nil
        } else {
            actionError = "Couldn't delete artifact."
        }
    }

    @ViewBuilder
    private func artifactPanel(for artifact: Artifact) -> some View {
        ArtifactPanel(
            kind: .artifact(artifact),
            // #1374: artifact content should be visible by default
            // in the Artifacts tab; collapsed headers were hiding
            // the bodies and making the panel look empty.
            defaultExpanded: true,
            onDelete: { Task { await deleteArtifact(artifact) } },
            onSave: { newContent in
                await saveArtifact(artifact, content: newContent)
            }
        )
        .contentShape(Rectangle())
        .onTapGesture {
            inspectArtifact(artifact)
        }
    }

    private func inspectArtifact(_ artifact: Artifact) {
        FocusedArtifact.shared.select(
            artifact.id,
            documentId: document.id,
            documentName: document.name,
            in: artifacts
        )
    }

    private func clearPageContent() async {
        // page_content is a Document field, not an artifact — clearing it
        // means a normal updateDocument call with pageContent: "".
        if let error = await persistPageContent(
            document: document,
            content: "",
            documentService: documentService,
            documentStore: documentStore
        ) {
            actionError = "Couldn't clear page content: \(error)"
        } else {
            actionError = nil
        }
    }

    private func saveArtifact(_ artifact: Artifact, content: String) async {
        do {
            let updated = try await artifactStore.update(
                id: artifact.id,
                documentId: artifact.documentId,
                content: content
            )
            FocusedArtifact.shared.select(
                updated.id,
                documentId: document.id,
                documentName: document.name,
                in: artifactStore.items
            )
            actionError = nil
        } catch {
            actionError = "Couldn't save: \(error.localizedDescription)"
        }
    }

    private func savePageContent(_ content: String) async {
        actionError = await persistPageContent(
            document: liveDocument,
            content: content,
            documentService: documentService,
            documentStore: documentStore
        ).map { "Couldn't save: \($0)" }
    }

    private func refreshVisibleDocument() async {
        guard mode == .pageContentOnly else { return }
        await documentStore.refreshDocumentsByIds([document.id])
    }

    static func refreshedDocument(_ document: Document, in currentDocuments: [Document]) -> Document {
        currentDocuments.first(where: { $0.id == document.id }) ?? document
    }

    static func shouldIncludeDescendantArtifacts(for document: Document, mode: Mode) -> Bool {
        mode == .artifactsOnly
            && document.docType == .file
            && document.fileType == .pdf
    }
}

@MainActor
func persistPageContent(
    document: Document,
    content: String,
    documentService: DocumentServiceGenerated,
    documentStore: DocumentStore
) async -> String? {
    // Run the PUT inside a STORE-OWNED task so a view re-render / blur that
    // cancels the editor's debounce/flush task can't abort the save mid-flight
    // (NSURLError -999, #2466). `refreshLocalContent` happens inside the store
    // task once the save lands.
    let id = document.id
    return await documentStore.savePageContent(documentId: id) {
        try await documentService.updateDocument(id, pageContent: content)
    }
}

// MARK: - Source outline (#3440)

/// Document-scoped observable store for the generated source outline (#3440).
///
/// Wraps `GET /api/documents/{id}/outline` through the injected
/// `DocumentServiceGenerated` — no hand-rolled URL, no view-owned fetch. Holds
/// the flat, depth-ordered rows; the view folds them into a hierarchy.
///
/// Source **anchors** for reveal-in-Preview are engine work (#3441): today the
/// rows carry only id / depth / kind / label / count, so this is a native
/// hierarchy/drill-down mode, and rows do not pretend to be source anchors.
@MainActor
@Observable
final class DocumentOutlineStore {
    private(set) var rows: [Components.Schemas.DocumentOutlineRow] = []
    private(set) var isLoading = false
    private(set) var loadError: String?
    private(set) var loadedDocumentId: String?

    func load(
        documentId: String,
        using service: DocumentServiceGenerated,
        force: Bool = false
    ) async {
        if !force, loadedDocumentId == documentId, loadError == nil { return }
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            rows = try await service.documentOutline(documentId)
            loadedDocumentId = documentId
        } catch is CancellationError {
            // Superseded by a newer selection — keep current state.
        } catch {
            rows = []
            loadError = error.localizedDescription
            loadedDocumentId = nil
        }
    }
}

/// One node in the source-outline tree — the flat depth-list folded into a
/// hierarchy for the native `OutlineGroup` (#3440).
struct SourceOutlineNode: Identifiable, Hashable {
    let row: Components.Schemas.DocumentOutlineRow
    var children: [SourceOutlineNode]?

    var id: String { row.id }

    /// Fold a flat, depth-ordered row list into a tree. Rows arrive depth-first
    /// (a parent immediately followed by its deeper descendants), with `depth`
    /// giving the level, so a recursive descent reconstructs the hierarchy.
    /// `children` is `nil` (not `[]`) for leaves, so the native outline shows a
    /// disclosure triangle only where there is something to expand. Pure + testable.
    static func tree(
        from rows: [Components.Schemas.DocumentOutlineRow]
    ) -> [SourceOutlineNode] {
        guard let minDepth = rows.map(\.depth).min() else { return [] }
        var index = 0

        func parse(atDepth depth: Int) -> [SourceOutlineNode] {
            var nodes: [SourceOutlineNode] = []
            while index < rows.count, rows[index].depth == depth {
                let row = rows[index]
                index += 1
                let children: [SourceOutlineNode]?
                if index < rows.count, rows[index].depth > depth {
                    children = parse(atDepth: depth + 1)
                } else {
                    children = nil
                }
                nodes.append(SourceOutlineNode(row: row, children: children))
            }
            return nodes
        }

        return parse(atDepth: minDepth)
    }

    /// The source anchor for an outline row, or nil for a group/structural row
    /// that isn't a source anchor (#3440 + #3441). Page/structural rows the
    /// engine marks reveal-capable (`sourceCapability == "reveal"`) with a
    /// document id route through the shared source-navigation contract; group
    /// rows (no anchor) deliberately return nil rather than fake one. Pure +
    /// testable.
    static func navigationRequest(
        for row: Components.Schemas.DocumentOutlineRow
    ) -> ClaimSourceNavigationRequest? {
        guard row.sourceCapability == "reveal",
              let documentId = row.sourceDocumentId,
              !documentId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else { return nil }
        return ClaimSourceNavigationRequest(documentId: documentId, pageLabel: row.pageLabel)
    }
}

/// Native document outline (#3440): the generated source hierarchy rendered as a
/// SwiftUI `List` with disclosure, so keyboard navigation, VoiceOver, and
/// full-row selection come from the platform. A deliberate hierarchy MODE inside
/// the Source section (see ``SourceSectionView``), not a permanent tab.
///
/// Source reveal for page/structural rows lands with #3441 (stable anchors);
/// until then this is drill-down/overview only.
struct SourceOutlineView: View {
    let documentId: String

    @Environment(DocumentServiceGenerated.self) private var documentService
    /// Per-window typed source-navigation bus (#3437) — reveal-capable outline
    /// rows route their source anchor through it, same contract as claims (#3440).
    @Environment(ClaimSourceNavigationState.self) private var claimSourceNavigationState: ClaimSourceNavigationState?
    @State private var store = DocumentOutlineStore()
    @State private var selection: String?

    var body: some View {
        Group {
            if store.isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let loadError = store.loadError {
                ContentUnavailableView {
                    Label("Couldn’t load outline", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(loadError)
                } actions: {
                    Button("Retry") {
                        Task { await store.load(documentId: documentId, using: documentService, force: true) }
                    }
                }
            } else if store.rows.isEmpty {
                ContentUnavailableView(
                    "No outline",
                    systemImage: "list.bullet.indent",
                    description: Text("This document has no structural outline yet.")
                )
            } else {
                List(
                    SourceOutlineNode.tree(from: store.rows),
                    children: \.children,
                    selection: $selection
                ) { node in
                    outlineRow(node.row)
                }
                .listStyle(.inset)
            }
        }
        .task(id: documentId) {
            await store.load(documentId: documentId, using: documentService)
        }
        // Selecting a reveal-capable page/structural row drives the reader to its
        // source via the shared contract (#3440/#3441); group rows no-op.
        .onChange(of: selection) { _, newSelection in
            guard let newSelection,
                  let row = store.rows.first(where: { $0.id == newSelection }),
                  let request = SourceOutlineNode.navigationRequest(for: row) else { return }
            claimSourceNavigationState?.request(request)
        }
    }

    private func outlineRow(_ row: Components.Schemas.DocumentOutlineRow) -> some View {
        HStack(spacing: 6) {
            Image(systemName: Self.icon(forKind: row.kind))
                .foregroundStyle(.secondary)
                .font(.caption)
            Text(row.label)
                .lineLimit(1)
            Spacer(minLength: 4)
            // `row.count` is a generated Int field (child/item count) on the
            // OpenAPI DocumentOutlineRow, not a collection — there is no
            // `isEmpty`, so the empty_count rule is a false positive here.
            // swiftlint:disable:next empty_count
            if row.count > 0 {
                Text("\(row.count)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .inspectorListRowTarget()
        .help(row.label)
    }

    /// SF Symbol for an outline row kind. Falls back to a generic marker so a new
    /// backend kind still renders (rather than a blank row).
    static func icon(forKind kind: String) -> String {
        switch kind.lowercased() {
        case "document", "file": return "doc.text"
        case "folder", "collection": return "folder"
        case "page": return "doc"
        case "section", "chunk": return "text.alignleft"
        case "entity", "person", "place", "organization": return "person.crop.circle"
        case "claim": return "quote.bubble"
        default: return "circle.fill"
        }
    }
}

/// The Source section body: ONE segmented toggle over the page **Content**, the
/// document **Info** (metadata), and the native document **Outline** (#3440/#3876).
/// This is the single Source picker — the former separate Content/Info facet picker
/// above it is gone; Info is the middle segment here.
struct SourceSectionView: View {
    let document: Document

    @SceneStorage("inspector.source.mode") private var mode: SourceSectionMode = .content

    var body: some View {
        VStack(spacing: 0) {
            Picker("Source view", selection: $mode) {
                Text("Content").tag(SourceSectionMode.content)
                Text("Info").tag(SourceSectionMode.info)
                Text("Outline").tag(SourceSectionMode.outline)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            Divider()

            switch mode {
            case .content:
                DisplayAttributesStrip(document: document)
                Divider()
                DocumentInspectorContentV2(document: document, mode: .pageContentOnly)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .info:
                SourceInfoView(document: document)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .outline:
                SourceOutlineView(documentId: document.id)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }
}

/// The document's Info + Metadata body — the Source section's Info mode (#3876).
/// One home for the info content, whether reached from the Source segmented picker
/// or the folded (exhaustiveness-only) Info tab.
struct SourceInfoView: View {
    let document: Document

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                DocumentInspectorInfoTab(document: document)
                if !document.metadata.isEmpty || document.path != nil {
                    DocumentInspectorMetadataTab(document: document)
                }
                Spacer()
            }
            .padding()
        }
    }
}

enum SourceSectionMode: String, CaseIterable {
    case content
    case info
    case outline
}
