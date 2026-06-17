import FicheroAPIClient
import SwiftUI

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
    @EnvironmentObject private var artifactService: ArtifactServiceGenerated
    @EnvironmentObject private var kgCurationService: KGCurationServiceGenerated
    @ObservedObject private var featureManager = FeatureManager.shared
    @ObservedObject private var claimFocusState = ClaimFocusState.shared
    /// Cross-view KG focus. When an entity is focused (a lozenge / WebKit-graph
    /// click), the inspector retargets to inspect that entity instead of the
    /// document (#1484). Clearing it returns to the document.
    @Environment(KGFocusState.self) private var kgFocusState

    /// The entity currently being inspected, loaded from kgFocusState.focusedEntityId.
    @State private var focusedEntity: Components.Schemas.KnowledgeEntity?
    @State private var isLoadingEntity = false

    var body: some View {
        Group {
            if kgFocusState.focusedEntityId != nil {
                entityInspection
            } else if let doc = document {
                documentDetail(doc)
            } else {
                emptyState
            }
        }
        .frame(minWidth: 220, maxWidth: .infinity, maxHeight: .infinity)
        .environmentObject(claimFocusState)
        .task(id: kgFocusState.focusedEntityId) {
            await loadFocusedEntity()
        }
        .onReceive(NotificationCenter.default.publisher(for: .ficheroOpenClaimSource)) { note in
            guard let info = note.userInfo else { return }
            if info["claimId"] is String || info["entityId"] is String {
                selectedTab = .knowledgeGraph
            }
        }
    }

    // MARK: - Entity Inspection (#1484)

    /// Inspector content when an entity is focused: a back affordance plus the
    /// shared EntityDigestContent (details, claims, provenance). Reuses the
    /// existing entity-digest view rather than a parallel one (iterate-not-replace).
    @ViewBuilder
    private var entityInspection: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Button {
                    kgFocusState.clear()
                } label: {
                    Label("Back to document", systemImage: "chevron.left")
                        .labelStyle(.titleAndIcon)
                }
                .buttonStyle(.plain)
                .help("Return to inspecting the document")
                Spacer()
            }
            .padding(.horizontal, 12)
            .frame(height: MiniToolbar<EmptyView>.standardHeight)
            .accessibilityIdentifier("inspectorEntityBackBar")

            Divider()

            if let entity = focusedEntity {
                EntityDigestContent(entity: entity, entityService: entityService)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if isLoadingEntity {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                Text("Entity not found")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }

    private func loadFocusedEntity() async {
        guard let entityId = kgFocusState.focusedEntityId, !entityId.isEmpty else {
            focusedEntity = nil
            return
        }
        // Avoid a reload + flash when the already-loaded entity is re-focused.
        if focusedEntity?.id == entityId { return }
        isLoadingEntity = true
        defer { isLoadingEntity = false }
        focusedEntity = try? await entityService.getEntity(entityId)
    }

    // MARK: - Document Detail

    private func documentDetail(_ doc: Document) -> some View {
        // Tab bar sits at the very top (matching every other pane header).
        // The attribute strip moved below the tabs and now lives *inside* the
        // Content tab only — it described the document, which is the Content
        // tab's concern, and it shouldn't crowd the Knowledge Graph /
        // Artifacts / Info tabs. (#1228)
        VStack(spacing: 0) {
            tabBar
            Divider()
            tabContent(for: doc)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(maxHeight: .infinity)
        .onChange(of: doc.id, initial: true) { _, _ in
            if !availableTabs(for: doc).contains(selectedTab) {
                selectedTab = .content
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
                    selectedTab = tab
                } label: {
                    Image(systemName: tab.icon)
                        .font(.system(size: 15, weight: .regular))
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .contentShape(Rectangle())
                }
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
        .frame(maxWidth: .infinity)
        // Single grouped capsule: subtle fill + hairline border, like Xcode's
        // inspector facet selector.
        .background(
            RoundedRectangle(cornerRadius: 7)
                .fill(Color(nsColor: .quaternaryLabelColor).opacity(0.5))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 7)
                .strokeBorder(Color(nsColor: .separatorColor), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 7))
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .frame(height: MiniToolbar<EmptyView>.standardHeight)
        // XCUITest hook for the inspector tab bar (#1230).
        .accessibilityIdentifier("inspectorTabBar")
    }

    // Tab content for the selected tab. One arm per inspector tab; complexity
    // scales with the (intentionally flat) tab list, not nested branching.
    // swiftlint:disable:next cyclomatic_complexity
    @ViewBuilder private func tabContent(for doc: Document) -> some View {
        switch selectedTab {
        case .content:
            contentTab(for: doc)
        case .outline:
            SourceOutlineView(documentId: doc.id)
        case .annotations:
            DocumentInspectorAnnotationsTab(document: doc)
        case .notes:
            DocumentNotesTab(document: doc)
        case .entities:
            entitiesTab(for: doc)
        case .knowledgeGraph:
            knowledgeGraphTab(for: doc)
        case .artifacts:
            artifactsTab(for: doc)
        case .citations:
            CitationsInspectorPane(document: doc)
        case .references:
            ReferencesInspectorPane(document: doc)
        case .edits:
            editsTab(for: doc)
        case .info:
            infoTab(for: doc)
        }
    }

    private func availableTabs(for doc: Document?) -> [InspectorTab] {
        guard let doc else { return InspectorTab.allCases }
        var tabs: [InspectorTab] = [
            .content, .annotations, .notes, .knowledgeGraph, .outline, .entities,
            .artifacts, .citations, .references
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
    }

    @ViewBuilder
    private func artifactsTab(for doc: Document) -> some View {
        // Track B (#2003): List + detachable detail, replacing the stacked
        // ArtifactPanels of DocumentInspectorContentV2(mode: .artifactsOnly).
        ArtifactsInspectorPane(document: doc)
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
}

private struct DocumentInspectorImageEditsTab: View {
    let document: Document

    @EnvironmentObject private var apiClient: APIClient
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
        .environmentObject(library.artifactService)
        .environmentObject(library.entityService)
        .environment(library.entityStore)
        .environment(library.claimStore)
        .environment(KGFocusState.shared)
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
        .environment(library.entityStore)
        .environment(library.claimStore)
        .environment(KGFocusState.shared)
        .frame(width: 280, height: 400)
}
