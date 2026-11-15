//
//  StoppedAtQuitAlert.swift
//  Fichero
//
//  The ONE alert at launch for the work the quit left unfinished (`activity.launch.nothing-starts-one-alert`, #6584;
//  owner 2026-11-13): the engine paused it all on open and starts nothing; the person chooses Leave Paused (the
//  default), Choose… (Activity), Continue All or Delete All (owner 2026-11-14 evening; undoable, as every Delete).
//  Shown once per launch. On the Mac it is an AppKit alert sheet: SwiftUI's alert there shows three buttons and
//  silently drops a fourth, so Delete All never appeared (seen 2026-11-14 night, #6584).
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
        /// The engine's kind of work: the automatic kinds roll into one line, a synced folder's read into another.
        var kind: String = ""
        var id: String { "\(libraryId.uuidString)|\(jobId)" }
    }

    /// The kinds the import queues by itself (thumbnails, search, names): one rolled-up line in the alert, not a row each
    /// (the review's answer 3: "… and background work: 412 thumbnails, 80 embeds").
    static let automaticKinds: Set<String> = ["thumbnail", "embedding", "embed", "nlp-draft", "nlp"]
    /// A synced folder's read the open held (`jobs.NEW_MATERIAL_REASON`): "New files in a synced folder".
    static let newMaterialKind = "read-from-folder"

    /// The alert's four answers, in the order shown; Leave Paused is the default (Return).
    enum Choice: CaseIterable {
        case leavePaused, choose, continueAll, deleteAll

        var title: String {
            switch self {
            case .leavePaused: "Leave Paused"
            case .choose: "Choose…"
            case .continueAll: "Continue All"
            case .deleteAll: "Delete All"
            }
        }
        var isDestructive: Bool { self == .deleteAll }
    }

    private(set) var items: [Item] = []
    var isPresented = false
    /// Projects already asked this launch: each is asked once, when it opens.
    @ObservationIgnored private var asked: Set<UUID> = []
    private let log = Logger(subsystem: "app.fichero.fichero", category: "StoppedAtQuitAlert")

    /// The alert's title, by the count: "3 runs were stopped when Fichero quit"; with no runs, what was: never "0 runs".
    static func title(count: Int, background: Bool = true) -> String {
        switch count {
        case 0: background ? "Background work was stopped when Fichero quit" : "New files are waiting in a synced folder"
        case 1: "1 run was stopped when Fichero quit"
        default: "\(count) runs were stopped when Fichero quit"
        }
    }

    /// The alert's message: the runs' names, at most five, then "and N more"; the automatic work rolled into one line
    /// ("and background work: 412 thumbnails, 80 embeds"); a synced folder's held read as "New files in a synced folder";
    /// and the one sentence that says nothing runs.
    static func message(names: [String]) -> String { message(items: names.map { ($0, "") }) }

    static func message(items: [(name: String, kind: String)]) -> String {
        let runs = items.filter { !automaticKinds.contains($0.kind) && $0.kind != newMaterialKind }
        var lines = Array(runs.map(\.name).prefix(5))
        if runs.count > 5 { lines.append("and \(runs.count - 5) more") }
        let background = items.filter { automaticKinds.contains($0.kind) }
        if !background.isEmpty {
            let counts = Dictionary(grouping: background, by: \.kind).map { kind, rows in
                "\(rows.count) \(Self.word(for: kind, count: rows.count))"
            }
            lines.append((runs.isEmpty ? "Background work: " : "and background work: ") + counts.sorted().joined(separator: ", "))
        }
        let folders = items.filter { $0.kind == newMaterialKind }.count
        if folders > 0 { lines.append(folders == 1 ? "New files in a synced folder" : "New files in \(folders) synced folders") }
        lines.append("Nothing runs until you choose. Leave Paused keeps them in Activity with Continue.")
        return lines.joined(separator: "\n")
    }

    /// The kind's word by its count: "1 embed", "80 embeds", never "1 embeds".
    private static func word(for kind: String, count: Int) -> String {
        let one = count == 1
        switch kind {
        case "thumbnail": return one ? "thumbnail" : "thumbnails"
        case "embedding", "embed": return one ? "embed" : "embeds"
        default: return one ? "names draft" : "names drafts"
        }
    }

    /// The runs the title counts: the automatic rows roll into their one line, so they are not "runs".
    var title: String {
        Self.title(count: items.filter { !Self.automaticKinds.contains($0.kind) && $0.kind != Self.newMaterialKind }.count,
                   background: items.contains { Self.automaticKinds.contains($0.kind) })
    }
    var message: String { Self.message(items: items.map { ($0.name, $0.kind) }) }

    /// Ask each newly opened project what the quit stopped; present when anything was.
    func check(libraries: [LibraryManager.LibraryReference]) async {
        for library in libraries where !asked.contains(library.id) {
            asked.insert(library.id)
            do {
                let stopped = try await library.activityService.stoppedAtQuit()
                items += stopped.map { Item(libraryId: library.id, jobId: $0.id, name: $0.name, kind: $0.kind) }
            } catch {
                log.error("stopped-at-quit read failed: \(error.localizedDescription, privacy: .public)")
            }
        }
        if !items.isEmpty { isPresented = true }  // automatic-only work still asks: the owner decides what starts
    }

    /// One answer carried out. Choose… leaves the rows paused and opens Activity through `openActivity`.
    func answer(_ choice: Choice, libraries: [LibraryManager.LibraryReference], steps: WindowSteps?,
                openActivity: () -> Void) async {
        switch choice {
        case .leavePaused: leavePaused()
        case .choose:
            leavePaused()
            openActivity()
        case .continueAll: await continueAll(libraries: libraries)
        // The alert is mounted above the window's own environment, where no WindowSteps is injected: without the front
        // window's steps Delete All went to no undo stack and Edit › Undo could not put the rows back.
        case .deleteAll: await deleteAll(libraries: libraries, steps: steps ?? WindowState.front?.steps)
        }
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

    /// Delete All: every stopped row is deleted through the one audited `job.delete`, per project, one step on the
    /// window's stack so Edit › Undo puts them back paused (`job.undelete`, `activity.pane.row-actions-on-the-table`).
    func deleteAll(libraries: [LibraryManager.LibraryReference], steps: WindowSteps?) async {
        for library in libraries {
            let ids = items.filter { $0.libraryId == library.id }.map(\.jobId)
            guard !ids.isEmpty else { continue }
            _ = await library.activityStore.performUndoable(
                "job.delete", ids: ids, named: UndoableChange.named("Delete", count: ids.count, one: "Row", many: "Rows"),
                actions: library.actionsService, steps: steps)
        }
        leavePaused()
    }
}
