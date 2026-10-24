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
            StageCompareColumns(pageId: pageId, candidates: shown, useThis: useThis.map { use in { use($0); dismiss() } })
        }
        .padding()
        .frame(minWidth: 560, minHeight: 520)
    }
}

/// One page, every given model beside the others: the page's picture with the model's lines on it and its reading under
/// it (`source.onboard.stages.compare-side-by-side-inline`, #6034). Used inline under Compare on These Pages and in the
/// page's own window.
struct StageCompareColumns: View {
    let pageId: String
    let candidates: [StageCandidate]
    var useThis: ((StageCandidate) -> Void)?
    var pictureWidth: ClosedRange<CGFloat> = 240...420

    var body: some View {
        ScrollView(.horizontal) {
            HStack(alignment: .top, spacing: 12) {
                ForEach(candidates, id: \.card) { candidate in column(candidate) }
            }
        }
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
                .frame(minWidth: pictureWidth.lowerBound, maxWidth: pictureWidth.upperBound)
            if let reading = page?.readings?.first?.text, !reading.isEmpty {
                Text(reading).font(.callout).lineLimit(8).textSelection(.enabled)
                    .frame(maxWidth: pictureWidth.upperBound, alignment: .leading)
            }
            if let useThis {
                Button("Use This One") { useThis(candidate) }
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

#Preview("A page opened from Compare, no model's lines yet") {
    StageCompareWindow(pageId: "page-1", name: "f. 1r", candidates: [])
}
