import Foundation

/// The Activity window's three groups, NOW / UP NEXT / DONE TODAY (`activity.window.three-groups`, #5960).
///
/// A run is ONE row (`activity.window.one-row-per-run`): only run rows and jobs of their own are listed here, never a
/// run's steps or pages (those are the bar's segments and the opened run's dots). A group with nothing in it is empty
/// and the view draws nothing for it.
struct ActivityWindowGroups: Equatable {
    /// What runs, or is paused (a paused run is still the person's current work).
    let now: [ActivityMonitorRow]
    /// What waits, in the order the lane will take it (`activity.window.up-next`).
    let upNext: [ActivityMonitorRow]
    /// What ended today, newest first.
    let doneToday: [ActivityMonitorRow]

    init(rows: [ActivityMonitorRow], now date: Date = Date(), calendar: Calendar = .current) {
        let listed = rows.filter { $0.kind == .run || $0.kind == .job }
        now = listed.filter { $0.phase == .running || $0.phase == .paused }
        upNext = listed.filter { $0.phase == .waiting }
            .sorted { ($0.queueKey, $0.startedKey) < ($1.queueKey, $1.startedKey) }
        doneToday = listed.filter { !$0.phase.isLive }
            .filter { row in row.started.map { calendar.isDate($0, inSameDayAs: date) } ?? false }
            .sorted { $0.startedKey > $1.startedKey }
    }

    var isEmpty: Bool { now.isEmpty && upNext.isEmpty && doneToday.isEmpty }
}

extension ActivityMonitorRow {
    /// The ONE button a row shows (`activity.window.one-button`). Stop, Show the Pages and Delete are context-menu items.
    enum OneButton: Equatable { case pause, resume, retry, show }

    var oneButton: OneButton? {
        switch phase {
        case .running: return jobId == nil ? nil : .pause
        case .paused: return jobId == nil ? nil : .resume
        case .waiting: return nil  // what does not apply is absent, never disabled
        case .failed, .partial, .interrupted, .cancelled: return retryJobId == nil ? .show : .retry
        case .done, .notRun, .unknown: return .show
        }
    }
}
