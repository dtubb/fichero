@testable import Fichero
import XCTest

/// The cold-launch rulings of 2026-10-10 (maintainer):
/// - the always-there project (`global.fichero`) has no name in the UI and is never renamed, closed
///   or deleted (`library.always-there-project.*`); the sidebar's top section is its own items with
///   no heading row, and the other projects sit under Projects
///   (`sidebar.top-section-is-the-always-there-project`, `sidebar.projects-heading`);
/// - a first launch opens setup with a welcome, Set Up a New Project… and Start Without a Project
///   (`source.onboard.first-launch-offers-setup`);
/// - a project opens on its Sources folder, never Workflows (`sidebar.project.opens-on-sources`);
/// - the panes are Projects · Items · Source · Inspector · Reader · Segments, and people read
///   "Project", never "Library" (`sidebar.panes.one-word-names`, `sidebar.project-never-library`).
final class ProjectNamingTests: XCTestCase {
    private let globalPath = "/Users/x/Library/Application Support/Fichero/global.fichero"

    // MARK: - The always-there project has no name

    func testTheAlwaysThereProjectHasNoName() {
        for given in [nil, "", "  ", "Local", "Global", "My Library", "Desk", "global", "My Project", "Scratch"] {
            XCTAssertEqual(AlwaysThereProject.displayName(forPath: globalPath, given: given), "", given ?? "nil")
        }
        XCTAssertTrue(AlwaysThereProject.isPackage(path: globalPath))
        XCTAssertTrue(AlwaysThereProject.isPackage(path: globalPath + "/"))
        XCTAssertFalse(AlwaysThereProject.isPackage(path: "/Users/x/Fichero/Mosquera.fichero"))
        // The app's own reference to it, and any Open Recent entry for it, carry no name either. Built here rather
        // than read from `LibraryManager.shared.globalLibrary`, which a test host that has not opened the
        // always-there project leaves nil (the assertion then compared nil with "").
        XCTAssertEqual(Self.alwaysThereReference(given: "My Project").displayName, "")
        XCTAssertEqual(LibraryRecents.Entry(path: globalPath, displayName: "My Project").displayName, "")
    }

    private static func alwaysThereReference(given name: String) -> LibraryManager.LibraryReference {
        LibraryManager.LibraryReference(
            url: URL(fileURLWithPath: "/Users/x/Library/Application Support/Fichero/global.fichero"),
            document: FicheroDocument(), displayName: name, id: LibraryManager.globalLibraryId
        )
    }

    /// Any other project keeps the name it was given, even one the always-there project once had.
    func testAnotherProjectKeepsItsName() {
        XCTAssertEqual(AlwaysThereProject.displayName(forPath: "/p/Mosquera.fichero", given: "Local"), "Local")
        XCTAssertEqual(AlwaysThereProject.displayName(forPath: "/p/Mosquera.fichero", given: "My Project"), "My Project")
        let row = KnownLibraryMenuEntry(id: "/p/Mosquera.fichero", path: "/p/Mosquera.fichero",
                                        name: nil, addedAt: nil, lastAccessed: nil)
        XCTAssertEqual(row.displayName, "Mosquera")
    }

    /// The one rename every project has refuses it, and nothing is saved for it.
    func testTheAlwaysThereProjectIsNeverRenamed() throws {
        let manager = LibraryManager.shared
        // The open reference when the host has one, else one built at the same path and id: the refusal is by id.
        let global = manager.globalLibrary ?? Self.alwaysThereReference(given: "")
        let defaults = EngineConfig.defaults
        let key = LibraryManager.libraryDisplayNamesByPathKey
        let savedNames = defaults.dictionary(forKey: key)
        defer {
            if let savedNames { defaults.set(savedNames, forKey: key) } else { defaults.removeObject(forKey: key) }
        }

        manager.renameLibrary(id: LibraryManager.globalLibraryId, to: "Scratch")

        XCTAssertEqual(global.displayName, "")
        let names = defaults.dictionary(forKey: key) as? [String: String]
        XCTAssertNotEqual(names?[global.url.path.nfcNormalized], "Scratch")
    }

    /// A project a person set up is renamed, shared, closed and deleted from its row; the
    /// always-there project, which has no row, is offered none of them.
    func testTheAlwaysThereProjectIsOfferedNoRenameCloseOrDelete() {
        let always = ProjectRowMenuOffers.forProject(isAlwaysThere: true, multiuser: true)
        XCTAssertEqual(always, ProjectRowMenuOffers(rename: false, share: false, close: false, delete: false))

        let other = ProjectRowMenuOffers.forProject(isAlwaysThere: false, multiuser: true)
        XCTAssertEqual(other, ProjectRowMenuOffers(rename: true, share: true, close: true, delete: true))
        XCTAssertFalse(ProjectRowMenuOffers.forProject(isAlwaysThere: false, multiuser: false).share)
    }

    // MARK: - The sidebar's two parts

    private struct Row: Equatable {
        let name: String
        let libraryId: UUID?
    }

    /// The top section is the always-there project's own items with no header row: its header is
    /// split out of the project list wherever it sits, and only its children are drawn.
    func testTheTopSectionIsTheAlwaysThereProjectWithNoHeader() throws {
        let other = UUID()
        let rows = [Row(name: "Mosquera", libraryId: other), Row(name: "", libraryId: LibraryManager.globalLibraryId)]
        let sections = SidebarProjectSections.split(rows, libraryId: { $0.libraryId },
                                                    alwaysThereId: LibraryManager.globalLibraryId)
        XCTAssertEqual(sections.top?.libraryId, LibraryManager.globalLibraryId)
        XCTAssertEqual(sections.projects.map(\.name), ["Mosquera"])

        // The view hands the top's CHILDREN to the rows, never its header.
        let view = try Self.appSource("Views/Sidebar/Sections/SidebarView+ViewComponents.swift")
        XCTAssertTrue(view.contains("alwaysThereProjectItems(top)"))
        let source = try Self.appSource("Views/Sidebar/Sections/SidebarView+UnifiedLibrarySections.swift")
        let after = try XCTUnwrap(source.components(separatedBy: "func alwaysThereProjectItems(").dropFirst().first)
        let body = after.components(separatedBy: "func unifiedLibraryBuckets(").first ?? ""
        XCTAssertTrue(body.contains("unifiedLibrarySections(libraryId: libraryId, buckets: buckets)"))
        XCTAssertFalse(body.contains("DisclosureGroup"), "no heading row over the top section")
        XCTAssertFalse(body.contains("libraryDisclosureLabel"), "no heading row over the top section")
        // Sources and Workflows are its folders; Models and the knowledge rows are the same nodes
        // every project draws, so the top draws them too.
        XCTAssertTrue(source.contains("SidebarModelsNode(store: library.trainedModelsStore"))
        XCTAssertTrue(source.contains("SidebarKnowledgeRowsNode(store: library.knowledgeRowCountsStore"))
    }

    /// Below it, a Projects heading over every other project, in order; none when no other is open.
    func testTheProjectsHeadingListsTheOtherProjects() throws {
        XCTAssertEqual(SidebarProjectSections.projectsHeading, "Projects")
        let first = UUID(), second = UUID()
        let rows = [Row(name: "", libraryId: LibraryManager.globalLibraryId),
                    Row(name: "Mosquera", libraryId: first), Row(name: "Marshall", libraryId: second)]
        let sections = SidebarProjectSections.split(rows, libraryId: { $0.libraryId },
                                                    alwaysThereId: LibraryManager.globalLibraryId)
        XCTAssertEqual(sections.projects.map(\.name), ["Mosquera", "Marshall"])

        let alone = SidebarProjectSections.split([rows[0]], libraryId: { $0.libraryId },
                                                 alwaysThereId: LibraryManager.globalLibraryId)
        XCTAssertNotNil(alone.top)
        XCTAssertTrue(alone.projects.isEmpty)

        let view = try Self.appSource("Views/Sidebar/Sections/SidebarView+ViewComponents.swift")
        XCTAssertTrue(view.contains("if !sections.projects.isEmpty {"))
        XCTAssertTrue(view.contains("Text(SidebarProjectSections.projectsHeading)"))
    }

    /// No code a person reads names the always-there project "My Project" any more.
    func testNothingSaysMyProject() throws {
        let paths = ["Views/Onboarding/FirstRunWindow.swift", "Views/Onboarding/FirstRunWindow+Models.swift",
                     "Views/Sidebar/Sections/LibraryHeaderRow.swift", "Views/Sidebar/Sections/SidebarSectionHeader.swift",
                     "Models/AlwaysThereProject.swift", "Models/LibraryManager.swift",
                     "Models/KnownLibraryRegistryStore.swift", "Models/LibraryRecents.swift",
                     "Models/NewProjectStore.swift", "Views/Onboarding/RecipeSetupFields.swift"]
        for path in paths {
            let code = try Self.appSource(path).components(separatedBy: .newlines)
                .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
                .joined(separator: "\n")
            XCTAssertFalse(code.contains("\"My Project\""), path)
            XCTAssertFalse(code.contains("Use My Project"), path)
        }
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
                      "only the always-there project known: nothing set up yet")
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

    @MainActor
    func testFirstLaunchSetupWelcomesAndOffersBothChoices() {
        XCTAssertEqual(FirstLaunchChoices.setUpNewProject, "Set Up a New Project...")
        XCTAssertEqual(FirstLaunchChoices.startWithoutProject, "Start Without a Project")
        XCTAssertTrue(FirstLaunchChoices.welcomeParagraphs.last?.contains("Your work lives in projects") == true)

        // The welcome's two choices are its footer's (ruled 2026-10-11, the Mac setup assistant's chrome).
        let steps = FirstRunWindow.flow(for: .firstRun, isCompanionPlatform: false).steps
        let footer = SetupFooter.of(.welcome, in: steps, mode: .firstRun, projectChosen: false)
        XCTAssertEqual(footer.primary.title, "Continue")
        XCTAssertNil(footer.leading, "the welcome only continues (#5828); Set Up a New Project… is on Your First Project")
        XCTAssertNotEqual(footer.leading?.title, "Use My Project for Now", "Use My Project for Now is retired")
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
        XCTAssertEqual(BreadcrumbBuilder.buildBreadcrumb(from: doc, parentLookup: lookup, rootName: "Mosquera"),
                       "Mosquera › Box 3 › File.pdf")
        XCTAssertEqual(BreadcrumbBuilder.buildSegments(from: doc, parentLookup: lookup, rootName: "Mosquera").first?.name,
                       "Mosquera")
    }

    // MARK: - Side effects of the unnamed always-there project (#5655)

    /// `sidebar.breadcrumb.no-root-for-unnamed-project`: the always-there project has no name, so
    /// its trail starts at the first folder, never " › Sources › …".
    func testTheBreadcrumbOmitsAnEmptyRoot() {
        let doc = Document(id: "f", parentId: "p", name: "File.pdf")
        let parent = Document(id: "p", docType: .folder, name: "Sources")
        let lookup: BreadcrumbBuilder.DocumentLookup = { $0 == "p" ? parent : nil }
        XCTAssertEqual(BreadcrumbBuilder.buildBreadcrumb(from: doc, parentLookup: lookup, rootName: ""),
                       "Sources › File.pdf")
        let segments = BreadcrumbBuilder.buildSegments(from: doc, parentLookup: lookup, rootName: "")
        XCTAssertEqual(segments.map(\.name), ["Sources", "File.pdf"])
        XCTAssertFalse(segments.contains(where: \.isRoot))
        XCTAssertEqual(BreadcrumbBuilder.buildSegments(from: nil, parentLookup: lookup, rootName: ""), [])
        XCTAssertEqual(BreadcrumbBuilder.buildBreadcrumbForLibraryMode(
            document: doc, parentLookup: lookup, rootName: ""), "Sources › File.pdf")
        XCTAssertEqual(BreadcrumbBuilder.buildBreadcrumbForLibraryMode(
            document: nil, parentLookup: lookup, rootName: ""), "")
    }

    /// `library.always-there-project.window-title`: the window titles by project; the always-there
    /// project's window reads "Fichero", another project's its name, no project nothing.
    func testTheAlwaysThereProjectsWindowIsTitledFichero() throws {
        XCTAssertEqual(AlwaysThereProject.windowTitle(projectName: ""), "Fichero")
        XCTAssertEqual(AlwaysThereProject.windowTitle(projectName: "Mosquera"), "Mosquera")
        XCTAssertEqual(AlwaysThereProject.windowTitle(projectName: nil), "")
        let window = try Self.appSource("App/LibraryWindow.swift")
        XCTAssertTrue(window.contains(
            ".navigationTitle(AlwaysThereProject.windowTitle(projectName: windowState.library?.displayName))"))
    }

    /// `sidebar.run-workflow.no-heading-for-the-always-there-project`: Run Workflow's own-workflows
    /// group has no heading for the unnamed project, never an empty one.
    func testRunWorkflowHasNoHeadingForTheAlwaysThereProject() throws {
        XCTAssertNil(SidebarItemRow.ownWorkflowsHeading(projectName: ""))
        XCTAssertEqual(SidebarItemRow.ownWorkflowsHeading(projectName: "Mosquera"), "Mosquera")
        XCTAssertEqual(SidebarItemRow.ownWorkflowsHeading(projectName: nil), "This Project")
        let menu = try Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift")
        XCTAssertTrue(menu.contains("Self.ownWorkflowsHeading(projectName: library?.displayName)"))
        XCTAssertFalse(menu.contains("Section(library?.displayName"))
    }

    /// `sidebar.top-section.empty-area-menu`: what the always-there project's header row menu offered
    /// is on a right-click in the sidebar's empty space, and only there (a row keeps its own menu).
    func testTheEmptyAreaMenuOffersWhatTheHeaderRowDid() throws {
        XCTAssertEqual(AlwaysThereProjectMenu.items,
                       ["New Folder", "Import Files…", "Edit Document Types…", "Show in Finder"])
        XCTAssertTrue(AlwaysThereProjectMenu.isShown(clicked: Set<SidebarDestination>()))
        XCTAssertFalse(AlwaysThereProjectMenu.isShown(clicked: Set([SidebarDestination.library(UUID())])))
        let list = try Self.appSource("Views/Sidebar/Sections/SidebarView+ViewComponents.swift")
        XCTAssertTrue(list.contains(".contextMenu(forSelectionType: SidebarDestination.self)"))
        XCTAssertTrue(list.contains("alwaysThereProjectMenu(clicked: clicked)"))
        let helpers = try Self.appSource("Views/Sidebar/Sections/SidebarView+LibraryHeaderHelpers.swift")
        // New Folder, Edit Document Types… and Show in Finder are the shared items File and Project render (#5652).
        XCTAssertTrue(helpers.contains("Button(AlwaysThereProjectMenu.importFiles)"))
        for item in ["NewFolderMenuItem(", "EditDocumentTypesMenuItem(target: verbs)", "ShowProjectInFinderMenuItem(target: verbs)"] {
            XCTAssertTrue(helpers.contains(item), item)
        }
        XCTAssertEqual(ProjectVerbs.editDocumentTypesTitle, AlwaysThereProjectMenu.editDocumentTypes)
        XCTAssertEqual(ProjectVerbs.showInFinderTitle, AlwaysThereProjectMenu.showInFinder)
        XCTAssertEqual(ItemVerbs.newFolderTitle, AlwaysThereProjectMenu.newFolder)
        let sidebar = try Self.appSource("Views/Sidebar/SidebarView.swift")
        XCTAssertTrue(sidebar.contains(".sheet(item: $alwaysThereTypeEditorLibrary)"))
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
