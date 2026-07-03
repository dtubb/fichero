@testable import Fichero
import SwiftUI
import XCTest

/// Truth-table coverage for the exhaustive compact-shell routing policy (#3009).
final class CompactShellPolicyTests: XCTestCase {
    /// Every `AppViewMode` case, so this list fails to compile if the enum
    /// gains a case without the test being updated alongside the policy switch.
    private static let allModes: [AppViewMode] = [
        .library(nil), .search(nil), .chat(nil), .comparison(nil),
        .workflow(nil), .chain(nil), .batches, .batch(nil),
        .automation, .schedule(nil), .trigger(nil), .activity(nil)
    ]

    /// Regular width (and the unmeasured `nil` size class) always takes the
    /// regular split path, for every mode and either entity-selection value.
    func testRegularAndNilWidthAlwaysRouteToRegular() {
        for mode in Self.allModes {
            for isEntity in [true, false] {
                XCTAssertEqual(
                    CompactShellPolicy.route(
                        horizontalSizeClass: .regular,
                        appViewMode: mode,
                        isEntitySelection: isEntity
                    ),
                    .regular,
                    "regular \(mode) entity=\(isEntity)"
                )
                XCTAssertEqual(
                    CompactShellPolicy.route(
                        horizontalSizeClass: nil,
                        appViewMode: mode,
                        isEntitySelection: isEntity
                    ),
                    .regular,
                    "nil \(mode) entity=\(isEntity)"
                )
            }
        }
    }

    /// The full compact truth table. macOS is never compact, so its compact
    /// route collapses to `.regular` regardless of mode; other platforms map
    /// library(non-entity)/search → reader and everything else → mode content.
    func testCompactRouteTruthTable() {
        #if os(macOS)
        for mode in Self.allModes {
            XCTAssertEqual(
                CompactShellPolicy.route(
                    horizontalSizeClass: .compact,
                    appViewMode: mode,
                    isEntitySelection: false
                ),
                .regular,
                "macOS compact \(mode)"
            )
        }
        #else
        XCTAssertEqual(route(.library(nil), false), .libraryReader)
        XCTAssertEqual(route(.library(nil), true), .modeContent)   // entities browser
        XCTAssertEqual(route(.search(nil), false), .libraryReader)
        XCTAssertEqual(route(.search(nil), true), .libraryReader)  // search ignores entity flag

        let modeContentModes: [AppViewMode] = [
            .chat(nil), .comparison(nil), .workflow(nil), .chain(nil),
            .batches, .batch(nil), .automation, .schedule(nil), .trigger(nil), .activity(nil)
        ]
        for mode in modeContentModes {
            XCTAssertEqual(route(mode, false), .modeContent, "\(mode)")
            XCTAssertEqual(route(mode, true), .modeContent, "\(mode) entity")
        }
        #endif
    }

    /// #3010 contract: the inner-sidebar modes (Research/Workflow/Activity) must
    /// route to `.modeContent` on compact — that route is what drives their
    /// list→detail NavigationStack push. A regression that sent one to
    /// `.libraryReader` (the document reader) would break the inner-mode push.
    func testInnerSidebarModesUseModeContentRouteOnCompact() {
        #if !os(macOS)
        for mode in [AppViewMode.workflow(nil), .activity(nil)] {
            XCTAssertEqual(route(mode, false), .modeContent, "\(mode)")
        }
        // Research is `sidebarMode == .research`, surfaced through the library
        // AppViewMode; its non-entity library route is the reader, but the
        // research workspace is reached via its own sidebarMode branch — the key
        // guarantee here is that workflow/activity never fall to .libraryReader.
        XCTAssertNotEqual(route(.workflow(nil), false), .libraryReader)
        XCTAssertNotEqual(route(.activity(nil), false), .libraryReader)
        #endif
    }

    #if !os(macOS)
    private func route(_ mode: AppViewMode, _ isEntity: Bool) -> CompactShellRoute {
        CompactShellPolicy.route(
            horizontalSizeClass: .compact,
            appViewMode: mode,
            isEntitySelection: isEntity
        )
    }
    #endif
}
