//
//  StoppedAtQuitAlert.swift
//  Fichero
//
//  The ONE alert at launch for the work the quit left unfinished (`activity.launch.nothing-starts-one-alert`, #6584;
//  owner 2026-11-13): the engine paused it all on open and starts nothing; the person chooses Leave Paused (the
//  default), Choose… (Activity) or Continue All. Shown once per launch.
//

import Foundation
import Observation
import OSLog

@MainActor
@Observable
final class StoppedAtQuitAlert {
    /// One stopped row, with the project it belongs to.
    struct Item: Equatable, Identifiable {
        let libraryId: UUID
        let jobId: String
        let name: String
        var id: String { "\(libraryId.uuidString)|\(jobId)" }
    }

    private(set) var items: [Item] = []
    var isPresented = false
    /// Projects already asked this launch: each is asked once, when it opens.
    @ObservationIgnored private var asked: Set<UUID> = []
    private let log = Logger(subsystem: "app.fichero", category: "StoppedAtQuitAlert")

    /// The alert's title, by the count: "3 runs were stopped when Fichero quit".
    static func title(count: Int) -> String {
        count == 1 ? "1 run was stopped when Fichero quit" : "\(count) runs were stopped when Fichero quit"
    }

    /// The alert's message: the names, at most five, then "and N more"; and the one sentence that says nothing runs.
    static func message(names: [String]) -> String {
        var lines = Array(names.prefix(5))
        if names.count > 5 { lines.append("and \(names.count - 5) more") }
        lines.append("Nothing runs until you choose. Leave Paused keeps them in Activity with Continue.")
        return lines.joined(separator: "\n")
    }

    var title: String { Self.title(count: items.count) }
    var message: String { Self.message(names: items.map(\.name)) }

    /// Ask each newly opened project what the quit stopped; present when anything was.
    func check(libraries: [LibraryManager.LibraryReference]) async {
        for library in libraries where !asked.contains(library.id) {
            asked.insert(library.id)
            do {
                let stopped = try await library.activityService.stoppedAtQuit()
                items += stopped.map { Item(libraryId: library.id, jobId: $0.id, name: $0.name) }
            } catch {
                log.error("stopped-at-quit read failed: \(error.localizedDescription, privacy: .public)")
            }
        }
        if !items.isEmpty { isPresented = true }
    }

    /// Leave Paused (the default): the rows stay paused in Activity; nothing is sent.
    func leavePaused() {
        isPresented = false
        items = []
    }

    /// Continue All: every project's stopped rows are let go.
    func continueAll(libraries: [LibraryManager.LibraryReference]) async {
        let wanted = Set(items.map(\.libraryId))
        for library in libraries where wanted.contains(library.id) {
            do {
                _ = try await library.activityService.continueAfterQuit(ids: nil, all: true)
            } catch {
                log.error("continue after quit failed: \(error.localizedDescription, privacy: .public)")
            }
        }
        leavePaused()
    }
}
