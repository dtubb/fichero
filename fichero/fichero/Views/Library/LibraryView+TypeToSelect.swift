import SwiftUI

// MARK: - Type-to-Select

extension LibraryView {
    /// Handle a typed character for type-to-select navigation
    func handleTypeToSelect(_ characters: String) {
        // Cancel any pending reset timer
        typeSelectTask?.cancel()

        // Append to the buffer
        typeSelectBuffer += characters.lowercased()

        if isShowingEntitiesCollection,
           let match = filteredEntities.first(where: {
               $0.canonicalName.lowercased().hasPrefix(typeSelectBuffer)
           }) {
            selection = [entitySelectionId(for: match)]
            focusEntityIfPossible(match)
        } else if let match = filteredDocuments.first(where: {
            $0.name.lowercased().hasPrefix(typeSelectBuffer)
        }) {
            selection = [match.id]
        }

        // Reset buffer after 0.5s of inactivity
        typeSelectTask = Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(500))
            guard !Task.isCancelled else { return }
            typeSelectBuffer = ""
        }
    }
}
