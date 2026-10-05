@testable import Fichero
import XCTest

/// #2807 — iOS first-run parity: the platform-gated step list must skip the
/// Mac-only steps on companion platforms (iPhone/iPad have no local engine), and the
/// list-relative navigation must clamp at both ends of WHICHEVER list the platform runs.
final class FirstRunStepSelectionTests: XCTestCase {

    // MARK: - Step selection

    /// The Mac runs the full flow, in declaration order. Setup is part of first run, not a
    /// second onboarding, in section 7b's order (ruled 2026-10-05): where it lives, your
    /// material, (kept exported, #5485, not built yet), what it is for, what it is, each ticked
    /// job, how it will be done, what runs by itself, Start. WHY: the files come before the
    /// purposes, so a person says where the project is and what is in it before what it is for.
    func testMacStepListIsTheFullFlowWithMaterialBeforePurpose() {
        XCTAssertEqual(
            FirstRunStep.steps(isCompanionPlatform: false),
            [.welcome, .permissions, .cloud, .location, .material, .purpose, .about, .jobs, .recipe, .automatic, .start]
        )
    }

    /// Set Up… from a project runs the same setup steps as first run (one code path), starting
    /// at screen 2, Your material (the project already lives somewhere); Set Up New Project…
    /// adds Where it lives before them. If either drifted, a new project and an existing one
    /// would be set up by different flows.
    func testSetUpStartsAtYourMaterialAndRunsTheFirstRunSteps() {
        XCTAssertEqual(FirstRunStep.setUpSteps.first, .material)
        XCTAssertEqual(FirstRunStep.setUpSteps, [.material, .purpose, .about, .jobs, .recipe, .automatic, .start])
        XCTAssertEqual(FirstRunStep.newProjectSteps, [.location] + FirstRunStep.setUpSteps)
        let full = FirstRunStep.steps(isCompanionPlatform: false)
        XCTAssertEqual(Array(full.suffix(FirstRunStep.newProjectSteps.count)), FirstRunStep.newProjectSteps)
    }

    /// Companion platforms skip every Mac-only step: project location,
    /// folder permissions, AI provider setup and the recipe all configure a LOCAL
    /// engine, which the companion does not have.
    func testCompanionStepListSkipsMacOnlySteps() {
        XCTAssertEqual(
            FirstRunStep.steps(isCompanionPlatform: true),
            [.welcome]
        )
    }

    /// The Mac-only marker is the single source of the split — welcome is the
    /// only shared step; everything else is Mac-only.
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
        var walked = [FirstRunStep.welcome]
        while walked.last != .start { walked.append(walked.last!.next(in: steps)) }
        XCTAssertEqual(walked, steps)
        XCTAssertEqual(FirstRunStep.start.next(in: steps), .start)
    }

    /// Backward navigation clamps at the first step.
    func testPreviousWalksMacListAndClampsAtStart() {
        let steps = FirstRunStep.steps(isCompanionPlatform: false)
        var walked = [FirstRunStep.start]
        while walked.last != .welcome { walked.append(walked.last!.previous(in: steps)) }
        XCTAssertEqual(walked, steps.reversed())
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
