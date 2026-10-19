@testable import Fichero
import FicheroAPIClient
import Foundation
import XCTest

/// `source.onboard.places-cap-projects` (#5828): the screen shows the engine's ids; this Mac is the default.
final class WhereTheWorkRunsTests: XCTestCase {
    func testTheDefaultIsThisMacOnly() {
        XCTAssertEqual(WhereTheWorkRuns.default, .thisMac)
    }

    func testTheFivePlacesAreTheEnginesIds() {
        XCTAssertEqual(WhereTheWorkRuns.allCases.map(\.rawValue),
                       ["this-mac", "another-mac", "cloud", "acenet", "huggingface"])
    }

    func testACardShowsWhatIsSetUpAndNothingTicks() {
        let none = WhatFicheroRuns.SetUp()
        XCTAssertNil(none.line(for: .cloud))
        let set = WhatFicheroRuns.SetUp(keys: ["Claude", "Gemini"], hasToken: true, clusters: ["ACENET Siku"])
        XCTAssertEqual(set.line(for: .cloud), "Keys saved: Claude, Gemini")
        XCTAssertEqual(set.line(for: .huggingface), "Token saved")
        XCTAssertEqual(set.line(for: .acenet), "ACENET Siku")
        XCTAssertNil(set.line(for: .thisMac))
        XCTAssertNil(set.line(for: .anotherMac))
    }

    /// Local providers report a key as present (they need none); the cloud card lists only real cloud keys (#5828).
    func testLocalProvidersAreNeverKeysSaved() throws {
        func provider(_ name: String, type: String, place: String) throws -> Components.Schemas.ProviderResponse {
            let json = #"{"id":"\#(type)","name":"\#(name)","provider_type":"\#(type)","enabled":true,"sort_order":0,"has_api_key":true,"created_at":"2026-10-19T00:00:00Z","place":"\#(place)"}"#
            return try JSONDecoder().decode(Components.Schemas.ProviderResponse.self, from: Data(json.utf8))
        }
        let local = [try provider("MLX (Local)", type: "omlx", place: "this_mac"),
                     try provider("spaCy (local NLP)", type: "spacy", place: "this_mac"),
                     try provider("Kraken (line segmentation)", type: "kraken", place: "this_mac"),
                     try provider("Whisper (local transcription)", type: "whisper", place: "this_mac")]
        XCTAssertNil(WhatFicheroRuns.SetUp(providers: local, clusters: []).line(for: .cloud))
        let withKey = local + [try provider("Anthropic", type: "anthropic", place: "provider")]
        XCTAssertEqual(WhatFicheroRuns.SetUp(providers: withKey, clusters: []).line(for: .cloud), "Keys saved: Anthropic")
    }

    func testASavedTokenReplacesAddATokenButAKeyOrClusterLeavesItsButton() {
        let set = WhatFicheroRuns.SetUp(keys: ["Claude"], hasToken: true, clusters: ["ACENET Siku"])
        XCTAssertTrue(set.hidesButton(for: .huggingface))
        XCTAssertFalse(set.hidesButton(for: .cloud))
        XCTAssertFalse(set.hidesButton(for: .acenet))
        XCTAssertFalse(WhatFicheroRuns.SetUp().hidesButton(for: .huggingface))
    }
}
