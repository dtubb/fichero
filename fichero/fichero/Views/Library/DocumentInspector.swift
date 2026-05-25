// swiftlint:disable file_length
// V2 inspector views (DisplayAttributesStrip, ArtifactPanel,
// DocumentInspectorContentV2) are appended at the bottom of this file —
// keeping them inline avoids a pbxproj edit (MEMORY: Swift main target not
// file-sync'd). When V2 promotes to default-on (per
// docs/architecture/swiftui/inspector_redesign.md Phase 2), they can be
// split into their own files at that point.
import SwiftUI

// MARK: - Notification Names

extension Notification.Name {
    /// Posted when a claim is selected in the inspector
    static let claimSelectedInInspector = Notification.Name("claimSelectedInInspector")
}

/// Tab selection for document inspector. Order matters — left-to-right is
/// content / knowledge graph / info, per Daniel's mental model:
/// "the document itself" → "the structured world inside it" → "metadata
/// about the document".
enum InspectorTab: String, CaseIterable, Identifiable {
    case content = "Content"
    case knowledgeGraph = "Knowledge Graph"
    case map = "Map"
    case artifacts = "Artifacts"
    case info = "Info"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .content: return "doc.text"
        case .knowledgeGraph: return "point.3.connected.trianglepath.dotted"
        case .map: return "map"
        case .artifacts: return "shippingbox"
        case .info: return "info.circle"
        }
    }
}

/// Inspector panel showing document metadata and details
struct DocumentInspector: View {
    let document: Document?
    /// Click-through callback for KG entity rows: receives a source page
    /// document id; ContentView resolves it to the parent file and selects
    /// it so the user can read the source. Optional so the previews and
    /// any non-ContentView host still compile. (#833)
    var onNavigateToSource: ((String) -> Void)?

    @SceneStorage("inspectorSelectedTab") private var selectedTab: InspectorTab = .content
    @EnvironmentObject private var entityService: EntityServiceGenerated
    @ObservedObject private var featureManager = FeatureManager.shared
    @ObservedObject private var claimFocusState = ClaimFocusState.shared

    var body: some View {
        Group {
            if let doc = document {
                documentDetail(doc)
            } else {
                emptyState
            }
        }
        .frame(minWidth: 220, maxWidth: .infinity, maxHeight: .infinity)
        .environmentObject(claimFocusState)
    }

    // MARK: - Document Detail

    private func documentDetail(_ doc: Document) -> some View {
        VStack(spacing: 0) {
            DisplayAttributesStrip(document: doc)
            Divider()
            tabBar
            Divider()
            tabContent(for: doc)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(maxHeight: .infinity)
    }

    /// Xcode-style icon-only tab bar
    @ViewBuilder
    private var tabBar: some View {
        HStack(spacing: 2) {
            ForEach(InspectorTab.allCases) { tab in
                Button {
                    selectedTab = tab
                } label: {
                    Image(systemName: tab.icon)
                        .font(.system(size: 16, weight: .regular))
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
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
        .frame(height: MiniToolbar<EmptyView>.standardHeight)
    }

    /// Tab content for the selected tab
    @ViewBuilder
    private func tabContent(for doc: Document) -> some View {
        switch selectedTab {
        case .content:
            DocumentInspectorContentV2(document: doc, mode: .pageContentOnly)
        case .knowledgeGraph:
            ScrollView {
                KnowledgeGraphInspectorSection(
                    documentId: doc.id,
                    entityService: entityService,
                    onNavigateToSource: onNavigateToSource,
                    onClaimSelect: { claimId, claimText, sourceDocId, pageLabel, charStart, charEnd in
                        // Notify the content view to sync claim selection
                        NotificationCenter.default.post(
                            name: .claimSelectedInInspector,
                            object: nil,
                            userInfo: [
                                "claimId": claimId,
                                "claimText": claimText as Any,
                                "sourceDocumentId": sourceDocId as Any,
                                "pageLabel": pageLabel as Any,
                                "charStart": charStart as Any,
                                "charEnd": charEnd as Any
                            ]
                        )
                    }
                )
                .padding()
            }
        case .map:
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Page-scoped Knowledge Graph (Map View)")
                        .font(.headline)
                    Text("Showing entities and relationships specific to this document.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    
                    // This would show a force-directed graph visualization of entities
                    // in the current document context (page-scoped)
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color.gray.opacity(0.1))
                        .frame(height: 300)
                        .overlay(
                            Text("Map tab placeholder - page-scoped graph would appear here")
                                .foregroundColor(.secondary)
                                .multilineTextAlignment(.center)
                                .padding()
                        )
                }
                .padding()
            }
        case .artifacts:
            DocumentInspectorContentV2(document: doc, mode: .artifactsOnly)
        case .info:
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    DocumentInspectorInfoTab(document: doc)
                    if !doc.metadata.isEmpty || doc.path != nil {
                        DocumentInspectorMetadataTab(document: doc)
                    }
                    Spacer()
                }
                .padding()
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
        .environmentObject(library.entityService)
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
        .environmentObject(library.entityService)
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
struct ArtifactPanel: View { // swiftlint:disable:this type_body_length
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

    /// Whether the panel starts expanded if there's no remembered choice.
    /// `true` for Page Content; `false` for generated artifacts.
    let defaultExpanded: Bool

    @State private var isExpanded: Bool

    /// UserDefaults key for this panel's expansion state, keyed by both
    /// artifact type AND producing provider so two transcriptions on the same
    /// document (Apple Vision + Qwen VL) maintain independent expand/collapse
    /// state across document switches and app launches. Without the provider
    /// in the key, collapsing the Apple Vision transcription on doc A would
    /// also collapse the Qwen transcription on doc B (#765).
    private static func storageKey(for kind: PanelKind) -> String {
        switch kind {
        case .pageContent:
            return "inspector.panel.expanded.pageContent"
        case .artifact(let artifact):
            let providerSuffix = (artifact.provider?.isEmpty == false)
                ? ".\(artifact.provider!)"
                : ""
            return "inspector.panel.expanded.\(artifact.artifactType)\(providerSuffix)"
        }
    }

    init(
        kind: PanelKind,
        defaultExpanded: Bool = true,
        onDelete: (() -> Void)? = nil,
        onSave: ((String) async -> Void)? = nil
    ) {
        self.kind = kind
        self.defaultExpanded = defaultExpanded
        self.onDelete = onDelete
        self.onSave = onSave

        // Read remembered choice if any; otherwise fall back to default.
        // `object(forKey:)` distinguishes "never set" (nil) from "set to
        // false" — required so first-run uses the parameter default,
        // not a coerced `false` from `bool(forKey:)`.
        let key = Self.storageKey(for: kind)
        let initial = (UserDefaults.standard.object(forKey: key) as? Bool) ?? defaultExpanded
        self._isExpanded = State(initialValue: initial)
    }
    @State private var confirmingDelete: Bool = false
    @State private var draftAttributedText: NSAttributedString = NSAttributedString(string: "")
    @State private var editorRevision: Int = 0
    @State private var isSaving: Bool = false
    @State private var saveError: String?
    @State private var autoSaveTask: Task<Void, Never>?
    @State private var lastSeededContent: String = ""
    @StateObject private var richTextController = RichTextController()

    var body: some View {
        // Daniel feedback 2026-04-27: drop the rounded-rect box outline (no
        // horizontal lines), let the editor go full panel width (no inner
        // horizontal padding), let separation between panels be just the
        // VStack spacing. Header still gets a little horizontal padding so
        // the title doesn't kiss the inspector edge.
        //
        // Sizing: when expanded, the panel flexes (maxHeight: .infinity) so
        // it fills remaining inspector space — and when there are multiple
        // expanded siblings, SwiftUI's VStack splits space equally. When
        // collapsed, the panel has no flex, so it shrinks to its header
        // height (~30 px) and lets siblings absorb the freed space.
        VStack(alignment: .leading, spacing: 0) {
            DisclosureGroup(isExpanded: $isExpanded) {
                contentBody
                    .padding(.bottom, 6)
                    .padding(.top, 2)
            } label: {
                header
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
        }
        // Sizing: AttributedTextEditor now reports its layoutManager-used
        // height via sizeThatFits, so an expanded panel matches its actual
        // content. We keep a small min so empty editors don't collapse to
        // a sliver (Daniel 2026-05-05: "the height was 0"); long artifacts
        // grow naturally and the outer ScrollView handles overflow (#960).
        // Collapsed panels have no frame and shrink to header height (~30 px).
        .frame(minHeight: isExpanded ? 60 : nil)
        .onChange(of: isExpanded) { _, newValue in
            // Persist the user's choice so it carries across documents
            // and across app launches. See `storageKey(for:)` for keying.
            UserDefaults.standard.set(newValue, forKey: Self.storageKey(for: kind))
        }
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
            // Save indicator (subtle): spinner while saving, green check when
            // idle and saved. No mode toggle — V2 panels are always editable
            // (Daniel feedback 2026-04-27 after preferring V1's always-on
            // behavior). Just type. Auto-saves on the debounce.
            if onSave != nil {
                if isSaving {
                    ProgressView().controlSize(.small)
                } else if saveError == nil {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 11))
                        .foregroundStyle(.green.opacity(0.7))
                        .help("Saved")
                }
            }
            if onDelete != nil {
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
            // Check if this is a structured output that should be read-only
            if isStructuredOutput {
                structuredOutputView
                    .frame(maxWidth: .infinity)
                    .background(Color(.textBackgroundColor))
                    .cornerRadius(4)
            } else {
                // Format controls live in the AppKit ruler view (Styles / alignment /
                // Spacing / Lists strip that AppKit draws above its numeric ruler)
                // and in the Format menu (bold/italic/underline shortcuts). No
                // separate SwiftUI format bar.
                AttributedTextEditor(
                    text: $draftAttributedText,
                    isEditable: onSave != nil,
                    rulersVisible: rulersVisible,
                    fontName: fontName,
                    fontSize: fontSize,
                    lineSpacing: lineSpacing,
                    marginH: marginH,
                    marginV: marginV,
                    contentRevision: editorRevision,
                    onTextChanged: { scheduleAutoSave() },
                    onEditingChanged: { editing in
                        if !editing { Task { await flushAutoSave() } }
                    },
                    onRulerVisibilityChanged: { visible in
                        if rulersVisible != visible { rulersVisible = visible }
                    },
                    marginLeading: marginH,
                    marginTrailing: 0,
                    controller: richTextController
                )
                // Width stretches; height comes from AttributedTextEditor's
                // sizeThatFits (its layoutManager.usedRect). No maxHeight here:
                // letting it claim .infinity inside the outer ScrollView made
                // every expanded panel fill the viewport (#960).
                .frame(maxWidth: .infinity)
                .background(Color(.textBackgroundColor))
                .cornerRadius(4)
            }
            if let saveError {
                Text(saveError)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
        .task(id: rawArtifactContent) {
            // Re-seed when the artifact content changes externally (workflow
            // re-run, navigation to a different doc). Skip if the change
            // came from our own auto-save echoing back, detected by the
            // lastSeededContent watermark.
            guard lastSeededContent != rawArtifactContent else { return }
            draftAttributedText = decodeArtifactContent(rawArtifactContent)
            lastSeededContent = rawArtifactContent
            editorRevision += 1
        }
    }

    // MARK: - Edit mode helpers

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
        // Mark the watermark BEFORE the save round-trips. When the engine echoes
        // the new pageContent/artifact content back through `rawArtifactContent`,
        // the `.task(id:)` guard `lastSeededContent != rawArtifactContent` will
        // short-circuit instead of reseeding the editor. Without this, every
        // successful save re-runs decodeArtifactContent on the just-saved RTF,
        // which costs the cursor/selection and looks to the user like the edit
        // didn't take.
        lastSeededContent = encoded
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

    /// Check if this artifact type should be read-only (structured outputs)
    private var isStructuredOutput: Bool {
        switch kind {
        case .pageContent:
            return false
        case .artifact(let artifact):
            // Structured outputs that shouldn't be edited as RTF
            let structuredTypes: Set<String> = ["entities", "classification", "embedding", "grouping", "segmentation"]
            return structuredTypes.contains(artifact.artifactType)
        }
    }

    /// Formatted view for structured outputs (JSON formatted)
    @ViewBuilder
    private var structuredOutputView: some View {
        switch kind {
        case .pageContent:
            // Shouldn't happen since isStructuredOutput is false for pageContent
            Text("Unsupported content type")
                .foregroundColor(.red)
        case .artifact(let artifact):
            if let content = artifact.content, !content.isEmpty {
                // Try to parse as JSON first for structured data
                if let jsonData = content.data(using: .utf8),
                   let jsonObject = try? JSONSerialization.jsonObject(with: jsonData, options: []),
                   let formattedJSON = try? JSONSerialization.data(withJSONObject: jsonObject, options: [.prettyPrinted]) {
                    if let formattedString = String(data: formattedJSON, encoding: .utf8) {
                        ScrollView {
                            Text(formattedString)
                                .font(.system(.body, design: .monospaced))
                                .foregroundColor(.primary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding()
                                .cornerRadius(4)
                        }
                        .frame(maxWidth: .infinity)
                        .frame(height: 200)
                    } else {
                        fallbackStructuredView(content: content)
                    }
                } else {
                    fallbackStructuredView(content: content)
                }
            } else {
                Text("(no content)")
                    .foregroundColor(.secondary)
                    .italic()
            }
        }
    }

    /// Fallback view for structured content that isn't valid JSON
    @ViewBuilder
    private func fallbackStructuredView(content: String) -> some View {
        ScrollView {
            Text(content)
                .font(.system(.body, design: .monospaced))
                .foregroundColor(.primary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding()
                .cornerRadius(4)
        }
        .frame(maxWidth: .infinity)
        .frame(height: 200)
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

    @EnvironmentObject private var artifactService: ArtifactServiceGenerated
    @EnvironmentObject private var documentService: DocumentServiceGenerated
    @EnvironmentObject private var documentStore: DocumentStore
    @Environment(WorkflowExecutionObserver.self) private var executionObserver

    @State private var artifacts: [Artifact] = []
    @State private var isLoading = false
    @State private var loadError: String?
    @State private var actionError: String?

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
                    kind: .pageContent(text: document.pageContent ?? ""),
                    onSave: { newContent in
                        await savePageContent(newContent)
                    }
                )
                // In pageContentOnly mode there's no outer ScrollView, so
                // the panel can safely claim all remaining inspector height.
                // Without this, the VStack wraps at the editor's sizeThatFits
                // and leaves dead space below (#1062).
                .frame(maxWidth: .infinity, maxHeight: mode == .pageContentOnly ? .infinity : nil)
            }

            // Generated artifacts — only when the mode wants them. Each one
            // is editable (RTF round-trips, auto-save) and deletable.
            if mode != .pageContentOnly {
                ForEach(sortedArtifacts) { artifact in
                    ArtifactPanel(
                        kind: .artifact(artifact),
                        // Start collapsed so the inspector reads as a list
                        // of headers; users expand the one they want.
                        defaultExpanded: false,
                        onDelete: { Task { await deleteArtifact(artifact) } },
                        onSave: { newContent in
                            await saveArtifact(artifact, content: newContent)
                        }
                    )
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
        if let pageContent = document.pageContent, !pageContent.isEmpty { count += 1 }
        return count
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
            document: document,
            content: content,
            documentService: documentService,
            documentStore: documentStore
        ).map { "Couldn't save: \($0)" }
    }
}

@MainActor
func persistPageContent(
    document: Document,
    content: String,
    documentService: DocumentServiceGenerated,
    documentStore: DocumentStore
) async -> String? {
    do {
        let updated = try await documentService.updateDocument(
            document.id,
            pageContent: content
        )
        documentStore.refreshLocalContent(updated)
        return nil
    } catch {
        return error.localizedDescription
    }
}
