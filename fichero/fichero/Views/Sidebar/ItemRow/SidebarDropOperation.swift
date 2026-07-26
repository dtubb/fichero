import Foundation
#if os(macOS)
import AppKit
#else
import GameController
#endif

/// Whether Option (⌥) is held RIGHT NOW — read at drop time so the existing
/// drag machinery (#711/#713 workarounds, NSTableView row drag) stays
/// untouched. macOS reads the live AppKit modifier flags; iPadOS/visionOS
/// read the hardware keyboard through GameController, since SwiftUI drop
/// callbacks never expose the session's modifiers. No hardware keyboard →
/// false → drops stay moves.
func sidebarOptionKeyIsHeld() -> Bool {
    #if os(macOS)
    return NSEvent.modifierFlags.contains(.option)
    #else
    guard let keyboard = GCKeyboard.coalesced?.keyboardInput else { return false }
    return keyboard.button(forKeyCode: .leftAlt)?.isPressed == true
        || keyboard.button(forKeyCode: .rightAlt)?.isPressed == true
    #endif
}

/// Whether Command (⌘) is held RIGHT NOW — same sampling strategy as ⌥.
func sidebarCommandKeyIsHeld() -> Bool {
    #if os(macOS)
    return NSEvent.modifierFlags.contains(.command)
    #else
    guard let keyboard = GCKeyboard.coalesced?.keyboardInput else { return false }
    return keyboard.button(forKeyCode: .leftGUI)?.isPressed == true
        || keyboard.button(forKeyCode: .rightGUI)?.isPressed == true
    #endif
}

/// What an internal sidebar drop should do with its payload.
enum SidebarDropOperation: Equatable {
    case move
    case copy
    case alias
}

/// The drop-relevant modifier keys, sampled together at the drop moment.
struct SidebarDropModifiers {
    let option: Bool
    let command: Bool

    /// Live read of both keys (see the per-platform probes above).
    static func current() -> SidebarDropModifiers {
        SidebarDropModifiers(
            option: sidebarOptionKeyIsHeld(),
            command: sidebarCommandKeyIsHeld()
        )
    }
}

/// Finder's modifier-drag grammar for DOCUMENT payloads — the one kind with
/// targeted duplicate + alias endpoints: plain = move, ⌥ = copy,
/// ⌘⌥ = make alias at the destination. Other kinds always move.
func sidebarDropOperation(
    optionHeld: Bool,
    commandHeld: Bool,
    kind: SidebarItemKind
) -> SidebarDropOperation {
    guard kind == .document, optionHeld else { return .move }
    return commandHeld ? .alias : .copy
}

/// Convenience overload for a sampled modifier pair.
func sidebarDropOperation(
    modifiers: SidebarDropModifiers,
    kind: SidebarItemKind
) -> SidebarDropOperation {
    sidebarDropOperation(optionHeld: modifiers.option, commandHeld: modifiers.command, kind: kind)
}

struct DocumentDuplicateActionParams: Encodable {
    let docId: String
    let parentId: String?
    var toRoot = false

    enum CodingKeys: String, CodingKey {
        case docId = "doc_id"
        case parentId = "parent_id"
        case toRoot = "to_root"
    }
}

/// Every document in the store's caches (roots, current folder, expanded
/// children). Built stepwise — one big concatenation expression trips the
/// type-checker's time limit (LibraryWindow.body lesson).
func sidebarAllCachedDocuments(in store: DocumentStore) -> [Document] {
    var docs: [Document] = store.collections
    docs.append(contentsOf: store.currentDocuments)
    for kids in store.childrenCache.values {
        docs.append(contentsOf: kids)
    }
    return docs
}

/// Find a document anywhere in the store's caches — used to read a drag
/// source's name/parent for the Finder alias-naming rule.
func sidebarFindDocument(id: String, in store: DocumentStore) -> Document? {
    sidebarAllCachedDocuments(in: store).first { $0.id == id }
}

/// Finder naming: an alias created BESIDE its original is "<name> alias";
/// one dropped elsewhere keeps the plain name (same rule as copies).
func sidebarAliasName(sourceName: String, sourceParentId: String?, targetParentId: String?) -> String {
    sourceParentId == targetParentId ? "\(sourceName) alias" : sourceName
}

/// One non-move insertion-line drop: what to do, with what, and where.
struct SidebarInsertionDropRequest {
    let operation: SidebarDropOperation
    let bareIds: [String]
    /// nil = library root.
    let parentId: String?
    let offset: Int
    let children: [SidebarItem]
}

/// Apply a non-move insertion-line drop: duplicate (⌥) or make-alias (⌘⌥)
/// each dragged document into the request's parent (nil = library root),
/// then place the new rows at the insertion offset. `invokeAction` returns
/// only audit metadata, so new rows are identified by a child-id snapshot
/// diff across the refresh.
/// ponytail: a concurrent insert by another client during the refresh window
/// can ride into the positioning diff — benign, it just gets ordered too.
@MainActor
func sidebarApplyInsertionDropOperation(
    _ request: SidebarInsertionDropRequest,
    library: LibraryManager.LibraryReference,
    sidebarState: SidebarState
) async {
    let operation = request.operation
    let parentId = request.parentId
    guard operation != .move, !request.bareIds.isEmpty else { return }
    sidebarState.dropErrorMessage = nil
    let store = library.documentStore
    let beforeDocs = sidebarAllCachedDocuments(in: store).filter { $0.parentId == parentId }
    let beforeIds = Set(beforeDocs.map(\.id))

    for id in request.bareIds {
        switch operation {
        case .copy:
            do {
                _ = try await library.actionsService.invokeAction(
                    name: "document.duplicate",
                    params: DocumentDuplicateActionParams(
                        docId: id, parentId: parentId, toRoot: parentId == nil
                    )
                )
            } catch {
                sidebarState.dropErrorMessage = error.localizedDescription
                return
            }
        case .alias:
            let source = sidebarFindDocument(id: id, in: store)
            let name = sidebarAliasName(
                sourceName: source?.name ?? "Item",
                sourceParentId: source?.parentId,
                targetParentId: parentId
            )
            let created = await library.bookmarkService.createBookmark(
                targetId: id, name: name, parentId: parentId
            )
            guard created else {
                sidebarState.dropErrorMessage = "Couldn’t create the alias."
                return
            }
        case .move:
            return
        }
    }

    await store.refresh()
    let afterDocs = sidebarAllCachedDocuments(in: store).filter { $0.parentId == parentId }
    let newIds = afterDocs.filter { !beforeIds.contains($0.id) }.map(\.id)
    guard !newIds.isEmpty, !request.children.isEmpty,
          let newOrder = sidebarReorderedDocIdsWithInsert(
            children: request.children, inserting: newIds, at: request.offset
          ) else { return }
    store.reorderChildrenOptimistically(orderedIds: newOrder)
}

extension SidebarItemRow {
    /// Option-drag copy executor for drops ONTO a folder: deep-copies the
    /// document into the target through the audited `document.duplicate`
    /// action (the same invokeAction path document.delete uses). The engine
    /// enforces cycle/lock rules and keeps the name for cross-folder copies
    /// (Finder suffixes only same-folder copies).
    func copyDocumentIntoFolder(documentId: String, folderId: String) async {
        guard let library else { return }
        do {
            _ = try await library.actionsService.invokeAction(
                name: "document.duplicate",
                params: DocumentDuplicateActionParams(docId: documentId, parentId: folderId)
            )
            await library.documentStore.refresh()
        } catch {
            sidebarRowLogger.error("⌥-copy failed: \(error.localizedDescription)")
            sidebarState.dropErrorMessage = error.localizedDescription
        }
    }

    /// ⌘⌥-drag alias executor for drops ONTO a folder: a real engine alias
    /// node (bookmarks surface, #2591) inside the target.
    func aliasDocumentIntoFolder(documentId: String, folderId: String) async {
        guard let library else { return }
        let store = library.documentStore
        let source = sidebarFindDocument(id: documentId, in: store)
        let name = sidebarAliasName(
            sourceName: source?.name ?? "Item",
            sourceParentId: source?.parentId,
            targetParentId: folderId
        )
        let created = await library.bookmarkService.createBookmark(
            targetId: documentId, name: name, parentId: folderId
        )
        if created {
            await store.refresh()
        } else {
            sidebarState.dropErrorMessage = "Couldn’t create the alias."
        }
    }
}
