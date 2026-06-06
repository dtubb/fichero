// swiftlint:disable file_length
import SwiftUI

enum CatalogueArtifactPreviews {
    static func items(from data: [String: AnyCodable]) -> [[String: Any]] {
        guard let rawItems = data["items"]?.value as? [Any] else { return [] }
        return rawItems.compactMap { item in
            if let dict = item as? [String: Any] {
                return dict
            }
            if let dict = item as? [String: AnyCodable] {
                return dict.mapValues(\.value)
            }
            return nil
        }
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

    /// When true the content editor expands to fill all available vertical
    /// space (top-aligned) rather than sizing to its intrinsic content height.
    /// Set only for the Page Content panel in the Content tab's no-ScrollView
    /// layout, so the editor runs full-height below the attribute strip with no
    /// vertical centring (#1286). Left false elsewhere to preserve the
    /// intrinsic-height sizing the ScrollView path relies on (#960/#1062).
    let fillsHeight: Bool

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
        fillsHeight: Bool = false,
        onDelete: (() -> Void)? = nil,
        onSave: ((String) async -> Void)? = nil
    ) {
        self.kind = kind
        self.defaultExpanded = defaultExpanded
        self.fillsHeight = fillsHeight
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

    /// Page Content is primary content and renders always-expanded with no
    /// collapse chrome; generated artifacts stay collapsable (#1245).
    private var isPageContent: Bool {
        if case .pageContent = kind { return true }
        return false
    }

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
        Group {
            if isPageContent {
                // Page Content is the document's PRIMARY content, not an
                // optional artifact — render it with NO disclosure chrome and
                // NO title row. The title is always "Page Content", so the
                // header is redundant; dropping it reclaims that space and lets
                // the editor start right below the attribute strip (#1286). The
                // content is top-aligned and fills the available height when the
                // panel owns the inspector pane (fillsHeight), so there's no
                // vertical centring / dead space (#1245, #1286).
                contentBody
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .frame(
                        maxWidth: .infinity,
                        maxHeight: fillsHeight ? .infinity : nil,
                        alignment: .top
                    )
            } else {
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
            }
        }
        // Sizing: AttributedTextEditor now reports its layoutManager-used
        // height via sizeThatFits, so an expanded panel matches its actual
        // content. We keep a small min so empty editors don't collapse to
        // a sliver (Daniel 2026-05-05: "the height was 0"); long artifacts
        // grow naturally and the outer ScrollView handles overflow (#960).
        // Collapsed panels have no frame and shrink to header height (~30 px).
        // Page Content is never collapsed, so it always gets the min.
        .frame(minHeight: (isPageContent || isExpanded) ? (isPageContent ? 60 : 120) : nil)
        // Clip so the editor's AppKit text view can't paint outside the panel's
        // SwiftUI frame onto the attribute strip above it (#1245).
        .clipped()
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
                // sizeThatFits (its layoutManager.usedRect). No maxHeight in the
                // ScrollView path: letting it claim .infinity there made every
                // expanded panel fill the viewport (#960). When fillsHeight is
                // set (Page Content in the no-ScrollView Content tab), the
                // editor DOES claim .infinity so it runs full-height (#1286).
                .frame(maxWidth: .infinity, maxHeight: fillsHeight ? .infinity : nil)
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
        ArtifactRichTextCodec.decode(content)
    }

    /// Encode an NSAttributedString back to a content string. Inline RTF
    /// source (not base64) so the artifact's `content` field stays human-
    /// readable when the artifact is plain text and round-trips losslessly
    /// when the user added formatting. See `ArtifactRichTextCodec` (#710).
    private func encodeArtifactContent(_ attr: NSAttributedString) -> String {
        ArtifactRichTextCodec.encode(attr)
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
                   let formattedJSON = try? JSONSerialization.data(
                       withJSONObject: jsonObject, options: [.prettyPrinted]
                   ) {
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
