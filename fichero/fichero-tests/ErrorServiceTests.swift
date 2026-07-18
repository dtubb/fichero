@testable import Fichero
import Foundation
import Testing

@MainActor
@Suite("ErrorService")
struct ErrorServiceTests {

    private func reset(_ service: ErrorService) {
        service.clearErrorHistory()
        service.currentAlert = nil
    }

    @Test("offline URL errors become high-severity network history entries")
    func offlineURLErrorClassification() {
        let service = ErrorService.shared
        reset(service)

        service.reportError(NSError(domain: NSURLErrorDomain, code: NSURLErrorNotConnectedToInternet), showUserFeedback: false)

        let error = service.errorHistory.first
        #expect(error?.type == .network)
        #expect(error?.severity == .high)
        #expect(service.currentAlert == nil)
    }

    @Test("file-write permission errors surface feedback and retain their context")
    func filePermissionErrorClassification() {
        let service = ErrorService.shared
        reset(service)

        service.reportError(NSError(domain: NSCocoaErrorDomain, code: NSFileWriteNoPermissionError))

        let error = service.errorHistory.first
        #expect(error?.type == .permission)
        #expect(error?.severity == .high)
        #expect(error?.context?["domain"] == NSCocoaErrorDomain)
        #expect(service.currentAlert?.id == error?.id)
    }

    @Test("history is newest-first and can be cleared")
    func historyOrderingAndClear() {
        let service = ErrorService.shared
        reset(service)

        service.reportError(ErrorModel.validationError(message: "first"), showUserFeedback: false)
        service.reportError(ErrorModel.validationError(message: "second"), showUserFeedback: false)

        #expect(service.getRecentErrors(limit: 1).map(\.message) == ["second"])
        service.clearErrorHistory()
        #expect(service.errorHistory.isEmpty)
    }
}
