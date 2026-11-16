import FicheroAPIClient
import Foundation
import Observation

/// `reading.choose_many`: confirm every line of the page whose counting reading is a review's (`wide.review.accept-line-and-all`).
struct ReviewAcceptAllRequest: Encodable, Equatable {
    let documentId: String
    var kind = "transcription"

    enum CodingKeys: String, CodingKey { case documentId = "document_id", kind }
}

/// The words of the button, one place.
enum ReviewAcceptWords {
    /// "Accept all 12": the engine's count, so the button never promises more than it will confirm.
    static func button(_ count: Int) -> String { "Accept all \(count)" }

    static func help(_ count: Int) -> String {
        let which = count == 1 ? "the 1 line" : "all \(count) lines"
        return "A review's corrections already count. This confirms \(which) as yours, in one step you can undo."
    }

    static func undoName(_ count: Int) -> String { "Accept \(count) \(count == 1 ? "Reading" : "Readings")" }
}

/// Accept all N on one page: the count comes from the engine; pressing it runs the one audited action, registered as one step on the
/// window's stack (⌘Z puts every line back), then reads the count again. A page with nothing waiting shows no button.
@MainActor @Observable
final class ReviewAcceptStore {
    private let client: FicheroClient
    let documentId: String
    private(set) var count = 0
    private(set) var failure: String?
    private(set) var isAccepting = false

    init(client: FicheroClient, documentId: String, count: Int = 0) {
        self.client = client
        self.documentId = documentId
        self.count = count
    }

    var isOffered: Bool { count >= 1 }

    func load() async {
        do {
            switch try await client.api.reviewWaitingApiContentRepresentationsDocumentDocumentIdReviewWaitingGet(
                path: .init(documentId: documentId)) {
            case .ok(let success):
                count = try success.body.json.count
                failure = nil
            default:
                failure = "Could not count the lines waiting to be accepted."
            }
        } catch {
            if error.isCancellationError { return }
            failure = "Could not count the lines waiting to be accepted: \(error.localizedDescription)"
        }
    }

    /// Press the button. The engine refuses in words when a person already chose them all (409): its words are kept.
    func accept(actionsService: ActionsService, steps: WindowSteps?) async {
        guard isOffered, !isAccepting else { return }
        isAccepting = true
        defer { isAccepting = false }
        let confirmed = count
        do {
            try await AuditedAction.run(
                "reading.choose_many", params: ReviewAcceptAllRequest(documentId: documentId),
                actionName: ReviewAcceptWords.undoName(confirmed), actionsService: actionsService, steps: steps,
                afterChange: { [weak self] in await self?.load() })
            failure = nil
        } catch {
            if error.isCancellationError { return }
            failure = error.localizedDescription  // the button stays; the count is read again when the page next opens
        }
    }
}
