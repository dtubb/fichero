import Foundation

/// The row's state, coarsely (moved out of ActivityMonitorModel.swift to keep that file under the length limit).
extension ActivityMonitorRow {
    /// The one line of a DONE TODAY row (`activity.window.done-today`): the engine's reason AS SENT plus the counts for a
    /// stopped run ("Stopped by you · 89 of 203 pages", "Stopped by you, through an agent (MCP) · …": the engine records who stopped it
    /// and says so; Swift never rewrites engine words), "Done · 14:02" for one that finished (partial and the rest keep the
    /// engine's words, never a green check). Pure over the row, so the wording is checked without drawing it.
    var endedLine: String {
        switch phase {
        case .cancelled:
            let counts = total > 0 ? ["\(done) of \(total) \(total == 1 ? "page" : "pages")"] : []
            return ([stateText] + counts).joined(separator: " · ")
        case .done where stateText == Phase.done.word:
            let time = ended.map { $0.formatted(date: .omitted, time: .shortened) }
            return [Phase.done.word, time].compactMap { $0 }.joined(separator: " · ")
        default:
            return [stateText, progressText].filter { !$0.isEmpty }.joined(separator: " · ")
        }
    }

    /// The state, coarsely, in the order the State column sorts it.
    enum Phase: Int {
        case running, waiting, paused, failed, cancelled, done
        /// Every state the engine reports has its own words (`activity.window.every-state-has-its-words`, #5957); a state
        /// nobody here knows is `unknown` and says so, never Done.
        case partial, interrupted, notRun, unknown

        init(engineState: String) {
            switch engineState.lowercased() {
            case "running", "stalled", "stopping", "pausing", "resuming", "retrying": self = .running  // transient: still live
            case "waiting", "accepted", "queued": self = .waiting
            case "paused": self = .paused
            case "failed", "error": self = .failed
            case "cancelled", "canceled", "stopped": self = .cancelled
            case "done", "completed", "complete", "finished": self = .done
            case "partial": self = .partial
            case "interrupted": self = .interrupted
            case "not run", "not_run", "skipped": self = .notRun
            default: self = .unknown
            }
        }

        init(_ status: ActivityRunStatus) {
            switch status {
            case .running: self = .running
            case .paused: self = .paused
            case .completed: self = .done
            case .failed: self = .failed
            case .cancelled: self = .cancelled
            case .unknown: self = .unknown
            }
        }

        init(_ state: ActivityJob.State) {
            switch state {
            case .running, .stalled: self = .running
            case .waiting: self = .waiting
            case .other(let name): self = Phase(engineState: name)
            case .paused: self = .paused
            case .failed: self = .failed
            case .completed: self = .done
            }
        }

        var word: String {
            switch self {
            case .running: "Running"
            case .waiting: "Waiting"
            case .paused: "Paused"
            case .failed: "Failed"
            case .cancelled: "Stopped"
            case .done: "Done"
            case .partial: "Partial"
            case .interrupted: "Interrupted"
            case .notRun: "Not run"
            case .unknown: "Unknown"
            }
        }

        /// The words for a state the engine is passing through, or nil for any other.
        static func transientWord(_ engineState: String?) -> String? {
            switch engineState?.lowercased() {
            case "stopping": "Stopping"
            case "pausing": "Pausing"
            case "resuming": "Resuming"
            case "retrying": "Retrying"
            default: nil
            }
        }

        var isLive: Bool { self == .running || self == .waiting || self == .paused }

        /// The state as an SF Symbol (#5560).
        var symbol: String {
            switch self {
            case .running: "play.circle.fill"
            case .waiting: "clock"
            case .paused: "pause.circle.fill"
            case .failed: "xmark.circle.fill"
            case .cancelled: "stop.circle.fill"
            case .done: "checkmark.circle.fill"
            case .partial: "exclamationmark.circle.fill"
            case .interrupted: "exclamationmark.triangle.fill"
            case .notRun: "minus.circle"
            case .unknown: "questionmark.circle"
            }
        }
    }
}
