import SwiftUI

/// The Inspector's Making section at page level (#5149): how each of the page's passes was made,
/// and, for an imported one, its original file -- read-only, exactly as it arrived.
struct InspectorMakingSection: View {
    let documentId: String

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(\.undoManager) private var undoManager
    @Environment(LibraryManager.self) private var libraryManager: LibraryManager?
    @State private var shown: PassOriginal?
    /// What the engine writes, for each pass's Export menu (#5162).
    @State private var formats: [PageExportChoice.Format] = []
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
                        exportMenu(entry)
                    }
                }
                if let failure {
                    Text(failure).font(.caption).foregroundStyle(.secondary)
                }
            }
            .sheet(item: $shown) { original in
                PassOriginalSheet(original: original)
            }
            .task { await loadFormats() }
        }
    }

    /// Export (#5162): this pass AS EDITED in each format the engine writes of its kind, and AS
    /// IMPORTED -- its original file, byte for byte -- when one is kept.
    @ViewBuilder
    private func exportMenu(_ entry: InspectorMaking.Entry) -> some View {
        let offers = PageExportChoice.offers(formats, georeferencing: entry.georeferencing)
        if let library = segmentService.flatMap({ libraryManager?.library(owningService: $0) }),
           !offers.isEmpty || entry.hasOriginal {
            Menu("Export") {
                if !offers.isEmpty {
                    Section("As Edited") {
                        ForEach(offers) { format in
                            Button(format.title + "…") {
                                Task {
                                    await PageExportRunner.exportPass(
                                        documentId: documentId, passId: entry.passId, format: format, library: library
                                    )
                                }
                            }
                        }
                    }
                }
                if entry.hasOriginal {
                    Button("As Imported…") { Task { await PageExportRunner.saveOriginal(passId: entry.passId, library: library) } }
                        .help("Save the file this pass was imported from, exactly as it arrived")
                }
            }
            .menuStyle(.button)
            .buttonStyle(.borderless)
            .font(.caption)
            .fixedSize()
        }
    }

    private func loadFormats() async {
        guard formats.isEmpty, let segmentService,
              let library = libraryManager?.library(owningService: segmentService) else { return }
        formats = (try? await library.documentService.formats()) ?? []
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
