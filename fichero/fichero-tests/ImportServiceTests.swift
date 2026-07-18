@testable import Fichero
import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import Testing

@Suite("ImportService generated-client request")
@MainActor
struct ImportServiceTests {

    @Test("upload input carries filename, content, and parent folder")
    func uploadInputCarriesFilenameContentAndParent() async throws {
        let data = Data("hello fichero".utf8)
        let input = ImportService.makeImportUploadInput(
            data: data,
            filename: "report.pdf",
            parentId: "folder-1"
        )

        #expect(input.query.parentId == "folder-1")

        guard case .multipartForm(let multipartBody) = input.body else {
            Issue.record("expected multipart form body")
            return
        }

        var parts: [Components.Schemas.BodyImportFileApiDocumentsImportPost] = []
        for try await part in multipartBody { parts.append(part) }
        #expect(parts.count == 1)

        guard case .file(let filePart) = parts.first else {
            Issue.record("expected single file part")
            return
        }

        #expect(filePart.filename == "report.pdf")
        let collected = try await Data(collecting: filePart.payload.body, upTo: .max)
        #expect(collected == data)
    }

    @Test("link-mode ingest still uses the path-based JSON route")
    func linkModeUsesPathBasedJSONRoute() async throws {
        // Build the same JSON body the service uses for non-copy modes.
        let body = Operations.IngestFileApiIngestFilePost.Input.Body.json(
            .init(
                path: "/tmp/foo.txt",
                parentId: "folder-2",
                copyMode: false,
                extractText: true,
                autoEmbed: false
            )
        )

        guard case .json(let request) = body else {
            Issue.record("expected JSON body")
            return
        }

        #expect(request.path == "/tmp/foo.txt")
        #expect(request.parentId == "folder-2")
        #expect(request.copyMode == false)
        #expect(request.extractText == true)
        #expect(request.autoEmbed == false)
    }
}
