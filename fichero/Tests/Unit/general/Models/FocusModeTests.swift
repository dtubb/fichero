//
//  FocusModeTests.swift
//  FicheroTests
//
//  panes.focus-mode (#6575, owner 2026-11-13): focus takes the window into real full screen only if it is not there
//  already, and leaving undoes only what focus did. See docs/contributor_manual/specs/ui/panes-workspaces.md.
//

@testable import Fichero
import Testing

struct FocusModeTests {
    @Test("a window not yet full screen goes full screen on entering focus, and comes back out on leaving")
    func entersAndLeaves() {
        #expect(FocusMode.entersFullScreen(windowIsFullScreen: false))
        #expect(FocusMode.leavesFullScreen(focusEnteredIt: true, windowIsFullScreen: true))
    }

    @Test("a window already full screen stays full screen when focus ends")
    func alreadyFullScreenStays() {
        #expect(!FocusMode.entersFullScreen(windowIsFullScreen: true))
        #expect(!FocusMode.leavesFullScreen(focusEnteredIt: false, windowIsFullScreen: true))
    }

    @Test("a window the person took out of full screen during focus is not toggled back in")
    func personLeftFullScreenFirst() {
        #expect(!FocusMode.leavesFullScreen(focusEnteredIt: true, windowIsFullScreen: false))
    }
}
