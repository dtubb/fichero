@testable import Fichero
import Foundation
import Testing

/// Decode coverage for the change-stream wire model (#1863, #2479).
///
/// `ChangeEvent.init(from:)` is the boundary where a raw SSE `data:` frame
/// becomes a typed event the domain stores fan on. Its contract — snake_case
/// keys, per-domain id arrays defaulting to `[]`, `actor` defaulting to
/// `"system"`, and `domain`/`verb` derived from the dotted `type` — is what
/// keeps a payload drift from silently mis-routing (or crashing) live updates.
@Suite("ChangeEvent decode")
struct LibraryChangeStreamDecodeTests {
    private func decode(_ object: [String: Any]) throws -> ChangeEvent {
        let data = try JSONSerialization.data(withJSONObject: object)
        return try JSONDecoder().decode(ChangeEvent.self, from: data)
    }

    // MARK: - domain / verb derivation

    @Test("a dotted type splits into domain and verb")
    func dottedTypeSplits() throws {
        let event = try decode(["type": "entity.updated", "actor": "alice"])
        #expect(event.domain == "entity")
        #expect(event.verb == "updated")
    }

    @Test("a multi-segment verb keeps everything after the first dot")
    func multiSegmentVerb() throws {
        // e.g. citation events can carry a compound verb.
        let event = try decode(["type": "citation.reference.updated"])
        #expect(event.domain == "citation")
        #expect(event.verb == "reference.updated")
    }

    @Test("a type with no dot is all domain, empty verb")
    func typeWithoutDot() throws {
        let event = try decode(["type": "ping"])
        #expect(event.domain == "ping")
        #expect(event.verb == "")
    }

    // MARK: - snake_case keys map onto camelCase properties

    @Test("snake_case id arrays and metadata decode onto camelCase properties")
    func snakeCaseKeysMap() throws {
        let event = try decode([
            "type": "entity.merged",
            "entity_ids": ["e1", "e2"],
            "claim_ids": ["c1"],
            "document_ids": ["d1"],
            "artifact_ids": ["a1"],
            "citation_ids": ["ci1"],
            "reference_ids": ["r1"],
            "interpretation_ids": ["in1"],
            "segment_ids": ["s1"],
            "pass_ids": ["p1"],
            "run_id": "run-9",
            "actor": "bob",
            "origin_window": "win-7",
            "ts": "2026-07-05T12:00:00Z"
        ])
        #expect(event.entityIds == ["e1", "e2"])
        #expect(event.claimIds == ["c1"])
        #expect(event.documentIds == ["d1"])
        // source-model slice 2 (#4920, source.events.segment-ids): the
        // engine has always sent artifact_ids/interpretation_ids; Swift
        // dropped both until now. segment_ids/pass_ids are new on the wire.
        #expect(event.artifactIds == ["a1"])
        #expect(event.citationIds == ["ci1"])
        #expect(event.referenceIds == ["r1"])
        #expect(event.interpretationIds == ["in1"])
        #expect(event.segmentIds == ["s1"])
        #expect(event.passIds == ["p1"])
        #expect(event.runId == "run-9")
        #expect(event.actor == "bob")
        #expect(event.originWindow == "win-7")
        #expect(event.timestamp == "2026-07-05T12:00:00Z")
    }

    // MARK: - defaults for absent fields

    @Test("absent id arrays default to empty, not nil")
    func absentArraysDefaultEmpty() throws {
        let event = try decode(["type": "document.updated", "actor": "x"])
        #expect(event.entityIds.isEmpty)
        #expect(event.claimIds.isEmpty)
        #expect(event.documentIds.isEmpty)
        #expect(event.artifactIds.isEmpty)
        #expect(event.citationIds.isEmpty)
        #expect(event.referenceIds.isEmpty)
        #expect(event.interpretationIds.isEmpty)
        #expect(event.segmentIds.isEmpty)
        #expect(event.passIds.isEmpty)
    }

    /// An OLDER event (today's real shape until every backend commit lands)
    /// carrying none of the new keys still decodes — the tolerant-decode
    /// half of `source.events.segment-ids` explicitly, not just implied by
    /// the empty-defaults test above.
    @Test("an event with none of the new keys still decodes, with empty lists for them")
    func olderEventWithoutNewKeysStillDecodes() throws {
        let event = try decode([
            "type": "entity.updated",
            "entity_ids": ["e1"],
            "actor": "system"
        ])
        #expect(event.entityIds == ["e1"])
        #expect(event.artifactIds.isEmpty)
        #expect(event.interpretationIds.isEmpty)
        #expect(event.segmentIds.isEmpty)
        #expect(event.passIds.isEmpty)
    }

    @Test("absent actor defaults to system")
    func absentActorDefaultsToSystem() throws {
        let event = try decode(["type": "entity.created"])
        #expect(event.actor == "system")
    }

    @Test("absent optional metadata stays nil")
    func absentOptionalMetadataNil() throws {
        let event = try decode(["type": "entity.created"])
        #expect(event.runId == nil)
        #expect(event.originWindow == nil)
        #expect(event.timestamp == nil)
    }

    // MARK: - required field

    @Test("a frame with no type fails to decode")
    func missingTypeThrows() {
        #expect(throws: (any Error).self) {
            try decode(["actor": "x"])
        }
    }
}
