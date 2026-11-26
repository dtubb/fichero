@testable import Fichero
import Testing

/// #7090: a click on the Activity button opens its popover and the next click closes it.
struct ActivityToolbarPopoverClickTests {
    @Test("two clicks leave the popover closed, three leave it open")
    func clicksToggle() {
        var open = false
        open = ActivityStatusToolbarItem.popoverAfterClick(open)
        #expect(open)
        open = ActivityStatusToolbarItem.popoverAfterClick(open)
        #expect(!open)
        open = ActivityStatusToolbarItem.popoverAfterClick(open)
        #expect(open)
    }
}
