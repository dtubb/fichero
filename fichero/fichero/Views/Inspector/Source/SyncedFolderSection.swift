import FicheroAPIClient
import SwiftUI

/// What a synced folder's section says, worked out from the engine's status and intake so the
/// words are testable without a rendered view (`source.sync.status-in-inspector`,
/// `source.sync.intake-is-opt-in`; #5480).
struct SyncedFolderSummary: Equatable {
    /// "Synced: kept in its own layout" or "Synced: Fichero's layout".
    let kind: String
    let path: String
    let formats: String
    /// Lines that need a look (conflicts, changed or deleted outside, files in the way); empty
    /// when nothing does.
    let notices: [String]
    /// The intake line: on, or what waits to come in.
    let intake: String
    /// Whether Take In would bring anything in now.
    let somethingWaits: Bool

    init(folder: Components.Schemas.SyncFolderStatus, intake state: Components.Schemas.IntakeState?) {
        kind = folder.adopted ? "Synced: kept in its own layout" : "Synced: Fichero's layout"
        path = folder.path
        formats = folder.formats.isEmpty ? "None yet" : folder.formats.map(Self.formatName).joined(separator: ", ")
        var notices: [String] = []
        if folder.pending > 0 { notices.append(Self.count(folder.pending, "file waits", "files wait") + " to be written") }
        if !folder.conflicts.isEmpty {
            notices.append(Self.count(folder.conflicts.count, "file", "files")
                           + " changed both here and in the folder: both kept as passes")
        }
        if !folder.changedOutside.isEmpty {
            notices.append(Self.count(folder.changedOutside.count, "file", "files") + " changed outside Fichero")
        }
        if !folder.deletedOutside.isEmpty {
            notices.append(Self.count(folder.deletedOutside.count, "file", "files")
                           + " deleted outside: written again on the next change")
        }
        if !folder.inTheWay.isEmpty {
            notices.append(Self.count(folder.inTheWay.count, "file", "files") + " Fichero did not write: left alone")
        }
        if !folder.notReadBack.isEmpty {
            notices.append(Self.count(folder.notReadBack.count, "file", "files") + " in a form Fichero does not read back")
        }
        self.notices = notices
        let waiting = (state?.wouldBringIn.additionalProperties ?? [:]).filter { $0.value > 0 }
        let total = waiting.values.reduce(0, +)
        somethingWaits = total > 0
        let isOn = state?.on ?? folder.intake
        if total > 0 {
            let byFormat = waiting.keys.sorted().map { "\(Self.formatName($0)) \(waiting[$0] ?? 0)" }
            intake = Self.count(total, "file", "files") + " changed in the folder "
                + (total == 1 ? "waits" : "wait") + " to come in (" + byFormat.joined(separator: ", ") + ")"
        } else if isOn {
            intake = "Taking in: files changed in the folder come in as new passes."
        } else {
            intake = "Not taking in. Nothing is waiting to come in."
        }
    }

    private static func count(_ number: Int, _ one: String, _ many: String) -> String {
        "\(number) \(number == 1 ? one : many)"
    }

    static func formatName(_ id: String) -> String {
        switch id {
        case "pagexml", "page": return "PAGE XML"
        case "alto": return "ALTO"
        case "tei": return "TEI"
        default: return id
        }
    }
}

/// A folder's synced-folder state, with Take In, Leave and Untie (#5480). Shown in a folder's
/// Inspector and on setup's Your material screen, so both say the same thing.
struct SyncedFolderSection: View {
    let store: SyncFolderStore
    let folder: Components.Schemas.SyncFolderStatus
    @State private var confirmingUntie = false
    @State private var busy = false

    var body: some View {
        let summary = SyncedFolderSummary(folder: folder, intake: store.intakeStates[folder.id])
        VStack(alignment: .leading, spacing: 6) {
            Label(summary.kind, systemImage: "arrow.triangle.2.circlepath")
                .font(.headline)
                .accessibilityLabel("This folder is synced. \(summary.kind)")
            Text(summary.path)
                .font(.caption)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
                .lineLimit(2)
                .truncationMode(.middle)
            LabeledContent("Formats", value: summary.formats).font(.callout)
            Picker("Kept as", selection: modeChoice) {
                Text("Index").tag(Components.Schemas.SyncFolderStatus.ModePayload.index)
                Text("Keep arranged").tag(Components.Schemas.SyncFolderStatus.ModePayload.keepArranged)
            }
            .pickerStyle(.segmented)
            .disabled(busy)
            .font(.callout)
            .help("Index leaves files where they are; Keep arranged also moves them inside the folder to follow the project's folders")
            if let proposal = store.proposedArrangements[folder.id] {
                KeepArrangedProposalView(
                    summary: KeepArrangedProposal(preview: proposal),
                    busy: busy,
                    arrange: { change { await store.confirmKeepArranged(folder.id) } },
                    cancel: { store.cancelKeepArranged(folder.id) }
                )
            }
            ForEach(summary.notices, id: \.self) { notice in
                Label(notice, systemImage: "exclamationmark.circle").font(.callout).foregroundStyle(.orange)
            }
            Text(summary.intake).font(.callout)
            HStack {
                Button("Take In") { change { await store.setIntake(folder.id, on: true) } }
                    .disabled(busy || (folder.intake && !summary.somethingWaits))
                    .help("Bring what changed in the folder in as new passes; nothing in the project is overwritten")
                    .accessibilityLabel("Take in what changed in the folder")
                Button("Leave") { change { await store.setIntake(folder.id, on: false) } }
                    .disabled(busy || !folder.intake)
                    .help("Stop taking files in from the folder; nothing comes in")
                    .accessibilityLabel("Leave what changed in the folder")
                Spacer()
                Button("Untie…", role: .destructive) { confirmingUntie = true }
                    .disabled(busy)
                    .accessibilityLabel("Untie this synced folder")
            }
            .buttonStyle(.borderless)
            if let error = store.errorMessage {
                Text(error).font(.caption).foregroundStyle(.secondary)
            }
        }
        .task(id: folder.id) { await store.fetchIntake(folder.id) }
        .confirmationDialog("Untie this folder?", isPresented: $confirmingUntie) {
            Button("Untie", role: .destructive) { change { await store.untie(folder.id) } }
        } message: {
            Text("Fichero stops writing to it and taking files in from it. Its files stay where they are.")
        }
    }

    /// Index / Keep arranged: Keep arranged shows its dry run first and moves nothing until
    /// Arrange (`SyncFolderStore.choose`).
    private var modeChoice: Binding<Components.Schemas.SyncFolderStatus.ModePayload> {
        Binding(
            get: { store.shownMode(of: folder) },
            set: { chosen in change { await store.choose(chosen, for: folder.id) } }
        )
    }

    private func change(_ work: @escaping () async -> Bool) {
        busy = true
        Task {
            _ = await work()
            busy = false
        }
    }
}

/// What the Keep arranged dry run says, from the engine's preview, so the words are testable
/// without a rendered view (`source.onboard.keep-arranged`): how many files would move, a few of
/// the new paths, or why the folder would not be arranged.
struct KeepArrangedProposal: Equatable {
    /// One sentence: the count that would move, or the engine's refusal.
    let headline: String
    /// Up to three moves, "from → to", inside the folder.
    let samples: [String]
    /// Arrange is offered only when the engine would arrange the folder.
    let canArrange: Bool

    static let sampleCount = 3

    init(preview: Components.Schemas.ArrangementPreview) {
        if let refused = preview.refused, !refused.isEmpty {
            headline = refused
            samples = []
            canArrange = false
            return
        }
        let count = preview.moves.count
        switch count {
        case 0: headline = "Nothing needs to move now. From now on, files follow the project's folders."
        case 1: headline = "1 file would move, inside this folder, to follow the project's folders."
        default: headline = "\(count) files would move, inside this folder, to follow the project's folders."
        }
        samples = preview.moves.prefix(Self.sampleCount).map { "\($0.fromPath) → \($0.toPath)" }
        canArrange = true
    }
}

/// The dry run and the yes: nothing moves until Arrange (`source.onboard.keep-arranged`).
struct KeepArrangedProposalView: View {
    let summary: KeepArrangedProposal
    let busy: Bool
    let arrange: () -> Void
    let cancel: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(summary.headline).font(.callout)
            ForEach(summary.samples, id: \.self) { sample in
                Text(sample)
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            HStack {
                Button("Cancel", action: cancel).disabled(busy)
                if summary.canArrange {
                    Button("Arrange", action: arrange)
                        .disabled(busy)
                        .help("Move the files now, only inside this folder; none is deleted")
                }
            }
            .controlSize(.small)
        }
        .padding(8)
        .background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 6))
    }
}

/// The synced-folder section of a folder's Inspector: shown only when the selected folder is
/// one the project is tied to (`source.sync.status-in-inspector`); any other selection shows
/// nothing.
struct FolderSyncInspectorSection: View {
    let document: Document

    @Environment(LibraryManager.self) private var libraryManager: LibraryManager?
    @Environment(DocumentStore.self) private var documentStore: DocumentStore?

    /// The synced folder a document is, if it is one: a folder whose place on disk the project
    /// is tied to. Nil for anything else, so the section draws nothing.
    static func syncedFolder(for document: Document, in store: SyncFolderStore)
        -> Components.Schemas.SyncFolderStatus? {
        guard document.docType == .folder, let path = document.path, !path.isEmpty else { return nil }
        return store.folder(atPath: path)
    }

    private var store: SyncFolderStore? {
        documentStore.flatMap { libraryManager?.library(owningService: $0)?.syncFolderStore }
    }

    var body: some View {
        if let store, document.docType == .folder, document.path != nil {
            Group {
                if let folder = Self.syncedFolder(for: document, in: store) {
                    SyncedFolderSection(store: store, folder: folder)
                }
            }
            .task(id: document.id) { await store.load() }
        }
    }
}

#Preview("Synced folder, files waiting") {
    let store = LibraryPreviewFixtures.library.syncFolderStore
    let folder = Components.Schemas.SyncFolderStatus(
        id: "f1", path: "/Users/historian/Archive/Letters", formats: ["pagexml"], mode: .index, intake: false,
        conflicts: [], adopted: true, pending: 0, files: ["letter-1.xml"], inTheWay: [],
        changedOutside: ["letter-1.xml"], takenIn: [], notReadBack: [], deletedOutside: []
    )
    return SyncedFolderSection(store: store, folder: folder)
        .padding()
        .frame(width: 320)
}

#Preview("Keep arranged, dry run") {
    KeepArrangedProposalView(
        summary: KeepArrangedProposal(preview: .init(mode: .index, moves: [
            .init(documentId: "d1", fromPath: "IMG_0001.jpg", toPath: "Letters/1851/IMG_0001.jpg"),
            .init(documentId: "d2", fromPath: "IMG_0002.jpg", toPath: "Letters/1851/IMG_0002.jpg"),
            .init(documentId: "d3", fromPath: "scan 3.tif", toPath: "Maps/scan 3.tif"),
            .init(documentId: "d4", fromPath: "scan 4.tif", toPath: "Maps/scan 4.tif")
        ])),
        busy: false, arrange: {}, cancel: {}
    )
    .padding()
    .frame(width: 320)
}
