import SwiftUI

/// Pure cursor resolution for keyboard navigation (#4160): the position the
/// arrows resume from. Preference order: the explicit cursor (last arrow-nav
/// landing), the anchor (last plain click), then the TOPMOST selected row in
/// visual order. Never `Set.first` — hash order made ↓ resume, Return open,
/// and follow-scroll target an arbitrary row after any multi-select.
enum LibraryKeyboardCursor {
    static func index(
        cursor: String?,
        anchor: String?,
        selection: Set<String>,
        ids: [String]
    ) -> Int? {
        if let cursor, selection.contains(cursor), let idx = ids.firstIndex(of: cursor) {
            return idx
        }
        if let anchor, selection.contains(anchor), let idx = ids.firstIndex(of: anchor) {
            return idx
        }
        return selection.compactMap { ids.firstIndex(of: $0) }.min()
    }
}

// MARK: - Arrow Navigation

extension LibraryView {
    enum ArrowDirection {
        case upDir, down, left, right, pageUp, pageDown, home, end
    }

    #if os(macOS)
    func handleMoveCommand(_ direction: MoveCommandDirection) {
        switch direction {
        case .up:
            _ = handleArrowKey(direction: .upDir)
        case .down:
            _ = handleArrowKey(direction: .down)
        case .left:
            _ = handleArrowKey(direction: .left)
        case .right:
            _ = handleArrowKey(direction: .right)
        default:
            break
        }
    }
    #endif

    /// Handle arrow key press for navigating documents.
    /// All four arrows navigate within the content area (like Finder).
    /// Tab/Shift+Tab cycle focus between panes.
    func handleArrowKey(direction: ArrowDirection) -> KeyPress.Result {
        // Miller columns (#4160 step 4): ←/→ move BETWEEN columns; ↑/↓ and
        // the rest fall through to the shared cursor logic over the ACTIVE
        // column's ids (keyboardNavigationDocuments).
        if displayMode == .columns, !isShowingEntitiesCollection {
            let result = handleColumnsArrowKey(direction: direction)
            if result == .handled { return result }
        }
        let ids: [String]
        if isShowingEntitiesCollection {
            ids = filteredEntities.map { entitySelectionId(for: $0) }
        } else {
            ids = keyboardNavigationDocuments.map(\.id)
        }
        guard !ids.isEmpty else { return .ignored }

        // Select first item if nothing is selected yet
        guard let currentIndex = currentSelectionIndex(in: ids) else {
            selection = [ids[0]]
            selectionAnchor = ids[0]
            selectionCursor = ids[0]
            focusSelectedEntityIfNeeded()
            return .handled
        }

        let targetIndex: Int
        switch direction {
        case .home: targetIndex = 0
        case .end: targetIndex = ids.count - 1
        default:
            let step = stepSize(for: direction)
            guard step != 0 else { return .ignored }
            let candidate = currentIndex + step
            guard candidate >= 0, candidate < ids.count else { return .handled }
            targetIndex = candidate
        }

        applySelection(targetIndex: targetIndex, ids: ids)
        if displayMode == .icon || displayMode == .list || displayMode == .table || displayMode == .columns {
            listScrollTarget = ids[targetIndex]
        }
        focusSelectedEntityIfNeeded()
        return .handled
    }

    /// The ordered documents keyboard actions navigate over — the ACTIVE
    /// Miller column in columns mode (#4160 step 4), the flat browsed list
    /// everywhere else. One seam so arrows / Return / Space / shift-ranges
    /// all agree on the same row order.
    var keyboardNavigationDocuments: [Document] {
        displayMode == .columns ? columnsActiveDocuments : filteredDocuments
    }

    /// Resolve a selectable id to its Document wherever it lives — the
    /// browsed list, or a deeper Miller column's children cache — so
    /// Return / Space / Quick Look / delete act on deep-column rows too.
    func navigableDocument(for id: String) -> Document? {
        filteredDocuments.first { $0.id == id }
            ?? columnsChildren.values.lazy.compactMap({ $0.first { $0.id == id } }).first
    }

    private func currentSelectionIndex(in ids: [String]) -> Int? {
        LibraryKeyboardCursor.index(
            cursor: selectionCursor,
            anchor: selectionAnchor,
            selection: selection,
            ids: ids
        )
    }

    /// The id keyboard/scroll actions should treat as "the" selection, in
    /// VISUAL order — never `.first` on the selection Set (hash order). Used
    /// by the list watchers and Return-to-open.
    var orderedPrimarySelectionId: String? {
        let ids: [String]
        if isShowingEntitiesCollection {
            ids = filteredEntities.map { entitySelectionId(for: $0) }
        } else {
            ids = keyboardNavigationDocuments.map(\.id)
        }
        if let idx = LibraryKeyboardCursor.index(
            cursor: selectionCursor,
            anchor: selectionAnchor,
            selection: selection,
            ids: ids
        ) {
            return ids[idx]
        }
        // Table outline child rows (#4160 step 3): "<doc>:artifact:<id>" ids
        // aren't in the document list, so resolve to the topmost selected
        // row's PARENT document — Return/Space/Quick Look then act on the
        // right document instead of silently doing nothing.
        return selection
            .compactMap { id -> Int? in
                guard let colon = id.firstIndex(of: ":") else { return nil }
                return ids.firstIndex(of: String(id[..<colon]))
            }
            .min()
            .map { ids[$0] }
    }

    private func stepSize(for direction: ArrowDirection) -> Int {
        switch direction {
        case .upDir:  return displayMode == .icon ? -gridColumnCount : -1
        case .down:   return displayMode == .icon ?  gridColumnCount :  1
        case .left:   return -1
        case .right:  return  1
        case .pageUp: return -pageStepSize()
        case .pageDown: return pageStepSize()
        // Absolute jumps — handled before stepSize is consulted.
        case .home, .end: return 0
        }
    }

    private func pageStepSize() -> Int {
        if displayMode == .icon {
            // Approximate one visual page in icon grid navigation.
            return max(gridColumnCount * 4, gridColumnCount)
        }
        return 10
    }

    private func applySelection(targetIndex: Int, ids: [String]) {
        let targetId = ids[targetIndex]
        #if os(macOS)
        if NSEvent.modifierFlags.contains(.shift) {
            // Finder/NNW semantics (#4160): the anchor NEVER moves during a
            // shift-extend — only the cursor end of the range does. The old
            // code re-anchored on the target whenever the anchor was missing,
            // so ⇧↓ degraded to add-one-at-a-time and could never shrink.
            let anchor = selectionAnchor.flatMap { ids.contains($0) ? $0 : nil }
                ?? selection.compactMap { ids.firstIndex(of: $0) }.min().map { ids[$0] }
                ?? targetId
            selectionAnchor = anchor
            if let anchorIndex = ids.firstIndex(of: anchor) {
                let range = min(anchorIndex, targetIndex)...max(anchorIndex, targetIndex)
                selection = Set(range.map { ids[$0] })
            } else {
                selection = [targetId]
            }
        } else {
            selection = [targetId]
            selectionAnchor = targetId
        }
        #else
        // iOS: keyboard modifier flags aren't available on .onKeyPress;
        // collapse to plain selection. Modifier-aware keyboard selection
        // is a separate iPad UI pass.
        selection = [targetId]
        selectionAnchor = targetId
        #endif
        selectionCursor = targetId
    }

    private func focusSelectedEntityIfNeeded() {
        guard isShowingEntitiesCollection,
              let primaryId = orderedPrimarySelectionId,
              let entity = filteredEntities.first(where: { entitySelectionId(for: $0) == primaryId }) else { return }
        focusEntityIfPossible(entity)
    }
}
