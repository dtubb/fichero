import Foundation

/// How background work runs on this Mac (`activity.mode.start-stop`, #5621).
    var mode: ActivityMode = .automatic
    /// This Mac's state as the engine's throttle reads it (`activity.popover.summary`).
    var machine: Components.Schemas.MachineState?
    /// The engine's one summary of the live blocks, the background group and History
    /// (`activity.popover.same-summary`, #5852): the window and the popover both read it.
    var activity: Components.Schemas.ActivitySummary?
}

/// How background work runs on this Mac (`activity.mode.start-stop`, #5621):
/// the engine's `mode`, set by the one Start / Stop control in the main
/// toolbar and the Activity window (`PUT /api/activity/jobs/mode`).
enum ActivityMode: String, Equatable, CaseIterable {
    /// Heavy work waits while the person uses the Mac or it is on battery.
    case automatic
    /// Start: it goes ahead anyway (memory and heat still hold it) until set back.
    case started
    /// Stop: Pause Background Work.
    case paused

    /// The engine's word; an unknown one reads as automatic (the engine's own default).
    init(engine raw: String?) {
        self = raw.flatMap(ActivityMode.init(rawValue:)) ?? .automatic
    }
}
