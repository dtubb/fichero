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
}
