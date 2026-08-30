import CoreTransferable
import OSLog
import SwiftUI
import UniformTypeIdentifiers

/// Failures saving/dragging the table CSV are LOGGED, never swallowed.
let readerTableExportLogger = Logger(
    subsystem: "com.fichero.app", category: "reader-table-export"
)

// MARK: - The reader's ARTIFACT lens (artifact-compare P1, Daniel 2026-08-26:
// "the reader can show different artifacts — an original, diplomatic, and
// translation — user can choose"). The pane head's controls slot gains a
// picker over the shown document's artifacts; picking one renders THAT
// artifact's text in place of the live transcript. Two panes side by side,
// each pinned to a different artifact, IS the comparison — the pane system
// already does the hard part (per the artifact-compare design ruling:
// compare splits the current window).

/// What the reader pane is pinned to instead of the live transcript.
struct ReaderArtifactLens: Equatable {
    let artifactId: String
    let label: String
}

/// The artifact types the reader can read a document THROUGH — the text
/// representations (Daniel, 2026-08-29: Content / Transcript / Translate…).
/// A closed display list over the types that actually exist; structural
/// artifact types (segmentation, grouping, entities, text_geometry) are not
/// readings of the text and never appear in the switcher.
enum ReaderRepresentation {
    /// Artifact types that ARE text representations, in display order.
    /// KEYED TO WHAT PRODUCERS ACTUALLY WRITE (check_artifact_type_contract,
    /// #4418 class): transcribe/audio_transcribe → transcription,
    /// translate/text_translate → translation, summarize → summary,
    /// convert → conversion. `normalized_text`/`transliteration`/`markdown`/
    /// `html` exist only as ContentRepresentationKind values — no tool emits
    /// them as artifact types, so listing them here was a lens to nowhere;
    /// they rejoin WITH their producers, not before.
    static let textTypes = [
        "transcription", "translation", "summary", "conversion"
    ]

    /// Table-family artifact types (Daniel, 2026-08-29 bedtime: CSV/table
    /// output is renderable in the Reader and choosable). `table_extract` —
    /// and the Accounts → Spreadsheet preset built on it — writes "table";
    /// the engine view renders these as a real HTML table.
    static let tableTypes = ["table"]

    static func title(for type: String) -> String {
        switch type {
        case "transcription": return "Transcript"
        case "translation": return "Translation"
        case "summary": return "Summary"
        case "conversion": return "Conversion"
        case "table": return "Table"
        default: return type.capitalized
        }
    }

    /// The distinct representation types present in a scope's artifacts, in
    /// the fixed display order (text readings, then tables) — file-scope so
    /// tests can call it directly.
    static func availableTypes(in artifactTypes: [String]) -> [String] {
        let present = Set(artifactTypes)
        return (textTypes + tableTypes).filter { present.contains($0) }
    }
}

/// A table representation's CSV, draggable OUT of the reader as a real file
/// (Daniel, 2026-08-29 bedtime: "drags the artifact to the Desktop or into
/// Excel"). WebKit content can't start a native file drag, so the seam is
/// native: this Transferable vends a FileRepresentation that writes the CSV
/// into the app container's tmp and hands the receiver that file.
struct ReaderTableCSVExport: Transferable, Sendable {
    let filename: String
    let csv: String
    /// Provenance for the in-app drop (Daniel's third target, 2026-08-29):
    /// dropping this on a sidebar FOLDER rides the existing artifact-promote
    /// path (`promoteArtifacts`), which stamps `source_artifact_id` +
    /// `source_document_id` on the created node — "you know where it came
    /// from". Empty artifactId = no in-app payload worth vending.
    var artifactId: String = ""
    var sourceDocumentId: String?
    var nodeName: String = ""

    /// The in-app drag payload the sidebar's drop classifier already accepts
    /// (`kind: .artifact` → `.internalArtifacts` → promote-with-provenance).
    var libraryDrag: LibraryItemDrag {
        LibraryItemDrag(
            kind: .artifact,
            id: artifactId,
            documentId: sourceDocumentId,
            text: csv,
            name: nodeName.isEmpty ? filename : nodeName
        )
    }

    static var transferRepresentation: some TransferRepresentation {
        // In-app first: a sidebar drop reads the ficheroDragItem payload and
        // promotes with provenance; Finder/Excel ignore it and take the file.
        ProxyRepresentation(exporting: \.libraryDrag)
        FileRepresentation(exportedContentType: .commaSeparatedText) { export in
            let dir = FileManager.default.temporaryDirectory
                .appendingPathComponent("reader-table-exports", isDirectory: true)
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let url = dir.appendingPathComponent(export.filename)
            try Data(export.csv.utf8).write(to: url, options: .atomic)
            // The receiver takes the file's own name — written under the
            // document's display name above, so no suggestedFileName needed.
            return SentTransferredFile(url)
        }
    }

    /// "Ledger 1933.csv" — the shown document's display name, with the
    /// path-hostile characters swapped out. File-scope for tests.
    static func filename(forDocumentNamed name: String) -> String {
        let cleaned = name
            .replacingOccurrences(of: "/", with: "-")
            .replacingOccurrences(of: ":", with: "-")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return (cleaned.isEmpty ? "Table" : cleaned) + ".csv"
    }
}

extension ReadingPaneView {

    /// The head's CSV-out chip, shown ONLY while a table representation is
    /// on screen and its artifact loaded: drag it to the Desktop/Excel for a
    /// real .csv, or click for a save panel (the sandbox-proof rung — a
    /// pasteboard sandbox-extension denial was seen on container-tmp drags,
    /// so the click path must always exist).
    @ViewBuilder
    var readerTableExportControl: some View {
        if let export = readerTableExport {
            Button {
                isExportingTableCSV = true
            } label: {
                Image(systemName: "square.and.arrow.down")
                    .foregroundStyle(Color.secondary)
                    .readerIconTarget()
            }
            .buttonStyle(.plain)
            .draggable(export)
            .help("Drag out as a CSV file (or onto a sidebar folder to make a library node), or click to save…")
            .accessibilityLabel("Save table as CSV")
            .accessibilityIdentifier("readerTableExportChip")
        }
    }

    /// Fetch the FULL newest table artifact for the scope when a table
    /// representation is selected (list rows carry truncated content), so the
    /// chip has real bytes to vend the moment a drag starts.
    func loadReaderTableExport() async {
        readerTableExport = nil
        guard let representation = readerRepresentation,
              ReaderRepresentation.tableTypes.contains(representation),
              let doc = effectiveDocument,
              let service = LibraryManager.shared
                  .getLibrary(id: LibraryManager.shared.currentLibraryId ?? LibraryManager.globalLibraryId)?
                  .artifactService
        else { return }
        guard let artifacts = try? await service.getArtifacts(
            forDocumentId: doc.id, includeDescendants: true
        ) else { return }
        guard let newest = artifacts
            .filter({ $0.artifactType == representation })
            .max(by: { $0.createdAt < $1.createdAt })
        else { return }
        guard let full = try? await service.getArtifact(id: newest.id),
              let content = full.content, !content.isEmpty
        else { return }
        let displayName = DocumentTitle.displayName(for: doc)
        readerTableExport = ReaderTableCSVExport(
            filename: ReaderTableCSVExport.filename(forDocumentNamed: displayName),
            csv: content,
            artifactId: full.id,
            sourceDocumentId: full.documentId,
            nodeName: displayName
        )
    }

    /// The head's representation switcher (Daniel, 2026-08-29): Content plus
    /// each representation type this document's scope actually has. Picking
    /// one re-requests the SAME WebKit page with `?representation=` — one
    /// renderer, several readings. Hidden when there is nothing to switch to.
    @ViewBuilder
    var readerRepresentationControl: some View {
        if !readerRepresentationChoices.isEmpty {
            Menu {
                Button {
                    readerRepresentation = nil
                } label: {
                    if readerRepresentation == nil {
                        Label("Content", systemImage: "checkmark")
                    } else {
                        Text("Content")
                    }
                }
                Divider()
                ForEach(readerRepresentationChoices, id: \.self) { type in
                    Button {
                        readerRepresentation = type
                    } label: {
                        if readerRepresentation == type {
                            Label(ReaderRepresentation.title(for: type), systemImage: "checkmark")
                        } else {
                            Text(ReaderRepresentation.title(for: type))
                        }
                    }
                }
            } label: {
                Text(readerRepresentation.map { ReaderRepresentation.title(for: $0) } ?? "Content")
                    .font(.caption)
                    .foregroundStyle(readerRepresentation == nil ? Color.secondary : Color.accentColor)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help("Read this document as its content or one of its representations")
            .accessibilityIdentifier("readerRepresentationSwitcher")
        }
    }

    /// The head's artifact-lens control: a menu of this document's artifacts
    /// plus "Live Transcript" to return. Hidden entirely for documents with
    /// no artifacts — absent beats present-and-useless (#4421).
    @ViewBuilder
    var artifactLensControl: some View {
        if !artifactLensChoices.isEmpty {
            Menu {
                Button {
                    artifactLens = nil
                } label: {
                    if artifactLens == nil {
                        Label("Live Transcript", systemImage: "checkmark")
                    } else {
                        Text("Live Transcript")
                    }
                }
                Divider()
                ForEach(artifactLensChoices, id: \.artifactId) { choice in
                    Button {
                        artifactLens = choice
                    } label: {
                        if artifactLens == choice {
                            Label(choice.label, systemImage: "checkmark")
                        } else {
                            Text(choice.label)
                        }
                    }
                }
            } label: {
                Image(systemName: "doc.on.doc")
                    .foregroundStyle(artifactLens == nil ? Color.secondary : Color.accentColor)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help(artifactLens.map { "Showing artifact: \($0.label)" }
                ?? "Show one of this document's artifacts instead of the live transcript")
        }
    }

    /// Load the artifact choices for the shown document. Newest first, labeled
    /// "type · model · date" the way the inspector's list reads.
    func loadArtifactLensChoices() async {
        artifactLens = nil
        artifactLensChoices = []
        readerRepresentation = nil
        readerRepresentationChoices = []
        guard let doc = effectiveDocument,
              let service = LibraryManager.shared
                  .getLibrary(id: LibraryManager.shared.currentLibraryId ?? LibraryManager.globalLibraryId)?
                  .artifactService
        else { return }
        // ONE fetch answers both head controls: the whole scope's artifacts
        // (pages included) drive the representation switcher; the document's
        // OWN artifacts drive the per-artifact lens, as before.
        guard let artifacts = try? await service.getArtifacts(
            forDocumentId: doc.id, includeDescendants: true
        ) else { return }
        readerRepresentationChoices = ReaderRepresentation.availableTypes(
            in: artifacts.map(\.artifactType)
        )
        let formatter = RelativeDateTimeFormatter()
        artifactLensChoices = artifacts
            .filter { $0.documentId == doc.id }
            .sorted { $0.createdAt > $1.createdAt }
            .prefix(12)
            .map { artifact in
                let when = formatter.localizedString(for: artifact.createdAt, relativeTo: Date())
                return ReaderArtifactLens(
                    artifactId: artifact.id,
                    label: "\(artifact.artifactType) · \(when)"
                )
            }
    }
}

/// The pinned artifact's text, full height, reader typography. Fetches the
/// FULL artifact (list rows carry truncated content).
struct ArtifactLensContentView: View {
    let lens: ReaderArtifactLens

    @Environment(ArtifactService.self) private var artifactService: ArtifactService?
    @State private var text: String?
    @State private var failed = false

    var body: some View {
        ScrollView {
            if let text {
                Text(text)
                    .font(.body)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
            } else if failed {
                ContentUnavailableView(
                    "Couldn’t Load Artifact",
                    systemImage: "exclamationmark.triangle",
                    description: Text(lens.label)
                )
                .padding(.top, 40)
            } else {
                ProgressView().padding(.top, 40)
            }
        }
        .background(Color(.textBackgroundColor))
        .task(id: lens.artifactId) {
            failed = false
            text = nil
            guard let artifactService,
                  let full = try? await artifactService.getArtifact(id: lens.artifactId),
                  let content = full.content, !content.isEmpty
            else {
                failed = true
                return
            }
            text = content
        }
    }
}
