//
//  ActivityPaneFixture.swift
//  FicheroTests
//
//  The Activity pane's test matrix fixture (docs/contributor_manual/specs/ui/activity-pane.md, Test matrix): a recipe run
//  with two steps over two pages, its Read step retried with another model; a second run touching one of the same pages.
//

@testable import Fichero
import Foundation

enum ActivityPaneFixture {
    typealias Row = ActivityMonitorRow

    static func row(_ id: String, _ phase: Row.Phase, kind: Row.Kind = .job, name: String? = nil, jobId: String? = "job",
                    model: String? = nil, documentId: String? = nil, started: Date? = nil, children: [Row]? = nil,
                    costUsd: Double? = nil, done: Int = 0, total: Int = 0) -> Row {
        var row = Row(id: id, kind: kind, libraryId: nil, runRowID: kind == .run ? id : nil, runThreadId: nil,
                      jobId: jobId.map { $0 == "job" ? id : $0 }, name: name ?? id, projectName: nil, phase: phase,
                      reason: nil, workingOn: nil, done: done, total: total, started: started, seconds: nil,
                      costUsd: costUsd, tokens: 0, errors: 0, model: model, isLive: phase.isLive, children: children)
        row.documentId = documentId
        return row
    }

    static func page(_ id: String, _ phase: Row.Phase, doc: String, model: String? = nil) -> Row {
        row(id, phase, kind: .page, name: "Page \(doc)", model: model, documentId: doc)
    }

    static let day = Date(timeIntervalSince1970: 1_800_000_000)

    /// "Letters": Segment over p1 and p2, then Read with Kraken (p2 failed), then Read again with Qwen (both done).
    static var letters: Row {
        row("letters", .done, kind: .run, name: "Letters", started: day, children: [
            row("seg", .done, kind: .step, name: "Segment", model: "Kraken",
                children: [page("seg-p1", .done, doc: "p1"), page("seg-p2", .done, doc: "p2")]),
            row("read1", .failed, kind: .step, name: "Read", model: "Kraken",
                children: [page("r1-p1", .done, doc: "p1", model: "Kraken"), page("r1-p2", .failed, doc: "p2", model: "Kraken")]),
            row("read2", .done, kind: .step, name: "Read", model: "Qwen 2 VL",
                children: [page("r2-p1", .done, doc: "p1", model: "Qwen 2 VL"), page("r2-p2", .done, doc: "p2", model: "Qwen 2 VL")])
        ], costUsd: 0.42)
    }

    /// "Names": a later run touching p2 only, running now.
    static var names: Row {
        row("names", .running, kind: .run, name: "Names", started: day.addingTimeInterval(3600), children: [
            row("ents", .running, kind: .step, name: "Names", model: "Claude",
                children: [page("n-p2", .running, doc: "p2", model: "Claude")])
        ])
    }
}
