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

/// The keys, the drag and the announcement around one page. Arrow keys reach it only when no text field has taken them.
private struct PagerBinding<Page: View>: View {
    let label: String
    let move: (Bool) -> Bool
    @ViewBuilder let page: Page
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        page
            .focusable()
            .focusEffectDisabled()
            .onKeyPress(.leftArrow) { move(false) ? .handled : .ignored }
            .onKeyPress(.rightArrow) { move(true) ? .handled : .ignored }
            .simultaneousGesture(DragGesture(minimumDistance: 60).onEnded { drag in
                guard abs(drag.translation.width) > 2 * abs(drag.translation.height) else { return }
                _ = move(drag.translation.width < 0)
            })
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
