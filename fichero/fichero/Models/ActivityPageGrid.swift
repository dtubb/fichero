import FicheroAPIClient
import Foundation

/// One dot per PAGE of a run for a chosen stage (`activity.window.page-grid`, #5960): done, running, waiting, failed, in
/// the order the lanes handled the pages (the engine's `GET /api/activity/jobs/{id}/pages`, which a person never has to
/// page through: the dots stand for them). Plain values, so what the grid says is checked without drawing it.
struct ActivityPageGrid: Equatable {
    /// `unknown`: a state this app does not know; drawn grey, never taken for done.
    enum Dot: Equatable { case done, running, waiting, failed, unknown }

    struct Page: Identifiable, Equatable {
        let id: String
        let name: String
        let dot: Dot
        /// What hovering says: the page, and for a failed or waiting one its reason in the engine's words.
        let help: String

        /// What VoiceOver says for the page: "p12.jpg, failed".
        var accessibilityLabel: String {
            let state = switch dot {
            case .done: "read"
            case .running: "reading"
            case .waiting: "waiting"
            case .failed: "failed"
            case .unknown: "not known"
            }
            return "\(name), \(state)"
        }
    }

    /// The one action that reaches the done pages without a pointer: the pages the grid shows (the run's, at most the 2,000 it
    /// reads) are selected in the project. Not "all pages": a project has more, and a long run more than the grid reads.
    static let showAllTitle = "Show the run's pages…"

    /// Most pages the grid offers an Open action for (a VoiceOver user does not step through 2,000 dots).
    static let actionLimit = 50

    /// The pages worth an action: the failed ones first, then running, then waiting, in the engine's order within each; the
    /// done ones are reached by clicking their dot.
    var actionPages: [Page] {
        let order: [Dot] = [.failed, .running, .waiting, .unknown]
        return order.flatMap { dot in pages.filter { $0.dot == dot } }.prefix(Self.actionLimit).map { $0 }
    }

    let pages: [Page]
    /// Pages in all for the stage; more than `pages` while the read is capped.
    let total: Int

    init(pages: [Page], total: Int) {
        self.pages = pages
        self.total = total
    }

    init(_ states: Components.Schemas.RunPageStates) {
        pages = states.items.map { item in
            let dot: Dot = switch item.state.rawValue {
            case "done": .done
            case "failed": .failed
            case "running": .running
            case "waiting": .waiting
            default: .unknown
            }
            let reason = item.reason?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let tells = dot == .failed || dot == .waiting
            return Page(id: item.documentId, name: item.name, dot: dot,
                        help: tells && !reason.isEmpty ? "\(item.name): \(reason)" : item.name)
        }
        total = states.total
    }

    /// The stages the chooser offers: the ones that ran (or are running), never one still waiting, not run, skipped or unknown.
    static func stagesThatRan(_ cards: [ActivityDetails.StageCard]) -> [ActivityDetails.StageCard] {
        cards.filter { [.done, .partial, .running, .failed].contains($0.state) }
    }

    var notShown: Int { max(0, total - pages.count) }

    func count(_ dot: Dot) -> Int { pages.filter { $0.dot == dot }.count }

    /// One VoiceOver label for the whole grid, in place of a stop per dot: "92 pages: 80 read, 3 failed, 9 waiting".
    var summary: String {
        let parts = [(count(.done), "read"), (count(.running), "reading"), (count(.failed), "failed"),
                     (count(.waiting), "waiting"), (count(.unknown), "not known")].filter { $0.0 > 0 }.map { "\($0.0) \($0.1)" }
        let shown = pages.count
        return "\(total) \(total == 1 ? "page" : "pages")" + (parts.isEmpty ? "" : ": " + parts.joined(separator: ", "))
            + (total > shown ? " (\(shown) shown)" : "")
    }
}
