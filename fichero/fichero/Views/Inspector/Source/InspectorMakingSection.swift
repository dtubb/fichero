import SwiftUI

/// The Inspector's Making section at page level (#5149): how each of the page's passes was made,
/// and, for an imported one, its original file -- read-only, exactly as it arrived.
struct InspectorMakingSection: View {
    let documentId: String

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(\.undoManager) private var undoManager
    @State private var shown: PassOriginal?
    @State private var failure: String?

    private var entries: [InspectorMaking.Entry] {
        guard let segmentService else { return [] }
        let store = SegmentStore.shared(for: segmentService)
        return InspectorMaking.entries(
            passes: store.passes(documentId: documentId), segments: store.segments(documentId: documentId)
        )
    }

    var body: some View {
        let entries = entries
        if !entries.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Making").font(.headline)
                ForEach(entries) { entry in
                    if entry.georeferencing, entry.id == entries.first(where: \.georeferencing)?.id {
                        // Georeferencing passes place the page in the world; they are not its text (#5122).
                        Text("Georeferencing").font(.subheadline).foregroundStyle(.secondary).padding(.top, 4)
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text(entry.title).font(.body).textSelection(.enabled)
                        Text(entry.detail).font(.caption).foregroundStyle(.secondary)
                        if let note = entry.workingNote {
                            Text(note).font(.caption.weight(.semibold))
                        } else if !entry.georeferencing {
                            Button("Make Working") { Task { await makeWorking(entry.passId) } }
                                .buttonStyle(.borderless)
                                .font(.caption)
                                .help("Make this the pass the page's text and edits come from, and the one drawn")
                        }
                        if entry.hasOriginal {
                            Button("Show Original") { Task { await show(entry.passId) } }
                                .buttonStyle(.borderless)
                                .font(.caption)
                                .accessibilityLabel("Show the original file \(entry.title)")
                        }
                    }
                }
                if let failure {
                    Text(failure).font(.caption).foregroundStyle(.secondary)
                }
            }
            .sheet(item: $shown) { original in
                PassOriginalSheet(original: original)
            }
        }
    }

    /// "Make Working" (#5156): the audited `pass.choose_working`, with ⌘Z.
    private func makeWorking(_ passId: String) async {
        guard let segmentService, let actionsService = actionStore?.actionsService else { return }
        do {
            try await WorkingPassChoice.run(
                documentId: documentId, passId: passId, actionsService: actionsService,
                store: SegmentStore.shared(for: segmentService), undoManager: undoManager
            )
            failure = nil
        } catch {
            failure = "The working pass could not be changed: \(error.localizedDescription)"
        }
    }

    private func show(_ passId: String) async {
        guard let segmentService else { return }
        do {
            shown = try await segmentService.original(passId: passId)
            failure = shown == nil ? "The original file is not kept for this pass." : nil
        } catch {
            failure = "The original could not be read: \(error.localizedDescription)"
        }
    }
}

extension PassOriginal: Identifiable {
    var id: String { (fileName ?? "") + String(bytes.count) }
}

/// The original, read-only, as text: what the file said, not what the library made of it.
struct PassOriginalSheet: View {
    let original: PassOriginal
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(original.fileName ?? "Original").font(.headline)
                if let format = original.importFormat {
                    Text(InspectorMaking.formatName(format)).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
            }
            .padding(12)
            Divider()
            ScrollView([.vertical, .horizontal]) {
                Text(original.text)
                    .font(.body.monospaced())
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(12)
            }
        }
        .frame(minWidth: 520, minHeight: 420)
    }
}

#if DEBUG
#Preview("An imported PAGE file") {
    PassOriginalSheet(original: PassOriginal(
        fileName: "0065.page.xml", importFormat: "pagexml", mediaType: "application/xml",
        bytes: Data(#"<PcGts><Page imageWidth="1969" imageHeight="2365"><TextRegion id="r1"/></Page></PcGts>"#.utf8)
    ))
}
#endif
