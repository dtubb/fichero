@testable import Fichero
import SwiftUI
import XCTest

/// One table-driven snapshot of the whole shell routing surface per horizontal
/// size class (#3019): compact-nav flag × CompactShellPolicy route × splittable
/// gate × inspector placement. If a shell-policy edit silently changes routing,
/// exactly one of these snapshots breaks — the regression is caught here rather
/// than in a device build.
final class ShellRoutingMatrixTests: XCTestCase {
    private struct ShellRouting: Equatable {
        let compactNav: Bool
        let libraryRoute: CompactShellRoute
        let entitiesRoute: CompactShellRoute
        let chatRoute: CompactShellRoute
        let splittableWhenRoomy: Bool
        let inspector: InspectorPlacement
    }

    private func routing(_ sizeClass: UserInterfaceSizeClass?) -> ShellRouting {
        ShellRouting(
            compactNav: ContentView.shouldUseCompactNavigationFlow(horizontalSizeClass: sizeClass),
            libraryRoute: CompactShellPolicy.route(
                horizontalSizeClass: sizeClass, appViewMode: .library(nil), isEntitySelection: false
            ),
            entitiesRoute: CompactShellPolicy.route(
                horizontalSizeClass: sizeClass, appViewMode: .library(nil), isEntitySelection: true
            ),
            chatRoute: CompactShellPolicy.route(
                horizontalSizeClass: sizeClass, appViewMode: .chat(nil), isEntitySelection: false
            ),
            splittableWhenRoomy: ContentView.shouldUseSplittablePane(
                horizontalSizeClass: sizeClass, windowWidth: 2000, minimumWidth: 800
            ),
            inspector: InspectorPlacement.adaptiveDefault(horizontalSizeClass: sizeClass)
        )
    }

    /// Regular width: full desktop/iPad shell — no compact nav, everything routes
    /// to the split path, splits available, docked inspector.
    func testRegularWidthRouting() {
        XCTAssertEqual(
            routing(.regular),
            ShellRouting(
                compactNav: false,
                libraryRoute: .regular,
                entitiesRoute: .regular,
                chatRoute: .regular,
                splittableWhenRoomy: true,
                inspector: .docked
            )
        )
    }

    /// Unknown size class (macOS reports nil historically) behaves like regular.
    func testUnknownSizeClassRouting() {
        XCTAssertEqual(routing(nil), routing(.regular))
    }

    /// Compact width. macOS is never actually compact-navigating (its
    /// shouldUseCompactNavigationFlow is compile-time false), so its compact
    /// snapshot collapses to the regular routes but still takes the sheet
    /// inspector and loses splits. iOS/iPadOS gets the real compact push routes.
    func testCompactWidthRouting() {
        #if os(macOS)
        XCTAssertEqual(
            routing(.compact),
            ShellRouting(
                compactNav: false,
                libraryRoute: .regular,
                entitiesRoute: .regular,
                chatRoute: .regular,
                splittableWhenRoomy: false,
                inspector: .sheet
            )
        )
        #else
        XCTAssertEqual(
            routing(.compact),
            ShellRouting(
                compactNav: true,
                libraryRoute: .libraryReader,
                entitiesRoute: .modeContent,
                chatRoute: .modeContent,
                splittableWhenRoomy: false,
                inspector: .sheet
            )
        )
        #endif
    }
}
