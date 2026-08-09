@testable import Fichero
import Testing

// The stack's DEPTH says roughly how big a PDF/folder is (Daniel,
// 2026-08-09: "we know that a 500 page pdf is larger than a 2 page pdf").
@Suite("stackSheetCount — container size → sheets behind the cover")
struct StackSheetCountTests {
    @Test("bands: 0-1 flat, few one sheet, tens two, hundreds three")
    func bands() {
        #expect(stackSheetCount(forChildCount: 0) == 0)
        #expect(stackSheetCount(forChildCount: 1) == 0)
        #expect(stackSheetCount(forChildCount: 2) == 1)
        #expect(stackSheetCount(forChildCount: 9) == 1)
        #expect(stackSheetCount(forChildCount: 10) == 2)
        #expect(stackSheetCount(forChildCount: 49) == 2)
        #expect(stackSheetCount(forChildCount: 50) == 3)
        #expect(stackSheetCount(forChildCount: 500) == 3)
    }
}
