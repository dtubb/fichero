@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `activity.popover.models-held` (#6129): the popover lists what the engine itself holds in memory, with sizes, in the
/// engine's names, so 'memory is tight' can be read against it.
struct ActivityModelsHeldTests {
    private func held(_ json: String) throws -> [Components.Schemas.HeldModel] {
        try JSONDecoder().decode([Components.Schemas.HeldModel].self, from: Data(json.utf8))
    }

    @Test func theTotalAndEachModelWithItsSize() throws {
        let models = try held(#"[{"name":"Search embedder (bge-m3)","kind":"search embedder","memory_bytes":2147483648},"#
            + #"{"name":"Kraken readers","kind":"Kraken"}]"#)
        let reading = try #require(ActivityPopoverSummary.heldReading(models).first)
        #expect(reading.id == "models" && reading.value == "2.0 GB")
        #expect(reading.help.contains("Search embedder (bge-m3): 2.0 GB") && reading.help.contains("Kraken readers"))
    }

    @Test func noSizeKnownShowsTheCountAndNothingHeldShowsNothing() throws {
        let unknown = try held(#"[{"name":"Kraken readers","kind":"Kraken"}]"#)
        #expect(ActivityPopoverSummary.heldReading(unknown).first?.value == "1 model")
        #expect(ActivityPopoverSummary.heldReading([]).isEmpty)
    }
}
