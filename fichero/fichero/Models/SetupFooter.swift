import Foundation

/// A setup page's footer, the Mac setup assistant's (ruled 2026-10-11, `source.onboard.app.footer`): one secondary
/// choice at the far left (plain), Back, then the primary action at the far right as the default button (⏎). Back is
/// hidden on the first page. No navigation sits in a page's content. Pure, for the tests.
struct SetupFooter: Equatable {
    enum Action: Equatable {
        /// Go on to the next page (the page's own work first: make the project, save the draft).
        case advance
        /// Your First Project: close the welcome and open a new project's own Set Up in the front window (#5828).
        case setUpNewProject
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
    /// Ready's Start lives in the page's last box with the total and why it waits (#5840), so the footer has no default
    /// button there.
    var primaryLivesInPage: Bool { primary.action == .start }

    /// Why the default button waits, said beside it; nil when it can be pressed (#5813).
    var waitsFor: String?

    /// Your Material's Continue waits for material, and says so (#5813, ruled 2026-10-19).
    static let addYourPages = "Add your pages to continue"

    /// About the Material's Continue waits for an answer to Languages: a language, or Not sure (never blank).
    static let chooseTheLanguage = "Choose the language, or Not sure, to continue"

    /// `hasMaterial`: the project has material (a file or folder added, or pages already counted).
    static func of(_ step: SetupStep, in steps: [SetupStep], mode: FirstRunWindow.Mode,
                   projectChosen: Bool, hasMaterial: Bool = true, hasLanguage: Bool = true) -> SetupFooter {
        let isLast = step == steps.last
        let primary: Choice
        var leading: Choice?
        switch step {
        case .welcome, .whatFicheroRuns:
            // The first launch is three fixed screens with Continue and Back between them (#5828).
            primary = Choice(title: "Continue", action: .advance)
        case .handOff:
            primary = Choice(title: FirstLaunchChoices.setUpNewProject, action: .setUpNewProject)
            leading = Choice(title: FirstLaunchChoices.startWithoutProject, action: .finish)
        case .project:
            primary = Choice(title: "Create Project", action: .advance)
        case .stage:
            primary = Choice(title: "Continue", action: .advance)
            leading = Choice(title: "Skip This Stage", action: .skip)
        case .ready:
            primary = Choice(title: "Start", action: .start)
        case .addMaterial:
            primary = Choice(title: "Continue", action: .advance)
            // Leaving here leaves Set Up: the stages have nothing to read without material (#5813).
            if mode == .firstRun { leading = Choice(title: "Not Now", action: .close) }
        default:
            primary = Choice(title: isLast ? "Done" : "Continue", action: .advance)
        }
        // A setup opened on purpose can always be closed: its left-hand choice where the page has none.
        if leading == nil, mode != .firstRun {
            leading = Choice(title: mode == .setUp ? "Close" : "Cancel", action: .close)
        }
        return SetupFooter(leading: leading, showsBack: step != steps.first, primary: primary,
                           waitsFor: step == .addMaterial && !hasMaterial ? addYourPages
                               : step == .aboutMaterial && !hasLanguage ? chooseTheLanguage : nil)
    }
}
