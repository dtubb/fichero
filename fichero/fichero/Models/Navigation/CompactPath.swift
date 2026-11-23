import Foundation

/// The iPhone's ONE navigation path: any number of folders, then at most one item, then Reader and Info in that
/// order (each optional).
/// Every push and every Back is a change to `steps`, so the drill-down is testable with no view.
struct CompactPath: Equatable {
    private(set) var steps: [CompactStep] = []

    /// The folder the stack's root list shows: where the first folder was pushed from. Kept after Back, so popping
    /// the last folder step returns to it (`ios.nav.folders-push`, #6945).
    private(set) var rootFolderId: String?

    /// The folders pushed, outermost first.
    var folderIds: [String] {
        steps.compactMap { if case .folder(let id) = $0 { id } else { nil } }
    }

    /// The folder whose list the top screen shows: the last pushed folder, else the root's.
    var currentFolderId: String? { folderIds.last ?? rootFolderId }

    /// The item the path holds, if any.
    var itemId: String? {
        for case .item(let id) in steps { return id }
        return nil
    }

    /// Whether `steps` is a legal path: folders, then an item, then Reader and Info in that order, each optional.
    static func isValid(_ steps: [CompactStep]) -> Bool {
        let tail = steps.drop { if case .folder = $0 { true } else { false } }
        guard !tail.isEmpty else { return true }
        let legal: [[CompactStep]] = [[], [.reader], [.reader, .info], [.info]]
        guard case .item = tail.first else { return false }
        return legal.contains(Array(tail.dropFirst()))
    }

    /// Replaces the whole path (the stack's own binding writes here). An illegal path is a programming error.
    mutating func set(_ newSteps: [CompactStep]) {
        precondition(Self.isValid(newSteps), "illegal compact path \(newSteps)")
        steps = newSteps
    }

    /// Pushes a step; ignored when it is already the last one.
    mutating func push(_ step: CompactStep) {
        guard steps.last != step else { return }
        set(steps + [step])
    }

    /// Pushes a folder's screen on top of the folders, from the list `current` shows. Ignored when the path holds an
    /// item (a folder is never pushed on one) or already ends at this folder.
    mutating func pushFolder(_ id: String, from current: String?) {
        guard itemId == nil, (currentFolderId ?? current) != id else { return }
        if folderIds.isEmpty { rootFolderId = current }
        set(steps + [.folder(id)])
    }

    /// Makes `id` the path's item: replaces the item (and what sits on it), or appends it after the folders.
    mutating func open(item id: String) {
        guard itemId != id else { return }
        let folders = steps.prefix { if case .folder = $0 { true } else { false } }
        set(Array(folders) + [.item(id)])
    }

    /// Back one screen.
    mutating func back() {
        if !steps.isEmpty { steps.removeLast() }
    }
}
