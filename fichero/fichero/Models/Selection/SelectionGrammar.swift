import Foundation

/// The ONE Mac selection grammar (#4377).
///
/// Click, ⌘-click, ⇧-click, ⇧-arrow and ⌘A are a single set of rules about an
/// ordered list, a selected set, and an anchor. Before this type the app had
/// two implementations of those rules — a correct reducer used by the inspector
/// entity list, and a private, subtly different copy inside `LibraryView` — so
/// the same gesture built a different selection depending on which list you
/// were pointing at.
///
/// The library copy's specific failure was a **silent no-op**: its shift-click
/// `guard let anchorIndex = …  else { return }` did nothing at all whenever the
/// remembered anchor was no longer in the visible list. That is not rare — it
/// happens after a filter change, a re-sort, a view-mode switch (columns mode
/// navigates a different ordered list), or any selection that arrived from
/// state restoration rather than from a click, which leaves the anchor nil
/// entirely. The gesture appeared "not enabled" because the app really did
/// nothing. The keyboard path had already grown a robust fallback chain for
/// exactly this (#4160); the mouse path never got it. Now there is one chain,
/// and both use it.
///
/// Pure, platform-free and `enum`-namespaced on purpose. Every rule below is a
/// row in `SelectionGrammarTests`' table, which is the thing that stops a third
/// copy of these rules appearing.
enum SelectionGrammar {

    // MARK: - Inputs

    /// The two modifiers that change what a click means. Deliberately NOT
    /// `NSEvent.ModifierFlags`: this type has to be constructible in a test and
    /// on iOS, so the platform event is translated at the call site.
    struct Modifiers: OptionSet, Equatable, Sendable {
        let rawValue: Int

        static let shift = Modifiers(rawValue: 1 << 0)
        static let command = Modifiers(rawValue: 1 << 1)

        init(rawValue: Int) {
            self.rawValue = rawValue
        }
    }

    // MARK: - Output

    /// The complete selection state after one gesture. All three fields are
    /// returned together because they must move together: a result that
    /// updated the selection but left the anchor or cursor stale is precisely
    /// how the two old implementations drifted.
    struct Result: Equatable {
        /// The ids that are now selected.
        let selection: Set<String>
        /// The row a future range extends FROM. Nil only when nothing is
        /// selected.
        let anchor: String?
        /// The row the arrows resume from — the moving end of a range, which
        /// is NOT the anchor.
        let cursor: String?
    }

    // MARK: - Anchor resolution

    /// The row a range must extend from, and never nil.
    ///
    /// Preference: the remembered anchor if it is still visible, then the
    /// TOPMOST selected row in visual order (so extending after a re-sort or a
    /// filter still means something), then the row the user just acted on.
    ///
    /// Never `selection.first` — that is `Set` hash order, which would make
    /// the same gesture produce different ranges on different runs.
    static func resolvedAnchor(
        anchor: String?,
        selection: Set<String>,
        ids: [String],
        fallingBackTo fallback: String
    ) -> String {
        if let anchor, ids.contains(anchor) { return anchor }
        if let topmostIndex = selection.compactMap({ ids.firstIndex(of: $0) }).min() {
            return ids[topmostIndex]
        }
        return fallback
    }

    // MARK: - Click

    /// The full click grammar.
    ///
    /// - plain → select one, anchor and cursor move to it
    /// - ⌘ → toggle one, keep the rest, anchor and cursor move to it
    /// - ⇧ → contiguous range from the anchor to the clicked row; the anchor
    ///   does NOT move (repeated ⇧-clicks re-extend from the same place), the
    ///   cursor does
    /// - ⇧⌘ → the same range, UNIONED with the existing selection, so a range
    ///   can be added to a discontiguous set
    ///
    /// A ⇧-click always produces a selection. If the clicked row is not in
    /// `ids` at all — a deep Miller-column child, which lives in a different
    /// ordered list — a range across two lists has no meaning, so it degrades
    /// to selecting that row. It never degrades to doing nothing.
    static func click(
        id: String,
        in ids: [String],
        selection: Set<String>,
        anchor: String?,
        modifiers: Modifiers
    ) -> Result {
        if modifiers.contains(.shift) {
            let anchorId = resolvedAnchor(
                anchor: anchor,
                selection: selection,
                ids: ids,
                fallingBackTo: id
            )
            guard let anchorIndex = ids.firstIndex(of: anchorId),
                  let clickedIndex = ids.firstIndex(of: id) else {
                return Result(selection: [id], anchor: id, cursor: id)
            }
            let range = min(anchorIndex, clickedIndex)...max(anchorIndex, clickedIndex)
            let rangeIds = Set(ids[range])
            return Result(
                selection: modifiers.contains(.command) ? selection.union(rangeIds) : rangeIds,
                anchor: anchorId,
                cursor: id
            )
        }

        if modifiers.contains(.command) {
            var updated = selection
            if updated.contains(id) {
                updated.remove(id)
            } else {
                updated.insert(id)
            }
            // The anchor follows a ⌘-click even when the click DESELECTED the
            // row: Finder extends from where you last acted, not from where
            // you last landed a selection.
            return Result(selection: updated, anchor: id, cursor: id)
        }

        return Result(selection: [id], anchor: id, cursor: id)
    }

    // MARK: - Keyboard

    /// Arrow-key movement. `extendingRange` is ⇧ held.
    ///
    /// Same anchor rule as `click`: during an extend the anchor never moves,
    /// only the cursor end does — which is what lets ⇧↓ ⇧↓ ⇧↑ SHRINK the
    /// selection instead of only ever growing it.
    static func extend(
        to targetId: String,
        in ids: [String],
        selection: Set<String>,
        anchor: String?,
        extendingRange: Bool
    ) -> Result {
        guard extendingRange else {
            return Result(selection: [targetId], anchor: targetId, cursor: targetId)
        }
        let anchorId = resolvedAnchor(
            anchor: anchor,
            selection: selection,
            ids: ids,
            fallingBackTo: targetId
        )
        guard let anchorIndex = ids.firstIndex(of: anchorId),
              let targetIndex = ids.firstIndex(of: targetId) else {
            return Result(selection: [targetId], anchor: targetId, cursor: targetId)
        }
        let range = min(anchorIndex, targetIndex)...max(anchorIndex, targetIndex)
        return Result(
            selection: Set(ids[range]),
            anchor: anchorId,
            cursor: targetId
        )
    }

    // MARK: - Select All / clear

    /// ⌘A over the rows actually shown (#4376) — "all" means all *visible*,
    /// so a filtered list selects what the filter left.
    ///
    /// The anchor goes to the FIRST row and the cursor to the last, so a
    /// following ⇧-click or ⇧↑ narrows the selection from the top the way
    /// Finder does. Leaving the anchor wherever the last click happened would
    /// make the next ⇧-click extend from a row the user can no longer see —
    /// the #4377 defect in a different disguise.
    static func selectAll(in ids: [String]) -> Result {
        guard let first = ids.first, let last = ids.last else {
            return Result(selection: [], anchor: nil, cursor: nil)
        }
        return Result(selection: Set(ids), anchor: first, cursor: last)
    }

    /// Escape, or a click on empty space.
    static func clear() -> Result {
        Result(selection: [], anchor: nil, cursor: nil)
    }
}
