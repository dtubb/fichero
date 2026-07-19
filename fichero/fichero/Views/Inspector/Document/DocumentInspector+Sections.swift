import SwiftUI

extension DocumentInspector {
    // Tab content for the selected tab. One arm per inspector tab; complexity
    // scales with the (intentionally flat) tab list, not nested branching.
    @ViewBuilder func tabContent(for doc: Document, selectedTab: InspectorTab) -> some View {
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
    // Kept for switch exhaustiveness — `.info` is no longer a selectable tab (#3876,
    // folded into SourceSectionMode). Delegates to the one shared Info body so there
    // is no divergent copy.
    private func infoTab(for doc: Document) -> some View {
        SourceInfoView(document: doc)
    }
}

private struct DocumentInspectorImageEditsTab: View {
    let document: Document

    @Environment(APIClient.self) private var apiClient
    @Environment(StorageService.self) private var storageService
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
            // Evict the storage-display cache after each edit so the Preview
            // canvas re-fetches the edited bytes (#3593) — same hook the
            // Preview-hosted editor uses (ImageEditorView).
            model.onEditApplied = { [storageService] id in
                storageService.invalidateImageCache(for: id)
            }
        }
    }
}
