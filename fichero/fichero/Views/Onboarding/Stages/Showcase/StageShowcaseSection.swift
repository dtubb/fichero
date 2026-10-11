import SwiftUI

/// The top of a Set Up stage page (#5668): what the stage does, played on a page (`source.onboard.stages.
/// shows-what-it-does`), and, when the engine compared candidates on the samples, the same page done by each of them
/// side by side with its measures and Use This (`source.onboard.stages.compares-candidates`). One candidate, or none
/// yet, is one picture.
struct StageShowcaseSection: View {
    let stageId: String
    let result: SetupStageTryResult?
    /// Use This: sets that candidate's card for the stage's step; nil when the stage has no step to set.
    var useThis: ((StageCandidate) -> Void)?

    /// The width the section has on a stage page.
    static let width: CGFloat = 440

    var body: some View {
        let columns = StageCandidate.columns(result?.candidates)
        if columns.count >= 2 {
            StageComparisonView(stageId: stageId, columns: columns, useThis: useThis)
        } else if let showcase = Self.showcase(result: result, single: columns.first) {
            StageShowcaseView(stageId: stageId, showcase: showcase)
        }
    }

    /// One picture's page: the one candidate's result, else the try's, else the example.
    static func showcase(result: SetupStageTryResult?, single: StageCandidate?) -> StageShowcase? {
        if let own = single?.showcase { return own }
        return StageShowcaseSource.showcase(for: result)
    }
}

/// A / B / C: the same sample page done by each candidate, its picture over its own result, its measures and Use This.
struct StageComparisonView: View {
    let stageId: String
    let columns: [StageCandidate]
    var useThis: ((StageCandidate) -> Void)?

    /// Each column's picture size, the section's width shared.
    static func pictureSize(columns: Int) -> CGSize {
        let count = CGFloat(max(1, columns))
        let width = (StageShowcaseSection.width - 10 * (count - 1)) / count
        return CGSize(width: width, height: min(220, width * 1.25))
    }

    var body: some View {
        let size = Self.pictureSize(columns: columns.count)
        HStack(alignment: .top, spacing: 10) {
            ForEach(columns) { candidate in
                VStack(alignment: .leading, spacing: 4) {
                    Text(candidate.title).font(.callout.weight(.medium)).lineLimit(1)
                    if let showcase = candidate.showcase ?? StageShowcaseSource.showcase(for: nil) {
                        StageShowcaseView(stageId: stageId, showcase: showcase, size: size)
                    }
                    ForEach(candidate.measures, id: \.self) { measure in
                        Text(measure).font(.caption).foregroundStyle(.secondary)
                    }
                    if let useThis {
                        Button("Use This") { useThis(candidate) }
                            .controlSize(.small)
                    }
                }
                .frame(width: size.width, alignment: .leading)
            }
        }
        .accessibilityIdentifier("setup.stage.comparison")
    }
}

#Preview("A / B comparison") {
    let json = """
    {"state":"done","candidates":[
      {"card":"kraken-catmus","name":"Kraken (CATMuS Medieval)","runs_on":"this-mac","local":true,"cer":0.041,"seconds":12,
       "per_page":[{"id":"p1","readings":[{"text":"enel tþo q́ el escriuio\\nnoseriadino de reprehension"}]}]},
      {"card":"qwen-vl","name":"Qwen2.5-VL 7B","runs_on":"cloud","local":false,"agreement":0.88,"seconds":30,
       "cost_usd":{"value":0.04,"basis":"estimate"},
       "per_page":[{"id":"p1","readings":[{"text":"en el tiempo que el escrivio\\nno seria digno de reprehension"}]}]}]}
    """
    let result = try? JSONDecoder().decode(SetupStageTryResult.self, from: Data(json.utf8))
    StageShowcaseSection(stageId: "read", result: result, useThis: { _ in })
        .padding()
}
