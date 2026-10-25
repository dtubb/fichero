import SwiftUI

/// A recipe run's details by Set Up's stages (#5670, §7c): one card per stage, in Set Up's order, each with its state,
/// a bar of its pages, what it made ("Read 91 of 92 pages", "73 People · 69 Places") and, when it did not run, why in
/// one short sentence under it, with Open Set Up… at that stage when setup can fix it. Never a step id.
struct ActivityDetailsStageCards: View {
    let cards: [ActivityDetails.StageCard]
    let perform: (ActivityDetails.Action) -> Void
    /// A stage's Read Again target (`ActivityRunMenuTarget.stage`), for the shared item (#5652).
    let readAgain: (_ threadId: String, _ offer: String) -> ActivityRunMenuTarget

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Stages").font(.headline)
            ForEach(cards) { card in
                cardView(card)
            }
        }
        .accessibilityIdentifier("activity.details.stageCards")
    }

    /// What the stage made, and each of its readers when it reads with several (#6134).
    @ViewBuilder
    private func stageLines(_ card: ActivityDetails.StageCard) -> some View {
        ForEach(card.made, id: \.self) { line in
            Text(line).font(.callout)
        }
        ForEach(card.readers, id: \.self) { line in
            Text(line).font(.callout).foregroundStyle(.secondary)
        }
    }

    private func cardView(_ card: ActivityDetails.StageCard) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Image(systemName: Self.symbol(card.state))
                    .foregroundStyle(Self.tint(card.state))
                Text(card.title).font(.body.weight(.semibold))
                Spacer()
                Text(card.stateWords)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(Self.tint(card.state))
            }
            if card.total > 0 {
                ProgressView(value: Double(min(card.done, card.total)), total: Double(card.total)) {
                    EmptyView()
                } currentValueLabel: {
                    Text("\(card.done) of \(card.total) pages").monospacedDigit()
                }
                .controlSize(.small)
                .tint(card.state == .failed ? .red : .accentColor)
            }
            stageLines(card)
            if let failed = card.failed {
                HStack(alignment: .firstTextBaseline) {
                    Label(failed.text, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
                    if let offer = failed.offer {
                        ActivityReadAgainMenuItem(target: readAgain(failed.threadId, offer))
                            .labelStyle(.titleOnly)
                            .controlSize(.small)
                    }
                }
                .font(.callout)
            }
            if let why = card.why {
                Text(why)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
            }
            if card.offersSetUp {
                Button("Open Set Up…") { perform(.openSetUp(stage: card.id)) }
                    .controlSize(.small)
                    .accessibilityIdentifier("activity.details.stage.\(card.id).setUp")
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.secondary.opacity(0.08)))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("activity.details.stage.\(card.id)")
    }

    static func symbol(_ state: ActivityStageCardState) -> String {
        switch state {
        case .done: "checkmark.circle.fill"
        case .partial: "exclamationmark.circle.fill"
        case .running: "play.circle.fill"
        case .waiting: "hourglass"
        case .notRun: "minus.circle"
        case .skipped: "arrow.uturn.right.circle"
        case .failed: "exclamationmark.triangle.fill"
        case .unknown: "questionmark.circle"
        }
    }

    static func tint(_ state: ActivityStageCardState) -> Color {
        switch state {
        case .done: .green
        case .running: .accentColor
        case .failed: .red
        case .partial: .orange
        case .waiting, .notRun, .skipped, .unknown: .secondary
        }
    }
}

#Preview("A finished recipe run, by stage") {
    ScrollView {
        ActivityDetailsStageCards(cards: [
            .init(id: "prepare-images", title: "Prepare Images", state: .done, done: 92, total: 92, made: [],
                  why: nil, offersSetUp: false, failed: nil, pagesFailed: 0),
            .init(id: "read", title: "Read", state: .done, done: 91, total: 92, made: ["Read 91 of 92 pages"],
                  why: nil, offersSetUp: false,
                  failed: .init(id: "w1", text: "1 page failed", offer: "Read Again", threadId: "w1"), pagesFailed: 1),
            .init(id: "names", title: "Names", state: .done, done: 92, total: 92,
                  made: ["73 People · 69 Places · 18 Organisations"], why: nil, offersSetUp: false, failed: nil, pagesFailed: 0),
            .init(id: "dates", title: "Dates & Times", state: .done, done: 92, total: 92, made: ["0 dates"],
                  why: nil, offersSetUp: false, failed: nil, pagesFailed: 0),
            .init(id: "statements", title: "Statements", state: .skipped, done: 0, total: 0, made: [],
                  why: "No model for Find statements.", offersSetUp: true, failed: nil, pagesFailed: 0)
        ], perform: { _ in }, readAgain: { .stage(threadId: $0, offer: $1, store: nil, report: { _ in }) })
        .padding()
    }
    .frame(width: 420, height: 560)
}
