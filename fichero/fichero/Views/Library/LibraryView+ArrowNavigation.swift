import SwiftUI

// MARK: - Arrow Navigation

extension LibraryView {
    enum ArrowDirection {
        case upDir, down, left, right, pageUp, pageDown
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
        let ids: [String]
        if isShowingEntitiesCollection {
            ids = filteredEntities.map { entitySelectionId(for: $0) }
        } else {
            ids = filteredDocuments.map(\.id)
        }
        guard !ids.isEmpty else { return .ignored }

        // Select first item if nothing is selected yet
        guard let currentIndex = currentSelectionIndex(in: ids) else {
            selection = [ids[0]]
            selectionAnchor = ids[0]
            focusSelectedEntityIfNeeded()
            return .handled
        }

        let step = stepSize(for: direction)
        guard step != 0 else { return .ignored }
        let targetIndex = currentIndex + step
        guard targetIndex >= 0, targetIndex < ids.count else { return .handled }

        applySelection(targetIndex: targetIndex, ids: ids)
        if displayMode == .icon || displayMode == .list || displayMode == .table {
            listScrollTarget = ids[targetIndex]
        }
        focusSelectedEntityIfNeeded()
        return .handled
    }

    private func currentSelectionIndex(in ids: [String]) -> Int? {
        guard let firstSelected = selection.first else { return nil }
        return ids.firstIndex(of: firstSelected)
    }

    private func stepSize(for direction: ArrowDirection) -> Int {
        switch direction {
        case .upDir:  return displayMode == .icon ? -gridColumnCount : -1
        case .down:   return displayMode == .icon ?  gridColumnCount :  1
        case .left:   return -1
        case .right:  return  1
        case .pageUp: return -pageStepSize()
        case .pageDown: return pageStepSize()
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
        if NSEvent.modifierFlags.contains(.shift),
           let anchor = selectionAnchor,
           let anchorIndex = ids.firstIndex(of: anchor) {
            let range = min(anchorIndex, targetIndex)...max(anchorIndex, targetIndex)
            selection = Set(range.map { ids[$0] })
        } else if NSEvent.modifierFlags.contains(.shift) {
            selection.insert(targetId)
            selectionAnchor = targetId
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
    }

    private func focusSelectedEntityIfNeeded() {
        guard isShowingEntitiesCollection,
              let firstId = selection.first,
              let entity = filteredEntities.first(where: { entitySelectionId(for: $0) == firstId }) else { return }
        focusEntityIfPossible(entity)
    }
}
