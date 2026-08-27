//
//  SidebarActionsEqualityTests.swift
//  FicheroTests
//
//  Regression guards for the FocusedValue update churn fix (2026-04-18).
//
//  `.focusedValue(\.sidebarActions, SidebarActions(...))` was republishing
//  every body evaluation because SidebarActions' 11 closure fields aren't
//  Equatable by default. SwiftUI then tripped the "FocusedValue update
//  tried to update multiple times per frame" runtime warning repeatedly.
//
//  Fix (`0433c60d`): SidebarActions conforms to Equatable with `== true`
//  — all instances are functionally equivalent because their closures
//  capture the SAME parent @State bindings.
//
//  Fix (`0848a58a`): SidebarSelectionInfo conforms to Equatable
//  structurally (all fields are Equatable; compiler-synthesized).
//
//  These tests lock in the equality contracts so the warning can't
//  regress silently.
//

@testable import Fichero
import Foundation
import Testing

// MARK: - SidebarActions Equality

/// SidebarActions.== MUST return true for any pair of instances. This
/// is the specific behavior that stops SwiftUI's focus-value republish
/// churn. If a future refactor changes the equality semantics (e.g.,
/// structural equality, reference equality), the FocusedValue warning
/// will come back.
@MainActor
struct SidebarActionsEqualityTests {

    private func makeActions() -> SidebarActions {
        SidebarActions(
            createFolder: {},
            importFiles: { _ in },
            renameItem: {},
            deleteItem: {},
            createChat: {},
            createWorkflow: {},
            createChain: {},
            createComparison: {},
            createSchedule: {},
            createTrigger: {},
            openSelectionInNewTab: {},
            openSelectionInNewWindow: {}
        )
    }

    @Test("Two freshly-constructed SidebarActions instances compare equal")
    func freshInstancesCompareEqual() {
        #expect(makeActions() == makeActions())
    }

    @Test("SelectionInfo equality includes the deletable-selection count")
    func selectionInfoEqualityTracksDeletableCount() {
        // Edit ▸ Delete retitles on the count ("Delete N Items"), so a count
        // change must republish the focused value — equality can't ignore it.
        let one = SidebarSelectionInfo(
            selectedItem: nil, canRename: false, canDelete: true, deletableCount: 1
        )
        let three = SidebarSelectionInfo(
            selectedItem: nil, canRename: false, canDelete: true, deletableCount: 3
        )
        #expect(one != three)
        #expect(
            one == SidebarSelectionInfo(
                selectedItem: nil, canRename: false, canDelete: true, deletableCount: 1
            )
        )
    }

    @Test("SidebarActions with different closures still compare equal")
    func differentClosuresStillEqual() {
        // Each closure here has a distinct capture list, so under any
        // structural-equality scheme they'd compare unequal. The fix
        // depends on `== true` being unconditional.
        var counterA = 0
        var counterB = 100
        let actions1 = SidebarActions(
            createFolder: { counterA += 1 },
            importFiles: { _ in counterA += 1 },
            renameItem: { counterA += 1 },
            deleteItem: { counterA += 1 },
            createChat: { counterA += 1 },
            createWorkflow: { counterA += 1 },
            createChain: { counterA += 1 },
            createComparison: { counterA += 1 },
            createSchedule: { counterA += 1 },
            createTrigger: { counterA += 1 },
            openSelectionInNewTab: { counterA += 1 },
            openSelectionInNewWindow: { counterA += 1 }
        )
        let actions2 = SidebarActions(
            createFolder: { counterB += 1 },
            importFiles: { _ in counterB += 1 },
            renameItem: { counterB += 1 },
            deleteItem: { counterB += 1 },
            createChat: { counterB += 1 },
            createWorkflow: { counterB += 1 },
            createChain: { counterB += 1 },
            createComparison: { counterB += 1 },
            createSchedule: { counterB += 1 },
            createTrigger: { counterB += 1 },
            openSelectionInNewTab: { counterB += 1 },
            openSelectionInNewWindow: { counterB += 1 }
        )
        #expect(actions1 == actions2)
    }
}

// MARK: - SidebarSelectionInfo Equality

/// SidebarSelectionInfo is Equatable so
/// `.focusedValue(\.sidebarSelectionInfo, ...)` short-circuits when the
/// selection, rename-availability, and delete-availability all match
/// the previously-published value. Without Equatable, every body
/// evaluation republished, tripping the FocusedValue warning.
@MainActor
struct SidebarSelectionInfoEqualityTests {

    private func makeItem(id: String, name: String) -> SidebarItem {
        SidebarItem(
            id: id,
            name: name,
            icon: "doc",
            category: .folder,
            itemType: .folder(folderPath: "/\(name)"),
            children: nil,
            progress: nil,
            showProgress: false,
            libraryId: nil,
            folderPath: "/",
            sortOrder: 0,
            isFolder: true
        )
    }

    private func makeItem(id: String, name: String, children: [SidebarItem]?) -> SidebarItem {
        SidebarItem(
            id: id,
            name: name,
            icon: "doc",
            category: .folder,
            itemType: .folder(folderPath: "/\(name)"),
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: nil,
            folderPath: "/",
            sortOrder: 0,
            isFolder: true
        )
    }

    @Test("Same selection + same capability flags → equal")
    func sameValuesAreEqual() {
        let itemA = makeItem(id: "doc:1", name: "One")
        let info1 = SidebarSelectionInfo(selectedItem: itemA, canRename: true, canDelete: false)
        let info2 = SidebarSelectionInfo(selectedItem: itemA, canRename: true, canDelete: false)
        #expect(info1 == info2)
    }

    @Test("#1162 child loading does not republish the same sidebar selection")
    func sameSelectionIdWithLoadedChildrenIsEqual() {
        let itemBeforeChildrenLoad = makeItem(id: "doc:1", name: "One", children: nil)
        let child = makeItem(id: "doc:child", name: "Child")
        let itemAfterChildrenLoad = makeItem(id: "doc:1", name: "One", children: [child])
        let info1 = SidebarSelectionInfo(
            selectedItem: itemBeforeChildrenLoad,
            canRename: true,
            canDelete: false
        )
        let info2 = SidebarSelectionInfo(
            selectedItem: itemAfterChildrenLoad,
            canRename: true,
            canDelete: false
        )
        #expect(info1 == info2)
    }

    @Test("Different selected item → not equal")
    func differentSelectionNotEqual() {
        let itemA = makeItem(id: "doc:1", name: "One")
        let itemB = makeItem(id: "doc:2", name: "Two")
        let info1 = SidebarSelectionInfo(selectedItem: itemA, canRename: true, canDelete: true)
        let info2 = SidebarSelectionInfo(selectedItem: itemB, canRename: true, canDelete: true)
        #expect(info1 != info2)
    }

    @Test("Different canRename → not equal")
    func differentCanRenameNotEqual() {
        let itemA = makeItem(id: "doc:1", name: "One")
        let info1 = SidebarSelectionInfo(selectedItem: itemA, canRename: true, canDelete: true)
        let info2 = SidebarSelectionInfo(selectedItem: itemA, canRename: false, canDelete: true)
        #expect(info1 != info2)
    }

    @Test("Different canDelete → not equal")
    func differentCanDeleteNotEqual() {
        let itemA = makeItem(id: "doc:1", name: "One")
        let info1 = SidebarSelectionInfo(selectedItem: itemA, canRename: true, canDelete: true)
        let info2 = SidebarSelectionInfo(selectedItem: itemA, canRename: true, canDelete: false)
        #expect(info1 != info2)
    }

    @Test("nil selection compares equal to itself")
    func nilSelectionEqualsItself() {
        let info1 = SidebarSelectionInfo(selectedItem: nil, canRename: false, canDelete: false)
        let info2 = SidebarSelectionInfo(selectedItem: nil, canRename: false, canDelete: false)
        #expect(info1 == info2)
    }
}
