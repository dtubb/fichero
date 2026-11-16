import FicheroAPIClient
import Foundation

/// A run as the window's one row (`activity.window.now-upnext-done-today`, #5960): a segmented stage bar, one segment a stage in Set
/// Up's order and filled as its pages finish, the section the run is in, and the one button whose label follows its state. Pure: the
/// engine's live block says the stages and their counts (`stages`); nothing is worked out from a step tree here.
struct ActivityOneBar: Equatable {
    enum Section: Equatable { case now, upNext, doneToday }
    enum Button: Equatable { case pause, resume, retry }

    struct Segment: Equatable, Identifiable {
        let id: String
        let title: String
        /// 0...1, the share of the stage's pages done; a finished stage is full, a stage not begun is empty.
        let fill: Double
        let state: String
        let failed: Int
    }

    let id: String
    let segments: [Segment]
    let section: Section
    let button: Button?

    init(block: Components.Schemas.LiveBlock) {
        id = block.id
        segments = (block.stages ?? []).map { stage in
            let total = stage.total ?? 0, done = stage.done ?? 0
            let fill: Double = stage.state == "done" ? 1 : (total > 0 ? min(1, Double(done) / Double(total)) : 0)
            return Segment(id: stage.stage, title: stage.title, fill: fill, state: stage.state, failed: stage.failed ?? 0)
        }
        section = Self.section(forState: block.state)
        button = Self.button(forState: block.state)
    }

    /// A working or paused run is NOW; a waiting one is UP NEXT; an ended one is DONE TODAY.
    static func section(forState state: String) -> Section {
        switch state {
        case "running", "paused", "stalled": .now
        case "waiting": .upNext
        default: .doneToday
        }
    }

    /// Pause a run that goes or waits, Resume one that is paused, Retry one that failed; none once it is done.
    static func button(forState state: String) -> Button? {
        switch state {
        case "running", "waiting", "stalled": .pause
        case "paused": .resume
        case "failed": .retry
        default: nil
        }
    }

    var buttonTitle: String? {
        switch button {
        case .pause: "Pause"
        case .resume: "Resume"
        case .retry: "Retry"
        case nil: nil
        }
    }
}
