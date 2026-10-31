import FicheroAPIClient
import Foundation
import Observation

/// One thumbnail in the chain strip (`wide.chain.strip-on-the-page`, #5386): the photograph, then each rendition a step wrote, with
/// the operation's name and figure in the engine's words. The engine works out the chain (`GET /api/pages/{id}/image-chain`); this
/// only picks the marks to show.
struct RenditionChainRow: Identifiable, Equatable {
    let id: String
    let renditionId: String?
    let title: String
    let figure: String
    /// "Find Lines reads this one" on the image every later step reads.
    let readsThis: Bool
    /// Why this rendition was passed over, if it was.
    let passedOver: String?

    static let readsThisWords = "Find Lines reads this one"

    static func rows(of chain: Components.Schemas.ImageChain) -> [RenditionChainRow] {
        chain.steps.map { step in
            RenditionChainRow(
                id: step.renditionId ?? "photograph", renditionId: step.renditionId, title: step.operation, figure: step.figure,
                readsThis: step.readsThis, passedOver: step.passedOver)
        }
    }

    /// The strip says nothing where no step wrote a picture of the page.
    static func isWorthShowing(_ rows: [RenditionChainRow]) -> Bool { rows.count > 1 }
}

/// Loads the chain for one page.
@MainActor @Observable
final class RenditionChainStore {
    private let client: FicheroClient
    let pageId: String
    private(set) var rows: [RenditionChainRow] = []
    private(set) var failure: String?

    init(client: FicheroClient, pageId: String) {
        self.client = client
        self.pageId = pageId
    }

    func load() async {
        do {
            switch try await client.api.getImageChainApiPagesPageIdImageChainGet(path: .init(pageId: pageId)) {
            case .ok(let success):
                rows = RenditionChainRow.rows(of: try success.body.json)
                failure = nil
            default:
                failure = "Could not read this page's pictures."
            }
        } catch {
            if error.isCancellationError { return }
            failure = "Could not read this page's pictures: \(error.localizedDescription)"
        }
    }
}
