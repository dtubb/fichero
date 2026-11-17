@testable import Fichero
import Testing

/// The Preview's folder-canvas callbacks live in the environment as a wrapper that compares equal, so a redraw
/// does not invalidate their readers (#6610).
struct FolderCanvasActionTests {
    @Test("two actions with different closures compare equal, and calling one runs its closure")
    func equalAndCallable() {
        var got: [Int] = []
        let first = FolderCanvasAction<Int> { got.append($0) }
        let second = FolderCanvasAction<Int> { _ in }
        #expect(first == second)
        first(7)
        #expect(got == [7])
    }
}
