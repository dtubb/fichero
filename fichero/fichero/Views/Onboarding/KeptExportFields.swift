import FicheroAPIClient
import SwiftUI
import UniformTypeIdentifiers

/// Keep an export, an optional row on setup's Ready step (#5485, #5492;
/// `source.onboard.kept-exported`); no rows skips it. One row per export: the folder (Choose…),
/// the format, and one file per page or per document (page formats are per page only), with ×
/// to remove. Rows are kept on Start (`KeptExportStore.keepDrafts`); exports already kept are
/// listed above them.
struct KeptExportFields: View {
    @Bindable var store: KeptExportStore

    /// Said once, where the export is set up (spec: the person is told so once).
    static let oneWaySentence = "Fichero writes these folders and never reads them back: "
        + "a file you change there by hand is replaced at the next write."

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(Self.oneWaySentence)
                .font(.callout)
                .foregroundStyle(.secondary)
            ForEach(store.exports, id: \.id) { export in
                KeptExportRow(export: export) {
                    Task { await store.remove(export.id) }
                }
            }
            ForEach($store.drafts) { $draft in
                KeptExportDraftRow(draft: $draft) { store.removeDraft(draft.id) }
            }
            Button("Add Export") { store.addDraft() }
            if let error = store.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
        }
        .task { await store.load() }
    }
}

/// A row not kept yet: Choose… for the folder, the format, per page or per document, and ×.
struct KeptExportDraftRow: View {
    @Binding var draft: KeptExportStore.Draft
    let remove: () -> Void
    @State private var choosingFolder = false

    var body: some View {
        HStack(spacing: 8) {
            Button("Choose…") { choosingFolder = true }
            Text(draft.folder?.path ?? "No folder chosen")
                .font(.callout)
                .foregroundStyle(draft.folder == nil ? .secondary : .primary)
                .lineLimit(1)
                .truncationMode(.middle)
                .frame(maxWidth: .infinity, alignment: .leading)
            Picker("Format", selection: $draft.format) {
                ForEach(KeptExportStore.formats, id: \.self) { format in
                    Text(KeptExportStore.title(of: format)).tag(format)
                }
            }
            .labelsHidden()
            .fixedSize()
            Picker("Files", selection: $draft.per) {
                Text("Per page").tag(KeptExportStore.Per.page)
                Text("Per document").tag(KeptExportStore.Per.document)
                    .selectionDisabled(!KeptExportStore.allowsPerDocument(draft.format))
            }
            .labelsHidden()
            .fixedSize()
            Button(action: remove) { Image(systemName: "xmark") }
                .buttonStyle(.borderless)
                .accessibilityLabel("Remove this export")
        }
        // The system folder panel; the folder is granted to the engine when the row is kept.
        .fileImporter(isPresented: $choosingFolder, allowedContentTypes: [.folder]) { result in
            if case .success(let url) = result { draft.folder = url }
        }
    }

}

/// A kept export: its folder, format and per, and × to stop keeping it (its files stay).
struct KeptExportRow: View {
    let export: Components.Schemas.KeptExport
    let remove: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "folder").foregroundStyle(.secondary).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 1) {
                Text(export.folder).lineLimit(1).truncationMode(.middle)
                Text("\(KeptExportStore.title(of: export.format)), \(KeptExportStore.title(of: export.per).lowercased())")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Button(action: remove) { Image(systemName: "xmark") }
                .buttonStyle(.borderless)
                .help("Stop keeping this export; the files it wrote stay in the folder")
                .accessibilityLabel("Stop keeping this export")
        }
    }
}

#Preview("Kept exported") {
    let store = KeptExportStore(client: FicheroClient(libraryPath: nil))
    store.drafts = [
        .init(folder: URL(fileURLWithPath: "/Users/historian/Exports/Word"), format: .word, per: .document),
        .init(folder: nil, format: .alto, per: .page)
    ]
    return KeptExportFields(store: store)
        .padding()
        .frame(width: 560, height: 320)
}
