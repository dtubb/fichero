import SwiftUI

/// A Set Up stage's picture of its work (#5668, `source.onboard.stages.shows-what-it-does`): played once as the page
/// appears, about 3 to 5 seconds, with Replay; with Reduce Motion, its last frame, still. Each stage's own view draws
/// one frame from a progress of 0 to 1; this plays them.
struct StageShowcaseView: View {
    let stageId: String
    let showcase: StageShowcase
    /// The size the picture is drawn at.
    var size = CGSize(width: 360, height: 220)

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var started = Date()

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            let duration = StageShowcasePlayback.duration(for: stageId)
            TimelineView(.animation(minimumInterval: 1 / 30, paused: reduceMotion)) { context in
                let progress = StageShowcasePlayback.progress(at: context.date, startedAt: started,
                                                              duration: duration, reduceMotion: reduceMotion)
                StageShowcaseCatalogue.picture(for: stageId, showcase: showcase, progress: progress)
                    .frame(width: size.width, height: size.height)
                    .background(Color(platformColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
                    .clipShape(RoundedRectangle(cornerRadius: 10))
            }
            HStack {
                ShowcaseCredit(showcase: showcase)
                Spacer()
                if !reduceMotion {
                    Button("Replay") { started = Date() }
                        .controlSize(.small)
                }
            }
            .frame(width: size.width)
        }
        .onAppear { started = Date() }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(StageShowcaseCatalogue.description(for: stageId))
        .accessibilityIdentifier("setup.stage.showcase")
    }
}

/// When a picture is: pure, so Reduce Motion's last frame and the timing are tested without a clock.
enum StageShowcasePlayback {
    /// How long a stage's picture plays: 3 to 5 seconds, the reading ones longest.
    static func duration(for stageId: String) -> TimeInterval {
        switch stageId {
        case "read", "structured-data", "statements": 4.5
        case "prepare-images", "translate", "normalise": 3.5
        default: 4
        }
    }

    /// The frame to draw: 0 at the start, 1 at the end, held there; always 1 with Reduce Motion.
    static func progress(at date: Date, startedAt start: Date, duration: TimeInterval, reduceMotion: Bool) -> Double {
        guard !reduceMotion, duration > 0 else { return 1 }
        return min(1, max(0, date.timeIntervalSince(start) / duration))
    }

    /// The part of the play between `from` and `to`, as 0 to 1, eased.
    static func phase(_ progress: Double, from: Double, to end: Double) -> Double {
        guard end > from else { return progress >= end ? 1 : 0 }
        let linear = min(1, max(0, (progress - from) / (end - from)))
        return linear * linear * (3 - 2 * linear)
    }
}

/// Every stage's picture, by the stage's id (`GET /api/recipes/stages`), and what it shows in words.
enum StageShowcaseCatalogue {
    /// The stages, in pipeline order; each has a picture.
    static let stageIds = ["prepare-images", "find-regions", "find-lines", "read", "normalise", "translate",
                           "organise", "names", "statements", "dates", "passages", "structured-data", "search",
                           "catalogue"]

    static func hasPicture(_ stageId: String) -> Bool { stageIds.contains(stageId) }

    /// What each picture shows, for VoiceOver and the tests.
    static let descriptions: [String: String] = [
        "prepare-images": "A tilted, dim scan straightens and brightens.",
        "find-regions": "The blocks of the page are outlined one after another.",
        "find-lines": "Each line's baseline is drawn from left to right.",
        "read": "The reading appears line by line beside the page.",
        "normalise": "An abbreviated word becomes its expanded form.",
        "translate": "A line becomes its translation.",
        "organise": "Pages slide together into the documents they belong to.",
        "names": "The names light up, coloured by kind.",
        "statements": "An arrow joins the names a statement links.",
        "dates": "The date words become dates.",
        "passages": "A passage lifts out of the page.",
        "structured-data": "Values from the page fill a table's cells.",
        "search": "A search lights its matches on the page.",
        "catalogue": "A folder's record fills in, field by field: title, dates, extent, scope and content."
    ]

    static func description(for stageId: String) -> String { descriptions[stageId] ?? "What this stage does." }

    /// The stages whose pictures work on the page itself; the others work on what it says.
    static let pageStages: Set<String> = ["prepare-images", "find-regions", "find-lines", "read", "normalise",
                                          "translate", "organise"]

    /// One frame of a stage's picture.
    @ViewBuilder
    static func picture(for stageId: String, showcase: StageShowcase, progress: Double) -> some View {
        if pageStages.contains(stageId) {
            pagePicture(for: stageId, showcase: showcase, progress: progress)
        } else {
            knowledgePicture(for: stageId, showcase: showcase, progress: progress)
        }
    }

    @ViewBuilder
    private static func pagePicture(for stageId: String, showcase: StageShowcase, progress: Double) -> some View {
        switch stageId {
        case "prepare-images": PrepareImagesPicture(showcase: showcase, progress: progress)
        case "find-regions": FindRegionsPicture(showcase: showcase, progress: progress)
        case "find-lines": FindLinesPicture(showcase: showcase, progress: progress)
        case "read": ReadPicture(showcase: showcase, progress: progress)
        case "normalise": NormalisePicture(showcase: showcase, progress: progress)
        case "translate": TranslatePicture(showcase: showcase, progress: progress)
        default: OrganisePicture(showcase: showcase, progress: progress)
        }
    }

    @ViewBuilder
    private static func knowledgePicture(for stageId: String, showcase: StageShowcase, progress: Double) -> some View {
        switch stageId {
        case "names": NamesPicture(showcase: showcase, progress: progress)
        case "statements": StatementsPicture(showcase: showcase, progress: progress)
        case "dates": DatesPicture(showcase: showcase, progress: progress)
        case "passages": PassagesPicture(showcase: showcase, progress: progress)
        case "structured-data": StructuredDataPicture(showcase: showcase, progress: progress)
        case "search": SearchPicture(showcase: showcase, progress: progress)
        case "catalogue": CataloguePicture(progress: progress)
        default: StagePageLayer(showcase: showcase) { _ in EmptyView() }
        }
    }
}

#Preview("Read, played") {
    if let example = StageShowcaseExample.bundled() {
        StageShowcaseView(stageId: "read", showcase: example.example.showcase(imageURL: example.imageURL))
            .padding()
    }
}
