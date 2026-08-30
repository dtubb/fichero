@testable import Fichero
import Testing

@Suite("MobileCaptureUploadSummary")
struct MobileCaptureUploadSummaryTests {

    @Test("starts with zero counts and supports independent outcome totals")
    func defaultsAndValues() {
        let empty = MobileCaptureUploadSummary()
        let summary = MobileCaptureUploadSummary(uploadedCount: 3, failedCount: 1, waitingCount: 2)

        #expect(empty == MobileCaptureUploadSummary(uploadedCount: 0, failedCount: 0, waitingCount: 0))
        #expect(summary.uploadedCount == 3)
        #expect(summary.failedCount == 1)
        #expect(summary.waitingCount == 2)
    }
}
