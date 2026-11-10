import Foundation
import Testing
@testable import Fichero

@Suite struct LibraryTableDisclosureAlignmentTests {
    @Test func chevronIsLevelWithIconTopOnOneAndFourLineRows() {
        let chevron: CGFloat = 12
        let oneLine = LibraryTableDisclosureAlignment.chevronY(rowHeight: 22, chevronHeight: chevron)
        let fourLine = LibraryTableDisclosureAlignment.chevronY(rowHeight: 88, chevronHeight: chevron)
        #expect(fourLine == LibraryTableDisclosureAlignment.iconTopInset)
        #expect(oneLine == fourLine)  // the icon's top is the same y in both
        #expect(LibraryTableDisclosureAlignment.chevronY(rowHeight: 14, chevronHeight: 12) == 1)  // too short: centred
    }
}
