@testable import Fichero
import Testing

/// `source.find.model-row-words` (#5812): a model row says Available, Downloaded or Download, never "Ships with Fichero".
struct ModelRowWordsTests {
    @Test func theSourceWordsAreAvailableAndDownloaded() {
        #expect(ModelFinderStore.sourceWords("shipped") == "Available")
        #expect(ModelFinderStore.sourceWords("installed") == "Downloaded")
        #expect(!["shipped", "installed", "kraken-repository", "hugging-face"]
            .map(ModelFinderStore.sourceWords).contains { $0.contains("Ships with") })
    }
}
