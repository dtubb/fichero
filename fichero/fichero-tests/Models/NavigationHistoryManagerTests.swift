@testable import Fichero
import Testing

@Suite("NavigationHistoryManager")
struct NavigationHistoryManagerTests {

    @Test("push ignores a consecutive duplicate")
    func duplicatePushIsIgnored() {
        let history = NavigationHistoryManager()
        history.push(.entityProfile(entityId: "entity-1"))
        history.push(.entityProfile(entityId: "entity-1"))

        #expect(history.stack == [.entityProfile(entityId: "entity-1")])
        #expect(history.cursor == 0)
    }

    @Test("pushing from the past discards the forward branch")
    func pushDropsForwardHistory() {
        let history = NavigationHistoryManager()
        history.push(.entityList)
        history.push(.entityProfile(entityId: "entity-1"))
        history.push(.claimJump(claimId: "claim-1", pageLabel: nil))
        _ = history.goBack()

        history.push(.pdfPage(pageLabel: "12"))

        #expect(history.stack == [.entityList, .entityProfile(entityId: "entity-1"), .pdfPage(pageLabel: "12")])
        #expect(!history.canGoForward)
        #expect(history.cursor == 2)
    }

    @Test("back and forward stop at their respective boundaries")
    func navigationBoundaries() {
        let history = NavigationHistoryManager()
        #expect(history.goBack() == nil)
        #expect(history.goForward() == nil)

        history.push(.entityList)
        history.push(.entityProfile(entityId: "entity-1"))
        #expect(history.goBack() == .entityList)
        #expect(history.goBack() == nil)
        #expect(history.goForward() == .entityProfile(entityId: "entity-1"))
        #expect(history.goForward() == nil)
    }

    @Test("history retains the newest fifty entries")
    func historyDepthCap() {
        let history = NavigationHistoryManager()
        for index in 0...NavigationHistoryManager.maxDepth {
            history.push(.entityProfile(entityId: "entity-\(index)"))
        }

        #expect(history.stack.count == NavigationHistoryManager.maxDepth)
        #expect(history.stack.first == .entityProfile(entityId: "entity-1"))
        #expect(history.cursor == NavigationHistoryManager.maxDepth - 1)
    }
}
