@testable import Fichero
import Foundation
import Testing

/// #4705 increment 3a: `SidebarMode.restored(from:)` is the tolerant decode
/// `ContentView.sidebarMode`'s raw `@SceneStorage` storage routes through,
/// instead of leaning on `@SceneStorage`'s own unproven `RawRepresentable`
/// fallback for a retired or unrecognized case (the #4703 restored-state
/// crash class).
///
/// The retired-string cases below are DATA, not enum-case references — this
/// file needs no edit when increment 3b actually deletes `.knowledgeGraph`,
/// which is the point: the test protects the string forever, independent of
/// whether the case still exists to compare against.
struct SidebarModeRestoreTests {

    /// #4705 increment 3: pins `.knowledgeGraph`'s deletion — 6 cases, not 7.
    /// A future case addition/removal fails this FIRST, before any behaviour
    /// test, naming exactly what changed.
    @Test("SidebarMode has exactly 6 cases — .knowledgeGraph retired in increment 3")
    func allCasesCountIsSix() {
        #expect(SidebarMode.allCases.count == 6)
        #expect(SidebarMode.allCases.map(\.rawValue).sorted() == [
            "activity", "automation", "chat", "library", "research", "workflows",
        ])
    }

    @Test("every current case round-trips through its own raw value", arguments: SidebarMode.allCases)
    func roundTripsCurrentCases(mode: SidebarMode) {
        #expect(SidebarMode.restored(from: mode.rawValue) == mode)
    }

    private static let retiredOrUnknown = [
        "knowledgeGraph", // #4705 increment 3b retires SidebarMode.knowledgeGraph.
        "search", // Pre-#4106 retired mode (AppViewMode's own precedent).
        "not-a-real-mode",
        "",
    ]

    @Test("a retired or unrecognized raw value degrades to .library", arguments: Self.retiredOrUnknown)
    func retiredOrUnknownDegradesToLibrary(rawValue: String) {
        #expect(SidebarMode.restored(from: rawValue) == .library)
    }
}
