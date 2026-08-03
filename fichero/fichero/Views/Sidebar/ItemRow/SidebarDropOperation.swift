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
///
/// This is THE grammar. Every surface that accepts a library-item drag routes
/// through it — sidebar rows, sidebar insertion lines, and (since #4475) the
/// library folder cells in all four view modes. The library cell used to always
/// move, so a user who learned ⌥-copy in the sidebar was silently wrong in the
/// pane where the documents actually are.
///
/// Modifier state is sampled ONCE per drop, at the drop entry point, and the
/// sampled `SidebarDropModifiers` is passed down (#4475 C). Nothing below an
/// entry point may call `.current()` itself: two functions re-reading live
/// modifier flags at different instants is the "two things nothing forces to
/// agree" shape this whole family of bugs is made of. The single exception is
/// hover highlighting (`targetedDropOperation`), which is not a drop and MUST
/// re-read so the cursor badge tracks the key being pressed mid-drag.
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
@MainActor
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
@MainActor
func sidebarFindDocument(id: String, in store: DocumentStore) -> Document? {
    sidebarAllCachedDocuments(in: store).first { $0.id == id }
}

/// Finder naming: an alias created BESIDE its original is "<name> alias";
/// one dropped elsewhere keeps the plain name (same rule as copies).
///
/// #116: this took a bare `sourceName: String`, and both callers handed it
/// `source?.name` — the raw storage name, written straight into the engine as a
/// new row. Taking the DOCUMENT instead means the name is composed by the same
/// ladder every display surface uses, and there is no `String` parameter left
/// for a caller to fill with an upload id.
func sidebarAliasName(source: Document?, targetParentId: String?) -> String {
    AliasName.forAlias(of: source, targetParentId: targetParentId)
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
                await store.refresh()   // show any copies made before the failure
                return
            }
        case .alias:
            let source = sidebarFindDocument(id: id, in: store)
            let name = sidebarAliasName(source: source, targetParentId: parentId)
            // Aliasing an alias targets the ORIGINAL (no alias chains).
            let targetId = (source?.isAlias == true ? source?.aliasTargetId : nil) ?? id
            let created = await library.bookmarkService.createBookmark(
                targetId: targetId, name: name, parentId: parentId
            )
            guard created else {
                sidebarState.dropErrorMessage = "Couldn’t create the alias."
                await store.refresh()   // show any rows created before the failure
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

// MARK: - The one drop executor for a library item onto a folder (#4475)

/// What applying one resolved operation to one dragged document actually did.
/// `.failed` carries a reportable reason — a drop that silently does nothing is
/// the defect this pair of issues is about, so there is no "nothing happened"
/// case to fall into.
enum LibraryItemDropOutcome: Equatable {
    case applied
    case failed(String)
}

/// Apply one resolved `SidebarDropOperation` to one document, into one folder.
///
/// Both surfaces call THIS: the sidebar row drop and the library folder cell.
/// They previously had separate executors, which is why ⌥ meant "duplicate" in
/// the sidebar and meant nothing in the library — there was no single place
/// saying what a drag of a library item DOES, so the two implementations were
/// free to disagree and did.
///
/// Deliberately does NOT refresh the store: callers apply several of these per
/// drop and refresh once at the end. Refreshing per item would re-render the
/// whole list once per dragged document.
@MainActor
func applyLibraryItemDropOperation(
    _ operation: SidebarDropOperation,
    documentId: String,
    intoFolderId: String,
    library: LibraryManager.LibraryReference
) async -> LibraryItemDropOutcome {
    switch operation {
    case .move:
        do {
            _ = try await library.documentStore.moveDocument(documentId, toParent: intoFolderId)
            return .applied
        } catch {
            return .failed(error.localizedDescription)
        }

    case .copy:
        // Deep-copies through the audited `document.duplicate` action (the same
        // invokeAction path document.delete uses). The engine enforces
        // cycle/lock rules and keeps the name for cross-folder copies (Finder
        // suffixes only same-folder copies).
        do {
            _ = try await library.actionsService.invokeAction(
                name: "document.duplicate",
                params: DocumentDuplicateActionParams(docId: documentId, parentId: intoFolderId)
            )
            return .applied
        } catch {
            return .failed(error.localizedDescription)
        }

    case .alias:
        // A real engine alias node (bookmarks surface, #2591) inside the target.
        let source = sidebarFindDocument(id: documentId, in: library.documentStore)
        let name = sidebarAliasName(source: source, targetParentId: intoFolderId)
        // Aliasing an alias targets the ORIGINAL (no alias chains).
        let targetId = (source?.isAlias == true ? source?.aliasTargetId : nil) ?? documentId
        let created = await library.bookmarkService.createBookmark(
            targetId: targetId, name: name, parentId: intoFolderId
        )
        return created ? .applied : .failed("Couldn’t create the alias.")
    }
}

extension SidebarItemRow {
    /// Option-drag copy executor for drops ONTO a folder. Thin wrapper over the
    /// shared executor: keeps this row's error reporting and store refresh.
    @discardableResult
    func copyDocumentIntoFolder(documentId: String, folderId: String) async -> Bool {
        guard let library else { return false }
        switch await applyLibraryItemDropOperation(
            .copy, documentId: documentId, intoFolderId: folderId, library: library
        ) {
        case .applied:
            await library.documentStore.refresh()
            return true
        case .failed(let reason):
            sidebarRowLogger.error("⌥-copy failed: \(reason)")
            sidebarState.dropErrorMessage = reason
            return false
        }
    }

    /// ⌘⌥-drag alias executor for drops ONTO a folder.
    @discardableResult
    func aliasDocumentIntoFolder(documentId: String, folderId: String) async -> Bool {
        guard let library else { return false }
        switch await applyLibraryItemDropOperation(
            .alias, documentId: documentId, intoFolderId: folderId, library: library
        ) {
        case .applied:
            await library.documentStore.refresh()
            return true
        case .failed(let reason):
            sidebarRowLogger.error("⌘⌥-alias failed: \(reason)")
            sidebarState.dropErrorMessage = reason
            return false
        }
    }
}
