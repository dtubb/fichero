import FicheroAPIClient
import SwiftUI

/// The project Inspector's kept exports (#5485, `source.onboard.kept-exported`): each folder the
/// project keeps an export in, its format and per, when it was last written, with Write Now and
/// Remove. Setting one up is setup's Kept exported screen (Set Up… reaches it).
struct KeptExportsInspectorSection: View {
    let store: KeptExportStore
    /// The export whose Choose Folder… panel is up.
    @State private var choosingFolderFor: String?

    var body: some View {
        Section("Kept Exported") {
            if store.exports.isEmpty {
                Text(store.hasLoaded ? "No exports are kept." : "Reading…").foregroundStyle(.secondary)
            }
            ForEach(store.exports, id: \.id) { export in
                VStack(alignment: .leading, spacing: 4) {
                    KeptExportRow(export: export) { Task { await store.remove(export.id) } }
                    HStack {
                        Text(Self.status(of: export, writing: store.writing.contains(export.id)))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Button("Write Now") { Task { await store.writeNow(export.id) } }
                            .controlSize(.small)
                            .help("Write this export again now, in the background; Activity shows it")
                    }
                    // Decision 28 (#6588): the automatic rewrite's switch, and the folder chosen again.
                    HStack {
                        Toggle("Keep up to date", isOn: Binding(
                            get: { export.keepUpToDate ?? true },
                            set: { isOn in Task { await store.setKeepUpToDate(export.id, isOn) } }))
                            .toggleStyle(.switch)
                            .controlSize(.mini)
                            .font(.caption)
                            .help("Off: an edit writes nothing here; Write Now still writes")
                        Spacer()
                        Button("Choose Folder…") { choosingFolderFor = export.id }
                            .controlSize(.small)
                            .help("Write this export to another folder from now on")
                    }
                }
            }
            if let error = store.errorMessage {
                Text(error).font(.caption).foregroundStyle(.secondary)
            }
        }
        .task { await store.load() }
        .fileImporter(isPresented: Binding(get: { choosingFolderFor != nil }, set: { if !$0 { choosingFolderFor = nil } }),
                      allowedContentTypes: [.folder]) { result in
            if case .success(let url) = result, let exportId = choosingFolderFor {
                Task { await store.chooseFolder(exportId, folder: url) }
            }
            choosingFolderFor = nil
        }
    }

    /// One line: writing, waiting, when it was last written, or never yet.
    static func status(of export: Components.Schemas.KeptExport, writing: Bool) -> String {
        if writing { return "Writing; Activity shows it." }
        if export.pending > 0 { return "\(export.pending) waiting to be written." }
        guard let written = export.lastWritten else { return "Not written yet." }
        return "Written \(written.formatted(.relative(presentation: .named)))."
    }
}

#Preview("Kept exports") {
    let gone = Components.Schemas.KeptExport(
        id: "k1", folder: "/Volumes/Archive/Letters", format: .plainText, per: .page, files: [], inTheWay: [], pending: 1,
        lastWritten: nil, keepUpToDate: true)
    let quiet = Components.Schemas.KeptExport(
        id: "k2", folder: "/Users/me/Desktop/Catálogo", format: .catalogueWorkbook, per: .document, files: ["Catálogo.xlsx"],
        inTheWay: [], pending: 0, lastWritten: Date(timeIntervalSinceNow: -3_600), keepUpToDate: false)
    Form {
        KeptExportsInspectorSection(store: .preview([gone, quiet], client: LibraryPreviewFixtures.library.ficheroClient))
    }
    .formStyle(.grouped)
    .frame(width: 320, height: 340)
}
