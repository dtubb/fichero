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
        // A run is archived by the engine's run archive; until then only a job of its own takes Archive (never a delete).
        case .archive: return row.kind == .job && [.done, .failed, .cancelled, .partial].contains(row.phase)
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
            switch action {
            case "open-settings", "choose-model": return .settings
            case "resume" where ActivityPaneVerb.resume.allows(self): return .verb(.resume)
            default: break
            }
        }
        for verb in [ActivityPaneVerb.pause, .resume, .retry] where verb.allows(self) { return .verb(verb) }
        return nil
    }
}

/// What a row's one button does: a verb, or the failure's fix in Settings.
enum ActivityPaneButton: Equatable {
    case verb(ActivityPaneVerb)
    case settings

    var title: String {
        switch self {
        case .verb(let verb): verb.title
        case .settings: "Settings…"
        }
    }

    var symbol: String {
        switch self {
        case .verb(let verb): verb.symbol
        case .settings: "gearshape"
        }
    }
}
