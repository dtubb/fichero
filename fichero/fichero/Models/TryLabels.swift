import FicheroAPIClient
import Foundation
import Observation

/// A try's readings on one page, labelled as a try's (`wide.try.shown-outside-set-up`): its stage, the day it ran and its model, never the
/// project's own and never a run's. The words are one place.
struct TryLabel: Equatable, Identifiable {
    let stage: String
    let ranAt: Date?
    let model: String?
    let lines: [String]

    var id: String { "\(stage)|\(ranAt?.timeIntervalSince1970 ?? 0)|\(model ?? "")" }

    /// "Try · read · 2 Nov · gemini-pro": what it is, when, and by which model.
    var title: String {
        var parts = ["Try", stage.replacingOccurrences(of: "-", with: " ")]
        if let ranAt { parts.append(ranAt.formatted(.dateTime.day().month(.abbreviated))) }
        if let model, !model.isEmpty { parts.append(model) }
        return parts.joined(separator: " · ")
    }

    static let note = "These readings came from a try. They are not yours until Start keeps them."
}

/// The tries kept for the page shown: read from the engine, which reads the kept copy and writes nothing.
@MainActor @Observable
final class TryLabelStore {
    private let client: FicheroClient
    let pageId: String
    private(set) var tries: [TryLabel] = []

    init(client: FicheroClient, pageId: String, tries: [TryLabel] = []) {
        self.client = client
        self.pageId = pageId
        self.tries = tries
    }

    func load() async {
        do {
            guard case .ok(let success) = try await client.api.triesOnPageApiRecipesTriesPagePageIdGet(path: .init(pageId: pageId)) else {
                return
            }
            tries = try success.body.json.tries.map {
                TryLabel(stage: $0.stage, ranAt: $0.ranAt.map { Date(timeIntervalSince1970: $0) }, model: $0.model,
                         lines: $0.readings.map(\.text))
            }
        } catch {
            if error.isCancellationError { return }
            tries = []  // no label is better than a wrong one
        }
    }
}
