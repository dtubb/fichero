@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Steps left off until turned on (#5677, `source.onboard.correct-off-unless-a-corrector-is-here`): the engine's
/// recipe says, one line per step, what turning it on would cost; Set Up's Read page lists Read's, the Start section
/// all of them; Turn On asks for the step (ticked, and "Correct with a second model?" yes), and the engine proposes
/// the plan again with it. Through the real `RecipeSetupStore` over the generated client; only the transport is stubbed.
private final class LeftOffEngine: URLProtocol {
    nonisolated(unsafe) static var assembled: [[String: Any]] = []

    override static func canInit(with request: URLRequest) -> Bool { request.url?.host == "left-off.test" }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let body = (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
        var json = "{}"
        if request.url?.path == "/api/recipes/assemble" {
            Self.assembled.append(body)
            let asked = (body["jobs"] as? [String])?.contains("correct") == true
            let steps = #"{"id":"read","job":"read-a-line","reasons":[]}"#
                + (asked ? #",{"id":"correct","job":"correct","reasons":[]}"# : "")
            let leftOff = asked ? "" : #"{"job":"correct","title":"Correct","#
                + #""sentence":"Correct is off: no correcting model is on this Mac; turning it on downloads Qwen2.5-VL 7B (5.7 GB)."}"#
            json = #"{"id":"generated","title":"t","purposes":["transcribe"],"steps":[\#(steps)],"gaps":[],"problems":[],"#
                + #""left_off":[\#(leftOff)]}"#
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor
@Suite(.serialized)
struct RecipeLeftOffTests {
    private func store() -> RecipeSetupStore {
        LeftOffEngine.assembled = []
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [LeftOffEngine.self]
        let store = RecipeSetupStore(client: FicheroClient(
            baseURL: URL(string: "https://left-off.test")!, libraryPath: "/tmp/left-off.fichero",
            session: URLSession(configuration: configuration)
        ))
        store.languages = ["es"]
        store.scripts = ["Latn"]
        return store
    }

    /// WHY: choosing Read brought a Correct step pinned to a 5.7 GB model no Mac had. It is off now, and the person
    /// must see that it is, and what turning it on would cost, where they choose Read and before Start.
    @Test("a left-off step is listed with its cost on its stage's page and in the Start section")
    func listedWhereChosen() async {
        let store = store()
        await store.assemble()

        let read: Set<String> = ["read-a-line", "read-a-page", "correct", "tie-text-to-lines"]
        #expect(store.leftOff(forJobs: read).map(\.title) == ["Correct"], "on the Read page")
        #expect(store.leftOff(forJobs: ["find-lines"]).isEmpty, "not on another stage's page")
        #expect(store.leftOff().first?.sentence.contains("5.7 GB") == true, "in the Start section, with its cost")
    }

    /// WHY: Turn On must ask for the step the way the rules read it -- ticked, and the Read question answered yes --
    /// or the engine leaves it off again on the next proposal.
    @Test("Turn On ticks the step, answers its question yes, and the plan comes back with it")
    func turnOnAsksForIt() async throws {
        let store = store()
        await store.assemble()

        await store.turnOn(job: "correct")

        let sent = try #require(LeftOffEngine.assembled.last)
        #expect((sent["jobs"] as? [String])?.contains("correct") == true)
        let answers = try #require(sent["job_answers"] as? [String: Any])
        #expect(answers["correct_with_a_second_model"] as? Bool == true)
        #expect(store.recipe?.steps.contains { $0.job == "correct" } == true)
        #expect(store.leftOff().isEmpty, "no longer left off")
    }
}
