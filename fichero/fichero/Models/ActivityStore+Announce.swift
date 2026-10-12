import SwiftUI

/// VoiceOver hears work start, finish and fail (#3724, `activity.voiceover-announcements`): a sighted person watches
/// a bar move; a VoiceOver user heard nothing, then had to go and look. The announcement is a side effect of the jobs
/// read landing in the store (every kind of work reports there: imports, indexing, Kraken and model pages, runs), at
/// the transitions only, never on a progress tick.
extension ActivityStore {
    /// What to announce for one jobs read, or nil. `before` is nil on the first read: what was already under way when
    /// the app looked is not news. Only jobs of their own (a page's step under a run would be chatter). Several
    /// changes in one read are one announcement.
    static func announcement(from before: [ActivityJob]?, to after: [ActivityJob]) -> String? {
        guard let before else { return nil }
        let was = Dictionary(before.filter { $0.parentId == nil }.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        var said: [String] = []
        for job in after where job.parentId == nil {
            let earlier = was[job.id]
            switch job.state {
            case .running where earlier == nil || earlier?.state == .waiting:
                said.append("\(job.name) started")
            case .failed where earlier?.state != .failed:
                said.append("\(job.name) failed" + (job.reason.map { ": \($0)" } ?? ""))
            case .completed where earlier.map { $0.state != .completed } ?? false:
                said.append("\(job.name) finished")
            default:
                break
            }
        }
        // A job that was under way and left the list has finished (a finished job is not listed).
        let listed = Set(after.map(\.id))
        for job in before where job.parentId == nil && job.state.isActive && !listed.contains(job.id) {
            said.append("\(job.name) finished")
        }
        return said.isEmpty ? nil : said.joined(separator: ". ")
    }

    /// The announcement, as VoiceOver speaks it (when no `announce` seam is set). Explicitly main-actor: it posts
    /// to the accessibility system, so an off-main call is a compile error, never a runtime trap.
    @MainActor
    static func postAnnouncement(_ text: String) {
        AccessibilityNotification.Announcement(text).post()
    }
}
