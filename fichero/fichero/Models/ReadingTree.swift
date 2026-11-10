import Foundation

/// A line's versions as a tree (`source.editor.reader-line-discloses-its-versions`, #6492): a reading made from
/// another reading of the line, or correcting one, hangs under it; every other reading is a root. Siblings run oldest
/// first. A reading whose parent is not shown (withdrawn, or not this line's) is a root, never dropped.
struct ReadingTree: Equatable, Identifiable {
    let reading: InspectorText.Reading
    let children: [ReadingTree]

    var id: String { reading.id }

    /// The roots for one segment's readings. `retracted` ids are left out unless `showsWithdrawn`.
    static func build(
        _ readings: [InspectorText.Reading], retracted: Set<String> = [], showsWithdrawn: Bool = false
    ) -> [ReadingTree] {
        let shown = readings.filter { showsWithdrawn || !retracted.contains($0.id) }
        let ids = Set(shown.map(\.id))
        let parentOf: (InspectorText.Reading) -> String? = { reading in
            [reading.derivedFromId, reading.correctsId].lazy.compactMap { $0 }.first { ids.contains($0) && $0 != reading.id }
        }
        let byParent = Dictionary(grouping: shown) { parentOf($0) ?? "" }
        // ponytail: a cycle in the data (A from B, B from A) has no root, so its readings fall out of the tree.
        func nodes(under parent: String) -> [ReadingTree] {
            let siblings = (byParent[parent] ?? []).sorted(by: oldestFirst)
            return siblings.map { ReadingTree(reading: $0, children: nodes(under: $0.id)) }
        }
        return nodes(under: "")
    }

    private static func oldestFirst(_ lhs: InspectorText.Reading, _ rhs: InspectorText.Reading) -> Bool {
        let left = lhs.createdAt ?? .distantPast, right = rhs.createdAt ?? .distantPast
        return left == right ? lhs.id < rhs.id : left < right
    }

    /// The line has something to disclose: more than one reading shown.
    static func discloses(_ roots: [ReadingTree]) -> Bool {
        roots.count > 1 || roots.contains { !$0.children.isEmpty }
    }
}
