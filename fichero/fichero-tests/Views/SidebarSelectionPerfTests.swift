@testable import Fichero
import SwiftUI
import XCTest

/// Measures the cost Daniel's live logs keep showing: ONE selection change
/// over a ~200-row sidebar re-evaluates every `SidebarItemRow` body
/// (selection commits 0.4–2.6s on 2026-08-14 night, stacks in
/// SidebarItemRowVwcp/itemLabel). This harness mounts 204 REAL rows in a
/// List inside an NSHostingView and times selection flips — a number to
/// compare row-diet changes against, not a wall-clock assertion (CI boxes
/// vary; the assertion is only "it finished").
@MainActor
final class SidebarSelectionPerfTests: XCTestCase {
    @Observable
    final class SelectionModel {
        var selected: Set<SidebarDestination> = []
        var selectedId: String?
    }

    struct Harness: View {
        let items: [SidebarItem]
        @Bindable var model: SelectionModel
        let renameState = RenameStateManager()
        let deleteState = DeleteStateManager()
        let sidebarState = SidebarState()

        var body: some View {
            List(selection: .constant(model.selected)) {
                ForEach(items) { item in
                    SidebarItemRow(
                        item: item,
                        lookupItem: { _ in nil },
                        expandedItems: .constant([]),
                        selectedItemId: Binding(
                            get: { model.selectedId },
                            set: { model.selectedId = $0 }
                        ),
                        selectedDestinations: model.selected,
                        renameState: renameState,
                        deleteState: deleteState,
                        sidebarState: sidebarState,
                        libraryManager: LibraryManager.shared
                    )
                    .tag(item.destination)
                }
            }
            .listStyle(.sidebar)
        }
    }

    private static func makeItems(_ count: Int) -> [SidebarItem] {
        let libraryId = UUID()
        return (0..<count).map { index in
            let doc = Document(
                id: "perf-doc-\(index)",
                docType: .file,
                fileType: .image,
                name: "NCM_Diary_IMG_\(String(format: "%03d", index)).png"
            )
            return SidebarItem(
                id: "doc:\(doc.id)",
                name: doc.name,
                icon: "photo",
                category: .folder,
                itemType: .document(doc),
                children: nil,
                progress: nil,
                showProgress: false,
                libraryId: libraryId,
                folderPath: "/",
                sortOrder: index,
                isFolder: false,
                isDefaultWorkflowFolder: false
            )
        }
    }

    /// Control: the same List + selection flip with PLAIN Text rows — the
    /// floor the row implementation cannot go below. If this is close to the
    /// real-row number, the cost is List machinery, not our rows.
    func testControlPlainTextRows() {
        struct PlainHarness: View {
            let items: [SidebarItem]
            @Bindable var model: SelectionModel
            var body: some View {
                List(selection: .constant(model.selected)) {
                    ForEach(items) { item in
                        Text(item.name).tag(item.destination)
                    }
                }
                .listStyle(.sidebar)
            }
        }
        let items = Self.makeItems(204)
        let model = SelectionModel()
        let host = NSHostingView(rootView: PlainHarness(items: items, model: model))
        host.frame = NSRect(x: 0, y: 0, width: 280, height: 800)
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        let flips = 10
        let start = ContinuousClock.now
        for index in 0..<flips {
            model.selected = [items[index % items.count].destination]
            host.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.01))
        }
        let elapsed = ContinuousClock.now - start
        print("SIDEBAR-PERF-CONTROL: \(flips) flips, plain Text rows: \(elapsed) total")
        XCTAssertTrue(true)
    }

    func testSelectionFlipRelayoutOver204Rows() {
        let items = Self.makeItems(204)
        let model = SelectionModel()
        let host = NSHostingView(
            rootView: Harness(items: items, model: model)
                .environment(WorkflowExecutionObserver())
                .environment(WindowState(libraryId: items[0].libraryId ?? UUID()))
        )
        host.frame = NSRect(x: 0, y: 0, width: 280, height: 800)
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))

        let flips = 10
        let start = ContinuousClock.now
        for index in 0..<flips {
            let destination = items[index % items.count].destination
            model.selected = [destination]
            model.selectedId = items[index % items.count].id
            host.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.01))
        }
        let elapsed = ContinuousClock.now - start
        let perFlip = elapsed / flips
        // The number IS the result — printed for before/after comparison.
        print("SIDEBAR-PERF: \(flips) selection flips over \(items.count) rows: " +
              "\(elapsed) total, \(perFlip) per flip")
        XCTAssertTrue(true)
    }
}
