import SwiftUI

// MARK: - Error Handling
extension DragDropService {

    @MainActor
    func handleProviderError(_ error: Error, providerType: String) {
        let errorModel = ErrorModel.fileSystemError(
            message: "Failed to load provider data: \((error.localizedDescription))",
            context: [
                "operation": "drag_drop",
                "provider_type": providerType,
                "error_type": "provider_error"
            ],
            isRecoverable: false
        )
        errorService?.reportError(errorModel)
        dragDropModel.incrementFailureCount()
    }

    @MainActor
    func handleInvalidDataError(providerType: String) {
        let errorModel = ErrorModel.validationError(
            message: "Invalid data received from provider",
            context: [
                "operation": "drag_drop",
                "provider_type": providerType,
                "error_type": "invalid_data"
            ]
        )
        errorService?.reportError(errorModel)
        dragDropModel.incrementFailureCount()
    }

    @MainActor
    func handleDecodingError(providerType: String) {
        let errorModel = ErrorModel.validationError(
            message: "Failed to decode provider data",
            context: [
                "operation": "drag_drop",
                "provider_type": providerType,
                "error_type": "decoding_error"
            ]
        )
        errorService?.reportError(errorModel)
        dragDropModel.incrementFailureCount()
    }

    @MainActor
    func handleInvalidURLError() {
        let errorModel = ErrorModel.validationError(
            message: "Invalid URL received from provider",
            context: [
                "operation": "drag_drop",
                "error_type": "invalid_url"
            ]
        )
        errorService?.reportError(errorModel)
        dragDropModel.incrementFailureCount()
    }

    // MARK: - User Feedback

    func showImportSuccessAlert(documentName: String) {
        // Class is @MainActor so we're already on main thread
        if let window = NSApp.keyWindow {
            let alert = NSAlert()
            alert.messageText = "File Imported"
            alert.informativeText = "\"\(documentName)\" was successfully imported to your library."
            alert.addButton(withTitle: "OK")
            alert.beginSheetModal(for: window, completionHandler: nil)
        }
    }

    func showImportErrorAlert(error: String) {
        // Class is @MainActor so we're already on main thread
        if let window = NSApp.keyWindow {
            let alert = NSAlert()
            alert.messageText = "Import Failed"
            alert.informativeText = "Failed to import file: \(error)"
            alert.addButton(withTitle: "OK")
            alert.beginSheetModal(for: window, completionHandler: nil)
        }
    }
}
