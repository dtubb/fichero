import FicheroAPIClient
import SwiftUI

/// Shared Tahoe glass-strip background for the inspector chrome strips (#3061 /
/// #2550): Liquid Glass on macOS/iOS, `.regularMaterial` on visionOS — mirrors
/// `MiniToolbar.body`. Applied as a TRAILING modifier so each strip's row content
/// is untouched (segment-selection styling, heights, and XCUITest a11y hooks stay
/// exactly as-is — this slice is visual-only).
private struct InspectorGlassStrip: ViewModifier {
    func body(content: Content) -> some View {
        #if os(visionOS)
        content
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
        #else
        GlassEffectContainer {
            content
                .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 8))
        }
        #endif
    }
}

extension View {
    /// Apply the inspector chrome-strip Tahoe glass treatment (#3061).
    func inspectorGlassStrip() -> some View {
        modifier(InspectorGlassStrip())
    }

    /// Make custom list rows behave like full-width native hit targets.
    func inspectorListRowTarget() -> some View {
        frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
    }
}

/// Shared bottom mini-toolbar shell for list-style inspector panes (#3414).
/// Keeps the glass treatment, fixed height, and left-status / right-actions
/// rhythm consistent while letting each pane supply its own native controls.
struct InspectorBottomMiniToolbar<Actions: View>: View {
    let statusText: String
    let actions: Actions

    init(statusText: String, @ViewBuilder actions: () -> Actions) {
        self.statusText = statusText
        self.actions = actions()
    }

    var body: some View {
        MiniToolbar {
            Text(statusText)
                .font(.caption)
                .foregroundStyle(.secondary)

            Spacer()

            actions
        } trailing: {
            EmptyView()
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

    @SceneStorage("inspectorSelectedTab") var selectedTab: InspectorTab = .content
    @Environment(DocumentStore.self) var documentStore
    @Environment(EntityService.self) var entityService
    @Environment(ArtifactService.self) var artifactService
    @Environment(KGCurationService.self) var kgCurationService
    @Environment(ClaimFocusState.self) var claimFocusState
    @State private var focusedArtifact = FocusedArtifact.shared
    /// Cross-view KG focus. Entity selection now routes into the Entities tab's
    /// lower detail pane instead of replacing the whole inspector. (#3400)
    @Environment(KGFocusState.self) var kgFocusState

    var body: some View {
        Group {
            if let doc = document {
                documentDetail(doc)
            } else {
                emptyState
            }
        }
        .frame(minWidth: 220, maxWidth: .infinity, maxHeight: .infinity)
        .environment(claimFocusState)
        .onChange(of: claimFocusState.selectedClaimId) { _, claimId in
            if claimId != nil {
                selectedTab = .knowledgeGraph
            }
        }
        .onChange(of: kgFocusState.focusedEntityId) { _, entityId in
            if entityId != nil {
                selectedTab = .entities
            }
        }
        .onChange(of: focusedArtifact.id) { _, _ in
            routeArtifactFocus()
        }
        .onChange(of: focusedArtifact.documentId) { _, _ in
            routeArtifactFocus()
        }
    }

    // MARK: - Document Detail

    private func documentDetail(_ doc: Document) -> some View {
        let effectiveTab = Self.clampedSelectedTab(selectedTab, for: doc)
        // Tab bar sits at the very top (matching every other pane header).
        // The attribute strip moved below the tabs and now lives *inside* the
        // Content tab only — it described the document, which is the Content
        // tab's concern, and it shouldn't crowd the Knowledge Graph /
        // Citations / Info tabs. (#1228)
        return VStack(spacing: 0) {
            sectionBar
            facetPicker(for: doc, selectedTab: effectiveTab)
            Divider()
            tabContent(for: doc, selectedTab: effectiveTab)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(maxHeight: .infinity)
        .onChange(of: doc.id, initial: true) { _, _ in
            let clamped = Self.clampedSelectedTab(selectedTab, for: doc)
            if selectedTab != clamped {
                selectedTab = clamped
            }
        }
    }

    // MARK: - Empty State

    private var emptyState: some View {
        Text("No selection")
            .font(.callout)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Helpers

    private func copyToClipboard(_ text: String) {
        PlatformPasteboard.writeString(text)
    }

    private func routeArtifactFocus() {
        guard let doc = document,
              focusedArtifact.id != nil,
              focusedArtifact.documentId == doc.id else { return }
        selectedTab = .artifacts
    }
}

// MARK: - Preview

#Preview("Empty") {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    DocumentInspector(document: nil)
        .environment(library.artifactService)
        .environment(library.entityService)
        .environment(library.documentStore)
        .environment(library.entityStore)
        .environment(library.claimStore)
        .environment(KGFocusState.shared)
        .environment(ClaimFocusState.shared)
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
        .environment(library.artifactService)
        .environment(library.entityService)
        .environment(library.documentStore)
        .environment(library.entityStore)
        .environment(library.claimStore)
        .environment(KGFocusState.shared)
        .environment(ClaimFocusState.shared)
        .frame(width: 280, height: 400)
}
