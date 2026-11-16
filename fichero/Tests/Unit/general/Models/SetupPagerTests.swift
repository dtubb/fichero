@testable import Fichero
import Foundation
import Testing

/// The wide Set Up's pager model (`wide.pager.*`): the move rules, the bounce, the label, the restore and the widths.
@MainActor
struct SetupPagerTests {
    private let steps: [SetupStep] = [.addMaterial, .aboutMaterial, .stages, .stage("prepare-images"), .stage("read"), .ready]

    @Test("advance and retreat move one page, and stop at the edges")
    func moves() {
        var pager = SetupPager(steps: steps, current: .addMaterial)
        #expect(pager.retreat() == .atEdge)
        #expect(pager.advance() == .moved(.aboutMaterial))
        #expect(pager.retreat() == .moved(.addMaterial))
        pager.jump(to: .ready)
        #expect(pager.current == .ready)
        #expect(pager.advance() == .atEdge, "the last page's Next is Start, not a swipe")
    }

    @Test("a page that cannot be left bounces with its reason and stays; going back is never held")
    func bounce() {
        var pager = SetupPager(steps: steps, current: .addMaterial)
        #expect(pager.advance(waitsFor: SetupFooter.addYourPages) == .bounced(reason: SetupFooter.addYourPages))
        #expect(pager.current == .addMaterial)
        _ = pager.advance()
        #expect(pager.retreat() == .moved(.addMaterial))
    }

    @Test("a forward move from a draft page saves the draft")
    func savesDraft() {
        #expect(SetupPager(steps: steps, current: .aboutMaterial).savesDraftOnAdvance)
        #expect(!SetupPager(steps: steps, current: .ready).savesDraftOnAdvance)
    }

    @Test("the label names the step, its count and its title, a stage by the engine's title")
    func label() {
        let pager = SetupPager(steps: steps, current: .stage("read"))
        #expect(pager.label(stageTitles: ["read": "Read"]) == "Step 5 of 6, Read")
        #expect(SetupPager(steps: steps, current: .stages).label() == "Step 3 of 6, Choose the Stages")
        #expect(SetupPager(steps: steps, current: .stages).compactPosition == "3 of 6")
    }

    @Test("a window reopens on the page it left, else Choose the Stages, else the first page")
    func restore() {
        #expect(SetupPager.restored(savedId: "stage:read", in: steps) == .stage("read"))
        #expect(SetupPager.restored(savedId: "stage:names", in: steps) == .stages, "a dropped stage falls back")
        #expect(SetupPager.restored(savedId: nil, in: steps) == .stages)
        #expect(SetupPager.restored(savedId: "x", in: [.welcome]) == .welcome)
    }

    @Test("Reduce Motion cross-fades instead of sliding")
    func motion() {
        #expect(SetupPager.transition(reduceMotion: true) == .crossFade)
        #expect(SetupPager.transition(reduceMotion: false) == .slide)
    }

    @Test("the Mac window is at least 820 by 600 with the list and two columns; compact stacks them")
    func widths() {
        let mac = SetupPager.Layout.of(.mac)
        #expect(mac.minWindow?.width == 820 && mac.minWindow?.height == 600)
        #expect(mac.stepListWidth == 260 && mac.questionsWidth == 420 && mac.minOutputWidth == 320)
        #expect(mac.leastWidth == 1000 && !mac.stacksColumns, "list 260 + questions 420 + output 320: wider than the 820 floor, which the library window supplies")
        #expect(SetupPager.Layout.of(.compact).stacksColumns)
        #expect(SetupPager.Layout.of(.compact).stepListWidth == nil)
    }

    @Test("the wide window holds the list and both columns; off, it is today's 820 x 600")
    func windowHoldsTheColumns() {
        let columns = SetupPager.Layout.of(.mac)
        #expect(FirstRunWindow.windowSize(wide: false) == CGSize(width: 820, height: 600))
        #expect(FirstRunWindow.windowSize(wide: true).width >= (columns.leastWidth ?? 0) + 2 * 28 + 24)
    }

    @Test("a forward move is held while a save or the project's creation runs")
    func forwardHeldWhileSaving() {
        #expect(SetupPager.forwardHeld(isSaving: true, isCreating: false))
        #expect(SetupPager.forwardHeld(isSaving: false, isCreating: true))
        #expect(!SetupPager.forwardHeld(isSaving: false, isCreating: false))
    }

    @Test("a drag that starts on a horizontal scroller scrolls it and does not move the page")
    func dragOnAScrollerDoesNotMove() {
        let strip = CGRect(x: 0, y: 100, width: 400, height: 80)
        let sideways = CGSize(width: -120, height: 5)
        #expect(SetupPager.dragMoves(translation: sideways, start: CGPoint(x: 50, y: 120), scrollers: [strip]) == nil)
        #expect(SetupPager.dragMoves(translation: sideways, start: CGPoint(x: 50, y: 20), scrollers: [strip]) == true)
        #expect(SetupPager.dragMoves(translation: CGSize(width: 120, height: 5), start: .zero, scrollers: []) == false)
        #expect(SetupPager.dragMoves(translation: CGSize(width: 60, height: 60), start: .zero, scrollers: []) == nil)
    }

    @Test("the wide window holds the columns inside the card's 44 points of insets")
    func windowCountsTheCardInsets() throws {
        let columns = SetupPager.Layout.of(.mac)
        #expect(try #require(columns.windowWidth) >= (columns.leastWidth ?? 0) + 2 * 28 + 24 + 1 + 44)
    }
}
