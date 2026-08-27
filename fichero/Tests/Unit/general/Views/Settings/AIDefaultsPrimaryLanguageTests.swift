import XCTest

@testable import Fichero

/// Coverage for the AIDefaults `primaryLanguage` field added in #1808 — the
/// Codable ↔ `primary_language` snake-case key mapping the Settings picker and
/// the AppState load/save round-trip depend on. (Uses full round-trips because
/// the synthesized Decodable requires every key present.)
final class AIDefaultsPrimaryLanguageTests: XCTestCase {

    func testPrimaryLanguageEncodesToSnakeCaseKey() throws {
        var defaults = AIDefaults()
        defaults.primaryLanguage = "es"

        let json = String(data: try JSONEncoder().encode(defaults), encoding: .utf8) ?? ""

        XCTAssertTrue(json.contains("\"primary_language\":\"es\""),
                      "primaryLanguage must serialize under the backend's snake_case key")
        XCTAssertFalse(json.contains("primaryLanguage"),
                       "the Swift camelCase name must never leak into the payload")
    }

    func testRoundTripPreservesPrimaryLanguage() throws {
        var defaults = AIDefaults()
        defaults.textProvider = "openrouter"
        defaults.textModel = "auto"
        defaults.primaryLanguage = "fr"

        let decoded = try JSONDecoder().decode(
            AIDefaults.self,
            from: try JSONEncoder().encode(defaults)
        )

        XCTAssertEqual(decoded, defaults)
        XCTAssertEqual(decoded.primaryLanguage, "fr")
    }

    func testEmptyPrimaryLanguageIsAutoAndRoundTrips() throws {
        let defaults = AIDefaults()  // primaryLanguage defaults to "" = Auto
        XCTAssertEqual(defaults.primaryLanguage, "")

        let decoded = try JSONDecoder().decode(
            AIDefaults.self,
            from: try JSONEncoder().encode(defaults)
        )
        XCTAssertEqual(decoded.primaryLanguage, "")
    }

    func testDecodesLanguageFromSnakeCaseKey() throws {
        // Prove the CodingKey reads `primary_language` back onto primaryLanguage:
        // encode with a value, confirm the key, decode the same payload.
        var defaults = AIDefaults()
        defaults.primaryLanguage = "de"
        let payload = try JSONEncoder().encode(defaults)

        let decoded = try JSONDecoder().decode(AIDefaults.self, from: payload)
        XCTAssertEqual(decoded.primaryLanguage, "de")
    }

    func testSeedAppleDefaultsDoesNotTouchPrimaryLanguage() {
        var defaults = AIDefaults()
        defaults.primaryLanguage = "es"

        // Seeding only fills empty provider/model slots — it must not clobber the
        // user's language choice.
        defaults.seedAppleDefaultsIfNeeded(appleAvailable: true)

        XCTAssertEqual(defaults.primaryLanguage, "es")
    }
}
