import FicheroAPIClient
import SwiftUI

/// The project Inspector's kept exports (#5485, `source.onboard.kept-exported`): each folder the
/// project keeps an export in, its format and per, when it was last written, with Write Now and
/// Remove. Setting one up is setup's Kept exported screen (Set Up… reaches it).
struct KeptExportsInspectorSection: View {
    let store: KeptExportStore

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
                }
            }
            if let error = store.errorMessage {
                Text(error).font(.caption).foregroundStyle(.secondary)
            }
        }
        .task { await store.load() }
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
    Form {
        KeptExportsInspectorSection(store: LibraryPreviewFixtures.library.keptExportStore)
    }
    .formStyle(.grouped)
    .frame(width: 320, height: 240)
}
