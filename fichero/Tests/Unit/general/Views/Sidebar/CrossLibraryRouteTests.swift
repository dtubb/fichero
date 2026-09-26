@testable import Fichero
import Foundation
import XCTest

/// #4995/#4996 — a sidebar click on a document in ANOTHER library used to write the window's
/// library and the view mode in one turn, so the first load ran against the OLD library's stores
/// ("Document not found"), and the library-change teardown then made every pane fetch again.
///
/// `CrossLibraryRoute` is the ordering rule. These drive it through a model of the window — one
/// request log per library, requests going to whichever library the window shows when the route
/// is applied — using the real decision functions for every step. No view is mounted, so this
/// pins the RULE; that `SidebarView` follows it is the instrumented run's job to show.
final class CrossLibraryRouteTests: XCTestCase {
    /// The window as the rule sees it: the library it shows, and what each library was asked.
    final class Window {
        var libraryId: UUID
        var requests: [UUID: [SidebarDestination]] = [:]
        var pending: CrossLibraryRoute.Pending?

        init(showing libraryId: UUID) { self.libraryId = libraryId }

        /// Routing loads from the stores of the library the window shows RIGHT NOW.
        private func route(_ destination: SidebarDestination) {
            requests[libraryId, default: []].append(destination)
        }

        /// `SidebarView.handleSelectionDestination`, reduced to its ordering.
        func select(_ destination: SidebarDestination, in destinationLibraryId: UUID?) {
            pending = nil
            let step = CrossLibraryRoute.firstStep(
                destinationLibraryId: destinationLibraryId, windowLibraryId: libraryId
            )
            switch step {
            case .routeNow:
                route(destination)
            case .switchLibraryFirst(let target):
                pending = CrossLibraryRoute.Pending(libraryId: target, destination: destination)
            }
        }

        /// The window's library switch landing: `.onChange(of: windowState.libraryId)`.
        func land(on landedLibraryId: UUID) {
            libraryId = landedLibraryId
            let waiting = pending
            pending = nil
            if let destination = CrossLibraryRoute.destinationToRoute(pending: waiting, landedLibraryId: landedLibraryId) {
                route(destination)
            }
        }
    }

    let oldLibrary = UUID()
    let newLibrary = UUID()
    let page = SidebarDestination.document("9c92")

    /// A cross-library selection asks the old library for nothing.
    func testCrossLibrarySelectionNeverAsksTheOldLibrary() {
        let window = Window(showing: oldLibrary)

        window.select(page, in: newLibrary)
        XCTAssertNil(window.requests[oldLibrary], "nothing may route before the library switch lands")
        XCTAssertEqual(window.pending, CrossLibraryRoute.Pending(libraryId: newLibrary, destination: page))

        window.land(on: newLibrary)
        XCTAssertNil(window.requests[oldLibrary], "the old library must never see the new library's document")
        XCTAssertEqual(window.requests[newLibrary], [page], "the selection routes exactly once, in its own library")
        XCTAssertNil(window.pending)
    }

    /// A same-library selection routes immediately.
    func testSameLibraryRoutesNow() {
        let window = Window(showing: oldLibrary)
        window.select(page, in: oldLibrary)
        XCTAssertEqual(window.requests[oldLibrary], [page])
        XCTAssertNil(window.pending)
    }

    /// A destination that belongs to no library routes immediately.
    func testLibraryLessDestinationRoutesNow() {
        let step = CrossLibraryRoute.firstStep(destinationLibraryId: nil, windowLibraryId: oldLibrary)
        XCTAssertEqual(step, .routeNow)
    }

    /// A window that lands on some OTHER library routes nothing.
    func testLandingElsewhereRoutesNothing() {
        let window = Window(showing: oldLibrary)
        let fallback = UUID()

        window.select(page, in: newLibrary)
        window.land(on: fallback)

        XCTAssertTrue(window.requests.isEmpty, "a selection must not be loaded from a library it does not belong to")
        XCTAssertNil(window.pending)
    }

    /// A newer selection replaces one still waiting for its library.
    func testNewerSelectionSupersedesPending() {
        let window = Window(showing: oldLibrary)
        let other = SidebarDestination.document("e231")

        window.select(page, in: newLibrary)
        window.select(other, in: oldLibrary)
        window.land(on: newLibrary)

        XCTAssertEqual(window.requests[oldLibrary], [other])
        XCTAssertNil(window.requests[newLibrary], "the superseded selection must not route when its library lands late")
    }
}
