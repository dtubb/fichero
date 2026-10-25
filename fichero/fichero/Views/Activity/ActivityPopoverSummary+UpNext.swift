import FicheroAPIClient
import Foundation

// Split out of ActivityPopoverSummary.swift by its type_body_length limit (ported from m-bugs-window-c16); behaviour unchanged.

extension ActivityPopoverSummary {
    /// "<model> · <where>" from the engine's own words; either alone; nil when it sends neither.
    static func subtitle(model: String?, place: String?) -> String? {
        let parts = [model, place].compactMap { $0?.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    /// The window's UP NEXT lines: every project's `up_next` that is not already a row of the list, in the engine's order.
    /// `runName` says the name of a run by its job id (with its project when the list is grouped), for the item's `run_id`:
    /// two runs' stage lines must tell apart.
    static func upNextLines(_ summaries: [Components.Schemas.ActivitySummary], excluding rowIds: Set<String>,
                            runName: (String) -> String? = { _ in nil }) -> [UpNextLine] {
        summaries.flatMap { $0.upNext ?? [] }.filter { !rowIds.contains($0.id) }.map { upNextLine($0, runName: runName) }
    }

    /// What it waits for is the engine's `why`, as sent (it already says "after Read" and the like), never rebuilt here.
    static func upNextLine(_ item: Components.Schemas.UpNextItem, runName: (String) -> String? = { _ in nil }) -> UpNextLine {
        let run = item.runId.flatMap(runName)
        return UpNextLine(id: item.id, name: item.name, waiting: worded(item.why), run: run)
    }
}
