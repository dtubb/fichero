import FicheroAPIClient
import Foundation

// Split out of ActivityPopoverSummary.swift by its type_body_length limit (ported from m-bugs-window-c16); behaviour unchanged.

extension ActivityPopoverSummary {
    /// "<model> · <where>" from the engine's own words; either alone; nil when it sends neither.
    static func subtitle(model: String?, place: String?) -> String? {
        let parts = [model, place].compactMap { $0?.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    /// The first UP NEXT lines: a waiting job its background line already says (same job, same name) is not said again
    /// (#6599); a run's stage always is.
    static func upNextLines(_ activity: Components.Schemas.ActivitySummary?, runName: (String) -> String?) -> [UpNextLine] {
        let waitingLines = Set((activity?.background ?? []).filter { $0.state == "waiting" }.map(\.name))
        return (activity?.upNext ?? []).filter { $0.runId != nil || !waitingLines.contains($0.name) }
            .prefix(upNextShown).map { upNextLine($0, runName: runName) }
    }

    /// What it waits for is the engine's `why`, as sent (it already says "after Read" and the like), never rebuilt here.
    static func upNextLine(_ item: Components.Schemas.UpNextItem, runName: (String) -> String? = { _ in nil }) -> UpNextLine {
        let run = item.runId.flatMap(runName)
        return UpNextLine(id: item.id, name: item.name, waiting: worded(item.why), run: run)
    }
}
