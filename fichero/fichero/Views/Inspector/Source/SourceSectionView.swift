import SwiftUI

/// The Source section body: ONE segmented toggle over the page **Content**, the
/// document **Info** (metadata), and the native document **Outline** (#3440/#3876).
/// This is the single Source picker — the former separate Content/Info facet picker
/// above it is gone; Info is the middle segment here.
struct SourceSectionView: View {
    let document: Document

    @SceneStorage("inspector.source.mode") private var mode: SourceSectionMode = .content

    var body: some View {
        VStack(spacing: 0) {
            Picker("Source view", selection: $mode) {
                Text("Content").tag(SourceSectionMode.content)
                Text("Info").tag(SourceSectionMode.info)
                Text("Outline").tag(SourceSectionMode.outline)
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
                DocumentInspectorInfoTab(document: document)
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
}
