import SwiftUI

// MARK: - An automation row's verbs, one component each (#5712, #5652 slice 4)

// A schedule's Pause, Resume and Run Now, a trigger's Pause and Resume, and a batch's Pause, Resume and Cancel are
// the engine's own actions (`/api/schedules/{id}/pause|resume|trigger`, `/api/triggers/{id}/pause|resume`,
// `/api/batches/{id}/pause|resume|cancel`), through `AutomationAPIService` and `BatchService`. Each is ONE item: the
// row's menu renders it on its row, and Project › Workflows ▸ renders it on the sidebar's selected automation row
// (`AutomationVerbsTarget`), each disabled with its reason under it. They used to be offered with no action behind
// them (#5712).

/// A verb an automation row offers.
enum AutomationVerb: String, CaseIterable, Equatable {
    case pause, resume, runNow, cancel

    var title: String {
        switch self {
        case .pause: "Pause"
        case .resume: "Resume"
        case .runNow: "Run Now"
        case .cancel: "Cancel Batch"
        }
    }

    var systemImage: String {
        switch self {
        case .pause: "pause"
        case .resume: "play"
        case .runNow: "play.fill"
        case .cancel: "xmark.circle"
        }
    }
}

/// What a row's kind and state allow, and the engine call for each. Pure where it can be.
enum AutomationVerbs {
    /// The verbs a row offers now, in menu order: a schedule that runs can be paused or run now, a paused one
    /// resumed; a trigger that watches paused, a paused one resumed; a batch that runs or waits paused or
    /// cancelled, a paused one resumed. Anything else (a finished batch, a document) offers none.
    static func offered(for itemType: SidebarItem.ItemType) -> [AutomationVerb] {
        switch itemType {
        case .schedule(let schedule):
            switch schedule.status {
            case "active": [.pause, .runNow]
            case "paused": [.resume]
            default: []
            }
        case .trigger(let trigger):
            switch trigger.status {
            case "active": [.pause]
            case "paused": [.resume]
            default: []
            }
        case .batch(let batch):
            switch batch.status {
            case "running", "pending": [.pause, .cancel]
            case "paused": [.resume, .cancel]
            default: []
            }
        default:
            []
        }
    }

    /// The engine's action for a verb on a row; throws its refusal.
    @MainActor
    static func perform(_ verb: AutomationVerb, on itemType: SidebarItem.ItemType,
                        automation: AutomationAPIService, batches: BatchService) async throws {
        switch (itemType, verb) {
        case (.schedule(let schedule), .pause): _ = try await automation.pauseSchedule(scheduleId: schedule.scheduleId)
        case (.schedule(let schedule), .resume): _ = try await automation.resumeSchedule(scheduleId: schedule.scheduleId)
        case (.schedule(let schedule), .runNow): _ = try await automation.triggerSchedule(scheduleId: schedule.scheduleId)
        case (.trigger(let trigger), .pause): _ = try await automation.pauseTrigger(triggerId: trigger.triggerId)
        case (.trigger(let trigger), .resume): _ = try await automation.resumeTrigger(triggerId: trigger.triggerId)
        case (.batch(let batch), .pause): _ = try await batches.pauseBatch(batchId: batch.batchId)
        case (.batch(let batch), .resume): try await batches.resumeBatch(batchId: batch.batchId)
        case (.batch(let batch), .cancel): _ = try await batches.cancelBatch(batchId: batch.batchId)
        default: throw AutomationVerbError.notOffered(verb)
        }
    }

    /// Why a verb cannot act on the selected row, or nil when it can.
    static func reason(_ verb: AutomationVerb, _ target: AutomationVerbsTarget?) -> String? {
        guard let target else { return "Select a schedule, trigger or batch in the sidebar" }
        return target.offered.contains(verb) ? nil : "This \(target.kind) cannot \(verb.title.lowercased()) now"
    }
}

enum AutomationVerbError: LocalizedError, Equatable {
    case notOffered(AutomationVerb)

    var errorDescription: String? {
        switch self {
        case .notOffered(let verb): "\(verb.title) is not offered for this row"
        }
    }
}

/// One automation row as its verbs see it. Equatable on what the menu shows, never on the action.
struct AutomationVerbsTarget: Equatable {
    let rowId: String
    /// "schedule", "trigger" or "batch", for the reasons.
    let kind: String
    let offered: [AutomationVerb]
    let perform: @MainActor (AutomationVerb) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.rowId == rhs.rowId && lhs.offered == rhs.offered
    }
}

extension FocusedValues {
    /// The sidebar's selected automation row.
    @Entry var automationVerbs: AutomationVerbsTarget?
}

/// One automation verb, as ONE item: the row's menu and Project › Workflows ▸.
struct AutomationVerbMenuItem: View {
    let verb: AutomationVerb
    let target: AutomationVerbsTarget?

    var body: some View {
        Button { target?.perform(verb) } label: { Label(verb.title, systemImage: verb.systemImage) }
            .disabled(AutomationVerbs.reason(verb, target) != nil)
    }
}

/// Project › Workflows ▸'s automation verbs on the sidebar's selected automation row, each disabled with its reason.
struct FocusedAutomationVerbButtons: View {
    @FocusedValue(\.automationVerbs) private var target

    var body: some View {
        ForEach(AutomationVerb.allCases, id: \.self) { verb in
            AutomationVerbMenuItem(verb: verb, target: target)
        }
        if let reason = target == nil ? AutomationVerbs.reason(.pause, nil) : nil {
            Text(reason)
        }
    }
}
