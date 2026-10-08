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
                ReadingOrderList(documentId: document.id, onSelected: { held = .init(wrote: $0, shown: []) })
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

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // How the page's passes were made (#5149): "Imported from X · PAGE XML · 22 lines".
                InspectorMakingSection(documentId: document.id)
                // A folder the project is tied to shows it is synced, its intake and Untie (#5480).
                FolderSyncInspectorSection(document: document)
                DocumentInspectorInfoTab(document: document)
                // Every step that has touched this document, newest first (#5434).
                WhatHasBeenRunInspectorSection(document: document)
                if !document.metadata.isEmpty || document.path != nil {
                    DocumentInspectorMetadataTab(document: document)
                }
                Spacer()
            }
            .padding()
        }
    }
}

enum SourceSectionMode: String, CaseIterable {
    case content
    case info
    case outline
    case order
}
