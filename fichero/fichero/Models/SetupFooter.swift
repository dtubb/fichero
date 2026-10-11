import Foundation

/// A setup page's footer, the Mac setup assistant's (ruled 2026-10-11, `source.onboard.app.footer`): one secondary
/// choice at the far left (plain), Back, then the primary action at the far right as the default button (⏎). Back is
/// hidden on the first page. No navigation sits in a page's content. Pure, for the tests.
struct SetupFooter: Equatable {
    enum Action: Equatable {
        /// Go on to the next page (the page's own work first: make the project, save the draft).
        case advance
        /// Welcome: set up a project, then go on.
        case setUpNewProject
        /// Welcome: go on without a project.
        case startWithoutProject
        /// The hand-off with no project: add a project's pages after it.
        case addAProject
        /// Move on, leaving this page's answers as they are (Not Now, Skip This Stage).
        case skip
        /// Ready: start the recipe.
        case start
        /// The last page of the app's own: close setup.
        case finish
        /// Close a setup opened on purpose (File › Set Up New Project…, Project › Set Up…).
        case close
    }

    struct Choice: Equatable {
        let title: String
        let action: Action
    }

    /// The far-left choice, or none on a page that cannot be skipped.
    let leading: Choice?
    let showsBack: Bool
    /// The default button, far right.
    let primary: Choice

    static func of(_ step: SetupStep, in steps: [SetupStep], mode: FirstRunWindow.Mode,
                   projectChosen: Bool) -> SetupFooter {
        let isLast = step == steps.last
        let primary: Choice
        var leading: Choice?
        switch step {
        case .welcome:
            primary = Choice(title: FirstLaunchChoices.setUpNewProject, action: .setUpNewProject)
            leading = Choice(title: FirstLaunchChoices.startWithoutProject, action: .startWithoutProject)
        case .whatFicheroRuns:
            primary = Choice(title: "Continue", action: .advance)
            leading = Choice(title: "Not Now", action: .skip)
        case .handOff:
            if projectChosen {
                primary = Choice(title: "Continue", action: .advance)
            } else {
                primary = Choice(title: "Start", action: .finish)
                leading = Choice(title: FirstLaunchChoices.setUpNewProject, action: .addAProject)
            }
        case .project:
            primary = Choice(title: "Create Project", action: .advance)
        case .stage:
            primary = Choice(title: "Continue", action: .advance)
            leading = Choice(title: "Skip This Stage", action: .skip)
        case .train:
            primary = Choice(title: "Continue", action: .advance)
            leading = Choice(title: "Not Now", action: .skip)
        case .ready:
            primary = Choice(title: "Start", action: .start)
        default:
            primary = Choice(title: isLast ? "Done" : "Continue", action: .advance)
        }
        // A setup opened on purpose can always be closed: its left-hand choice where the page has none.
        if leading == nil, mode != .firstRun {
            leading = Choice(title: mode == .setUp ? "Close" : "Cancel", action: .close)
        }
        return SetupFooter(leading: leading, showsBack: step != steps.first, primary: primary)
    }
}
