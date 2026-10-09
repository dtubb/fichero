@testable import Fichero
import Foundation
import Testing

/// `panes.chrome.breadcrumb-opens-like-the-sidebar` (#5633): a folder crumb in a pane head does what
/// clicking that folder's sidebar row does — it is selected and the Preview shows its canvas.
///
/// The bug: with Sources selected in the sidebar and a file inside it picked in the Library, the
/// "Sources" crumb re-selected the row that was already selected. Nothing changed, so neither of
/// the handlers a click runs (sidebar routing on `selectedDestination`, the pane half
/// `handleSidebarSelectionChange` on `selectedItemId`) fired and the Preview stayed on the file.
///
/// Driven through the real `SidebarSelectionState`, the store the sidebar's click and the crumb's
/// reveal both write. A sidebar click on a single row leaves `selectedItemId`'s programmatic shape
/// (`[d]` highlighted, `d` routed), so that setter stands in for the click.
struct BreadcrumbOpensFolderTests {
    private let sources = SidebarDestination.document("folder-sources")
    private let diary = SidebarDestination.document("pdf-ncm-diary")

    /// What a crumb does to the store: reopen when already selected, else the click's write.
    private func crumbClick(_ destination: SidebarDestination, on state: SidebarSelectionState) {
        if !state.reopenIfSelected(destination) {
            state.selectedItemId = destination.serializedID
        }
    }

    private func sidebarClick(_ destination: SidebarDestination, on state: SidebarSelectionState) {
        state.selectedItemId = destination.serializedID
    }

    @Test("a crumb for a folder not selected leaves the selection a sidebar click leaves")
    func crumbOnAnotherFolderMatchesTheSidebarClick() {
        // WHY: the crumb must not have a path of its own; from the same start both end equal.
        let viaSidebar = SidebarSelectionState()
        let viaCrumb = SidebarSelectionState()
        viaSidebar.selectedItemId = diary.serializedID
        viaCrumb.selectedItemId = diary.serializedID

        sidebarClick(sources, on: viaSidebar)
        crumbClick(sources, on: viaCrumb)

        #expect(viaCrumb.selectedDestinations == viaSidebar.selectedDestinations)
        #expect(viaCrumb.selectedDestination == viaSidebar.selectedDestination)
        #expect(viaCrumb.selectedItemId == "doc:folder-sources")
        // The selection moved, so the click's own `.onChange` handlers run; no reopen is needed.
        #expect(viaCrumb.reopenGeneration == 0)
    }

    @Test("a crumb for the folder already selected opens it again instead of doing nothing")
    func crumbOnTheSelectedFolderReopens() {
        // WHY: this is the bug. Sources is the sidebar's selection while the Preview shows a file
        // picked inside it; re-selecting Sources writes nothing, so the Preview never left the file.
        let state = SidebarSelectionState()
        sidebarClick(sources, on: state)
        let before = state.reopenGeneration

        crumbClick(sources, on: state)

        #expect(state.reopenGeneration == before + 1, "the window re-runs the click's handlers on this")
        #expect(state.selectedDestinations == [sources])
        #expect(state.selectedDestination == sources)
    }

    @Test("a crumb into a multi-row selection collapses it to that row, as a plain click does")
    func crumbIntoABatchSelectionIsAPlainClick() {
        // WHY: reopen is only for "already exactly this"; a batch holding the folder must narrow
        // to it through the ordinary write, never be left as a batch.
        let state = SidebarSelectionState()
        state.selectedDestinations = [sources, diary]
        state.selectedDestination = sources

        crumbClick(sources, on: state)

        #expect(state.reopenGeneration == 0)
        #expect(state.selectedDestinations == [sources])
    }

    @Test("every crumb asks the sidebar to reopen; the restore path's plain reveal does not")
    func crumbRequestCarriesReopen() {
        // WHY: reopen re-runs the pane handler, which clears the Library pick. A relaunch restore
        // posts the same reveal and must keep the pick, so only crumbs carry the flag.
        let folder = PaneCrumb(id: "folder-sources", title: "Sources", icon: "folder.fill")
        let info = PaneCrumb.revealInfo(folder)
        #expect(info["documentId"] as? String == "folder-sources")
        #expect(info["reopen"] as? Bool == true)

        let libraryId = UUID()
        let library = PaneCrumb(id: PaneCrumb.libraryPrefix + libraryId.uuidString, title: "L",
                                icon: "books.vertical.fill")
        let libraryInfo = PaneCrumb.revealInfo(library)
        #expect(libraryInfo["libraryId"] as? String == libraryId.uuidString)
        #expect(libraryInfo["reopen"] as? Bool == true)
    }
}
