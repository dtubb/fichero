@testable import Fichero
import Foundation
import Testing

/// Spec: docs/contributor_manual/specs/source/readings-and-apparatus.md -- `source.hand.assign-from-every-surface`,
/// `source.hand.mixed-selection-shows-mixed`. What breaks without these: a surface that attributes one line at a time
/// where the engine takes many in one undo, a Remove Hand that leaves the file's attribution standing, a mixed
/// selection shown as one hand, a shortcut with no hand to attribute to.
struct HandAssignmentTests {
    private let hands: [InspectorHands.ListedHand] = [
        .init(id: "b", label: "hand B", scribe: nil, date: nil, style: nil),
        .init(id: "c", label: "hand C", scribe: nil, date: nil, style: nil)
    ]

    private func attribution(_ id: String, hand: String) -> InspectorHands.Attribution {
        .init(id: id, handId: hand, certainty: nil, judgedBy: nil, fromFile: nil)
    }

    @Test("one segment is hand.attribute; several are one hand.attribute_many; none is no call")
    func attributeCalls() throws {
        let one = try #require(HandAssignment.attribute(handId: "b", segmentIds: ["s1"]))
        #expect(one.action == "hand.attribute")
        #expect(one.name == "Attribute Hand")
        let many = try #require(HandAssignment.attribute(handId: "b", segmentIds: ["s1", "s2", "s1"]))
        #expect(many.action == "hand.attribute_many")
        #expect(many.name == "Attribute Hand to 2 Segments")
        #expect((many.params as? HandAttributeManyRequest)?.segmentIds == ["s1", "s2"])
        #expect(HandAssignment.attribute(handId: "b", segmentIds: []) == nil)
    }

    @Test("Remove Hand withdraws every live attribution of the selection, the file's too, once each")
    func removeCalls() throws {
        let bySegment = ["s1": [attribution("a1", hand: "b")], "s2": [attribution("a2", hand: "c"), attribution("a3", hand: "b")]]
        let many = try #require(HandAssignment.remove(selection: ["s1", "s2"], attributions: bySegment))
        #expect(many.action == "hand.unattribute_many")
        #expect(Set((many.params as? HandUnattributeManyRequest)?.attributionIds ?? []) == ["a1", "a2", "a3"])
        let one = try #require(HandAssignment.remove(selection: ["s1"], attributions: bySegment))
        #expect(one.action == "hand.unattribute")
        #expect(HandAssignment.remove(selection: ["s9"], attributions: bySegment) == nil)
    }

    @Test("the selection's hand: none, one hand's label, or Mixed")
    func summary() {
        let onB = [attribution("a1", hand: "b")], alsoB = [attribution("a2", hand: "b")]
        let onC = [attribution("a3", hand: "c")]
        #expect(HandAssignment.summary(selection: ["s1"], attributions: [:], hands: hands) == "No hand")
        #expect(HandAssignment.summary(selection: ["s1", "s2"], attributions: ["s1": onB, "s2": alsoB], hands: hands) == "hand B")
        #expect(HandAssignment.summary(selection: ["s1", "s2"], attributions: ["s1": onB, "s2": onC], hands: hands) == "Mixed")
        #expect(HandAssignment.summary(selection: ["s1", "s2"], attributions: ["s1": onB], hands: hands) == "Mixed")
        #expect(HandAssignment.summary(selection: ["s1"], attributions: ["s1": onB + onC], hands: hands) == "hand B + hand C")
        #expect(HandAssignment.summary(selection: [], attributions: [:], hands: hands) == "No hand")
    }

    @Test("the last-used hand is remembered per defaults suite and offered only while it is still listed")
    func lastHand() throws {
        let defaults = try #require(UserDefaults(suiteName: "HandAssignmentTests"))
        defaults.removePersistentDomain(forName: "HandAssignmentTests")
        #expect(HandAssignment.lastHand(in: hands, defaults: defaults) == nil)
        HandAssignment.remember("c", defaults: defaults)
        #expect(HandAssignment.lastHand(in: hands, defaults: defaults)?.label == "hand C")
        HandAssignment.remember("gone", defaults: defaults)
        #expect(HandAssignment.lastHand(in: hands, defaults: defaults) == nil)
    }
}
