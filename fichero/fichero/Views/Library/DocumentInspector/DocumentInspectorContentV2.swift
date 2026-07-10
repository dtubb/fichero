import SwiftUI

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

    @Environment(ArtifactServiceGenerated.self) private var artifactService
    @Environment(DocumentServiceGenerated.self) private var documentService
    @Environment(DocumentStore.self) private var documentStore: DocumentStore
    @Environment(WorkflowExecutionObserver.self) private var executionObserver

    @State private var artifacts: [Artifact] = []
    @State private var isLoading = false
    @State private var loadError: String?
    @State private var actionError: String?

    private var liveDocument: Document {
        Self.refreshedDocument(document, in: documentStore.currentDocuments)
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
            await loadArtifacts()
        }
        .onChange(of: executionObserver.fileCompletedCount) { _, _ in
            Task { await refreshVisibleDocument() }
            // Refresh after individual file completions — but don't compete
            // with an in-flight load.
            Task { await loadArtifacts() }
        }
        .onChange(of: executionObserver.workflowCompletedCount) { _, _ in
            Task { await refreshVisibleDocument() }
            Task { await loadArtifacts() }
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
                Task { await loadArtifacts() }
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

    private func loadArtifacts() async {
        // The page-content-only tab never renders artifacts (the artifact list
        // is gated by `mode != .pageContentOnly`), so fetching them on every
        // document selection is wasted work — and it flashed a stray "Loading
        // artifacts…" spinner over the page editor (#3186).
        guard mode != .pageContentOnly else { return }
        guard !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            // V2 usually wants strict per-document scope — see #696/V2
            // redesign. Parent PDFs are the exception: extraction workflows
            // write per-page entity artifacts to page children, and the
            // parent inspector must surface those raw page outputs.
            artifacts = try await artifactService.getArtifacts(
                forDocumentId: document.id,
                forceRefresh: true,
                includeDescendants: Self.shouldIncludeDescendantArtifacts(
                    for: document,
                    mode: mode
                )
            )
            loadError = nil
        } catch is CancellationError {
            // Task superseded by a newer page selection — not a load failure.
        } catch {
            loadError = "Couldn't load artifacts: \(error.localizedDescription)"
        }
    }

    private func deleteArtifact(_ artifact: Artifact) async {
        // Optimistic remove (#705 pattern). The artifact panel disappears
        // immediately; rollback if the backend rejects the delete.
        let snapshot = artifacts
        artifacts.removeAll { $0.id == artifact.id }
        do {
            try await artifactService.deleteArtifact(
                id: artifact.id, documentId: document.id
            )
            actionError = nil
        } catch {
            artifacts = snapshot
            actionError = "Couldn't delete: \(error.localizedDescription)"
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
            let updated = try await artifactService.updateArtifact(
                id: artifact.id,
                documentId: document.id,
                content: content
            )
            // Replace in local list so the read view picks up the new text
            // immediately; the next loadArtifacts will reconcile if needed.
            if let index = artifacts.firstIndex(where: { $0.id == updated.id }) {
                artifacts[index] = updated
            }
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
