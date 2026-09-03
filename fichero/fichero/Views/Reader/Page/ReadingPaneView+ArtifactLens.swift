import CoreTransferable
import FicheroAPIClient
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

    /// "Transcription — claude-opus-5" (Daniel, 2026-09-02). The head has to
    /// name WHICH artifact it is showing, and "transcription · 2 hours ago"
    /// names the wrong axis: several models produce the same type, and which
    /// model wrote it is the thing you are comparing. The relative date stays
    /// as the fallback for an artifact with no recorded model — a bare type
    /// would leave two rows reading identically.
    ///
    /// Pure and static so the naming rule is testable without a view.
    static func label(type: String, model: String?, relativeDate: String) -> String {
        let title = ReaderRepresentation.title(for: type)
        guard let model, !model.trimmingCharacters(in: .whitespaces).isEmpty else {
            return "\(title) · \(relativeDate)"
        }
        return "\(title) — \(model)"
    }
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

    /// The markup-review reading (Daniel, 2026-08-30 ruling 5: "see
    /// annotations somewhere" — the Marked idea). NOT an artifact type: it is
    /// a reading over the scope's user annotations, offered only when the
    /// scope actually has some — never a toggle to nowhere.
    static let annotationsType = "annotations"

    static func title(for type: String) -> String {
        switch type {
        case "transcription": return "Transcript"
        case "translation": return "Translation"
        case "summary": return "Summary"
        case "conversion": return "Conversion"
        case "table": return "Table"
        case annotationsType: return "Annotations"
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

    /// What this pane is SHOWING, in words (Daniel, 2026-09-02: the reader
    /// head "never says WHAT is displayed — document content, or which
    /// artifact"). Rendered beside the head's one glyph.
    ///
    /// Only the Content lens has a choice to state: the knowledge surfaces
    /// ARE their lens, so they name themselves. Precedence matches the
    /// renderer's own (`ReadingPaneView+Tabs`): the artifact lens outranks
    /// the representation switcher, which outranks the live content.
    var readerShownLabel: String {
        guard readerTab == .page else { return readerLensBinding.wrappedValue.title }
        if let artifactLens { return artifactLens.label }
        if let readerRepresentation {
            return ReaderRepresentation.title(for: readerRepresentation)
        }
        return ReaderLens.page.title
    }

    /// The "Showing" submenu of the head's View menu (Daniel, 2026-09-02:
    /// the View menu "should gain a submenu listing the artifacts AVAILABLE
    /// for the current document … so you can point the pane at any of them").
    ///
    /// This is ONE menu where the head used to carry two more controls beside
    /// the selector — a text menu of representations and a `doc.on.doc` menu
    /// of artifacts. Three menus a divider apart, none of which said what was
    /// on screen. Every row they offered is here; nothing was dropped.
    ///
    /// Absent entirely when the document has neither representations nor
    /// artifacts: a submenu whose only row is the state you are already in is
    /// the menu lying (dead-simple-UX).
    func readerShowingMenu() -> AnyView {
        guard !readerRepresentationChoices.isEmpty || !artifactLensChoices.isEmpty else {
            return AnyView(EmptyView())
        }
        return AnyView(
            Menu {
                Button {
                    readerRepresentation = nil
                    artifactLens = nil
                } label: {
                    Self.showingRow(
                        title: ReaderLens.page.title,
                        isCurrent: readerRepresentation == nil && artifactLens == nil,
                        icon: "doc.text"
                    )
                }
                if !readerRepresentationChoices.isEmpty {
                    Section("Representations") {
                        ForEach(readerRepresentationChoices, id: \.self) { type in
                            Button {
                                artifactLens = nil
                                readerRepresentation = type
                            } label: {
                                Self.showingRow(
                                    title: ReaderRepresentation.title(for: type),
                                    isCurrent: artifactLens == nil && readerRepresentation == type,
                                    icon: "text.alignleft"
                                )
                            }
                        }
                    }
                }
                if !artifactLensChoices.isEmpty {
                    Section("Artifacts") {
                        ForEach(artifactLensChoices, id: \.artifactId) { choice in
                            Button {
                                artifactLens = choice
                            } label: {
                                Self.showingRow(
                                    title: choice.label,
                                    isCurrent: artifactLens == choice,
                                    icon: "doc.on.doc"
                                )
                            }
                        }
                    }
                }
            } label: {
                Label("Showing: \(readerShownLabel)", systemImage: "eye")
            }
        )
    }

    /// One checkmarked row. Extracted and explicitly typed: the inline
    /// conditional inside three nested ForEach builders is exactly the shape
    /// that has collapsed this file's type checker before.
    @ViewBuilder
    static func showingRow(title: String, isCurrent: Bool, icon: String) -> some View {
        if isCurrent {
            Label(title, systemImage: "checkmark")
        } else {
            Label(title, systemImage: icon)
        }
    }

    /// Load the artifact choices for the shown document. Newest first, labeled
    /// "type · model · date" the way the inspector's list reads.
    func loadArtifactLensChoices() async {
        artifactLens = nil
        artifactLensChoices = []
        readerRepresentation = nil
        readerRepresentationChoices = []
        guard let doc = effectiveDocument else { return }
        // The pane's OWN injected service first (2026-09-02): the
        // currentLibraryId lookup is the app-global pointer, and in a
        // multi-library window it named a different library than this pane —
        // the artifact fetch answered for the wrong scope and the "Showing"
        // submenu rendered empty (Daniel: "reader view has no artefact
        // submenu"). The lookup stays only as the headless-host fallback.
        let library = LibraryManager.shared
            .getLibrary(id: LibraryManager.shared.currentLibraryId ?? LibraryManager.globalLibraryId)
        guard let service = paneArtifactService ?? library?.artifactService
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
        // "Annotations" joins the switcher whenever the SCOPE has any markup
        // (Daniel, 2026-08-30 ruling 5). The annotations list route matches a
        // node exactly (a page annotation stores the page's id), so the scope
        // check asks about the shown node AND the descendant nodes the
        // artifact fetch just named — capped, first hit wins.
        if let library, await Self.scopeHasAnnotations(
            documentId: doc.id,
            descendantIds: artifacts.map(\.documentId),
            annotationService: library.annotationService
        ) {
            readerRepresentationChoices.append(ReaderRepresentation.annotationsType)
        }
        let formatter = RelativeDateTimeFormatter()
        artifactLensChoices = artifacts
            .filter { $0.documentId == doc.id }
            .sorted { $0.createdAt > $1.createdAt }
            .prefix(12)
            .map { artifact in
                ReaderArtifactLens(
                    artifactId: artifact.id,
                    label: ReaderArtifactLens.label(
                        type: artifact.artifactType,
                        model: artifact.model,
                        relativeDate: formatter.localizedString(
                            for: artifact.createdAt, relativeTo: Date()
                        )
                    )
                )
            }
    }

    /// Whether the reader scope carries ANY annotation (ruling 5's gate for
    /// the "Annotations" switcher entry). Asks the list endpoint directly —
    /// `AnnotationService.load` would overwrite the shared `annotations`
    /// state the inspector observes, and this check must not. The list route
    /// matches one node exactly, so the shown document is asked first, then
    /// the descendant nodes the artifact fetch named — capped, first hit
    /// wins, and failures read as "none" (the menu just stays smaller).
    @MainActor
    static func scopeHasAnnotations(
        documentId: String,
        descendantIds: [String],
        annotationService: AnnotationService
    ) async -> Bool {
        annotationService.syncLibraryPath()
        var candidates: [String] = [documentId]
        for id in descendantIds where id != documentId && !candidates.contains(id) {
            candidates.append(id)
            if candidates.count >= 9 { break }
        }
        for id in candidates {
            guard let response = try? await annotationService.client.api
                .listAnnotationsApiAnnotationsGet(.init(query: .init(documentId: id))),
                case .ok(let okResponse) = response,
                let body = try? okResponse.body.json
            else { continue }
            if body.count > 0 { return true }
        }
        return false
    }
}

// ArtifactLensContentView retired 2026-08-30: the artifact lens rides the ONE
// WebKit renderer now (`?artifact_id=`, via the "artifact:<id>" representation
// channel) — tables parse, prose reads with the document's own typography.
