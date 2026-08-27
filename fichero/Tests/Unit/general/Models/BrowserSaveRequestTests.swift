@testable import Fichero
import Foundation
import Testing

@Suite("BrowserSaveRequest and BrowserSaveResponse")
struct BrowserSaveRequestTests {

    @Test("request encodes optional browser-save fields with API snake-case keys")
    func requestEncoding() throws {
        let request = BrowserSaveRequest(
            url: "https://example.com/article",
            projectId: "project-1",
            suggestedName: "Article",
            parentFolderId: "folder-1"
        )

        let json = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any])
        #expect(json["url"] as? String == "https://example.com/article")
        #expect(json["project_id"] as? String == "project-1")
        #expect(json["suggested_name"] as? String == "Article")
        #expect(json["parent_folder_id"] as? String == "folder-1")
    }

    @Test("response decodes success and document metadata from backend field names")
    func responseDecoding() throws {
        let data = Data(
            """
            {"success":true,"document_id":"document-1","document_name":"Article.pdf",
             "file_path":"/library/Article.pdf","content_type":"application/pdf","size_bytes":1234}
            """.utf8
        )

        let response = try JSONDecoder().decode(BrowserSaveResponse.self, from: data)

        #expect(response.success)
        #expect(response.documentId == "document-1")
        #expect(response.documentName == "Article.pdf")
        #expect(response.filePath == "/library/Article.pdf")
        #expect(response.contentType == "application/pdf")
        #expect(response.sizeBytes == 1234)
        #expect(response.error == nil)
    }
}
