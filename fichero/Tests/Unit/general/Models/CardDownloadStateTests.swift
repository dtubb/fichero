import FicheroAPIClient
import Foundation
@testable import Fichero
import Testing

/// #5809 item 3: a card the engine says is downloading shows progress, never a Download button beside "Downloading".
/// What breaks without it: a download started elsewhere (another surface, an earlier launch) leaves the app not
/// tracking it, so its card said "Downloading" and still offered Download, which queued a second job.
@MainActor
@Suite("A card's download state drives its button (#5809)")
struct CardDownloadStateTests {
    private static func card(downloading: Bool) throws -> Components.Schemas.ModelCandidate {
        let json = """
        {"id":"mlx:hf/x@main","name":"A model","source":"hugging-face","offered_because":"","pin":{},
         "jobs":["read-a-line"],"open_licence":true,"size":"","measured":"","in_recipe_rules":true,
         "runs_where":"this_mac","availability":"download","availability_words":"Downloading","chosen":false,
         "download":{"runtime":"mlx","model":"x","action":"model.download","params":{},"downloading":\(downloading)}}
        """
        return try JSONDecoder().decode(Components.Schemas.ModelCandidate.self, from: Data(json.utf8))
    }

    @Test("the engine saying downloading is enough, whether or not this app is tracking the download")
    func engineSaysDownloading() throws {
        #expect(ModelFinderCard.isDownloading(try Self.card(downloading: true), tracked: false))
        #expect(ModelFinderCard.isDownloading(try Self.card(downloading: false), tracked: true))
    }

    @Test("neither saying so means the Download button is offered")
    func notDownloading() throws {
        #expect(!ModelFinderCard.isDownloading(try Self.card(downloading: false), tracked: false))
    }
}
