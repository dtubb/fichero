@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `activity.failure.bar-one-button-per-action` (#6731): a failed recipe run whose summary names the same stage run's offer more
/// than once ("Read the 149 pages..." twice, build 31) offers each action once, deduplicated by action and target. Written from the
/// spec line. The summary is the engine's recorded one (`recipe_run_summary_failed.route.json`), its `failed` list repeated.
struct ActivityFailedOffersOnceTests {
    private static func recorded(_ name: String) throws -> [String: Any] {
        // Tests/Unit/general/Models/<this file> → Tests/Fixtures/recipes
        let tests = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let url = tests.appendingPathComponent("Fixtures/recipes/\(name).route.json")
        let record = try #require(try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        return try #require(record["response"] as? [String: Any])
    }

    @Test("a failure with repeated per-run actions offers each action once, in the engine's order")
    func repeatedOffersAreOfferedOnce() throws {
        var summary = try Self.recorded("recipe_run_summary_failed")
        let first = try #require((summary["failed"] as? [[String: Any]])?.first)
        var other = first
        other["thread_id"] = "thread-other"
        other["offer"] = "Read the 137 pages that failed"
        summary["failed"] = [first, other, first, other]
        var tree = try Self.recorded("recipe_run_tree")
        tree["state"] = "failed"
        tree["summary"] = summary
        // The recorded tree's stage timings are date-times, as the client reads them: not the decoder's default Double.
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let text = try decoder.singleValueContainer().decode(String.self)
            guard let date = parseEngineDate(text) else {
                throw DecodingError.dataCorruptedError(in: try decoder.singleValueContainer(), debugDescription: text)
            }
            return date
        }
        let node = ActivityJobNode(try decoder.decode(
            Components.Schemas.JobTree.self, from: try JSONSerialization.data(withJSONObject: tree)))

        let failed = try #require(ActivityDetails.summary(of: node)?.failed)

        #expect(failed.map(\.offer) == [first["offer"] as? String, "Read the 137 pages that failed"])
        #expect(failed.map(\.threadId) == [first["thread_id"] as? String, "thread-other"])
    }
}
