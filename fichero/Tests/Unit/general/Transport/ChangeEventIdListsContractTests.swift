@testable import Fichero
import Foundation
import Testing

/// source-model slice 2, app half (#4920): `source.events.segment-ids`.
///
/// The engine's own contract fixture — `fichero-server/tests/contracts/
/// change_event_all_id_lists.json` — is generated FROM `CHANGE_ID_LISTS`
/// (`api/change_stream.py`), the one declared tuple naming every id list a
/// `ChangeEvent` carries; an engine test fails when the fixture goes stale
/// against that tuple. This suite reads that SAME file (never copied into
/// the Swift tree — a copy could drift from the engine's own generator) and
/// decodes it through BOTH of `ChangeEvent`'s decode paths, so a kind added
/// to `CHANGE_ID_LISTS` and missed in Swift's `CodingKeys`/`init`s fails
/// HERE, not silently in production.
@Suite("ChangeEvent id-lists contract (engine fixture)")
struct ChangeEventIdListsContractTests {

    // MARK: - Fixture access

    private static func fixtureData() throws -> Data {
        let url = try AppSource.sibling("fichero-server")
            .appendingPathComponent("tests/contracts/change_event_all_id_lists.json")
        return try Data(contentsOf: url)
    }

    private static func fixtureDict() throws -> [String: Any] {
        let object = try JSONSerialization.jsonObject(with: try fixtureData())
        return try #require(object as? [String: Any])
    }

    /// Every top-level key in the fixture that names an id list — discovered
    /// from the fixture itself (its own `_ids` suffix and array shape), NOT
    /// from a second hand-written Swift list. A literal Swift array of
    /// expected keys is exactly the kind of second list `CHANGE_ID_LISTS`
    /// itself exists to replace (see its own doc comment) — repeating that
    /// mistake here, one file away, would defeat the point of reading the
    /// engine's fixture at all.
    private static func idLists(in fixture: [String: Any]) -> [String: [String]] {
        var result: [String: [String]] = [:]
        for (key, value) in fixture {
            guard key.hasSuffix("_ids"), let list = value as? [String] else { continue }
            result[key] = list
        }
        return result
    }

    /// `entity_ids` → `entityIds`, matching `ChangeEvent`'s own `CodingKeys`
    /// naming, so the fixture's own key names drive which `ChangeEvent`
    /// property is checked — not a hand-maintained translation table.
    private static func camelCase(fromSnakeCase snake: String) -> String {
        let parts = snake.split(separator: "_")
        guard let first = parts.first else { return snake }
        let rest = parts.dropFirst().map { $0.prefix(1).uppercased() + $0.dropFirst() }
        return ([String(first)] + rest).joined()
    }

    /// Every `[String]`-typed property `ChangeEvent` actually decoded onto,
    /// keyed by its Swift property name — via `Mirror`, the same coverage
    /// idiom `SegmentMappingTests` uses, so a NEW id list the fixture gains
    /// but no `ChangeEvent` property claims is caught by name-matching
    /// below, not merely by presence somewhere in the struct.
    private static func decodedIdLists(from event: ChangeEvent) -> [String: [String]] {
        var result: [String: [String]] = [:]
        for child in Mirror(reflecting: event).children {
            guard let label = child.label, let list = child.value as? [String] else { continue }
            result[label] = list
        }
        return result
    }

    /// Every fixture id list must land on ITS named `ChangeEvent` property,
    /// non-empty, with the SAME values in the SAME order. A list present in
    /// the fixture but absent from `decodedIdLists` (a kind
    /// `CHANGE_ID_LISTS` grew and neither decode path was updated for)
    /// fails here: `actual` is `nil`, `nil != expectedList`.
    private static func assertFixtureListsSurvive(
        decoding event: ChangeEvent,
        fixture: [String: Any],
        path: String
    ) throws {
        let expected = Self.idLists(in: fixture)
        // A floor, not an exact count: the fixture is free to grow past what
        // this file knew about when written, and that growth is exactly the
        // case this suite exists to catch — not to reject.
        #expect(expected.count >= 9, "\(path): fewer *_ids arrays in the fixture than expected (\(expected.count)) — did the fixture's own shape change?")
        let decoded = Self.decodedIdLists(from: event)
        for (key, expectedList) in expected {
            let swiftName = Self.camelCase(fromSnakeCase: key)
            let actualList = decoded[swiftName]
            #expect(
                actualList == expectedList,
                "\(path): fixture key \(key) (Swift `\(swiftName)`) expected \(expectedList), decoded \(String(describing: actualList))"
            )
        }
    }

    // MARK: - Direct stream path

    @Test("the direct stream decode path (ChangeEvent.init(from:)) carries every fixture id list, non-empty, in order")
    func directStreamPathCarriesEveryFixtureIdList() throws {
        let fixture = try Self.fixtureDict()
        let event = try JSONDecoder().decode(ChangeEvent.self, from: try Self.fixtureData())
        try Self.assertFixtureListsSurvive(decoding: event, fixture: fixture, path: "direct stream")
    }

    // MARK: - Folded activity path

    /// Builds the SAME `[String: String]` metadata shape
    /// `_change_event_to_activity_response` folds a `ChangeEvent` into
    /// (`api/routes/system/activity.py`: every `CHANGE_ID_LISTS` list
    /// `json.dumps`'d into a string value under its own key, plus
    /// `change_type`) — from the fixture's own id lists, not a second
    /// hand-typed metadata literal.
    private static func foldedActivityMetadata(from fixture: [String: Any]) throws -> [String: String] {
        var metadata: [String: String] = ["change_type": fixture["type"] as? String ?? ""]
        for (key, list) in Self.idLists(in: fixture) {
            let data = try JSONSerialization.data(withJSONObject: list)
            metadata[key] = String(data: data, encoding: .utf8)
        }
        return metadata
    }

    @Test("the folded activity decode path (ChangeEvent.init(activityMetadata:)) carries every fixture id list, non-empty, in order")
    func activityPathCarriesEveryFixtureIdList() throws {
        let fixture = try Self.fixtureDict()
        let metadata = try Self.foldedActivityMetadata(from: fixture)
        let event = try #require(ChangeEvent(activityMetadata: metadata))
        try Self.assertFixtureListsSurvive(decoding: event, fixture: fixture, path: "folded activity")
    }
}
