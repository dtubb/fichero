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
    /// The wide Set Up's compare view on this page (`CompareReadersView`), shown under the candidates; nil off the flag.
    var readers: CompareReadersStore?
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
            if let readers { Divider(); CompareReadersView(store: readers) }
        }
        .padding()
        .frame(minWidth: 560, idealWidth: 960, maxWidth: .infinity, minHeight: 520, idealHeight: 720, maxHeight: .infinity)
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

    /// The caption of counts under a model's name goes in the wide Set Up: the picture and the model's own lines say it
    /// (`wide.compare.replaces-the-captions-and-the-animation`).
    nonisolated static func showsCountCaption(wide: Bool) -> Bool { !wide }

    /// The column's width as laid out; the pictures share it, or the strip says it scrolls (`output-visible-without-hunting`, #6402).
    @State private var columnWidth: CGFloat = 0

    private var fit: StageStripFit {
        columnWidth > 0 ? .layout(columnWidth: columnWidth, count: candidates.count, minimum: pictureWidth.lowerBound)
                        : .fits(pictureWidth: pictureWidth.upperBound)
    }

    var body: some View {
        let fit = fit
        VStack(alignment: .leading, spacing: 4) {
            if let cue = fit.cueWords {
                Text(cue).font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("setup.stage.stripCue")
            }
            ScrollView(.horizontal) {
                HStack(alignment: .top, spacing: 12) {
                    ForEach(candidates, id: \.card) { candidate in column(candidate, width: fit.pictureWidth) }
                }
            }
        }
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { columnWidth = $0 }
    }

    @ViewBuilder
    private func column(_ candidate: StageCandidate, width: CGFloat) -> some View {
        let page = candidate.perPage?.first { $0.id == pageId }
        VStack(alignment: .leading, spacing: 6) {
            Text(candidate.title).font(.callout.weight(.medium))
            if Self.showsCountCaption(wide: FeatureManager.shared.isWideSetUpEnabled),
               let counts = page.flatMap({ SetupStageTryResult.countWords($0.segments ?? [:]) }) {
                Text(counts).font(.caption).foregroundStyle(.secondary)
            }
            LibraryImageView(documentId: pageId, imageType: .display)
                .aspectRatio(contentMode: .fit)
                .overlay { ShapesOverlay(shapes: page?.shapes ?? []) }
                .frame(width: width)
            if let reading = page?.readings?.first?.text, !reading.isEmpty {
                Text(reading).font(.callout).lineLimit(8).textSelection(.enabled)
                    .frame(maxWidth: width, alignment: .leading)
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
