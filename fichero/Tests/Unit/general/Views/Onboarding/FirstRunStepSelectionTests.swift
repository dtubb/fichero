@testable import Fichero
import XCTest

/// #2807 — iOS first-run parity: the platform-gated step list must skip the
/// Mac-only Library/Permissions/Cloud steps on companion platforms (iPhone/
/// iPad have no local engine), and the list-relative navigation must clamp at
/// both ends of WHICHEVER list the platform runs.
final class FirstRunStepSelectionTests: XCTestCase {

    // MARK: - Step selection

    /// The Mac runs the full flow, in declaration order. Recipe setup is part of
    /// first run, not a second onboarding: purpose first, then the material ending
    /// in the proposed recipe (source.onboard.screens-in-order).
    func testMacStepListIsTheFullFlow() {
        XCTAssertEqual(
            FirstRunStep.steps(isCompanionPlatform: false),
            [.welcome, .library, .permissions, .cloud, .purpose, .material, .start]
        )
    }

    /// Onboarding says "Project", not "Library" (ruled 2026-10-03); only the
    /// user-facing words change, the code keeps `.library` until a spec-first rename.
    func testLibraryStepIsTitledProject() {
        XCTAssertEqual(FirstRunStep.library.title, "Project")
    }

    /// Set Up… from the Inspector runs the same recipe steps as first run (one
    /// code path), purpose first; if it drifted, an existing library would be set
    /// up by a different flow than a new one.
    func testSetUpRunsTheFirstRunRecipeSteps() {
        XCTAssertEqual(FirstRunStep.setUpSteps, [.purpose, .material, .start])
        let full = FirstRunStep.steps(isCompanionPlatform: false)
        XCTAssertEqual(Array(full.suffix(FirstRunStep.setUpSteps.count)), FirstRunStep.setUpSteps)
    }

    /// Companion platforms skip every Mac-only step: library location,
    /// folder permissions, and AI provider setup all configure a LOCAL
    /// engine, which the companion does not have.
    func testCompanionStepListSkipsMacOnlySteps() {
        XCTAssertEqual(
            FirstRunStep.steps(isCompanionPlatform: true),
            [.welcome]
        )
    }

    /// The Mac-only marker is the single source of the split — welcome is the
    /// only shared step; everything else is Mac-only. A new step added without
    /// deciding its platform fails `CaseIterable` coverage here.
    func testMacOnlyMarkerTruthTable() {
        for step in FirstRunStep.allCases {
            XCTAssertEqual(
                step.isMacOnly,
                step != .welcome,
                "\(step)"
            )
        }
    }

    /// The compile-time platform constant matches the target this test runs on.
    func testIsCompanionPlatformMatchesBuildTarget() {
        #if os(macOS)
        XCTAssertFalse(FirstRunStep.isCompanionPlatform)
        #else
        XCTAssertTrue(FirstRunStep.isCompanionPlatform)
        #endif
    }

    // MARK: - List-relative navigation

    /// Forward navigation walks the full Mac list in order and clamps at the
    /// last step (the caller finishes there — it never wraps).
    func testNextWalksMacListAndClampsAtEnd() {
        let steps = FirstRunStep.steps(isCompanionPlatform: false)
        XCTAssertEqual(FirstRunStep.welcome.next(in: steps), .library)
        XCTAssertEqual(FirstRunStep.library.next(in: steps), .permissions)
        XCTAssertEqual(FirstRunStep.permissions.next(in: steps), .cloud)
        XCTAssertEqual(FirstRunStep.cloud.next(in: steps), .purpose)
        XCTAssertEqual(FirstRunStep.purpose.next(in: steps), .material)
        XCTAssertEqual(FirstRunStep.material.next(in: steps), .start)
        XCTAssertEqual(FirstRunStep.start.next(in: steps), .start)
    }

    /// Backward navigation clamps at the first step.
    func testPreviousWalksMacListAndClampsAtStart() {
        let steps = FirstRunStep.steps(isCompanionPlatform: false)
        XCTAssertEqual(FirstRunStep.start.previous(in: steps), .material)
        XCTAssertEqual(FirstRunStep.material.previous(in: steps), .purpose)
        XCTAssertEqual(FirstRunStep.purpose.previous(in: steps), .cloud)
        XCTAssertEqual(FirstRunStep.cloud.previous(in: steps), .permissions)
        XCTAssertEqual(FirstRunStep.permissions.previous(in: steps), .library)
        XCTAssertEqual(FirstRunStep.library.previous(in: steps), .welcome)
        XCTAssertEqual(FirstRunStep.welcome.previous(in: steps), .welcome)
    }

    /// On the single-step companion list, navigation is a fixed point in both
    /// directions — Welcome is first AND last, so the flow's advance action
    /// finishes rather than stepping into a Mac-only screen.
    func testCompanionListNavigationIsAFixedPointOnWelcome() {
        let steps = FirstRunStep.steps(isCompanionPlatform: true)
        XCTAssertEqual(FirstRunStep.welcome.next(in: steps), .welcome)
        XCTAssertEqual(FirstRunStep.welcome.previous(in: steps), .welcome)
        XCTAssertEqual(steps.first, steps.last)
    }

    /// A step NOT in the platform list (stale @State after a hypothetical list
    /// change) clamps to the list's boundaries instead of trapping the flow.
    func testStepOutsideListClampsToBoundaries() {
        let steps = FirstRunStep.steps(isCompanionPlatform: true)
        XCTAssertEqual(FirstRunStep.permissions.next(in: steps), .welcome)
        XCTAssertEqual(FirstRunStep.permissions.previous(in: steps), .welcome)
    }
}
