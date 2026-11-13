@testable import Fichero
import SwiftUI
import Testing

/// The iPad's columns run into the home indicator's area so their bottom bars sit at the screen's edge; the iPhone and
/// the Mac keep theirs (owner, 2026-11-13).
struct BottomSafeAreaPolicyTests {
    @Test func theIPadRunsIntoTheBottomEdge() {
        #expect(BottomSafeAreaPolicy.ignoredEdges(isIOS: true, isCompact: false) == .bottom)
    }

    @Test func theIPhoneKeepsItsBottomMargin() {
        #expect(BottomSafeAreaPolicy.ignoredEdges(isIOS: true, isCompact: true).isEmpty)
    }

    @Test func theMacIsUnchanged() {
        #expect(BottomSafeAreaPolicy.ignoredEdges(isIOS: false, isCompact: false).isEmpty)
    }
}
