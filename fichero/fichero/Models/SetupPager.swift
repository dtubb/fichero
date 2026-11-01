import Foundation

/// The wide Set Up's pager (`wide.pager.*`, #5668): the move rules over the flow's steps, the label an assistive technology reads,
/// the columns' widths per platform and the page the window reopens on. Pure: a swipe, the arrow keys, ⌘[ ⌘] and the footer's Back
/// and Next all reduce to `advance` and `retreat` on this one model, so none of them can move differently.
struct SetupPager: Equatable {
    let steps: [SetupStep]
    private(set) var current: SetupStep

    init(steps: [SetupStep], current: SetupStep) {
        self.steps = steps
        self.current = steps.contains(current) ? current : (steps.first ?? current)
    }

    /// What a move did.
    enum Move: Equatable {
        /// Moved to this page.
        case moved(SetupStep)
        /// The page cannot be left yet: stay, with the reason said beside Next (`SetupFooter.waitsFor`).
        case bounced(reason: String)
        /// Already on the first or the last page: nothing moves (the last page's Next is Start or Done, not a swipe).
        case atEdge
    }

    /// One page on. `waitsFor` is the footer's reason the page cannot be left, nil when it can.
    mutating func advance(waitsFor: String? = nil) -> Move {
        guard let index = steps.firstIndex(of: current), index + 1 < steps.count else { return .atEdge }
        if let reason = waitsFor, !reason.isEmpty { return .bounced(reason: reason) }
        current = steps[index + 1]
        return .moved(current)
    }

    /// One page back; never held by a page's reason (going back loses nothing: a page's answers are kept).
    mutating func retreat() -> Move {
        guard let index = steps.firstIndex(of: current), index > 0 else { return .atEdge }
        current = steps[index - 1]
        return .moved(current)
    }

    /// The step list on the left jumps to any page.
    mutating func jump(to step: SetupStep) {
        if steps.contains(step) { current = step }
    }

    /// Whether a forward move saves the draft first (the page's Continue does).
    var savesDraftOnAdvance: Bool { current.savesDraft }

    /// "Step 3 of 9, Choose the Stages": the pager's one accessibility label, posted again on every page change
    /// (`wide.pager.accessible`).
    func label(stageTitles: [String: String] = [:]) -> String {
        let index = (steps.firstIndex(of: current) ?? 0) + 1
        return "Step \(index) of \(steps.count), \(current.title(stageTitles: stageTitles))"
    }

    /// "3 of 9": the compact layouts' replacement for the step list.
    var compactPosition: String { "\((steps.firstIndex(of: current) ?? 0) + 1) of \(steps.count)" }

    // MARK: Restoring the page

    /// The page a window reopens on: the one the person left (its `SetupStep.id`) when the flow still has it, else Choose the Stages
    /// (a stage dropped since), else the first page. Try results and answers are the engine's, never kept here.
    static func restored(savedId: String?, in steps: [SetupStep]) -> SetupStep {
        if let savedId, let kept = steps.first(where: { $0.id == savedId }) { return kept }
        if steps.contains(.stages) { return .stages }
        return steps.first ?? .welcome
    }

    // MARK: Motion

    enum Transition: Equatable {
        case slide
        /// Reduce Motion: a cross-fade, and a picture holds its last frame.
        case crossFade
    }

    static func transition(reduceMotion: Bool) -> Transition { reduceMotion ? .crossFade : .slide }

    // MARK: Widths

    enum Platform: Equatable {
        case mac
        /// iPad and iPhone.
        case compact
    }

    /// The window's and columns' sizes as pure values (`wide.pager.window-is-wide`).
    /// A forward move waits while a save or the project's creation runs: a second press must not move a second page.
    static func forwardHeld(isSaving: Bool, isCreating: Bool) -> Bool { isSaving || isCreating }

    struct Layout: Equatable {
        let minWindow: (width: Double, height: Double)?
        let stepListWidth: Double?
        let questionsWidth: Double?
        let minOutputWidth: Double?
        /// Compact: the list is "3 of 9" with page dots, and the two columns stack in one page.
        let stacksColumns: Bool

        static func == (lhs: Layout, rhs: Layout) -> Bool {
            lhs.minWindow?.width == rhs.minWindow?.width && lhs.minWindow?.height == rhs.minWindow?.height
                && lhs.stepListWidth == rhs.stepListWidth && lhs.questionsWidth == rhs.questionsWidth
                && lhs.minOutputWidth == rhs.minOutputWidth && lhs.stacksColumns == rhs.stacksColumns
        }

        static func of(_ platform: Platform) -> Layout {
            switch platform {
            case .mac:
                Layout(minWindow: (820, 600), stepListWidth: 260, questionsWidth: 420, minOutputWidth: 320, stacksColumns: false)
            case .compact:
                Layout(minWindow: nil, stepListWidth: nil, questionsWidth: nil, minOutputWidth: nil, stacksColumns: true)
            }
        }

        /// The least window that holds the list and both columns: the list, the questions and the output's minimum.
        var leastWidth: Double? {
            guard let list = stepListWidth, let questions = questionsWidth, let output = minOutputWidth else { return nil }
            return list + questions + output
        }

        /// The window that holds `leastWidth` with the page's padding either side (28), the gap between the columns (24) and the
        /// divider (1), plus room for the card's own insets.
        var windowWidth: Double? { leastWidth.map { $0 + 2 * 28 + 24 + 1 + 40 } }
    }
}
