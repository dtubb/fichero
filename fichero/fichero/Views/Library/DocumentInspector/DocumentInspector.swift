import FicheroAPIClient
import SwiftUI

// swiftlint:disable file_length

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

    @SceneStorage("inspectorSelectedTab") private var selectedTab: InspectorTab = .content
    @Environment(DocumentStore.self) private var documentStore
    @Environment(EntityServiceGenerated.self) private var entityService
    @Environment(ArtifactServiceGenerated.self) private var artifactService
    @Environment(KGCurationServiceGenerated.self) private var kgCurationService
    @EnvironmentObject private var featureManager: FeatureManager
    @Environment(ClaimFocusState.self) private var claimFocusState
    @State private var focusedArtifact = FocusedArtifact.shared
    /// Cross-view KG focus. Entity selection now routes into the Entities tab's
    /// lower detail pane instead of replacing the whole inspector. (#3400)
    @Environment(KGFocusState.self) private var kgFocusState

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

    /// The four-section top icon row — the approved IA switcher (#3434, top icon
    /// row chosen 2026-07-11): Source / Artifacts / Knowledge / Notes. One
    /// grouped capsule with a selected-segment fill, reading as ONE control.
    /// Stays icon-only buttons (not a `.segmented` Picker) so per-section `.help`
    /// tooltips and `.accessibilityIdentifier` XCUITest hooks attach per segment.
    /// Multi-facet sections reveal a sub-picker below (see ``facetPicker``).
    /// The shared `SurfaceTabBar` (#3530) — the same icon-button row the Reader
    /// uses — over the document's available sections. Per-section help + XCUITest
    /// hooks (`inspectorSection-Source`, …) and the container `inspectorSectionBar`
    /// hook are preserved via `InspectorSection: SurfaceTab` + the container id.
    private var sectionBar: some View {
        SurfaceTabBar(
            tabs: availableSections(for: document),
            selection: sectionSelectionBinding,
            accessibilityID: "inspectorSectionBar"
        )
    }

    /// Active section ↔ selected facet: reads the section the current tab belongs
    /// to; selecting a section switches to its first facet (unchanged behaviour).
    private var sectionSelectionBinding: Binding<InspectorSection> {
        Binding(
            get: { Self.section(for: selectedTab, in: document) },
            set: { selectSection($0) }
        )
    }

    /// Sub-facet selector shown only when the active section absorbs more than
    /// one legacy facet (Knowledge = entities/graph/citations; Notes =
    /// notes/annotations/interpretation). A native segmented picker over the
    /// section's facets — each facet body is reused unchanged (iterate, not
    /// replace). Single-facet sections (Artifacts) show nothing here.
    @ViewBuilder
    private func facetPicker(for doc: Document, selectedTab tab: InspectorTab) -> some View {
        let section = Self.section(for: tab, in: doc)
        let facets = facets(in: section, for: doc)
        if facets.count > 1 {
            Picker("Facet", selection: facetSelection) {
                ForEach(facets) { facet in
                    Text(facet.rawValue).tag(facet)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .padding(.horizontal, 8)
            .padding(.bottom, 6)
            .accessibilityIdentifier("inspectorFacetPicker")
        }
    }

    private var facetSelection: Binding<InspectorTab> {
        Binding(
            get: { Self.clampedSelectedTab(selectedTab, for: document) },
            set: { selectTab($0) }
        )
    }

    /// The section for a facet, clamped to something valid for this document.
    static func section(for tab: InspectorTab, in doc: Document?) -> InspectorSection {
        InspectorSection.section(for: clampedSelectedTab(tab, for: doc)) ?? .source
    }

    /// The legacy facets of `section` that are available for this document.
    private func facets(in section: InspectorSection, for doc: Document?) -> [InspectorTab] {
        let available = Set(Self.availableTabs(for: doc))
        return section.facets.filter { available.contains($0) }
    }

    private func availableSections(for doc: Document?) -> [InspectorSection] {
        InspectorSection.allCases.filter { !facets(in: $0, for: doc).isEmpty }
    }

    /// Switch top section: jump to its first facet unless already inside it.
    private func selectSection(_ section: InspectorSection) {
        guard Self.section(for: selectedTab, in: document) != section else { return }
        if let first = facets(in: section, for: document).first {
            selectTab(first)
        }
    }

    /// Switch the inspector tab, first persisting any in-flight Page Content
    /// edit so it isn't lost when the Content tab's editor disappears (#2476).
    /// Only defers when an editor is registered, so tab switching stays snappy.
    private func selectTab(_ tab: InspectorTab) {
        if documentStore.activePageEditFlush != nil {
            Task { @MainActor in
                await documentStore.flushActivePageEdit()
                selectedTab = tab
            }
        } else {
            selectedTab = tab
        }
    }

    // Tab content for the selected tab. One arm per inspector tab; complexity
    // scales with the (intentionally flat) tab list, not nested branching.
    @ViewBuilder private func tabContent(for doc: Document, selectedTab: InspectorTab) -> some View {
        switch selectedTab {
        case .content:
            contentTab(for: doc)
        case .artifacts:
            ArtifactsInspectorPane(document: doc)
        case .annotations:
            DocumentInspectorAnnotationsTab(document: doc)
        case .notes:
            DocumentNotesTab(document: doc)
        case .interpretations:
            DocumentInterpretationsTab(document: doc)
        case .entities:
            entitiesTab(for: doc)
        case .knowledgeGraph:
            knowledgeGraphTab(for: doc)
        case .citations:
            CitationsInspectorPane(document: doc)
        case .edits:
            editsTab(for: doc)
        case .info:
            infoTab(for: doc)
        }
    }

    static func clampedSelectedTab(_ selectedTab: InspectorTab, for doc: Document?) -> InspectorTab {
        let tabs = availableTabs(for: doc)
        return tabs.contains(selectedTab) ? selectedTab : .content
    }

    private static func availableTabs(for doc: Document?) -> [InspectorTab] {
        guard let doc else { return InspectorTab.allCases }
        // Image Edits left the inspector for the dedicated editor / Reader canvas
        // (#3434) — it is intentionally not a facet here.
        var tabs: [InspectorTab] = [
            .content, .artifacts, .annotations, .notes, .interpretations, .knowledgeGraph,
            .entities, .citations
        ]
        tabs.append(.info)
        return tabs
    }

    @ViewBuilder
    private func contentTab(for doc: Document) -> some View {
        // Source section = a Content / Outline mode toggle (#3440). The native
        // document Outline is a hierarchy mode within Source, not a new tab.
        SourceSectionView(document: doc)
    }

    @ViewBuilder
    private func entitiesTab(for doc: Document) -> some View {
        DocumentInspectorEntitiesTab(
            document: doc,
            documentId: doc.id,
            selectedEntityId: kgFocusState.focusedEntityId,
            onEntitySelect: { entityId in
                kgFocusState.focusEntity(entityId: entityId)
            }
        )
    }

    @ViewBuilder
    private func knowledgeGraphTab(for doc: Document) -> some View {
        // No outer ScrollView — KnowledgeGraphInspectorSection owns its own
        // scroll + pinned bottom mini-toolbar (#3461).
        KnowledgeGraphInspectorSection(
            documentId: doc.id,
            documentScope: doc.docType == .page ? .page : .folder,
            entityService: entityService,
            artifactService: artifactService,
            kgCurationService: kgCurationService,
            onNavigateToSource: onNavigateToSource,
            onClaimSelect: { claimId, claimText, sourceDocId, pageLabel, charStart, charEnd in
                // Direct observable call — no NotificationCenter round-trip
                // (#3034). Passes the full payload the old .claimSelectedInInspector
                // bus carried but the ContentView handler dropped (it forwarded
                // only claimId), so the other panes now get text/source/range too.
                claimFocusState.selectClaim(
                    claimId: claimId,
                    claimText: claimText,
                    sourceDocumentId: sourceDocId,
                    pageLabel: pageLabel,
                    charStart: charStart,
                    charEnd: charEnd
                )
            }
        )
    }

    @ViewBuilder
    private func editsTab(for doc: Document) -> some View {
        if doc.fileType == .image || doc.fileType == .pdf || doc.docType == .page {
            DocumentInspectorImageEditsTab(document: doc)
        } else {
            Text("Edits are available for images and PDF pages.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
                .padding()
        }
    }

    @ViewBuilder
    private func infoTab(for doc: Document) -> some View {
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

private struct DocumentInspectorImageEditsTab: View {
    let document: Document

    @Environment(APIClient.self) private var apiClient
    @State private var model = ImageEditorModel()

    var body: some View {
        VStack(spacing: 0) {
            if model.isBusy {
                ProgressView()
                    .controlSize(.small)
                    .padding(.top, 10)
            }

            ImageEditChainPanel(
                chain: model.chain,
                isBusy: model.isBusy,
                selectedStepIndex: Binding(
                    get: { model.selectedStepIndex },
                    set: { model.selectedStepIndex = $0 }
                ),
                onRemove: { index in Task { await model.removeOperation(at: index) } },
                onReset: { Task { await model.resetAll() } },
                onRotate: { angle in Task { await model.rotate(by: angle) } },
                onStraighten: { Task { await model.straighten() } },
                onEnhance: { brightness, contrast, sharpen, auto in
                    Task { await model.enhance(brightness: brightness, contrast: contrast, sharpen: sharpen, autoLevels: auto) }
                },
                onCrop: { left, top, width, height in
                    Task { await model.crop(left: left, top: top, width: width, height: height) }
                },
                onRemoveBackground: { Task { await model.removeBackground() } },
                onFuzzyClean: { Task { await model.fuzzyClean() } },
                onSegment: { Task { await model.segment() } }
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .task(id: document.id) {
            await model.configure(apiClient: apiClient, documentId: document.id)
        }
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

// swiftlint:enable file_length
