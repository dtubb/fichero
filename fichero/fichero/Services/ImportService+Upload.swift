import FicheroAPIClient
import Foundation
import OpenAPIRuntime

extension ImportService {
    /// Build the multipart body for the generated `POST /api/documents/import` upload.
    /// ponytail: exposed static helper so tests can verify filename/content
    ///          without a real network call or security-scoped URL.
    static func makeImportUploadBody(
        data: Data,
        filename: String
    ) -> Operations.ImportFileApiDocumentsImportPost.Input.Body {
        let part = OpenAPIRuntime.MultipartPart(
            payload: Components.Schemas.BodyImportFileApiDocumentsImportPost.FilePayload(
                body: OpenAPIRuntime.HTTPBody(data)
            ),
            filename: filename
        )
        return .multipartForm([.file(part)])
    }

    /// Build the full generated input for a single-file upload.
    static func makeImportUploadInput(
        data: Data,
        filename: String,
        parentId: String?
    ) -> Operations.ImportFileApiDocumentsImportPost.Input {
        .init(
            query: .init(parentId: parentId),
            body: makeImportUploadBody(data: data, filename: filename)
        )
    }

    /// Build the error thrown when EVERY file in a batch import failed —
    /// surfacing the per-file reasons, not one opaque "All imports failed"
    /// (#4068, prefer-raise-over-silent-fallback). The per-file descriptions
    /// ride in `NSLocalizedRecoverySuggestionErrorKey` (the alert's
    /// informative text) and the first underlying error in
    /// `NSUnderlyingErrorKey`, so the user can see WHICH files failed and WHY.
    /// Exposed static so a test can verify the shape without a live network.
    static func makeAllImportsFailedError(errors: [ImportError]) -> Error {
        let details = errors.map { error in
            "• \(error.url.lastPathComponent): \(error.error.localizedDescription)"
        }.joined(separator: "\n")
        return NSError(
            domain: "ImportService",
            code: -1,
            userInfo: [
                NSLocalizedDescriptionKey: "All \(errors.count) import(s) failed",
                NSLocalizedRecoverySuggestionErrorKey: details,
                NSUnderlyingErrorKey: errors.first?.error
                    ?? NSError(domain: "ImportService", code: -1),
            ]
        )
    }
}
