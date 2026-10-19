import SwiftUI

/// The Source section body: ONE segmented toggle over the page **Content**, the
/// document **Info** (metadata), and the native document **Outline** (#3440/#3876).
/// This is the single Source picker — the former separate Content/Info facet picker
/// above it is gone; Info is the middle segment here.
struct SourceSectionView: View {
    let document: Document

    @SceneStorage("inspector.source.mode") private var mode: SourceSectionMode = .content
    @Environment(WindowState.self) private var windowState: WindowState?
    @Environment(SegmentService.self) private var segmentService: SegmentService?
    /// A selection this Inspector's own Order list wrote, and what it was showing then (#4981, #5424).
    @State private var held: InspectorPath.Hold?

    var body: some View {
        // A selection on this page is inspected at its level (ruled 2026-09-27); with none, the page.
        // One the Inspector's own Order list wrote leaves it where it was (`InspectorPath.Hold`).
        let selected = InspectorPath.Hold.inspected(selectedSegmentIds, held: held)
        Group {
            if selected.isEmpty {
                documentBody
            } else {
                SegmentInspectorView(
                    documentId: document.id, selectedIds: selected,
                    onOrderSelected: { held = .init(wrote: $0, shown: selected) }
                )
            }
        }
        // Any other selection is followed, and ends the hold.
        .onChange(of: selectedSegmentIds) { _, now in
            if now != held?.wrote { held = nil }
        }
    }

    /// The focused Source-view pane's selection on THIS page, as segment ids.
    private var selectedSegmentIds: [String] {
        guard let selection = windowState?.focusedRegionSelection, let segmentService else { return [] }
        return InspectorPath.selectedSegmentIds(
            selection: selection, documentId: document.id, store: SegmentStore.shared(for: segmentService)
        )
    }

    private var documentBody: some View {
        VStack(spacing: 0) {
            // A page whose original moved says so first, with Locate Originals… (#5672).
            if let originals = windowState?.library?.originalsStore {
                MissingOriginalNote(store: originals, documentId: document.id)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(8)
            }
            Picker("Source view", selection: $mode) {
                Text("Content").tag(SourceSectionMode.content)
                Text("Info").tag(SourceSectionMode.info)
                Text("Outline").tag(SourceSectionMode.outline)
                // The page's reading order, rearrangeable (ruled 2026-09-27, Q5).
                Text("Order").tag(SourceSectionMode.order)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            Divider()

            switch mode {
            case .content:
                DisplayAttributesStrip(document: document)
                Divider()
                DocumentInspectorContentV2(document: document, mode: .pageContentOnly)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .info:
                SourceInfoView(document: document)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .outline:
                SourceOutlineView(documentId: document.id)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .order:
                // Lines grouped under their region, each with its region's tone (#5505), as in the Segments pane.
                ReadingOrderList(documentId: document.id, onSelected: { held = .init(wrote: $0, shown: []) }, nests: true)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }
}

/// The document's Info + Metadata body — the Source section's Info mode (#3876).
/// One home for the info content, whether reached from the Source segmented picker
/// or the folded (exhaustiveness-only) Info tab.
struct SourceInfoView: View {
    let document: Document

    /// The Info tab's parts, in order; each is its own grouped section (#5840 part 2), the one a page needs shown.
    enum Part: CaseIterable {
        case making, folderSync, iiif, foundDocuments, readingAgreement, info, whatHasBeenRun, metadata
    }

    private func isShown(_ part: Part) -> Bool {
        part != .metadata || !document.metadata.isEmpty || document.path != nil
    }

    var body: some View {
        // Native grouped sections, as System Settings draws them (#5840): the Form scrolls itself, so no outer
        // ScrollView (a List collapses inside one, #2107).
        Form {
            ForEach(Part.allCases.filter(isShown), id: \.self) { part in
                Section { content(part) }
            }
        }
        .formStyle(.grouped)
    }

    @ViewBuilder
    private func content(_ part: Part) -> some View {
        switch part {
        // How the page's passes were made (#5149): "Imported from X · PAGE XML · 22 lines".
        case .making: InspectorMakingSection(documentId: document.id)
        // A folder the project is tied to shows it is synced, its intake and Untie (#5480).
        case .folderSync: FolderSyncInspectorSection(document: document)
        // A folder bound to a IIIF source: where from, how many, Refresh (#5671).
        case .iiif: IIIFFolderInspectorSection(document: document)
        // A folder: the documents Find the Documents proposed, waiting for a person (#5550).
        case .foundDocuments: FoundDocumentsInspectorSection(document: document)
        // A page read by two readers or more: how far they agree, the page and each line (#5665).
        case .readingAgreement: ReadingAgreementInspectorSection(document: document)
        case .info: DocumentInspectorInfoTab(document: document)
        // Every step that has touched this document, newest first (#5434).
        case .whatHasBeenRun: WhatHasBeenRunInspectorSection(document: document)
        case .metadata: DocumentInspectorMetadataTab(document: document)
        }
    }
}

enum SourceSectionMode: String, CaseIterable {
    case content
    case info
    case outline
    case order
}
