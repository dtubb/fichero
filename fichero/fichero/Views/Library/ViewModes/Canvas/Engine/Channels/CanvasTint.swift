import Foundation

// MARK: - Colour by — re-encode, don't re-arrange (§13.2, §20.3)

/// WHAT each card is, said in colour.
///
/// The third of §20.3's four pickers, and the second that moves nothing.
/// §13.2's core move is the argument for it: *same positions, different
/// channel* — ask a new question by changing what the cards SAY, not where they
/// are. Re-arranging costs the user's spatial memory every time; re-encoding
/// costs nothing, which is why most questions should be answered this way and
/// only a few by `CanvasArrangement`.
///
/// **Its own channel, beside `CanvasEmphasis`.** Emphasis carries STRENGTH
/// (which cards matter — a search's heat, an entity highlight); tint carries
/// HUE (what a card is). Multiplexing hue into a scalar strength would make one
/// number mean two things, which is the drift the one-channel argument for
/// emphasis was defending against in the first place. Two channels, each with
/// one meaning, both re-encoding in place.
///
/// **The producer contract, same shape as emphasis:**
/// - keys are PLACEABLE ids (`doc:<id>` via
///   `SpatialLibraryProjector.nodeId(forDocument:)`); a producer working from
///   documents maps through it.
/// - values are palette SLOTS, not colours. The renderers own the actual
///   colours so 2D and 3D cannot drift, and the palette is system-semantic
///   throughout — no hand-rolled ramps.
/// - **EMPTY means NEUTRAL** — no colouring is asked for and every card keeps
///   its kind tint. It does not mean "nothing has this attribute"; a card the
///   producer has no value for is simply absent from the map and keeps its kind
///   tint too.
///
/// **Stable across reconciles.** A slot is derived from the attribute VALUE,
/// never from board position or ordering, so re-arranging never recolours
/// anything — otherwise every transition would be a disco, and the colour would
/// stop being information. See `slot(forValue:)` for why this cannot use
/// `Hasher`.
struct CanvasTint: Equatable {
    /// Placeable id → palette slot. Empty is neutral, NOT "no values".
    private(set) var slots: [String: Int]

    /// How many distinct colours the palette offers. Small on purpose: a legend
    /// the eye can hold is worth more than a unique colour per folder, and
    /// beyond about eight, categorical colours stop being distinguishable —
    /// especially over page images.
    static let paletteSize = 8

    /// Nothing is being asked: every card keeps its kind tint.
    static let neutral = CanvasTint(slots: [:])

    init(slots: [String: Int] = [:]) {
        self.slots = slots.compactMapValues { slot in
            guard slot >= 0 else { return nil }
            return slot % Self.paletteSize
        }
    }

    var isActive: Bool { !slots.isEmpty }

    /// The palette slot for one card, or nil to keep its kind tint.
    func slot(for id: String) -> Int? { slots[id] }

    /// Slots for cards keyed by an attribute VALUE — one colour per distinct
    /// value, the same colour every time.
    static func byValue(_ values: [String: String]) -> CanvasTint {
        guard !values.isEmpty else { return .neutral }
        return CanvasTint(slots: values.mapValues { slot(forValue: $0) })
    }

    /// A stable palette slot for an attribute value.
    ///
    /// FNV-1a rather than `hashValue`, and this is not a style preference:
    /// Swift's `Hasher` is seeded per PROCESS, so a hash-derived colour would
    /// be stable within a launch and different after the next one. A folder
    /// that is teal today and pink tomorrow is not information, it is noise
    /// with a colour — and the user would have no way to tell which it was.
    static func slot(forValue value: String) -> Int {
        var hash: UInt64 = 0xcbf2_9ce4_8422_2325
        for byte in value.utf8 {
            hash ^= UInt64(byte)
            hash = hash &* 0x0000_0100_0000_01b3
        }
        return Int(hash % UInt64(paletteSize))
    }
}
