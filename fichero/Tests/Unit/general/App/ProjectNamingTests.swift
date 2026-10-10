@testable import Fichero
import XCTest

/// The cold-launch rulings of 2026-10-10 (maintainer):
/// - the always-there project (`global.fichero`) is named My Project by default and renamed like any
///   project; it is never closed or deleted (`library.always-there-project.*`);
/// - a first launch opens setup with a welcome, Set Up a New Project… and Use My Project for Now
///   (`source.onboard.first-launch-offers-setup`);
/// - a project opens on its Sources folder, never Workflows (`sidebar.project.opens-on-sources`);
/// - the panes are Projects · Items · Source · Inspector · Reader · Segments, and people read
///   "Project", never "Library" (`sidebar.panes.one-word-names`, `sidebar.project-never-library`).
final class ProjectNamingTests: XCTestCase {
    private let globalPath = "/Users/x/Library/Application Support/Fichero/global.fichero"

    // MARK: - The always-there project's name

    func testTheAlwaysThereProjectIsMyProjectByDefault() {
        XCTAssertEqual(AlwaysThereProject.defaultName, "My Project")
        XCTAssertEqual(AlwaysThereProject.displayName(forPath: globalPath, given: nil), "My Project")
        XCTAssertEqual(AlwaysThereProject.displayName(forPath: globalPath, given: "  "), "My Project")
        XCTAssertTrue(AlwaysThereProject.isPackage(path: globalPath))
        XCTAssertTrue(AlwaysThereProject.isPackage(path: globalPath + "/"))
        XCTAssertFalse(AlwaysThereProject.isPackage(path: "/Users/x/Fichero/Mosquera.fichero"))
    }

    /// A name the app gave it before the ruling is not a person's choice: it reads as My Project.
    func testASavedOldNameReadsAsMyProject() {
        for old in ["Local", "Global", "My Library", "Desk", "global"] {
            XCTAssertEqual(AlwaysThereProject.displayName(forPath: globalPath, given: old), "My Project", old)
        }
        // Open Recent's entry and the registry's row read the same way.
        XCTAssertEqual(LibraryRecents.Entry(path: globalPath, displayName: "Local").displayName, "My Project")
        let row = KnownLibraryMenuEntry(id: globalPath, path: globalPath, name: "Local", addedAt: nil, lastAccessed: nil)
        XCTAssertEqual(row.displayName, "My Project")
    }

    /// A name a person chose is kept, for the always-there project and any other.
    func testANameAPersonChoseIsKept() {
        XCTAssertEqual(AlwaysThereProject.displayName(forPath: globalPath, given: "Scratch"), "Scratch")
        XCTAssertEqual(AlwaysThereProject.displayName(forPath: "/p/Mosquera.fichero", given: "Local"), "Local",
                       "only the always-there project's old names retire")
        XCTAssertEqual(LibraryRecents.Entry(path: globalPath, displayName: "Scratch").displayName, "Scratch")
    }

    /// Renaming it goes through the one rename every project has, is shown, and is kept under its
    /// path in the saved display names.
    func testRenamingTheAlwaysThereProjectIsShownAndKept() throws {
        let manager = LibraryManager.shared
        let global = try XCTUnwrap(manager.globalLibrary)
        let defaults = EngineConfig.defaults
        let key = LibraryManager.libraryDisplayNamesByPathKey
        let savedNames = defaults.dictionary(forKey: key)
        let originalName = global.displayName
        defer {
            global.displayName = originalName
            if let savedNames { defaults.set(savedNames, forKey: key) } else { defaults.removeObject(forKey: key) }
        }

        manager.renameLibrary(id: LibraryManager.globalLibraryId, to: "  Scratch  ")

        XCTAssertEqual(global.displayName, "Scratch")
        let names = try XCTUnwrap(defaults.dictionary(forKey: key) as? [String: String])
        XCTAssertEqual(names[global.url.path.nfcNormalized], "Scratch")
    }

    /// Every project is renamed from its row; the always-there one is never closed, deleted or shared.
    func testTheAlwaysThereProjectOffersRenameButNeverCloseOrDelete() {
        let always = ProjectRowMenuOffers.forProject(isAlwaysThere: true, multiuser: true)
        XCTAssertTrue(always.rename)
        XCTAssertFalse(always.close)
        XCTAssertFalse(always.delete)
        XCTAssertFalse(always.share)

        let other = ProjectRowMenuOffers.forProject(isAlwaysThere: false, multiuser: true)
        XCTAssertEqual(other, ProjectRowMenuOffers(rename: true, share: true, close: true, delete: true))
        XCTAssertFalse(ProjectRowMenuOffers.forProject(isAlwaysThere: false, multiuser: false).share)
    }

    /// File › Close Project is not offered for it either (the window's action is nil for it).
    func testFileCloseIsNotOfferedForTheAlwaysThereProject() throws {
        let actions = try Self.appSource("App/LibraryWindow+Actions.swift")
        let close = try XCTUnwrap(actions.components(separatedBy: "var closeLibraryAction: FocusedLibraryAction? {").dropFirst().first)
        XCTAssertTrue(close.prefix(300).contains("library.id != LibraryManager.globalLibraryId"))
    }

    // MARK: - First launch

    #if os(macOS)
    func testAFirstLaunchOffersSetUp() {
        XCTAssertTrue(firstLaunchOffersSetUp(firstRunCompleted: false, knownProjectPaths: []))
        XCTAssertTrue(firstLaunchOffersSetUp(firstRunCompleted: false, knownProjectPaths: [globalPath, globalPath]),
                      "only My Project known: nothing set up yet")
    }

    /// Later launches never show it: first run done, or a project the person set up is known.
    func testALaterLaunchDoesNotOfferSetUp() {
        XCTAssertFalse(firstLaunchOffersSetUp(firstRunCompleted: true, knownProjectPaths: [globalPath]))
        XCTAssertFalse(firstLaunchOffersSetUp(firstRunCompleted: false,
                                              knownProjectPaths: [globalPath, "/Users/x/Fichero/Mosquera.fichero"]))
    }

    /// The sheet reads the decision, made once when it is armed (so making a project in setup does
    /// not close setup).
    func testTheFirstRunSheetReadsTheFirstLaunchDecision() throws {
        let window = try Self.appSource("App/LibraryWindow.swift")
        XCTAssertTrue(window.contains("firstLaunchDue || libraryIsLoadedAndEmpty("))
        XCTAssertTrue(window.contains("firstLaunchDue = firstLaunchIsDue"))
        let actions = try Self.appSource("App/LibraryWindow+Actions.swift")
        XCTAssertTrue(actions.contains("firstLaunchOffersSetUp("))
    }
    #endif

    func testFirstLaunchSetupWelcomesAndOffersBothChoices() throws {
        XCTAssertEqual(FirstLaunchChoices.setUpNewProject, "Set Up a New Project…")
        XCTAssertEqual(FirstLaunchChoices.useAlwaysThereProject(named: "My Project"), "Use My Project for Now")
        XCTAssertEqual(FirstLaunchChoices.useAlwaysThereProject(named: "Scratch"), "Use Scratch for Now")
        XCTAssertTrue(FirstLaunchChoices.welcome.contains("setting up a project"))

        let window = try Self.appSource("Views/Onboarding/FirstRunWindow.swift")
        XCTAssertTrue(window.contains("title: \"Welcome to Fichero\""))
        XCTAssertTrue(window.contains("subtitle: FirstLaunchChoices.welcome"))
        XCTAssertTrue(window.contains("primaryTitle: FirstLaunchChoices.setUpNewProject"))
        XCTAssertTrue(window.contains("secondary: (FirstLaunchChoices.useAlwaysThereProject(), { finish() })"))
    }

    // MARK: - A project opens on its Sources

    private func folder(_ id: String, _ name: String, parent: String? = nil) -> Document {
        Document(id: id, parentId: parent, docType: .folder, name: name)
    }

    func testAProjectOpensOnItsSourcesNeverWorkflows() {
        let roots = [folder(Document.defaultWorkflowsContainerID, "Default Workflows"), folder("src", "Sources")]
        XCTAssertEqual(OpeningSelection.selectionId(restoredId: nil, viewModeType: "library", roots: roots), "doc:src")
        XCTAssertEqual(OpeningSelection.collectionToOpen(in: roots)?.id, "src", "the store opens Sources, not Default Workflows")
    }

    func testARestoredSelectionWins() {
        let roots = [folder("src", "Sources")]
        XCTAssertEqual(OpeningSelection.selectionId(restoredId: "doc:other", viewModeType: "library", roots: roots), "doc:other")
        XCTAssertEqual(OpeningSelection.selectionId(restoredId: nil, viewModeType: "activity", roots: roots), "activity-browser")
        XCTAssertNil(OpeningSelection.selectionId(restoredId: nil, viewModeType: "chat", roots: roots))
    }

    func testNoSourcesNoSelection() {
        XCTAssertNil(OpeningSelection.selectionId(restoredId: nil, viewModeType: "library", roots: []))
        // A nested folder named Sources is not the project's Sources.
        let nested = [folder("a", "Box"), folder("n", "Sources", parent: "a")]
        XCTAssertNil(OpeningSelection.selectionId(restoredId: nil, viewModeType: "library", roots: nested))
        XCTAssertEqual(OpeningSelection.collectionToOpen(in: nested)?.id, "a", "a project with no Sources opens its first root")
    }

    // MARK: - Pane names and the breadcrumb

    func testThePanesAreItemsAndSource() throws {
        XCTAssertEqual(ItemsPane.name, "Items")
        XCTAssertEqual(ItemsPane.showLabel, "Show Items")
        XCTAssertEqual(SourcePane.name, "Source")
        XCTAssertEqual(SourcePane.hideLabel, "Hide Source")
        XCTAssertEqual(SidebarMode.library.label, ItemsPane.name)
        // App Intents reads these at build time, so they are literals; they must say the same.
        let verbs = try Self.appSource("Intents/UIVerbs.swift")
        XCTAssertTrue(verbs.contains(".library: \"\(ItemsPane.name)\", .preview: \"\(SourcePane.name)\""))
    }

    func testTheBreadcrumbRootIsTheProjectsName() {
        let doc = Document(id: "f", parentId: "p", name: "File.pdf")
        let parent = Document(id: "p", docType: .folder, name: "Box 3")
        let lookup: BreadcrumbBuilder.DocumentLookup = { $0 == "p" ? parent : nil }
        XCTAssertEqual(BreadcrumbBuilder.buildBreadcrumb(from: doc, parentLookup: lookup, rootName: "My Project"),
                       "My Project › Box 3 › File.pdf")
        XCTAssertEqual(BreadcrumbBuilder.buildSegments(from: doc, parentLookup: lookup, rootName: "Mosquera").first?.name,
                       "Mosquera")
    }

    // MARK: - Project, never Library

    /// Proper nouns that contain the word and are not about projects.
    private static let allowed: [(phrase: String, reason: String)] = [
        ("Library of Congress", "the name authority Wikidata and VIAF sit beside, not a project")
    ]

    /// No first string literal of a call people read (`Button`, `Text`, `Label`, `Menu`, `Section`,
    /// `Toggle`, `LabeledContent`, `ContentUnavailableView`, `.help`, `.accessibilityLabel`,
    /// `.accessibilityHint`, `.navigationTitle`, `.alert`, `.confirmationDialog`) says Library or
    /// Libraries. Comments, identifiers and interpolated code are not words a person reads.
    func testNoUserVisibleStringSaysLibrary() throws {
        let root = try AppSource.root().standardizedFileURL
        let enumerator = try XCTUnwrap(FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil))
        let calls = "Button|Text|Label|Menu|Section|Toggle|LabeledContent|ContentUnavailableView|help|"
            + "accessibilityLabel|accessibilityHint|navigationTitle|alert|confirmationDialog"
        let call = try NSRegularExpression(pattern: #"(?<![A-Za-z0-9_])\.?(?:"# + calls + #")\(\s*"((?:[^"\\\n]|\\.)*)""#)
        let interpolation = try NSRegularExpression(pattern: #"\\\([^)]*\)"#)
        let word = try NSRegularExpression(pattern: #"\b[Ll]ibrar(?:y|ies)\b"#)
        var scanned = 0
        var offenders: [String] = []
        for case let url as URL in enumerator where url.pathExtension == "swift" {
            let text = try String(contentsOf: url, encoding: .utf8)
                .components(separatedBy: .newlines)
                .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
                .joined(separator: "\n")
            let range = NSRange(text.startIndex..<text.endIndex, in: text)
            for match in call.matches(in: text, range: range) {
                guard let literalRange = Range(match.range(at: 1), in: text) else { continue }
                scanned += 1
                var literal = String(text[literalRange])
                literal = interpolation.stringByReplacingMatches(
                    in: literal, range: NSRange(literal.startIndex..., in: literal), withTemplate: "")
                for allowed in Self.allowed { literal = literal.replacingOccurrences(of: allowed.phrase, with: "") }
                if word.firstMatch(in: literal, range: NSRange(literal.startIndex..., in: literal)) != nil {
                    offenders.append("\(AppSource.relativePath(of: url, under: root)): \(text[literalRange])")
                }
            }
        }
        XCTAssertGreaterThan(scanned, 500, "the scan found almost no labels — it measures nothing")
        XCTAssertEqual(offenders, [], "people read Project, never Library (ruled 2026-10-03, 2026-10-10)")
    }

    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }
}
