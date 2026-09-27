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

/// One RUN's worth of artifact rows in the reader's "Showing" submenu
/// (Daniel, 2026-09-04: "sub-artifacts ought to be by RUN, no?"). The flat
/// list read as five interchangeable rows — three reviews from the same pass
/// were indistinguishable from three separate passes, and nothing said which
/// was newest.
struct ReaderArtifactLensGroup: Identifiable, Equatable {
    /// The producing run id, or "earlier" for the ungrouped trailing section.
    let id: String
    /// "Paleographer Review", or "Earlier" for the ungrouped section.
    let title: String
    /// When the run last wrote — empty for the "Earlier" section, which spans
    /// no single moment.
    let time: String
    /// True for the newest run: the submenu has to make the pass you just ran
    /// obvious, which is the whole complaint.
    let isLatest: Bool
    let choices: [ReaderArtifactLens]

    /// The section header the menu prints: the run, when it ran, and — for the
    /// newest one — that it IS the newest.
    var header: String {
        var text = title
        if !time.isEmpty { text += " — \(time)" }
        if isLatest { text += " (latest)" }
        return text
    }
}
