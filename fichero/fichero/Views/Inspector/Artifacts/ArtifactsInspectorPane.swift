import SwiftUI

enum ArtifactInspectorFocusRouting {
    /// Preserve a cross-tab artifact selection when the artifacts pane appears
    /// for the same inspected document. A different document still resets the
    /// shared focus to avoid selection bleed across files.
    static func shouldClearSelection(
        focusedDocumentId: String?,
        inspectedDocumentId: String
    ) -> Bool {
        guard let focusedDocumentId else { return false }
        return focusedDocumentId != inspectedDocumentId
    }
}

/// Params for the audited `artifact.translate` action (#3325). Snake-case keys
/// match the backend `ArtifactTranslateParams` pydantic model.
struct ArtifactTranslateActionParams: Encodable {
    let documentId: String
    let targetLang: String
    let sourceLang: String
    let provider: String?

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id"
        case targetLang = "target_lang"
        case sourceLang = "source_lang"
        case provider
    }
}

/// A target language the user can translate a document into (#3325). Codes are
/// ISO-639-1; the list leans toward the archival corpora (Spanish colonial,
/// Latin, Portuguese) but stays short — the backend accepts any code.
struct TranslationLanguage: Identifiable, Hashable {
    let code: String
    let name: String
    var id: String { code }

    static let common: [TranslationLanguage] = [
        .init(code: "en", name: "English"),
        .init(code: "es", name: "Spanish"),
        .init(code: "pt", name: "Portuguese"),
        .init(code: "fr", name: "French"),
        .init(code: "la", name: "Latin"),
        .init(code: "de", name: "German"),
        .init(code: "it", name: "Italian"),
        .init(code: "nl", name: "Dutch")
    ]
}

private func inspectorArtifactTitle(_ artifact: Artifact) -> String {
    artifact.artifactType
        .split(separator: "_")
        .map { $0.prefix(1).uppercased() + $0.dropFirst() }
        .joined(separator: " ")
}

/// The Artifacts inspector tab, rebuilt as List + detail (#2003, EPIC #2002).
///
/// Replaces the old `DocumentInspectorContentV2(mode: .artifactsOnly)` stacked
/// `ArtifactPanel`s. A vertical stack: a lightweight `ArtifactListView` on top
/// for overview, a single `ArtifactDetailView` below that follows the selection.
/// A toolbar button tears the detail off into a
/// separate, draggable window (`ArtifactDetailWindow`) that also follows
/// selection.
///
/// Data comes from the document-scoped `ArtifactStore` (#1997) — the sanctioned
/// reactive source. The pane points the store at the current document; the
/// store live-updates on `artifact.*` change events, so the list and detail
/// stay current without manual refetch.
struct ArtifactsInspectorPane: View {
    let document: Document

    @Environment(ArtifactStore.self) private var store
    @Environment(ArtifactService.self) private var artifactService
    @Environment(DocumentService.self) private var documentService
    @Environment(DocumentStore.self) private var documentStore: DocumentStore
    @Environment(LibraryManager.self) private var libraryManager
    @Environment(WorkflowExecutionObserver.self) private var executionObserver
    @Environment(\.openWindow) private var openWindow
    @Environment(\.supportsMultipleWindows) private var supportsMultipleWindows
    /// Per-window source-navigation bus (#3437).
    @Environment(ClaimSourceNavigationState.self) private var claimSourceNavigationState: ClaimSourceNavigationState?

    /// Shared selection — the same instance the detached window observes.
    @State private var focused = FocusedArtifact.shared
    @State private var actionError: String?
    /// A translate action is in flight (#3325).
    @State private var isTranslating = false
    /// The run whose trace is being shown from "Produced by" (#4319/#4320).
    @State private var traceRun: TraceRunSelection?

    /// Identifiable wrapper so `.sheet(item:)` can present a run trace.
    private struct TraceRunSelection: Identifiable {
        let threadId: String
        var id: String { threadId }
    }

    /// The artifact currently selected, resolved live from the store so inline
    /// edits and workflow re-runs flow through immediately.
    private var selectedArtifact: Artifact? {
        focused.id.flatMap { id in store.items.first { $0.id == id } }
    }

    private var knownDocumentsById: [String: Document] {
        (
            documentStore.collections
                + documentStore.currentDocuments
                + documentStore.sidebarDocuments
                + [document]
        ).reduce(into: [String: Document]()) { result, item in
            result[item.id] = item
        }
    }

    private var selectedProvenance: ArtifactProvenanceDisplay? {
        guard let selectedArtifact else { return nil }
        return ArtifactProvenance.display(
            for: selectedArtifact,
            inspectedDocument: document,
            documentsById: knownDocumentsById
        )
    }

    var body: some View {
        VStack(spacing: 0) {
            if let actionError {
                errorBox(actionError)
            }
            InspectorListDetailSplit {
                ArtifactListView(
                    store: store,
                    inspectedDocument: document,
                    documentsById: knownDocumentsById,
                    focused: focused,
                    onOpenInWindow: openDetailWindow,
                    onTranslate: { translate(to: $0) },
                    workflowNameForId: workflowName(forId:)
                )
            } detail: {
                ArtifactDetailView(
                    artifact: selectedArtifact,
                    provenance: selectedProvenance,
                    onOpenSource: openSelectedArtifactSource,
                    onOpenRun: openSelectedArtifactRun,
                    onSave: { artifact, content in
                        await saveArtifact(artifact, content: content)
                    },
                    onDelete: { artifact in
                        Task { await deleteArtifact(artifact) }
                    }
                )
            }
            Divider()
            InspectorBottomMiniToolbar(statusText: artifactsToolbarStatusText) {
                Button {
                    Task { await store.reload() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .help("Reload artifacts")
                .accessibilityLabel("Reload artifacts")

                Button {
                    openSelectedArtifactSource()
                } label: {
                    Image(systemName: "arrow.turn.down.right")
                }
                .buttonStyle(.plain)
                .help("Open artifact source")
                .accessibilityLabel("Open artifact source")
                .disabled(selectedProvenance?.sourceDocumentId == nil)

                Button {
                    openDetailWindow()
                } label: {
                    Image(systemName: "macwindow.badge.plus")
                }
                .buttonStyle(.plain)
                .help("Open the selected artifact in a separate window")
                .accessibilityLabel("Open selected artifact in window")
                .disabled(focused.id == nil)
            }
        }
        // The top-toolbar detach button was removed (#3461): the bottom
        // mini-toolbar's "Open in window" button is the single detach affordance,
        // keeping the top of the inspector as just the section switcher.
        .task(id: document.id) {
            // Preserve a same-document artifact selection when another pane
            // (e.g. Content / outline) routes into Artifacts; otherwise the tab
            // handoff clears the selected artifact before the detail can render.
            if ArtifactInspectorFocusRouting.shouldClearSelection(
                focusedDocumentId: focused.documentId,
                inspectedDocumentId: document.id
            ) {
                focused.clear()
            }
            focused.documentId = document.id
            focused.documentName = document.name
            await store.setScope(
                documentId: document.id,
                includeDescendants: false,
                force: true
            )
            focused.resolve(in: store.items)
        }
        .onChange(of: executionObserver.fileCompletedCount) { _, _ in
            Task { await store.reload() }
        }
        .onChange(of: executionObserver.workflowCompletedCount) { _, _ in
            Task { await store.reload() }
        }
        // "Produced by" → the run's trace (#4319/#4320).
        .sheet(item: $traceRun) { selection in
            RunTraceSheet(threadId: selection.threadId)
        }
    }

    /// Resolve a workflow id to its name for the run-group headers (#4319).
    private func workflowName(forId workflowId: String) -> String? {
        libraryManager.globalLibrary?.workflowStore.workflows
            .first { $0.id == workflowId }?
            .name
    }

    private func openSelectedArtifactRun() {
        guard let runId = selectedArtifact?.runId, !runId.isEmpty else { return }
        traceRun = TraceRunSelection(threadId: runId)
    }

    private var artifactsToolbarStatusText: String {
        if let selectedArtifact {
            return inspectorArtifactTitle(selectedArtifact)
        }
        return "\(store.items.count) artifacts"
    }

    private func openDetailWindow() {
        // #2254: gate every `openWindow` on multi-window support so the floating
        // placement degrades safely (the detail stays docked) on platforms that
        // can't open a second window.
        guard supportsMultipleWindows else { return }
        // Make sure the snapshot is current before the window reads it.
        focused.resolve(in: store.items)
        openWindow(id: "artifact-detail")
    }

    private func openSelectedArtifactSource() {
        guard let selectedArtifact else { return }
        let provenance = ArtifactProvenance.display(
            for: selectedArtifact,
            inspectedDocument: document,
            documentsById: knownDocumentsById
        )
        claimSourceNavigationState?.request(
            ClaimSourceNavigationRequest(
                documentId: provenance.sourceDocumentId,
                pageLabel: provenance.pageLabel
            )
        )
    }

    // MARK: - Mutations
    //
    // Mirrors the old DocumentInspectorContentV2 save/delete, but routes the
    // refresh through the store (the change-stream usually beats us to it; the
    // explicit reload keeps the UI snappy if an event is delayed).

    /// Returns nil on success, or the user-facing error message — the panel
    /// keeps the draft dirty and retries on a non-nil return (#4285).
    @discardableResult
    private func saveArtifact(_ artifact: Artifact, content: String) async -> String? {
        do {
            _ = try await artifactService.updateArtifact(
                id: artifact.id,
                documentId: document.id,
                content: content
            )
            actionError = nil
            await store.reload()
            return nil
        } catch {
            let message = "Couldn't save: \(error.localizedDescription)"
            actionError = message
            return message
        }
    }

    private func deleteArtifact(_ artifact: Artifact) async {
        do {
            try await artifactService.deleteArtifact(id: artifact.id, documentId: document.id)
            if focused.id == artifact.id { focused.clear() }
            actionError = nil
            await store.reload()
        } catch {
            actionError = "Couldn't delete: \(error.localizedDescription)"
        }
    }

    private func translate(to language: TranslationLanguage) {
        guard let actionsService = libraryManager.globalLibrary?.actionsService else {
            actionError = "No library available to translate."
            return
        }
        isTranslating = true
        Task { @MainActor in
            defer { isTranslating = false }
            do {
                _ = try await actionsService.invokeAction(
                    name: "artifact.translate",
                    params: ArtifactTranslateActionParams(
                        documentId: document.id,
                        targetLang: language.code,
                        sourceLang: "auto",
                        provider: nil
                    )
                )
                actionError = nil
                // The new translation artifact also arrives via the change stream;
                // reload so it shows immediately in the list.
                await store.reload()
            } catch {
                actionError = "Couldn't translate: \(error.localizedDescription)"
            }
        }
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
            Button("Dismiss") { actionError = nil }
                .buttonStyle(.bordered)
                .controlSize(.small)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.orange.opacity(0.1))
    }
}

/// The torn-off detail window (#2003). A separate, naturally-draggable scene
/// that renders the selected artifact read-only and, by default, **follows the
/// inspector's selection** via the shared `FocusedArtifact`. A pin toggle parks
/// the window on the current artifact so it can sit alongside others while the
/// inspector moves on.
struct ArtifactDetailWindow: View {
    @State private var focused = FocusedArtifact.shared

    /// When pinned, the window stops following and shows `pinnedArtifact`.
    @State private var isPinned = false
    @State private var pinnedArtifact: Artifact?

    private var shownArtifact: Artifact? {
        isPinned ? pinnedArtifact : focused.artifact
    }

    var body: some View {
        ArtifactDetailView(artifact: shownArtifact)
            .navigationTitle(shownArtifact.map(inspectorArtifactTitle) ?? "Artifact")
            #if !os(visionOS)
            .navigationSubtitle(focused.documentName ?? "")
            #endif
            .toolbar {
                ToolbarItem(placement: .automatic) {
                    Toggle(isOn: $isPinned) {
                        Label(
                            isPinned ? "Pinned" : "Following selection",
                            systemImage: isPinned ? "pin.fill" : "pin"
                        )
                    }
                    .toggleStyle(.button)
                    .help(
                        isPinned
                            ? "Pinned to this artifact — won't follow selection"
                            : "Following the inspector's selection"
                    )
                    .onChange(of: isPinned) { _, pinned in
                        // Capture the current artifact the moment we pin so the
                        // window parks even as the inspector selection moves on.
                        pinnedArtifact = pinned ? focused.artifact : nil
                    }
                }
            }
            .frame(minWidth: 360, minHeight: 320)
    }

}
