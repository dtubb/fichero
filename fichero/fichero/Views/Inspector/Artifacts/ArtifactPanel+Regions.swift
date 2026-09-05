import OSLog
import SwiftUI

// MARK: - Regions section (B2, Daniel 2026-08-25: "when you click on a region
// in the artifact browser, perhaps it can show the word level bboxes")
//
// A geometry-bearing artifact (regions / transcription with boxes) gains a
// collapsible list of its LINE regions under the text content. Clicking a
// region posts the SAME `.readerTextSelection` seam the reader's word-linking
// uses, so the preview highlights that region's word boxes with zero new
// plumbing — char spans when the geometry recorded them, text anchoring
// otherwise (the handler already supports both).
//
// 2026-08-29 (regions as first-class): rows now also TOGGLE membership in the
// shared `RegionSelection` — the same instance the Preview overlay observes —
// so N selected rows highlight on the image in N distinct, stable palette
// colors, and the Combine verb appears here exactly as it does in Preview.

/// Loads the full artifact (list payloads omit geometry to stay lean) and
/// renders its line-level regions as clickable rows.
struct ArtifactRegionsSection: View {
    let artifactId: String
    let documentId: String

    @Environment(ArtifactService.self) private var artifactService: ArtifactService?
    /// (full-list index, box) pairs — the index is how the engine addresses a
    /// region for curation, so filtering must not renumber.
    @State private var rows: [(index: Int, box: OCRGeometryBox)] = []
    @State private var loaded = false
    @State private var selection = RegionSelection.shared
    /// The fetched artifact, kept so selecting a row can FOCUS it — the
    /// preview draws the focused artifact's boxes (2026-09-02, Daniel: "when
    /// I select multiple regions in artifacts browser, they're supposed to
    /// show up in preview"). Without the focus, the selection lit indices in
    /// an artifact the preview wasn't displaying, and nothing showed.
    @State private var fullArtifact: Artifact?

    var body: some View {
        Group {
            if !rows.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text("Regions")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        // How much of this geometry is a guess (2026-09-04).
                        // The overlay draws low-confidence boxes recessive and
                        // dashed; the number belongs somewhere countable too,
                        // because "some of them look faint" is not something a
                        // reader can act on.
                        if let doubt = OCRBoxConfidence.summary(for: rows.map(\.box)) {
                            Text(doubt)
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                                .lineLimit(1)
                                .help("These boxes are drawn dashed and dimmed: the machine is unsure where the word is")
                                .accessibilityIdentifier("regions.confidenceSummary")
                        }
                        Spacer(minLength: 0)
                        if selection.artifactId == artifactId, selection.count >= 2 {
                            Button("Combine") { combineSelected() }
                                .buttonStyle(.plain)
                                .font(.caption)
                                .foregroundStyle(Color.accentColor)
                                .help("Merge the selected regions: union box, texts in reading order")
                        }
                    }
                    .padding(.top, 6)
                    ForEach(rows, id: \.index) { row in
                        regionRow(row)
                    }
                }
            }
        }
        .task(id: artifactId) {
            await loadBoxes()
        }
    }

    @ViewBuilder
    private func regionRow(_ row: (index: Int, box: OCRGeometryBox)) -> some View {
        let isSelected = selection.isSelected(row.index, in: artifactId)
        Button {
            selection.toggle(row.index, artifactId: artifactId, documentId: documentId)
            // Selecting (not deselecting) still drives the reader/preview
            // word-linking seam, as before — and FOCUSES this artifact so
            // the preview is drawing the boxes the selection indexes into.
            if !isSelected {
                if let fullArtifact {
                    FocusedArtifact.shared.select(
                        artifactId, documentId: documentId, in: [fullArtifact]
                    )
                }
                postSelection(row.box)
            }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: isSelected ? "rectangle.inset.filled" : "rectangle.dashed")
                    .foregroundStyle(
                        isSelected
                            ? RegionPalette.color(forBoxIndex: row.index)
                            : Color.accentColor
                    )
                    .font(.caption)
                Text(row.box.text.isEmpty ? "Untitled region" : row.box.text)
                    .lineLimit(1)
                    .truncationMode(.tail)
                Spacer(minLength: 0)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help("Select this region — it highlights in the Preview; click again to deselect")
    }

    /// LINE-level rows only: word rows would be one row per word — noise. The
    /// click highlights the line's WORDS via the span the line covers.
    /// Region-level boxes (hand-drawn / combined) list alongside lines: they
    /// are exactly the objects region curation is about.
    private func loadBoxes() async {
        loaded = false
        rows = []
        guard let artifactService else { return }
        guard let full = try? await artifactService.getArtifact(id: artifactId),
              let geometry = full.ocrGeometry else { return }
        fullArtifact = full
        let indexed = geometry.boxes.enumerated().map { (index: $0.offset, box: $0.element) }
        let lines = indexed.filter {
            ($0.box.level == "line" || $0.box.level == "region") && !$0.box.text.isEmpty
        }
        // A geometry with no line tier (older artifacts) falls back to
        // whatever it has, capped so a word-level dump can't flood the panel.
        rows = lines.isEmpty
            ? Array(indexed.filter { !$0.box.text.isEmpty }.prefix(60))
            : lines
        loaded = true
    }

    /// COMBINE from the attribute browser — the same audited engine action as
    /// the Preview's verb; the merged list reloads from the response.
    private func combineSelected() {
        guard let artifactService,
              selection.artifactId == artifactId, selection.count >= 2 else { return }
        let indices = selection.indices
        Task {
            do {
                _ = try await artifactService.combineRegions(
                    artifactId: artifactId, documentId: documentId, indices: indices
                )
                selection.invalidate(artifactId: artifactId)
                await loadBoxes()
            } catch {
                // The section has no error surface; the log is the witness —
                // the list simply keeps its pre-combine rows.
                Logger(subsystem: "app.fichero.fichero", category: "ArtifactRegionsSection")
                    .error("Region combine failed: \(String(describing: error))")
            }
        }
    }

    private func postSelection(_ box: OCRGeometryBox) {
        var userInfo: [String: Any] = ["documentId": documentId, "text": box.text]
        if let start = box.charStart, let end = box.charEnd {
            userInfo["charStart"] = start
            userInfo["charEnd"] = end
        }
        NotificationCenter.default.post(
            name: .readerTextSelection, object: nil, userInfo: userInfo
        )
    }
}
