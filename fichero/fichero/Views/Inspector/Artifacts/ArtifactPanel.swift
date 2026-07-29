import SwiftUI

/// One read-only panel showing a single artifact (transcription, catalogue,
/// summary, etc.) in the V2 inspector. Each artifact gets its own panel —
/// new artifacts append rather than replace, so workflow re-runs never
/// overwrite what's already on screen.
///
/// Phase 1: read-only display. Phase 2 will add per-artifact actions
/// (copy, regenerate, hide). See docs/contributor/architecture/fichero/inspector_redesign.md.
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
    /// persisting it, returning nil on success or a user-facing error
    /// message on failure (#4285: a failed save must keep the draft dirty
    /// and retry — never silently discard). nil hides the edit affordance
    /// (read-only panel).
    var onSave: ((String) async -> String?)?

    /// The owning document store. Passed only by the Content-tab inspector so
    /// the focused Page Content editor can register its flush with the store —
    /// an external navigation (image prev/next, inspector tab switch) calls
    /// `flushActivePageEdit()` before changing the focused document so the
    /// in-flight edit isn't lost when the editor reseeds (#2476). nil for
    /// read-only / detached hosts (no flush needed).
    var documentStore: DocumentStore?

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
        documentStore: DocumentStore? = nil,
        onDelete: (() -> Void)? = nil,
        onSave: ((String) async -> String?)? = nil
    ) {
        self.kind = kind
        self.defaultExpanded = defaultExpanded
        self.fillsHeight = fillsHeight
        self.documentStore = documentStore
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
    @State var confirmingDelete: Bool = false
    /// The editor's working copy, in SwiftUI-native `AttributedString` (#2453).
    @State var draftText = AttributedString("")
    @State var saveError: String?
    @State var autoSaveTask: Task<Void, Never>?
    /// Serial + coalescing save runner. A flush during an in-flight save is
    /// coalesced (not dropped), so blur/close truly persists the latest text
    /// (#2536). Extracted from inline @State so the race is unit-testable.
    @State var saver = CoalescingSaveRunner()
    /// The seeded/saved-content watermarks — reseed guard (#2478) plus the
    /// failed-save dirtiness transaction (#4285). Pure state machine so the
    /// paste → failed save → still dirty → retry cycle is unit-testable
    /// (ArtifactSaveWatermarksTests).
    @State var watermarks = ArtifactSaveWatermarks()
    /// Consecutive failed-save auto-retries since the last success or user
    /// edit (#4285). Bounded so a persistently failing backend doesn't loop
    /// forever; a new keystroke / blur / flush always retries regardless.
    @State var saveRetryAttempts: Int = 0
    @FocusState var isEditorFocused: Bool

    /// Page Content is primary content and renders always-expanded with no
    /// collapse chrome; generated artifacts stay collapsable (#1245).
    var isPageContent: Bool {
        if case .pageContent = kind { return true }
        return false
    }

    var body: some View {
        // User feedback 2026-04-27: drop the rounded-rect box outline (no
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
        // a sliver (user feedback 2026-05-05: "the height was 0"); long artifacts
        // grow naturally and the outer ScrollView handles overflow (#960).
        // Collapsed panels have no frame and shrink to header height (~30 px).
        // Page Content is never collapsed, so it always gets the min.
        .frame(minHeight: (isPageContent || isExpanded) ? (isPageContent ? 60 : 120) : nil)
        // Clip so the editor's AppKit text view can't paint outside the panel's
        // SwiftUI frame onto the attribute strip above it (#1245).
        .clipped()
        .onDisappear {
            // Stop offering this editor's flush once it leaves the hierarchy
            // (tab switched away, document deselected) so a later
            // flushActivePageEdit() doesn't call into a gone editor (#2476).
            if isPageContent { documentStore?.unregisterActivePageEdit() }
        }
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
}
