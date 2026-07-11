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
            tabBar
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

    /// Xcode-style icon-only facet selector, grouped into a single segmented
    /// control: one rounded capsule with hairline dividers between segments and
    /// a selected-segment fill, so the row reads as ONE control rather than a
    /// loose row of N buttons (#1228). Stays icon-only buttons (not a native
    /// `.segmented` Picker) so the per-tab `.help` tooltips and `.accessibility
    /// Identifier` XCUITest hooks (#1230) attach to individual segments — a
    /// `.segmented` Picker swallows those per-segment modifiers.
    @ViewBuilder
    private var tabBar: some View {
        let tabs = availableTabs(for: document)
        let selectedTabTitle = Self.clampedSelectedTab(selectedTab, for: document).rawValue
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 0) {
                ForEach(Array(tabs.enumerated()), id: \.element) { index, tab in
                    if index > 0 {
                        // Hairline divider between segments — hidden adjacent to the
                        // selected segment so its fill reads as one continuous pill.
                        Divider()
                            .frame(height: 14)
                            .opacity(selectedTab == tab || selectedTab == tabs[index - 1] ? 0 : 1)
                    }
                    Button {
                        selectTab(tab)
                    } label: {
                        Label(tab.rawValue, systemImage: tab.icon)
                            .labelStyle(.iconOnly)
                            .font(.body)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                            .contentShape(Rectangle())
                    }
                    .accessibilityLabel(tab.rawValue)
                    .buttonStyle(.plain)
                    .background(
                        RoundedRectangle(cornerRadius: 5)
                            .fill(selectedTab == tab
                                    ? Color.accentColor.opacity(0.18)
                                    : Color.clear)
                            .padding(2)
                    )
                    .foregroundStyle(selectedTab == tab ? Color.accentColor : Color.secondary)
                    .help(tab.helpText)
                    // Stable per-tab XCUITest hook, e.g. "inspectorTab-Content" (#1230).
                    .accessibilityIdentifier("inspectorTab-\(tab.rawValue)")
                }
            }
            Text(selectedTabTitle)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .padding(.horizontal, 6)
        }
        .frame(maxWidth: .infinity)
        // Grouped facet capsule now on the shared Tahoe glass treatment (#3061 /
        // #2550), replacing the hand-rolled quaternary fill + hairline border, so
        // the strip matches SidebarModeBar / the pane mini-toolbars. The
        // per-segment selection fill above is unchanged.
        .inspectorGlassStrip()
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .frame(height: MiniToolbar<EmptyView, EmptyView>.standardHeight)
        // XCUITest hook for the inspector tab bar (#1230).
        .accessibilityIdentifier("inspectorTabBar")
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

    private func availableTabs(for doc: Document?) -> [InspectorTab] {
        Self.availableTabs(for: doc)
    }

    static func clampedSelectedTab(_ selectedTab: InspectorTab, for doc: Document?) -> InspectorTab {
        let tabs = availableTabs(for: doc)
        return tabs.contains(selectedTab) ? selectedTab : .content
    }

    private static func availableTabs(for doc: Document?) -> [InspectorTab] {
        guard let doc else { return InspectorTab.allCases }
        var tabs: [InspectorTab] = [
            .content, .artifacts, .annotations, .notes, .interpretations, .knowledgeGraph,
            .entities, .citations
        ]
        if doc.fileType == .image || doc.fileType == .pdf || doc.docType == .page {
            tabs.append(.edits)
        }
        tabs.append(.info)
        return tabs
    }

    @ViewBuilder
    private func contentTab(for doc: Document) -> some View {
        VStack(spacing: 0) {
            DisplayAttributesStrip(document: doc)
            Divider()
            DocumentInspectorContentV2(document: doc, mode: .pageContentOnly)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
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
        ScrollView {
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
            .padding()
        }
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
