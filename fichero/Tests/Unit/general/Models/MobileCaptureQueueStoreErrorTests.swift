@testable import Fichero
import Testing

@Suite("MobileCaptureQueueStoreError")
struct MobileCaptureQueueStoreErrorTests {

    @Test("each failure exposes a concrete recovery diagnosis")
    func errorDescriptions() {
        #expect(MobileCaptureQueueStoreError.noLibraryAvailable.errorDescription == "No paired library is available yet.")
        #expect(MobileCaptureQueueStoreError.importFailed.errorDescription == "The paired engine did not return a document.")
    }
}
