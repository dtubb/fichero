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
/// ## The two anchor rules, which are the whole difference between multi-select
/// ## feeling right and feeling nearly right
///
/// 1. **⌘-click moves the anchor even when the click DESELECTED the row.**
///    Finder extends from where you last *acted*, not from where you last
///    landed a selection. A copy that only moves the anchor on selection looks
///    correct until someone ⌘-clicks a row off and then ⇧-clicks.
///
/// 2. **⇧ holds the anchor still and moves only the cursor.** That is what lets
///    ⇧↓ ⇧↓ ⇧↑ *shrink* a selection instead of only ever growing it. A copy
///    that moves the anchor on ⇧ appears to work until someone reverses
///    direction mid-extend.
///
/// Neither is something a second implementation arrives at by accident, which
/// is the practical argument for delegating here rather than reimplementing.
///
/// ## Adopting this from a new surface
///
/// `click` needs an **ordered list**. ⌘ does not use it — that branch is a pure
/// toggle — but ⇧ indexes into it to build a range, so a surface with no
/// inherent order (a spatial canvas, say) can adopt ⌘ immediately and must
/// first *decide* what order ⇧ extends along. That is a design question about
/// the surface, not a gap in this type.
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

    /// Land on exactly one row, with no modifier in play (#4377).
    ///
    /// Three callers needed this and none of them could say it: Miller-columns
    /// ←/→, `openDocument`, and the arrow path's "nothing was selected yet"
    /// branch each wrote `Result(selection: [id], anchor: id, cursor: id)` by
    /// hand. That construction is the WORST shape to leave lying around,
    /// because it is the grammar's own output type filled in manually — it
    /// reads as delegation, the guardrail scored it as delegation, and it is a
    /// fourth private copy of the plain-select rule. If that rule ever changes
    /// (a surface that wants the cursor to lag the anchor, say), those three
    /// sites are exactly the ones that would not change with it.
    ///
    /// It is deliberately NOT expressed as `click(modifiers: [])`: `click`
    /// requires an ordered list, and every caller here is landing on a row for
    /// which no single ordered list is meaningful — a different Miller column,
    /// a document opened from another window, an empty selection. Needing a
    /// list you have to invent is how a caller ends up passing the wrong one,
    /// which is the other half of this same issue.
    static func select(_ id: String) -> Result {
        Result(selection: [id], anchor: id, cursor: id)
    }

    // MARK: - Marquee

    /// Rubber-band selection over a surface with NO inherent order (#4436).
    ///
    /// The canvases were assigning the marqueed ids straight over the top of
    /// whatever was selected, so a ⇧-marquee threw away the selection it was
    /// meant to extend — the other half of #4409 from the one already fixed
    /// ("published one of five"). In Finder both ⇧ and ⌘ ADD to the selection
    /// during a rubber-band; a plain drag replaces.
    ///
    /// A plain marquee that swept up nothing is a click on empty space, and
    /// clears — the same thing the background tap does, so the two gestures
    /// cannot disagree.
    ///
    /// The anchor is the LEXICALLY smallest id, not `ids.first`: this surface
    /// has no visual order to take a topmost from, and `Set.first` is hash
    /// order, which would make the same drag leave a different anchor on
    /// different runs. Deterministic beats meaningful when meaningful is not
    /// available; the ordered choice belongs to #4460.
    static func marquee(
        ids: Set<String>,
        selection: Set<String>,
        modifiers: Modifiers
    ) -> Result {
        let combined = modifiers.isEmpty ? ids : selection.union(ids)
        guard let anchor = combined.min() else { return clear() }
        return Result(selection: combined, anchor: anchor, cursor: anchor)
    }

    // MARK: - Reconciling a selection changed outside the grammar

    /// Recover the anchor and cursor after something OTHER than this grammar
    /// wrote the selection (#4436).
    ///
    /// This exists for exactly one caller: the native `Table`, which owns its
    /// own clicks. That is deliberate — `NSTableView` already implements these
    /// same Finder rules, and taking the clicks back would cost column
    /// drag-reorder, the native keyboard loop and its accessibility. What the
    /// Table does NOT own is `selectionAnchor` / `selectionCursor`, which the
    /// SHARED arrow-key path reads. So the anchor is reconstructed from the
    /// set change rather than re-derived from the new selection alone.
    ///
    /// Deriving it from `current` alone is what the old table code did, and it
    /// cannot express rule 1: a ⌘-click that DESELECTED a row must still move
    /// the anchor there, and that row is by definition ABSENT from `current`.
    /// The symmetric difference is the only place it survives.
    ///
    /// When many rows changed at once (a ⇧-range, ⌘A) the anchor is held still
    /// per rule 2 as long as it is still selected, and the cursor goes to the
    /// selected row FURTHEST from it in visual order — which for a contiguous
    /// range is exactly the moving end, growing or shrinking. For a
    /// discontiguous ⌘-built set "furthest" is a convention rather than a
    /// truth, but it is a deterministic, visual-order convention, which is more
    /// than `Set` iteration offered.
    ///
    /// ## Why `modifiers` is threaded in (#4531)
    ///
    /// The set delta ALONE cannot arbitrate between the two anchor rules: a
    /// one-row ⇧-shrink (⇧↑ after ⇧↓⇧↓, or a ⇧-click one row back) and a
    /// one-row ⌘-deselect produce the IDENTICAL before/after pair, and the
    /// rules demand opposite answers — hold the anchor (rule 2) versus follow
    /// the acted row (rule 1). Two shipped pins asked for both at once. So the
    /// Table's caller now passes the modifiers that were down when the
    /// selection changed: ⇧ present means a range operation and the anchor
    /// holds, whatever the count; otherwise a single-row change is a click and
    /// the anchor follows it. Callers with no gesture context pass nothing and
    /// get the old click-leaning defaults.
    static func reconcile(
        from previous: Set<String>,
        to current: Set<String>,
        anchor: String?,
        in ids: [String],
        modifiers: Modifiers = []
    ) -> Result {
        if current.isEmpty { return clear() }

        let changed = previous.symmetricDifference(current)

        // ⇧ was down: this is a range operation, whatever the delta's size —
        // rule 2 says the anchor holds and only the cursor end moves. Skips
        // both click-shaped branches below, because with ⇧ known they would
        // both be wrong answers.
        if !modifiers.contains(.shift) {
            // ⌘ was down and exactly one row changed: that is a ⌘-toggle, and
            // rule 1 says the anchor follows the acted row EVEN when the
            // toggle deselected it — including deselecting down to a single
            // survivor, which without the modifier is indistinguishable from
            // a plain click on that survivor.
            if modifiers.contains(.command), changed.count == 1, let acted = changed.first {
                return Result(selection: current, anchor: acted, cursor: acted)
            }

            // ONE NAMED AMBIGUITY when no gesture context arrived, because a
            // set difference cannot resolve it and pretending otherwise is how
            // a "fix" ships a new wrong answer.
            //
            // Collapsing a multi-selection with a PLAIN click ({a,b} → {a})
            // and ⌘-clicking the second row of a pair OFF ({a,c} → {a})
            // produce the IDENTICAL before/after pair. Resolved toward the
            // plain click, which is far more frequent, and whose wrong answer
            // would be worse: it would leave the anchor on a row the user just
            // DESELECTED. A caller that DOES pass modifiers never reaches this
            // compromise for the ⌘ case — the branch above claims it.
            if current.count == 1, let survivor = current.first, previous.contains(survivor) {
                return Result(selection: current, anchor: survivor, cursor: survivor)
            }

            if changed.count == 1, let acted = changed.first {
                return Result(selection: current, anchor: acted, cursor: acted)
            }
        }

        let topmost = current.compactMap { ids.firstIndex(of: $0) }.min().map { ids[$0] }
        let heldAnchor = anchor.flatMap { current.contains($0) ? $0 : nil } ?? topmost
        guard let heldAnchor, let anchorIndex = ids.firstIndex(of: heldAnchor) else {
            // Nothing selected is in `ids` — outline child rows, say, whose ids
            // are not document ids. Fall back to the lexical minimum so the
            // result is at least deterministic instead of hash-ordered.
            let fallback = current.min()
            return Result(selection: current, anchor: fallback, cursor: fallback)
        }
        let cursor = current
            .compactMap { ids.firstIndex(of: $0) }
            .max { abs($0 - anchorIndex) < abs($1 - anchorIndex) }
            .map { ids[$0] }
        return Result(selection: current, anchor: heldAnchor, cursor: cursor ?? heldAnchor)
    }
}
