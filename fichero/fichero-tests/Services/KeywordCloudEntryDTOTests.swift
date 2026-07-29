@testable import Fichero
import Foundation
import Testing

@Suite("KeywordCloudEntryDTO")
struct KeywordCloudEntryDTOTests {

    @Test("decodes keyword counts and uses the keyword as stable identity")
    func decodingAndIdentity() throws {
        let entry = try JSONDecoder().decode(
            KeywordCloudEntryDTO.self,
            from: Data(#"{"name":"archival","count":12}"#.utf8)
        )

        #expect(entry.name == "archival")
        #expect(entry.count == 12)
        #expect(entry.id == "archival")
    }
}
