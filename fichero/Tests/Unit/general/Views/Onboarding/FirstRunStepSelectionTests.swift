@testable import Fichero
import XCTest

/// Setting up, in one window (section 7d, ruled 2026-10-11, #5668; #2807 for the companion platforms): the app's
/// pages, then Set Up a Project's, with one page per chosen stage; navigation clamps at both ends of WHICHEVER list
/// the window runs.
@MainActor
final class FirstRunStepSelectionTests: XCTestCase {

    // MARK: - The two set-ups

    /// `source.onboard.app.steps`: the app is set up in three pages, and Permissions is not one of them (folder access
    /// is asked when a folder is added).
    func testTheAppIsWelcomeWhatFicheroRunsAndTheHandOff() {
        XCTAssertEqual(SetupStep.appSteps, [.welcome, .whatFicheroRuns, .handOff])
        XCTAssertEqual(FirstRunWindow.flow(for: .firstRun, isCompanionPlatform: false).steps, SetupStep.appSteps)
    }

    /// `source.onboard.project.steps`: Set Up a Project runs Your project → Add material → About the material →
    /// Choose the Stages → one page per chosen stage → Train → Ready; Project › Set Up… starts at Add material.
    func testAProjectIsSetUpInSmallPagesWithOnePerChosenStage() {
        XCTAssertEqual(
            SetupStep.projectSteps(chosenStages: [], isNewProject: true),
            [.project, .addMaterial, .aboutMaterial, .stages, .train, .ready]
        )
        XCTAssertEqual(
            SetupStep.projectSteps(chosenStages: ["find-lines", "read"], isNewProject: false),
            [.addMaterial, .aboutMaterial, .stages, .stage("find-lines"), .stage("read"), .train, .ready]
        )
    }

    /// `source.onboard.project.one-view`: every way in opens the same pages; only where they begin differs.
    func testEveryWayInOpensTheSamePages() {
        let fromTheMenu = FirstRunWindow.flow(for: .newProject).steps
        let fromSetUp = FirstRunWindow.flow(for: .setUp).steps
        var fromTheWelcome = FirstRunWindow.flow(for: .firstRun, isCompanionPlatform: false)
        fromTheWelcome.project = .new
        XCTAssertEqual(Array(fromTheWelcome.steps.dropFirst(SetupStep.appSteps.count)), fromTheMenu)
        XCTAssertEqual(Array(fromTheMenu.dropFirst()), fromSetUp, "Set Up… is the same pages from Add material")
    }

    /// `source.onboard.first-launch-three-screens` (#5828): the first launch's sidebar is three items whatever is
    /// chosen; choosing a project never appends its pages; Continue and Back move between the three.
    func testTheFirstLaunchSidebarIsThreeFixedScreens() {
        let three: [SetupStep] = [.welcome, .whatFicheroRuns, .handOff]
        XCTAssertEqual(FirstRunWindow.flow(for: .firstRun, isCompanionPlatform: false).steps, three)
        XCTAssertEqual(SetupStep.welcome.title(), "Welcome")
        XCTAssertEqual(SetupStep.whatFicheroRuns.title(), "Where the work runs")
        XCTAssertEqual(SetupStep.handOff.title(), "Your First Project")
        XCTAssertEqual(SetupStep.welcome.next(in: three), .whatFicheroRuns)
        XCTAssertEqual(SetupStep.handOff.previous(in: three), .whatFicheroRuns)
        XCTAssertEqual(SetupStep.handOff.next(in: three), .handOff, "clamped: Start finishes")
    }

    /// Set Up a New Project… opens a separate window and does not touch this window's pages.
    func testSetUpANewProjectOpensItsOwnWindowAndLeavesTheSidebarAlone() {
        let footer = SetupFooter.of(.handOff, in: SetupStep.appSteps, mode: .firstRun, projectChosen: false)
        XCTAssertEqual(footer.leading, .init(title: "Set Up a New Project…", action: .openProjectSetUp))
        XCTAssertEqual(NewProjectSetUpWindow.id, "new-project-setup")
        XCTAssertEqual(FirstRunWindow.flow(for: .firstRun, isCompanionPlatform: false).project, .none)
    }

    /// Companion platforms have no local engine to set up: the welcome alone.
    func testCompanionPlatformsShowTheWelcomeAlone() {
        XCTAssertEqual(FirstRunWindow.flow(for: .firstRun, isCompanionPlatform: true).steps, [.welcome])
    }

    /// The compile-time platform constant matches the target this test runs on.
    func testIsCompanionPlatformMatchesBuildTarget() {
        #if os(macOS)
        XCTAssertFalse(SetupFlow.runsOnCompanionPlatform)
        #else
        XCTAssertTrue(SetupFlow.runsOnCompanionPlatform)
        #endif
    }

    /// Only the pages before a project exists can be reached without one.
    func testOnlyTheAppPagesAndYourProjectNeedNoProject() {
        XCTAssertTrue(SetupStep.appSteps.allSatisfy(\.needsNoProject))
        XCTAssertTrue(SetupStep.project.needsNoProject)
        XCTAssertFalse(SetupStep.addMaterial.needsNoProject)
        XCTAssertFalse(SetupStep.stage("read").needsNoProject)
    }

    // MARK: - List-relative navigation

    /// Forward navigation walks the list in order and clamps at the last page (the caller finishes there).
    func testNextWalksTheListAndClampsAtEnd() {
        let steps = SetupStep.projectSteps(chosenStages: ["read"], isNewProject: true)
        var walked = [SetupStep.project]
        while walked.last != .ready { walked.append(walked.last!.next(in: steps)) }
        XCTAssertEqual(walked, steps)
        XCTAssertEqual(SetupStep.ready.next(in: steps), .ready)
    }

    /// Backward navigation clamps at the first page.
    func testPreviousWalksTheListAndClampsAtStart() {
        let steps = SetupStep.appSteps
        var walked = [SetupStep.handOff]
        while walked.last != .welcome { walked.append(walked.last!.previous(in: steps)) }
        XCTAssertEqual(walked, steps.reversed())
        XCTAssertEqual(SetupStep.welcome.previous(in: steps), .welcome)
    }

    /// A page NOT in the list (a stage unticked while its page showed) clamps to the list's ends instead of
    /// trapping the flow.
    func testAPageOutsideTheListClampsToItsEnds() {
        let steps = SetupStep.projectSteps(chosenStages: [], isNewProject: false)
        XCTAssertEqual(SetupStep.stage("names").next(in: steps), .ready)
        XCTAssertEqual(SetupStep.stage("names").previous(in: steps), .addMaterial)
    }

    // MARK: - Each page opens at its top (#5801)

    /// Back, Next or the sidebar: the page's scroll view is keyed on the page, so moving to another page (two stage
    /// pages included) gives it a new scroll view at the top; the same page keeps its own.
    func testMovingToAnotherPageResetsTheScroll() {
        let pages = SetupStep.projectSteps(chosenStages: ["find-lines", "read"], isNewProject: true)
        let keys = pages.map(FirstRunWindow.scrollResetID(for:))
        XCTAssertEqual(Set(keys).count, pages.count, "every page scrolls on its own key: \(keys)")
        XCTAssertNotEqual(FirstRunWindow.scrollResetID(for: .stage("find-lines")),
                          FirstRunWindow.scrollResetID(for: .stage("read")))
        XCTAssertEqual(FirstRunWindow.scrollResetID(for: .ready), FirstRunWindow.scrollResetID(for: .ready))
    }
}
