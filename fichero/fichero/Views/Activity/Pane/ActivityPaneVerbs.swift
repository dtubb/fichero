//
//  ActivityPaneVerbs.swift
//  Fichero
//
//  The one verb list (`activity.pane.row-actions-on-the-table`, #6441, #6583): which verbs each state allows (the spec's
//  states table), the Mail rule for several rows selected, the row's one button and the status bar's count of what was
//  skipped. Pure, so the states table is the test's fixture.
//

import Foundation

enum ActivityPaneVerb: String, CaseIterable, Identifiable {
    case pause, resume, stop, retry, archive, putBack, delete

    var id: String { rawValue }

    /// The one wording, the same in the context menu, Project › Activity and the row's button ("Continue", never "Resume").
    var title: String {
        switch self {
        case .pause: "Pause"
        case .resume: "Continue"
        case .stop: "Stop"
        case .retry: "Retry"
        case .archive: "Archive"
        case .putBack: "Put Back"
        case .delete: "Delete"
        }
    }

    var symbol: String {
        switch self {
        case .pause: "pause.fill"
        case .resume: "play.fill"
        case .stop: "stop.fill"
        case .retry: "arrow.counterclockwise"
        case .archive: "archivebox"
        case .putBack: "arrow.uturn.backward"
        case .delete: "trash"
        }
    }

    /// Whether this row's state allows the verb (the states table). Only a run or a job of its own takes a verb; a file row
    /// goes with its run.
    func allows(_ row: ActivityMonitorRow) -> Bool {
        guard row.kind == .run || row.kind == .job else { return false }
        if row.isArchived { return self == .putBack || self == .delete }
        let hasJob = row.jobId != nil
        // Pausing, stopping, resuming, retrying: the engine is part-way; only Stop and Delete apply.
        if row.transientState != nil { return (self == .stop && hasJob) || self == .delete }
        switch self {
        case .pause: return hasJob && (row.phase == .running || row.phase == .waiting)
        // A failure whose fix the engine says is to continue (a spend cap, a rate limit) continues too.
        case .resume: return hasJob && (row.phase == .paused || row.phase == .interrupted
                                        || (row.phase == .failed && row.failure?.actions.contains("resume") == true))
        case .stop: return hasJob && row.phase.isLive
        case .retry: return row.retryJobId != nil && [.failed, .cancelled, .partial].contains(row.phase)
        case .archive: return [.done, .failed, .cancelled, .partial].contains(row.phase)
        case .putBack: return false
        case .delete: return row.phase != .notRun && row.phase != .unknown
        }
    }

    /// The Mail rule: enabled when ANY selected row allows it.
    func isEnabled(for rows: [ActivityMonitorRow]) -> Bool { rows.contains(where: allows) }

    /// The rows it applies to, and how many it skips (the status bar says so: "Deleted 4 · 1 running, skipped").
    func split(_ rows: [ActivityMonitorRow]) -> (targets: [ActivityMonitorRow], skipped: Int) {
        let targets = rows.filter(allows)
        return (targets, rows.count - targets.count)
    }

    /// Delete on a running row is Stop then Delete, after one confirmation.
    static func deleteNeedsConfirmation(_ rows: [ActivityMonitorRow]) -> Bool {
        rows.contains { $0.phase == .running && delete.allows($0) }
    }

    /// The status bar's line for a verb done on a selection: "Deleted 4 · 1 skipped"; nil when nothing was done.
    static func outcome(_ verb: ActivityPaneVerb, done: Int, skipped: Int) -> String? {
        guard done > 0 || skipped > 0 else { return nil }
        let past: String = switch verb {
        case .pause: "Paused"
        case .resume: "Continued"
        case .stop: "Stopped"
        case .retry: "Retried"
        case .archive: "Archived"
        case .putBack: "Put back"
        case .delete: "Deleted"
        }
        return skipped > 0 ? "\(past) \(done) · \(skipped) skipped" : "\(past) \(done)"
    }
}

extension ActivityMonitorRow {
    /// The row's ONE button (`activity.pane.less-is-more-table`): a failed row's primary fix, else its state's verb
    /// (Pause, Continue, Retry); none when its state has no verb. Everything else is in the context menu.
    var paneButton: ActivityPaneButton? {
        if phase == .failed || phase == .partial || phase == .paused || phase == .interrupted,
           let action = failure?.primaryAction {
            if let button = ActivityPaneButton.forAction(action, row: self) { return button }
        }
        for verb in [ActivityPaneVerb.pause, .resume, .retry] where verb.allows(self) { return .verb(verb) }
        return nil
    }
}

/// What a row's one button does: a verb, the failure's fix in Settings, or a kept export's folder chosen again.
enum ActivityPaneButton: Equatable {
    case verb(ActivityPaneVerb)
    case settings
    /// Choose Folder… for the kept export whose folder is gone (`activity.kept-export.one-row-per-export`, #6588).
    case chooseFolder(export: String)
    /// An action the row cannot do itself: the row is selected and the Inspector shows its fix (`activity.pane.fix-button-has-words`).
    case showDetails

    /// The button for a failure's primary action as the engine names it (`llm/failure.ActionKind`), with its word; an action
    /// the row cannot carry out, or does not know, is Show Details, never a gear; nil when a verb the row allows fits better.
    static func forAction(_ action: String, row: ActivityMonitorRow) -> ActivityPaneButton? {
        switch action {
        case "open-settings", "choose-model": return .settings
        case "choose-folder": return row.failure?.folderFor.map { .chooseFolder(export: $0) } ?? .showDetails
        case "resume": return ActivityPaneVerb.resume.allows(row) ? .verb(.resume) : .showDetails
        case "retry": return ActivityPaneVerb.retry.allows(row) ? .verb(.retry) : .showDetails
        default: return .showDetails
        }
    }

    var title: String {
        switch self {
        case .verb(let verb): verb.title
        case .settings: "Settings…"
        case .chooseFolder: "Choose Folder…"
        case .showDetails: "Show Details"
        }
    }

    var symbol: String {
        switch self {
        case .verb(let verb): verb.symbol
        case .settings: "gearshape"
        case .chooseFolder: "folder"
        case .showDetails: "info.circle"
        }
    }
}
