import CoreTransferable
import FicheroAPIClient
import OSLog
import SwiftUI
import UniformTypeIdentifiers

//  Extracted for file_length (#5113) with that issue's checklist: path asserted free, cut
//  above the declaration's attributes and doc comment, no file-scope conditional-compilation
//  blocks and no file-scope `private` to strand, imports copied from the source verbatim.

/// How the reader's artifact submenu is BUILT — pure, so the grouping and the
/// labels are testable without a view.
///
/// Both halves are borrowed rather than re-derived, deliberately:
/// `ArtifactRunGrouping` (#4319) already groups the inspector's artifact
/// browser by run in pipeline order, and `WorkflowBarPolicy.artifactLabels`
/// already names an artifact the way tonight's scope menu names it. Two menus
/// listing the same artifacts under two different naming rules is exactly the
/// disagreement this reuse forecloses.
enum ReaderArtifactMenu {
    /// Beyond this many runs the submenu is a wall, not a menu. The rest stay
    /// reachable in the Artifacts inspector, which is the full browser.
    static let maxRuns = 8

    static func groups(
        from artifacts: [Artifact],
        workflowName: (String) -> String? = { _ in nil },
        now: Date = Date()
    ) -> [ReaderArtifactLensGroup] {
        // ONE label vocabulary with the scope menu, including its
        // collision-breaking tail for cached re-runs that mint identical rows.
        let labels = WorkflowBarPolicy.artifactLabels(
            artifacts.map(choice(for:)), now: now
        )
        let runs = ArtifactRunGrouping.groups(from: artifacts).prefix(maxRuns)
        var newestRunSeen = false
        return runs.map { group in
            let isLatest = !group.isEarlier && !newestRunSeen
            if isLatest { newestRunSeen = true }
            return ReaderArtifactLensGroup(
                id: group.id,
                title: title(for: group, workflowName: workflowName),
                time: group.isEarlier
                    ? ""
                    : WorkflowBarPolicy.provenanceTime(group.latestCreatedAt, now: now),
                isLatest: isLatest,
                choices: group.artifacts.map { artifact in
                    ReaderArtifactLens(
                        artifactId: artifact.id,
                        label: labels[artifact.id]
                            ?? WorkflowBarPolicy.artifactChoiceLabel(
                                choice(for: artifact), now: now
                            )
                    )
                }
            )
        }
    }

    /// The run's name: its workflow's, where the store knows it; else the step
    /// that wrote it; else an honest generic. Never a guess at a nicer name.
    static func title(
        for group: ArtifactRunGroup,
        workflowName: (String) -> String?
    ) -> String {
        if group.isEarlier { return "Earlier" }
        if let workflowId = group.workflowId,
           let name = workflowName(workflowId),
           !name.trimmingCharacters(in: .whitespaces).isEmpty {
            return name
        }
        if let step = group.artifacts.compactMap(\.stepName).first,
           !step.trimmingCharacters(in: .whitespaces).isEmpty {
            return step
        }
        return "Workflow Run"
    }

    static func choice(for artifact: Artifact) -> WorkflowBarPolicy.ArtifactChoice {
        WorkflowBarPolicy.ArtifactChoice(
            id: artifact.id,
            artifactType: artifact.artifactType,
            displayName: nil,
            provider: artifact.provider,
            model: artifact.model,
            stepName: artifact.stepName,
            createdAt: artifact.createdAt
        )
    }

    /// Every row, flattened — what the pane keeps so a lens can be re-resolved
    /// (or dropped) after a refresh without re-walking the groups.
    static func flattened(_ groups: [ReaderArtifactLensGroup]) -> [ReaderArtifactLens] {
        groups.flatMap(\.choices)
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
