@testable import Fichero
import Foundation
import Testing

/// Compare is the wipe, Before is press-and-hold, and Side-by-Side is gone (`preview.edit.tool.compare-is-hold-and-wipe`, #4872).
struct ImageEditCompareModesTests {
    @Test("the compare modes are single and the wipe, with no side-by-side")
    func singleAndWipeOnly() {
        #expect(CompareMode.allCases == [.single, .wipe])
    }
}
