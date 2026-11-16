import SwiftUI

/// The wide Set Up's pager bound to the window (`wide.pager.*`, #5668, behind the `wideSetUp` flag): ← and → (and ⌘[ ⌘]) and a
/// horizontal drag move one page through `SetupPager`, the one model the footer's Back and Next also reduce to. A forward move runs
/// the page's own Continue (`advance()`, which saves the draft), and is held where the footer already says it waits for something:
/// the reason stays beside Next. The page's one accessibility label is posted again on every move.
extension FirstRunWindow {
    @ViewBuilder
    func paged<Page: View>(_ page: Page) -> some View {
        if FeatureManager.shared.isWideSetUpEnabled {
            PagerBinding(label: pagerLabel, move: movePage) { page }
        } else {
            page
        }
    }

    private var pagerLabel: String {
        SetupPager(steps: steps, current: step).label(stageTitles: store?.stageTitles ?? [:])
    }

    /// One page on or back. Returns whether it moved.
    @discardableResult
    func movePage(forward: Bool) -> Bool {
        var pager = SetupPager(steps: steps, current: step)
        if forward {
            // One save at a time: a second press while one runs would move two pages (and pass a page that bounced).
            guard !SetupPager.forwardHeld(isSaving: isSaving, isCreating: newProject.isCreating) else { return false }
            let model = SetupFooter.of(step, in: steps, mode: mode, projectChosen: flow.project != .none,
                                       hasMaterial: store?.hasMaterial ?? false, hasLanguage: store?.languageWait == nil)
            guard case .moved = pager.advance(waitsFor: model.waitsFor) else { return false }
            advance()
            return true
        }
        guard case .moved(let page) = pager.retreat() else { return false }
        step = page
        return true
    }
}

/// Where a horizontal scroller sits inside the pager, so a drag that starts on it scrolls it and does not turn the page.
enum PagerScrollers {
    static let space = "setup.pager.space"
    struct Key: PreferenceKey {
        static let defaultValue: [CGRect] = []
        static func reduce(value: inout [CGRect], nextValue: () -> [CGRect]) { value += nextValue() }
    }
}

extension View {
    /// Marks this view as a horizontal scroller for the pager's drag.
    func pagerScroller() -> some View {
        background(GeometryReader { proxy in
            Color.clear.preference(key: PagerScrollers.Key.self, value: [proxy.frame(in: .named(PagerScrollers.space))])
        })
    }
}

/// The keys, the drag and the announcement around one page. Arrow keys reach it only when no text field has taken them.
private struct PagerBinding<Page: View>: View {
    let label: String
    let move: (Bool) -> Bool
    @ViewBuilder let page: Page
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var scrollers: [CGRect] = []

    var body: some View {
        page
            .focusable()
            .focusEffectDisabled()
            .onPreferenceChange(PagerScrollers.Key.self) { scrollers = $0 }
            // A held key is not a new press: one page per press.
            .onKeyPress(.leftArrow, phases: .down) { _ in move(false) ? .handled : .ignored }
            .onKeyPress(.rightArrow, phases: .down) { _ in move(true) ? .handled : .ignored }
            .simultaneousGesture(DragGesture(minimumDistance: 60, coordinateSpace: .named(PagerScrollers.space)).onEnded { drag in
                guard let forward = SetupPager.dragMoves(translation: drag.translation, start: drag.startLocation,
                                                         scrollers: scrollers) else { return }
                _ = move(forward)
            })
            .coordinateSpace(name: PagerScrollers.space)
            .trackpadSwipe { forward in _ = move(forward) }
            .background {
                Group {
                    Button("") { _ = move(false) }.keyboardShortcut("[", modifiers: .command)
                    Button("") { _ = move(true) }.keyboardShortcut("]", modifiers: .command)
                }
                .opacity(0).frame(width: 0, height: 0).accessibilityHidden(true)
            }
            .animation(SetupPager.transition(reduceMotion: reduceMotion) == .slide ? .default : nil, value: label)
            .accessibilityElement(children: .contain)
            .accessibilityLabel(label)
            .accessibilityIdentifier("setup.pager")
            .onChange(of: label) { _, new in AccessibilityNotification.Announcement(new).post() }
    }
}

#Preview("Pager around a page") {
    PagerBinding(label: "Page 2 of 5", move: { _ in true }, page: { Text("A page of Set Up").padding() })
        .frame(width: 320, height: 120)
}
