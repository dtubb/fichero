@testable import Fichero
import Foundation
import Testing

/// `source.inspector.reading-says-who-read-it`: what the Inspector's reading rows say about who read a line.
/// Without this a row says only "Workflow", and two readings of one line look the same.
struct InspectorTextReadingTests {
    private func reading(model: String?, provider: String?) -> InspectorText.Reading {
        var r = InspectorText.Reading(id: "r", kind: "transcription", content: "x", maker: "workflow", author: nil,
                                      guideline: nil, pairId: nil, pairRole: nil)
        r.producerModel = model
        r.producerProvider = provider
        return r
    }

    @Test("model and provider read 'model via Provider', the model by its own name")
    func modelViaProvider() {
        #expect(reading(model: "google/gemini-3-flash-preview", provider: "openrouter").whoRead
                == "gemini-3-flash-preview via OpenRouter")
    }

    @Test("a missing half says the other alone; neither says nothing, so a typed reading falls back to its maker")
    func partialAndNone() {
        #expect(reading(model: nil, provider: "kraken").whoRead == "Kraken")
        #expect(reading(model: "blla", provider: nil).whoRead == "blla")
        #expect(reading(model: nil, provider: nil).whoRead == nil)
    }

    private func twin(_ id: String, content: String, provisional: Bool, artifact: String? = "art-1") -> InspectorText.Reading {
        var r = InspectorText.Reading(id: id, kind: "transcription", content: content, maker: "workflow", author: nil,
                                      guideline: nil, pairId: nil, pairRole: nil)
        r.provisional = provisional
        r.derivedFromArtifactId = artifact
        return r
    }

    @Test("a provisional reading with a stored twin (same artifact, kind, content) is hidden; others stay")
    func hidesOnlyTheTwin() {
        let all = [
            twin("s", content: "una linea", provisional: false),
            twin("p", content: "una linea", provisional: true),
            twin("p2", content: "otra linea", provisional: true),
            twin("p3", content: "una linea", provisional: true, artifact: "art-2"),
        ]
        #expect(InspectorText.hidingProvisionalTwins(all).map(\.id) == ["s", "p2", "p3"])
    }
}
