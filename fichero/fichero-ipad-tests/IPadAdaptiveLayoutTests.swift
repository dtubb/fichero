#if os(iOS)
@testable import Fichero
import SwiftUI
import XCTest

/// The iPad-relevant layout decisions, run on iPad for the first time (#4472).
///
/// These are pure mappings, so they could in principle run anywhere — but they
/// are the rules that only MATTER on iPad, and running them here is what makes
/// the platform claim real rather than inferred. The inspector audit (#4502)
/// recorded that `DocumentInspector` reads no `horizontalSizeClass` itself, so
/// only the CONTAINER adapts and not the contents; these pin the container half
/// that does exist.
final class IPadAdaptiveLayoutTests: XCTestCase {

    // MARK: - Compact width is a sheet, not a docked pane

    func testCompactWidthPresentsTheInspectorAsASheet() {
        XCTAssertEqual(
            InspectorPresenter.adaptiveDefault(horizontalSizeClass: .compact),
            .sheet
        )
    }

    /// The case a full-screen iPad actually hits. A docked inspector needs the
    /// width to be there, and on iPad it is.
    func testRegularWidthDocksTheInspector() {
        XCTAssertEqual(
            InspectorPresenter.adaptiveDefault(horizontalSizeClass: .regular),
            .docked
        )
    }

    /// Compact resolves to a navigation PUSH rather than a sheet-over-sheet.
    /// The distinction is invisible on Mac and is the whole difference between
    /// a usable and an unusable inspector in an iPad split view.
    func testCompactSheetBecomesANavigationPush() {
        XCTAssertEqual(
            InspectorPresenter.adaptivePresentation(horizontalSizeClass: .compact),
            .navigationPush
        )
        XCTAssertEqual(
            InspectorPresenter.adaptivePresentation(horizontalSizeClass: .regular),
            .docked
        )
    }

    /// An explicit request wins over the size class, in both directions — the
    /// detach affordance has to be able to override the adaptive default or it
    /// is not a choice.
    func testAnExplicitPlacementIsHonouredWhateverTheSizeClass() {
        for sizeClass: UserInterfaceSizeClass? in [.compact, .regular, nil] {
            for requested in InspectorPlacement.allCases {
                XCTAssertEqual(
                    InspectorPresenter.adaptiveDefault(
                        horizontalSizeClass: sizeClass,
                        requested: requested
                    ),
                    requested
                )
            }
        }
    }

    // MARK: - iOS never runs a local engine

    /// #2465: iOS must never probe localhost. There is no engine on the device,
    /// so a local strategy would produce a connection failure the user cannot
    /// act on. Worth running ON iOS specifically, because the strategy is
    /// decided from `isMacOS` and a macOS-only test can never exercise the
    /// branch that matters here.
    func testIOSNeverResolvesToALocalEngineStrategy() {
        for strategy in [
            EngineConfig.EngineProvisioningStrategy.iosCompanion,
            .configuredRemote
        ] {
            XCTAssertFalse(
                strategy.spawnsBundledEngine,
                "\(strategy) would try to spawn an engine that cannot exist on iPad"
            )
            XCTAssertEqual(EngineConfig.transportMode(for: strategy), .https)
        }
    }
}
#endif
