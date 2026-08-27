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

/// Loads the full artifact (list payloads omit geometry to stay lean) and
/// renders its line-level regions as clickable rows.
struct ArtifactRegionsSection: View {
    let artifactId: String
    let documentId: String

    @Environment(ArtifactService.self) private var artifactService: ArtifactService?
    @State private var boxes: [OCRGeometryBox] = []
    @State private var loaded = false

    var body: some View {
        Group {
            if !boxes.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Regions")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .padding(.top, 6)
                    ForEach(boxes) { box in
                        Button {
                            postSelection(box)
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: "rectangle.dashed")
                                    .foregroundStyle(Color.accentColor)
                                    .font(.caption)
                                Text(box.text)
                                    .lineLimit(1)
                                    .truncationMode(.tail)
                                Spacer(minLength: 0)
                            }
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .help("Highlight this region's word boxes in the Preview")
                    }
                }
            }
        }
        .task(id: artifactId) {
            await loadBoxes()
        }
    }

    /// LINE-level rows only: word rows would be one row per word — noise. The
    /// click highlights the line's WORDS via the span the line covers.
    private func loadBoxes() async {
        loaded = false
        boxes = []
        guard let artifactService else { return }
        guard let full = try? await artifactService.getArtifact(id: artifactId),
              let geometry = full.ocrGeometry else { return }
        let lines = geometry.boxes.filter { $0.level == "line" && !$0.text.isEmpty }
        // A geometry with no line tier (older artifacts) falls back to
        // whatever it has, capped so a word-level dump can't flood the panel.
        boxes = lines.isEmpty ? Array(geometry.boxes.filter { !$0.text.isEmpty }.prefix(60)) : lines
        loaded = true
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
