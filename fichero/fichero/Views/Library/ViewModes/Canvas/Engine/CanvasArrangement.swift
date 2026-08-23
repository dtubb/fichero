import Foundation

// MARK: - Arrange by — the one axis that MOVES cards (§20.3, §25.4 step 3)

/// How a board orders its cards into slots.
///
/// §20.3's control strip is four pickers, and this is the only one that moves
/// anything: *Arrange by* re-lays the board, while *Colour by*, *Depth* and
/// *Highlight* re-encode in place. That ratio is the design — most questions
/// should be answered by re-encoding and only a few by re-arranging (§13.2) —
/// which also means the expensive operation is used rarely and deliberately,
/// exactly when an animation is worth watching.
///
/// **A saved layout row always wins.** An arrangement supplies the slot a card
/// takes when nothing has pinned it, so §20.2's "cards that don't move are the
/// ones you pinned" is not a feature to build: it is what
/// `CanvasSceneState.resolve` already does with any default placement.
///
/// **EXTENSION POINT.** New arrangements go here and nowhere else — Date and
/// Entity (build-order step 8) plug in as cases with their own `sortKey`, and
/// get animation, pinning and both canvases for free. What must NOT happen is a
/// second ordering path in a renderer or a view: the two canvases share a layout
/// store, so an arrangement they disagree about is two different boards.
///
/// Deliberately only four cases today. Date and Entity need the dating and
/// entity-density work that has not landed; a picker offering them now would be
/// a menu that lies, which breaks the dead-simple-UX rule harder than their
/// absence does.
enum CanvasArrangement: String, CaseIterable, Identifiable, Sendable {
    /// The order the library handed us — page order for a diary folder. The
    /// pre-arrangement behaviour, renamed rather than changed.
    case asFiled
    /// By label, case-insensitively.
    case name
    /// Grouped by kind, then by label within a kind.
    case type
    /// Nothing but saved rows: unpinned cards keep As Filed order, so this is
    /// "leave my board alone".
    case free

    var id: String { rawValue }

    /// Menu title. Sentence case, matching the rest of the canvas controls.
    var label: String {
        switch self {
        case .asFiled: "As Filed"
        case .name: "Name"
        case .type: "Type"
        case .free: "Free"
        }
    }

    /// SF Symbol for the picker row.
    var icon: String {
        switch self {
        case .asFiled: "tray.full"
        case .name: "textformat.abc"
        case .type: "square.grid.3x1.folder.badge.plus"
        case .free: "hand.raised"
        }
    }

    /// Slot index per placeable id, for a board of `nodes` then non-link
    /// `items` — the order `CanvasSceneState.resolve` walks.
    ///
    /// Sorting is STABLE: ties fall back to the incoming order, so equal keys
    /// never shuffle between two resolves of the same board. Without that, a
    /// board of same-named cards would re-flow on every reconcile and the
    /// animation would fire at random.
    /// One card's sort inputs. A struct rather than a tuple because four
    /// members is past the readable limit for one (and past SwiftLint's).
    private struct SlotEntry {
        let id: String
        let group: Int
        let key: String
        let original: Int
    }

    static func slotIndices(
        _ arrangement: CanvasArrangement,
        nodes: [SpatialNode],
        items: [CanvasItemDisplay]
    ) -> [String: Int] {
        var entries: [SlotEntry] = []
        entries.reserveCapacity(nodes.count + items.count)

        for (index, node) in nodes.enumerated() {
            entries.append(
                SlotEntry(
                    id: node.id, group: groupRank(of: node),
                    key: node.displayLabel.lowercased(), original: index
                )
            )
        }
        // Items come after nodes in `resolve`'s own walk, and keep that
        // relation under every arrangement: a note is a thing you put ON the
        // board, not a document to be filed among the pages.
        for (offset, item) in items.enumerated() where item.kind != .link {
            entries.append(
                SlotEntry(
                    id: item.id, group: itemGroupRank,
                    key: (item.text ?? "").lowercased(), original: nodes.count + offset
                )
            )
        }

        let ordered: [SlotEntry]
        switch arrangement {
        case .asFiled, .free:
            ordered = entries
        case .name:
            ordered = entries.sorted { left, right in
                left.key == right.key ? left.original < right.original : left.key < right.key
            }
        case .type:
            ordered = entries.sorted { left, right in
                if left.group != right.group { return left.group < right.group }
                if left.key != right.key { return left.key < right.key }
                return left.original < right.original
            }
        }

        return Dictionary(
            uniqueKeysWithValues: ordered.enumerated().map { ($0.element.id, $0.offset) }
        )
    }

    /// Kind order for `.type`: the pages first, because a diary folder is
    /// mostly pages and burying them under their annotations would bury the
    /// board. Everything unknown sorts last rather than interleaving.
    private static func groupRank(of node: SpatialNode) -> Int {
        switch node.nodeType {
        case .source: 0
        case .transcription: 1
        case .claim: 2
        case .note: 3
        case .entity: 4
        case .unknown: 5
        }
    }

    /// Canvas items sit after every node kind — see `slotIndices`.
    private static let itemGroupRank = 6
}
