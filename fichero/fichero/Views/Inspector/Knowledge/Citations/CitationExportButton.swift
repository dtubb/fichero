import FicheroAPIClient
import SwiftUI

// MARK: - Load model

/// Loads BibTeX for the current citation scope so ``CitationExportButton`` can
/// hand it to ShareLink / drag-and-drop. An observable phase machine, injected
/// with a fetch seam (the store's `exportCitationsBibtex` / `documentBibtexCitation`)
/// so it is testable without the network.
@Observable
@MainActor
final class CitationExportModel {
    enum Phase: Equatable {
        case loading
        case ready(String)
        case empty
        case failed
    }

    private(set) var phase: Phase = .loading

    func load(using fetch: @MainActor () async throws -> String) async {
        phase = .loading
        do {
            let bibtex = try await fetch()
            phase = bibtex.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                ? .empty
                : .ready(bibtex)
        } catch {
            if error.isCancellationError {
                // Superseded by a newer scope — leave the phase to the newer load.
                return
            }
            phase = .failed
        }
    }
}

// MARK: - View

/// Export the current selection's citations to a citation manager (#3451):
/// **copy / share** via the platform share sheet (`ShareLink`) and
/// **drag-and-drop** the BibTeX out. Cross-platform (macOS/iPadOS/iOS) — no
/// AppKit `NSSharingService`. Covers all four citation kinds because the BibTeX
/// the engine emits already spans cite-this-document, page, in-text usages, and
/// references cited.
///
/// RIS is not offered yet — the engine only exports BibTeX; a RIS exporter is a
/// separate engine follow-up (noted on #3451).
struct CitationExportButton: View {
    /// Fetches the BibTeX for the current scope (one or many document ids).
    let fetch: @MainActor () async throws -> String
    var label: String = "Export Citations"

    @State private var model = CitationExportModel()

    var body: some View {
        Group {
            switch model.phase {
            case .loading:
                ProgressView()
                    .controlSize(.small)
            case .ready(let bibtex):
                ShareLink(
                    item: bibtex,
                    subject: Text("Citations"),
                    preview: SharePreview("BibTeX citations")
                ) {
                    Label(label, systemImage: "square.and.arrow.up")
                }
                .draggable(bibtex)
                .help("Copy, share, or drag these citations (BibTeX) to a citation manager")
            case .empty:
                Label("No citations to export", systemImage: "text.quote")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            case .failed:
                Label("Export failed", systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .task { await model.load(using: fetch) }
    }
}
