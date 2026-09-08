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
            switch Self.inspectorArm(
                hasDocument: document != nil,
                focusedEntityId: kgFocusState.focusedEntityId
            ) {
            case .document:
                if let doc = document { documentDetail(doc) }
            case .entity:
                // No document is selected but an entity is focused (Entities
                // collection / Knowledge Graph mode). Show that entity rather
                // than "No selection". (spec: kg-entity-inspector, F2)
                if let entityId = kgFocusState.focusedEntityId {
                    entityArm(entityId)
                }
            case .empty:
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
        // While the image editor is open the inspector shows ONLY the edit
        // steps (Daniel, 2026-09-01). `.edits` IS edit mode — `EditorView`
        // derives `isEditing` from this same scene value — so the section bar
        // and the facet picker would be offering to walk away from a canvas
        // that is mid-edit, with the chain the only thing that applies. The
        // way out is the editor's own Done button, which returns to Content.
        let isEditingImage = effectiveTab == .edits
        return VStack(spacing: 0) {
            if !isEditingImage {
                sectionBar
                facetPicker(for: doc, selectedTab: effectiveTab)
            }
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

    /// The entity arm, with the library's claim store injected so the digest's
    /// statements load through the observable data layer (spec: F3). Store
    /// resolved defensively — if no library is open the digest falls back to a
    /// direct fetch rather than trapping.
    @ViewBuilder
    private func entityArm(_ entityId: String) -> some View {
        let arm = EntityInspectorArm(entityId: entityId, entityService: entityService)
        if let claimStore = LibraryManager.shared.globalLibrary?.claimStore {
            arm.environment(claimStore)
        } else {
            arm
        }
    }

    // MARK: - Which arm

    /// Which inspector arm to show. A shown document wins (an entity focused
    /// alongside it routes to that document's Entities tab, not away from it);
    /// with no document but a focused entity, the entity arm; otherwise the empty
    /// state. Pure so the rule is testable without a rendered inspector.
    /// (spec: kg-entity-inspector, kg.entity.select.inspector-shows-entity — F2)
    enum InspectorArm: Equatable { case document, entity, empty }

    static func inspectorArm(hasDocument: Bool, focusedEntityId: String?) -> InspectorArm {
        if hasDocument { return .document }
        return focusedEntityId != nil ? .entity : .empty
    }

    /// The inspector's entity arm: the focused entity resolved to its record and
    /// shown via `EntityDigestContent` — the same entity surface the Entities tab
    /// renders inside a document, so statements + source click-through come for
    /// free. Re-keyed on `entityId` so a focus change re-fetches and the pane
    /// belongs to the new entity. (spec: kg-entity-inspector, F2 / rekey.on-focus-change)
    private struct EntityInspectorArm: View {
        let entityId: String
        let entityService: EntityService
        @State private var entity: Components.Schemas.KnowledgeEntity?
        @State private var loadFailed = false

        var body: some View {
            Group {
                if let entity {
                    EntityDigestContent(entity: entity, entityService: entityService)
                } else if loadFailed {
                    ContentUnavailableView(
                        "Entity Unavailable",
                        systemImage: "person.crop.circle.badge.exclamationmark",
                        description: Text("Could not load this entity.")
                    )
                } else {
                    ProgressView()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .task(id: entityId) {
                loadFailed = false
                entity = nil
                do {
                    entity = try await entityService.getEntity(entityId)
                } catch {
                    loadFailed = true
                }
            }
        }
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
