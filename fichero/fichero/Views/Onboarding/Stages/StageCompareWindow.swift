import FicheroAPIClient
import SwiftUI

/// A page opened from Compare on These Pages (`source.onboard.stages.compare-results-per-model`, #5856): the page's
/// picture with each model's lines drawn on it, one model at a time or all side by side, and Use This One for each.
/// The picture comes by storage like every thumbnail (no local path); the shapes are the engine's, normalised to the
/// page, so they scale to any size.
struct StageCompareWindow: View {
    let pageId: String
    let name: String
    let candidates: [StageCandidate]
    var useThis: ((StageCandidate) -> Void)?
    @Environment(\.dismiss) private var dismiss
    /// nil: every model beside the others; a card: that model alone.
    @State private var only: String?

    private var shown: [StageCandidate] {
        candidates.filter { $0.perPage?.contains { $0.id == pageId } == true && (only == nil || $0.card == only) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(name).font(.headline)
                Spacer()
                Picker("Show", selection: $only) {
                    Text("Side by side").tag(String?.none)
                    ForEach(candidates, id: \.card) { Text($0.title).tag(String?.some($0.card)) }
                }
                .pickerStyle(.menu).fixedSize()
                Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
            }
            ScrollView(.horizontal) {
                HStack(alignment: .top, spacing: 12) {
                    ForEach(shown, id: \.card) { candidate in column(candidate) }
                }
            }
        }
        .padding()
        .frame(minWidth: 560, minHeight: 520)
    }

    @ViewBuilder
    private func column(_ candidate: StageCandidate) -> some View {
        let page = candidate.perPage?.first { $0.id == pageId }
        VStack(alignment: .leading, spacing: 6) {
            Text(candidate.title).font(.callout.weight(.medium))
            if let counts = page.flatMap({ SetupStageTryResult.countWords($0.segments ?? [:]) }) {
                Text(counts).font(.caption).foregroundStyle(.secondary)
            }
            LibraryImageView(documentId: pageId, imageType: .display)
                .aspectRatio(contentMode: .fit)
                .overlay { ShapesOverlay(shapes: page?.shapes ?? []) }
                .frame(minWidth: 240, maxWidth: 420)
            if let useThis {
                Button("Use This One") { useThis(candidate); dismiss() }
            }
        }
    }
}

/// A model's lines and regions drawn over a picture: boxes in the page's own fractions.
struct ShapesOverlay: View {
    let shapes: [SetupStageTryResult.Shape]

    var body: some View {
        Canvas { context, size in
            for shape in shapes where shape.bbox.count == 4 {
                let rect = CGRect(x: shape.bbox[0] * size.width, y: shape.bbox[1] * size.height,
                                  width: shape.bbox[2] * size.width, height: shape.bbox[3] * size.height)
                context.stroke(Path(rect), with: .color(shape.kind == "region" ? .orange : .blue), lineWidth: 1)
            }
        }
        .allowsHitTesting(false)
    }
}
