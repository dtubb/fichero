import Foundation

/// Whether a run can actually be shown, and why not when it can't (#4358).
///
/// "View Run" was enabled whenever an artifact's `runId` was merely non-nil, but
/// the action ALSO required it to be non-empty — so an artifact carrying an empty
/// run id rendered an enabled control that silently did nothing, the exact
/// pattern the codebase forbids. One pure resolver now answers both questions,
/// so the control's enablement and its action can never disagree.
enum RunTraceLink {
    /// The trace thread id, or nil when there is nothing to open. Blank strings
    /// are nothing: the engine wrote run provenance only from #4313 onward, and
    /// older rows carry null or "".
    static func threadId(_ raw: String?) -> String? {
        guard let trimmed = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty else { return nil }
        return trimmed
    }

    /// The hover reason for a control that cannot act — nil when it can. A
    /// disabled control with a reason beats an enabled control that does nothing.
    static func unavailableReason(_ raw: String?) -> String? {
        threadId(raw) == nil
            ? "This run wasn't recorded, so its trace can't be shown."
            : nil
    }

    /// Whether the "View Run" control should be interactive.
    static func canOpen(_ raw: String?) -> Bool {
        threadId(raw) != nil
    }
}
