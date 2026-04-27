// swiftlint:disable file_length
// V2 inspector views (DisplayAttributesStrip, ArtifactPanel,
// DocumentInspectorContentV2) are appended at the bottom of this file —
// keeping them inline avoids a pbxproj edit (MEMORY: Swift main target not
// file-sync'd). When V2 promotes to default-on (per
// docs/architecture/swiftui/inspector_redesign.md Phase 2), they can be
// split into their own files at that point.
import SwiftUI

/// Tab selection for document inspector
enum InspectorTab: String, CaseIterable, Identifiable {
    case info = "Info"
    case content = "Content"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .info: return "info.circle"
        case .content: return "doc.text"
        }
    }
}

/// Inspector panel showing document metadata and details
struct DocumentInspector: View {
    let document: Document?

    @SceneStorage("inspectorSelectedTab") private var selectedTab: InspectorTab = .info
    @ObservedObject private var featureManager = FeatureManager.shared

    var body: some View {
        Group {
            if let doc = document {
                documentDetail(doc)
            } else {
                emptyState
            }
        }
        .frame(minWidth: 220, maxWidth: .infinity)
    }

    // MARK: - Document Detail

    private func documentDetail(_ doc: Document) -> some View {
        VStack(spacing: 0) {
            // Xcode-style icon-only tab bar
            HStack(spacing: 2) {
                ForEach(InspectorTab.allCases) { tab in
                    Button {
                        selectedTab = tab
                    } label: {
                        Image(systemName: tab.icon)
                            .font(.system(size: 16, weight: .regular))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 7)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .background(
                        RoundedRectangle(cornerRadius: 6)
                            .fill(selectedTab == tab
                                  ? Color.accentColor.opacity(0.15)
                                  : Color.clear)
                    )
                    .foregroundStyle(selectedTab == tab ? Color.accentColor : Color.secondary)
                    .help(tab.rawValue)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 6)

            Divider()

            // Tab content.
            // Content tab renders directly without ScrollView — NSTextView manages its own scrolling.
            // Info tab wraps in ScrollView since it contains only static SwiftUI views.
            switch selectedTab {
            case .content:
                if featureManager.isInspectorV2Enabled {
                    DocumentInspectorContentV2(document: doc)
                } else {
                    DocumentInspectorContentTab(document: doc)
                }
            case .info:
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        DocumentInspectorInfoTab(document: doc)
                        if !doc.metadata.isEmpty || doc.path != nil {
                            DocumentInspectorMetadataTab(document: doc)
                        }
                        DocumentInspectorArtifactsTab(documentId: doc.id)
                        Spacer()
                    }
                    .padding()
                }
            }
        }
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "sidebar.right")
                .font(.system(size: 36))
                .foregroundColor(.secondary)

            Text("No Selection")
                .font(.headline)

            Text("Select a document to view details")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    // MARK: - Helpers

    private func copyToClipboard(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }
}

// MARK: - Preview

#Preview("Empty") {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    DocumentInspector(document: nil)
        .environmentObject(library.artifactService)
        .frame(width: 280, height: 400)
}

#Preview("With Document") {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    let mockDocument = Document(
        id: UUID().uuidString,
        parentId: nil,
        docType: .file,
        fileType: .pdf,
        name: "Sample Document.pdf",
        path: nil,
        sequence: nil,
        bbox: nil,
        status: .completed,
        metadata: [:],
        pageContent: nil,
        createdAt: Date(),
        updatedAt: Date()
    )

    DocumentInspector(document: mockDocument)
        .environmentObject(library.artifactService)
        .frame(width: 280, height: 400)
}

/// Compact key-value strip at the top of the V2 inspector — modeled on
/// Tinderbox's "Displayed Attributes" panel. Read-only in Phase 1.
///
/// Shows the few fields a researcher checks most often when scanning a
/// document: status, kind, ingest mode, timestamps. The list is intentionally
/// short — anything more belongs in the Info tab. See
/// docs/architecture/swiftui/inspector_redesign.md.
struct DisplayAttributesStrip: View {
    let document: Document

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            row("Status", value: statusValue, color: statusColor)
            Divider()
            row("Kind", value: kindValue)
            Divider()
            row("Ingest", value: ingestValue)
            if let path = document.path, !path.isEmpty {
                Divider()
                row("Path", value: path, monospaced: true)
            }
            Divider()
            row("Created", value: relativeDateString(document.createdAt))
            Divider()
            row("Modified", value: relativeDateString(document.updatedAt))
        }
        .padding(.vertical, 6)
        .background(Color(.controlBackgroundColor))
    }

    // MARK: - Row helpers

    @ViewBuilder
    private func row(
        _ label: String,
        value: String,
        color: Color = .primary,
        monospaced: Bool = false
    ) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .frame(width: 64, alignment: .leading)
            Text(value)
                .font(monospaced ? .caption.monospaced() : .caption)
                .foregroundStyle(color)
                .lineLimit(1)
                .truncationMode(.middle)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 3)
    }

    // MARK: - Value computation

    private var statusValue: String {
        switch document.status {
        case .pending: return "Pending"
        case .processing: return "Processing"
        case .completed: return "Completed"
        case .failed: return "Failed"
        }
    }

    private var statusColor: Color {
        switch document.status {
        case .pending: return .secondary
        case .processing: return .blue
        case .completed: return .green
        case .failed: return .red
        }
    }

    private var kindValue: String {
        switch document.docType {
        case .folder: return "Folder"
        case .group: return "Group"
        case .file:
            if let fileType = document.fileType {
                return fileType.rawValue.uppercased()
            }
            return "File"
        case .page: return "Page"
        case .chunk: return "Chunk"
        }
    }

    private var ingestValue: String {
        document.isLinked ? "LINK" : "COPY"
    }

    private func relativeDateString(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}

/// One read-only panel showing a single artifact (transcription, catalogue,
/// summary, etc.) in the V2 inspector. Each artifact gets its own panel —
/// new artifacts append rather than replace, so workflow re-runs never
/// overwrite what's already on screen.
///
/// Phase 1: read-only display. Phase 2 will add per-artifact actions
/// (copy, regenerate, hide). See docs/architecture/swiftui/inspector_redesign.md.
struct ArtifactPanel: View {
    enum PanelKind {
        case artifact(Artifact)
        /// Special case for showing the document's `page_content` so existing
        /// docs aren't blank in V2 before notes-as-artifact migrates over.
        case pageContent(text: String)
    }

    let kind: PanelKind
    /// Optional delete action. When provided, a trash button shows in the
    /// header on hover. nil hides the button (use for kinds that aren't
    /// individually deletable, like `pageContent` which is a Document field).
    var onDelete: (() -> Void)?
    /// Optional save action. When provided, an edit pencil shows in the
    /// header. The closure receives the new content (RTF source if the
    /// editor produced rich text, plain otherwise) and is responsible for
    /// persisting it. nil hides the edit affordance (read-only panel).
    var onSave: ((String) async -> Void)?

    @AppStorage("editor.rulersVisible") private var rulersVisible = true
    @AppStorage("editor.fontName") private var fontName: String = "System"
    @AppStorage("editor.fontSize") private var fontSize: Double = 14
    @AppStorage("editor.lineSpacing") private var lineSpacing: Double = 4
    @AppStorage("editor.marginHorizontal") private var marginH: Double = 16
    @AppStorage("editor.marginVertical") private var marginV: Double = 12

    @State private var isExpanded: Bool = true
    @State private var confirmingDelete: Bool = false
    @State private var isEditing: Bool = false
    @State private var draftAttributedText: NSAttributedString = NSAttributedString(string: "")
    @State private var editorRevision: Int = 0
    @State private var isSaving: Bool = false
    @State private var saveError: String?
    @State private var autoSaveTask: Task<Void, Never>?
    @State private var lastSeededContent: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            DisclosureGroup(isExpanded: $isExpanded) {
                contentBody
                    .padding(.horizontal, 12)
                    .padding(.bottom, 10)
                    .padding(.top, 4)
            } label: {
                header
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
        }
        .background(
            RoundedRectangle(cornerRadius: 6)
                .stroke(Color(.separatorColor), lineWidth: 1)
        )
        .padding(.horizontal, 8)
        .confirmationDialog(
            "Delete this artifact?",
            isPresented: $confirmingDelete,
            titleVisibility: .visible
        ) {
            Button("Delete", role: .destructive) { onDelete?() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text(deleteMessage)
        }
    }

    // MARK: - Header

    @ViewBuilder
    private var header: some View {
        HStack(spacing: 8) {
            Image(systemName: iconName)
                .foregroundStyle(.secondary)
                .font(.system(size: 13))
            Text(title)
                .font(.subheadline)
                .fontWeight(.medium)
            if let subtitle = subtitle {
                Text("·")
                    .foregroundStyle(.tertiary)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            Spacer()
            // Always-visible action buttons — gating them on hover meant
            // they vanished as the user moved the cursor off the panel
            // toward the button (Daniel feedback 2026-04-26). Stable
            // visibility, no chase.
            if onSave != nil, !isEditing {
                Button {
                    enterEdit()
                } label: {
                    Image(systemName: "square.and.pencil")
                        .font(.system(size: 11))
                }
                .buttonStyle(.borderless)
                .foregroundStyle(.secondary)
                .help("Edit this artifact")
            }
            if onDelete != nil, !isEditing {
                Button {
                    confirmingDelete = true
                } label: {
                    Image(systemName: "trash")
                        .font(.system(size: 11))
                }
                .buttonStyle(.borderless)
                .foregroundStyle(.secondary)
                .help("Delete this artifact")
            }
            if isEditing {
                if isSaving {
                    ProgressView().controlSize(.small)
                } else if saveError == nil {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 11))
                        .foregroundStyle(.green)
                        .help("Saved")
                }
                Button("Done") { exitEdit() }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
            }
        }
    }

    private var deleteMessage: String {
        switch kind {
        case .artifact(let artifact):
            return "\(title) from \(artifact.provider ?? "unknown") will be removed."
        case .pageContent:
            return "Page content will be cleared."
        }
    }

    // MARK: - Content body
    //
    // Always render via AttributedTextEditor — toggling between a plain
    // Text(read) and an editor(edit) was stripping formatting in the read
    // view (Daniel: "not displaying the rtf, unless I click [edit]") and
    // was responsible for the per-panel layout looking inconsistent. One
    // editor for both modes, isEditable flips the cursor/typing behavior.
    @ViewBuilder
    private var contentBody: some View {
        VStack(alignment: .leading, spacing: 4) {
            AttributedTextEditor(
                text: $draftAttributedText,
                isEditable: isEditing,
                rulersVisible: isEditing && rulersVisible,
                fontName: fontName,
                fontSize: fontSize,
                lineSpacing: lineSpacing,
                marginH: marginH,
                marginV: marginV,
                contentRevision: editorRevision,
                onTextChanged: {
                    if isEditing { scheduleAutoSave() }
                },
                onEditingChanged: { editing in
                    if !editing && isEditing {
                        Task { await flushAutoSave() }
                    }
                }
            )
            .frame(minHeight: 240, maxHeight: .infinity)
            .background(Color(.textBackgroundColor))
            .cornerRadius(4)
            if let saveError {
                Text(saveError)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
        .task(id: rawArtifactContent) {
            // Re-seed when the artifact content changes (e.g. after a workflow
            // re-run rewrites it). Don't re-seed if the user is mid-edit —
            // their draft survives until they Done or blur.
            guard !isEditing, lastSeededContent != rawArtifactContent else { return }
            draftAttributedText = decodeArtifactContent(rawArtifactContent)
            lastSeededContent = rawArtifactContent
            editorRevision += 1
        }
    }

    // MARK: - Edit mode helpers

    private func enterEdit() {
        // The draft is already seeded by the .task(id: rawArtifactContent)
        // modifier on contentBody — no need to re-decode here. Just flip
        // isEditable.
        isEditing = true
        saveError = nil
    }

    private func exitEdit() {
        // "Done" — flush any pending debounce before leaving edit mode so
        // the read view shows the final saved content.
        Task { await flushAutoSave() }
        isEditing = false
    }

    /// Debounced auto-save. The previous explicit Save button created a
    /// "did my edit save?" anxiety loop — auto-save with a small visible
    /// indicator is calmer. (Daniel feedback 2026-04-26.)
    private func scheduleAutoSave() {
        autoSaveTask?.cancel()
        autoSaveTask = Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(800))
            if Task.isCancelled { return }
            await performSave()
        }
    }

    private func flushAutoSave() async {
        autoSaveTask?.cancel()
        autoSaveTask = nil
        await performSave()
    }

    private func performSave() async {
        guard let onSave, !isSaving else { return }
        isSaving = true
        defer { isSaving = false }
        let encoded = encodeArtifactContent(draftAttributedText)
        await onSave(encoded)
    }

    /// Raw content used when seeding the editor — for `.artifact` we use the
    /// content field as the editor source, even if it's RTF, so formatting
    /// round-trips. For `.pageContent` we don't have access to the document's
    /// metadata-stored RTF here (we'd need to plumb it through), so plain
    /// text is the editable surface.
    private var rawArtifactContent: String {
        switch kind {
        case .pageContent(let text): return text
        case .artifact(let artifact): return artifact.content ?? ""
        }
    }

    /// Decode an artifact's stored content into an NSAttributedString. RTF
    /// source (`{\rtf...`) is parsed; plain text becomes a styled run.
    private func decodeArtifactContent(_ content: String) -> NSAttributedString {
        if content.hasPrefix("{\\rtf"),
           let data = content.data(using: .utf8),
           let attr = try? NSAttributedString(
               data: data,
               options: [.documentType: NSAttributedString.DocumentType.rtf],
               documentAttributes: nil
           ) {
            return attr
        }
        return NSAttributedString(string: content)
    }

    /// Encode an NSAttributedString back to a content string. Inline RTF
    /// source (not base64) so the artifact's `content` field stays human-
    /// readable when the artifact is plain text and round-trips losslessly
    /// when the user added formatting.
    ///
    /// Custom paragraph styles (ruler tab stops, indents, line spacing
    /// changes) MUST round-trip through RTF — earlier this function
    /// excluded .paragraphStyle from the formatting check, which made
    /// ruler edits silently lose on save (Daniel feedback 2026-04-26).
    private func encodeArtifactContent(_ attr: NSAttributedString) -> String {
        let fullRange = NSRange(location: 0, length: attr.length)
        let plain = attr.string

        var hasFormatting = false
        let defaultPara = NSParagraphStyle.default
        attr.enumerateAttributes(in: fullRange) { attrs, _, stop in
            for (key, value) in attrs {
                if key == .paragraphStyle {
                    if let para = value as? NSParagraphStyle, para != defaultPara {
                        hasFormatting = true
                    }
                    continue
                }
                hasFormatting = true
            }
            if hasFormatting { stop.pointee = true }
        }

        if !hasFormatting { return plain }

        guard let data = try? attr.data(
            from: fullRange,
            documentAttributes: [.documentType: NSAttributedString.DocumentType.rtf]
        ), let rtfString = String(data: data, encoding: .utf8) else {
            return plain
        }
        return rtfString
    }

    // MARK: - Computed properties

    private var iconName: String {
        switch kind {
        case .pageContent: return "doc.text"
        case .artifact(let artifact):
            switch artifact.artifactType {
            case "transcription": return "text.quote"
            case "catalogue": return "books.vertical"
            case "summary": return "text.alignleft"
            case "key_people", "people": return "person.2"
            case "timeline", "dates": return "calendar"
            case "keywords": return "tag"
            case "rivers": return "water.waves"
            case "events": return "star"
            case "mines": return "hammer"
            case "properties": return "house"
            case "legal_references": return "scale.3d"
            default: return "sparkles"
            }
        }
    }

    private var title: String {
        switch kind {
        case .pageContent: return "Page Content"
        case .artifact(let artifact):
            return artifact.artifactType
                .split(separator: "_")
                .map { $0.prefix(1).uppercased() + $0.dropFirst() }
                .joined(separator: " ")
        }
    }

    private var subtitle: String? {
        switch kind {
        case .pageContent: return nil
        case .artifact(let artifact):
            var parts: [String] = []
            if let provider = artifact.provider, !provider.isEmpty { parts.append(provider) }
            if let model = artifact.model, !model.isEmpty { parts.append(model) }
            return parts.isEmpty ? nil : parts.joined(separator: " · ")
        }
    }

    private var timestamp: String? {
        switch kind {
        case .pageContent: return nil
        case .artifact(let artifact):
            // RelativeDateTimeFormatter renders <1 minute as "in 0 secs",
            // which Daniel correctly called silly. For fresh artifacts show
            // "just now"; otherwise the abbreviated relative string.
            let interval = abs(Date().timeIntervalSince(artifact.createdAt))
            if interval < 60 { return "just now" }
            let formatter = RelativeDateTimeFormatter()
            formatter.unitsStyle = .abbreviated
            return formatter.localizedString(for: artifact.createdAt, relativeTo: Date())
        }
    }

    private var bodyText: String {
        switch kind {
        case .pageContent(let text):
            return text.isEmpty ? "(empty)" : text
        case .artifact(let artifact):
            guard let content = artifact.content, !content.isEmpty else {
                return "(no text)"
            }
            // If the stored content is RTF source, render the plain string
            // for the read view. The decode→encode round-trip on the editor
            // path preserves the formatting; the read view shows plain so
            // users see what's actually written without RTF chrome.
            if content.hasPrefix("{\\rtf"),
               let data = content.data(using: .utf8),
               let attr = try? NSAttributedString(
                   data: data,
                   options: [.documentType: NSAttributedString.DocumentType.rtf],
                   documentAttributes: nil
               ) {
                return attr.string
            }
            return content
        }
    }
}

/// V2 inspector Content tab. Tinderbox-style layout:
///   - DisplayAttributesStrip at top (compact key-value).
///   - One ArtifactPanel per artifact below.
///   - The document's `page_content` (if any) renders as one final panel
///     so existing data is visible without a migration.
///
/// Phase 1: read-only. No save logic, no caching, no signature dance —
/// we re-fetch artifacts when the document selection or workflow events
/// change, full stop. See docs/architecture/swiftui/inspector_redesign.md.
struct DocumentInspectorContentV2: View {
    let document: Document

    @EnvironmentObject private var artifactService: ArtifactServiceGenerated
    @EnvironmentObject private var documentService: DocumentServiceGenerated
    @EnvironmentObject private var documentStore: DocumentStore
    @Environment(WorkflowExecutionObserver.self) private var executionObserver

    @State private var artifacts: [Artifact] = []
    @State private var isLoading = false
    @State private var loadError: String?
    @State private var actionError: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                // Daniel feedback 2026-04-26: the prior DisplayAttributesStrip
                // showed static doc metadata (Status, Kind, Ingest, etc.) but
                // those are already in the Info tab. The top strip's intended
                // purpose is AI-EXTRACTED attributes — names, places, dates
                // from list-typed extractor artifacts. That requires the
                // artifact-payload-type system (people/places/dates as
                // structured attributes). Until that exists, the strip is
                // empty: panels only. (See inspector_redesign.md.)

                if let loadError {
                    errorBox(loadError)
                }
                if let actionError {
                    errorBox(actionError)
                }

                ForEach(sortedArtifacts) { artifact in
                    ArtifactPanel(
                        kind: .artifact(artifact),
                        onDelete: { Task { await deleteArtifact(artifact) } },
                        onSave: { newContent in
                            await saveArtifact(artifact, content: newContent)
                        }
                    )
                }

                if let pageContent = document.pageContent, !pageContent.isEmpty {
                    ArtifactPanel(
                        kind: .pageContent(text: pageContent),
                        onDelete: { Task { await clearPageContent() } },
                        onSave: { newContent in
                            await savePageContent(newContent)
                        }
                    )
                }

                if !isLoading
                    && sortedArtifacts.isEmpty
                    && (document.pageContent ?? "").isEmpty
                    && loadError == nil {
                    emptyState
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
            .padding(.vertical, 8)
        }
        .task(id: document.id) {
            await loadArtifacts()
        }
        .onChange(of: executionObserver.fileCompletedCount) { _, _ in
            // Refresh after individual file completions — but don't compete
            // with an in-flight load.
            Task { await loadArtifacts() }
        }
        .onChange(of: executionObserver.workflowCompletedCount) { _, _ in
            Task { await loadArtifacts() }
        }
    }

    // MARK: - Subviews

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
        artifacts.sorted { $0.createdAt > $1.createdAt }
    }

    private func loadArtifacts() async {
        guard !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            // V2 wants strict per-document scope — see #696/V2 redesign.
            // The legacy aggregation (parent + children) made delete look
            // broken because deleting one artifact left a sibling in place.
            artifacts = try await artifactService.getArtifacts(
                forDocumentId: document.id,
                forceRefresh: true,
                includeDescendants: false
            )
            loadError = nil
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

    private func clearPageContent() async {
        // page_content is a Document field, not an artifact — clearing it
        // means a normal updateDocument call with pageContent: "".
        do {
            let updated = try await documentService.updateDocument(
                document.id,
                pageContent: ""
            )
            documentStore.refreshLocalContent(updated)
            actionError = nil
        } catch {
            actionError = "Couldn't clear page content: \(error.localizedDescription)"
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
        do {
            let updated = try await documentService.updateDocument(
                document.id,
                pageContent: content
            )
            documentStore.refreshLocalContent(updated)
            actionError = nil
        } catch {
            actionError = "Couldn't save: \(error.localizedDescription)"
        }
    }
}
