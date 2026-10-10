@testable import Fichero
import XCTest

final class MenuTerminologyBoundaryTests: XCTestCase {
    func testFileAndImportMenusUseProjectAndMoveTerminology() throws {
        // Export handlers split to FileMenuCommands+Export.swift (2026-08-21,
        // file_length) — the service call moved there; the labels stayed.
        let fileMenuSource = try Self.appSource("App/Menus/FileMenuCommands.swift")
            + Self.appSource("App/Menus/FileMenuCommands+Export.swift")
        // Library was renamed Project (2026-10-03); File says so (ruled 2026-10-10).
        XCTAssertTrue(fileMenuSource.contains("Button(\"Close Project\")"))
        XCTAssertTrue(fileMenuSource.contains("Button(\"Save Project As…\")"))
        XCTAssertTrue(fileMenuSource.contains("Label(\"Markdown Static Site…\", systemImage: \"globe\")"))
        XCTAssertTrue(fileMenuSource.contains("library.documentService.exportEleventySite("))
        XCTAssertTrue(fileMenuSource.contains("Text(\"Couldn’t load recent projects\")"))
        // Open Recent's empty/error states are explicit menu ROWS now, not a
        // .disabled modifier (the lane's refactor): pin the branch chain.
        XCTAssertTrue(fileMenuSource.contains("Text(\"No Recent Projects\")"))
        XCTAssertFalse(fileMenuSource.contains(".disabled(registry.libraries.isEmpty"))
        XCTAssertFalse(fileMenuSource.contains("Close Database"))
        XCTAssertFalse(fileMenuSource.contains("Save Database As..."))
        XCTAssertFalse(fileMenuSource.contains("Label(\"Static Site (11ty)...\", systemImage: \"globe\")"))

        // The "Move Files..." button moved into the +SidebarActions.swift sibling.
        let focusedCommandsSource = try [
            Self.appSource("App/Menus/FocusedCommands/FocusedCommandButtons.swift"),
            Self.appSource("App/Menus/FocusedCommands/FocusedCommandButtons+SidebarActions.swift")
        ].joined(separator: "\n")
        XCTAssertTrue(focusedCommandsSource.contains("Button(\"Move Files...\")"))
        XCTAssertFalse(focusedCommandsSource.contains("Button(\"Add Files...\")"))

        let addItemMenuSource = try Self.appSource("App/Menus/AddItemMenu.swift")
        XCTAssertTrue(addItemMenuSource.contains("Button(\"Move Files...\")"))
        XCTAssertFalse(addItemMenuSource.contains("Button(\"Add Files...\")"))
    }

    /// Ruled 2026-10-10: File's labels say Project, never Library (renamed 2026-10-03), and end
    /// in the ellipsis character, never three dots. Only quoted labels are checked, so comments,
    /// type names (`LibraryRecents`) and identifiers (`closeLibraryAction`) are not words a
    /// person reads.
    func testFileMenuLabelsSayProjectAndUseTheEllipsis() throws {
        let source = try Self.appSource("App/Menus/FileMenuCommands.swift")
        let labels = try Self.quotedLabels(in: source)
        XCTAssertFalse(labels.isEmpty, "found no labels in File — the scan measures nothing")
        for label in labels {
            XCTAssertFalse(label.localizedCaseInsensitiveContains("librar"), "File says Library: \(label)")
            XCTAssertFalse(label.contains("..."), "File uses three dots, not …: \(label)")
        }
        // One set-up item in File: Set Up New Project… makes a project; setting up the key window's
        // project is Project › Set Up….
        XCTAssertTrue(labels.contains("Set Up New Project…"))
        XCTAssertFalse(labels.contains("Set Up Project…"), "Set Up Project… is Project › Set Up… now")
    }

    /// Ruled 2026-10-10: one Project menu with Set Up… and Start at the top, then a titled section per
    /// recipe stage in recipe order (Read · Organise · Structure · Connect · Train). Knowledge retired
    /// into it.
    func testProjectMenuDeclaresTheStageSectionsInRecipeOrder() throws {
        XCTAssertEqual(
            ProjectMenuStage.allCases.map(\.title),
            ["Read", "Organise", "Structure", "Connect", "Train"]
        )

        let source = try Self.appSource("App/Menus/ReadKnowledgeMenuCommands.swift")
        XCTAssertFalse(source.contains("CommandMenu(\"Knowledge\")"), "the Knowledge menu retired into Project")
        let project = try XCTUnwrap(source.range(of: "CommandMenu(\"Project\")"), "no Project menu")
        let body = String(source[project.upperBound...])

        // Set Up… and Start come first, before the stages.
        let setUp = try XCTUnwrap(body.range(of: "FocusedSetUpButton()"))
        let start = try XCTUnwrap(body.range(of: "FocusedStartRecipeButton()"))
        let stages = try XCTUnwrap(body.range(of: "ForEach(ProjectMenuStage.allCases)"))
        XCTAssertLessThan(setUp.lowerBound, start.lowerBound)
        XCTAssertLessThan(start.lowerBound, stages.lowerBound)

        // Each built stage is a titled Section holding its verbs; Workflows ▸ and Chat ▸ moved here.
        XCTAssertTrue(body.contains("case .organise:\n            Section(stage.title) {\n                FocusedFindDocumentsButton()"))
        XCTAssertTrue(body.contains("case .connect:\n            Section(stage.title) {"))
        XCTAssertTrue(body.contains("Button(\"SPARQL Console…\")"))
        XCTAssertTrue(body.contains("Menu(\"Workflows\")"))
        XCTAssertTrue(body.contains("Menu(\"Chat\")"))
    }

    /// Every context-menu verb is in the menu bar through ONE component (ruled 2026-10-10,
    /// `menus.context-matches-bar`): the label "Find the Documents" is written once in the app, in
    /// `FindDocumentsMenuItem`, and both context menus and the Project menu render that component.
    func testFindTheDocumentsIsOneComponent() throws {
        let root = try AppSource.root().standardizedFileURL
        let enumerator = try XCTUnwrap(FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil))
        var labelSites: [String] = []
        var componentSites: [String] = []
        for case let url as URL in enumerator where url.pathExtension == "swift" {
            let relative = AppSource.relativePath(of: url, under: root)
            let source = try String(contentsOf: url, encoding: .utf8)
            for line in source.components(separatedBy: .newlines) {
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if trimmed.hasPrefix("//") { continue }
                if trimmed.contains("Label(\"Find the Documents\"") || trimmed.contains("Button(\"Find the Documents\"") {
                    labelSites.append(relative)
                }
                if trimmed.contains("FindDocumentsMenuItem(") && !trimmed.hasPrefix("struct ") {
                    componentSites.append(relative)
                }
            }
        }
        XCTAssertEqual(labelSites, ["App/Menus/FocusedCommands/FocusedCommandButtons+Recipe.swift"])
        XCTAssertEqual(
            Set(componentSites),
            [
                "App/Menus/FocusedCommands/FocusedCommandButtons+Recipe.swift",
                "Views/Library/LibraryView+ContextMenu.swift",
                "Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift",
            ]
        )
        // No surface calls the service itself any more.
        for file in ["Views/Library/LibraryView+ContextMenu.swift", "Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift"] {
            XCTAssertFalse(try Self.appSource(file).contains("findDocuments(scopeIds:"), "\(file) calls the service itself")
        }
    }

    /// What Find the Documents looks through, from a context menu and from the menu bar.
    func testFindDocumentsScope() {
        // A context menu: several selected and the clicked one among them → all of them.
        XCTAssertEqual(FindDocumentsScope.forClick(on: "b", isFolder: false, selection: ["a", "b"]), ["a", "b"])
        // The clicked one outside the selection → only it, when it is a folder; a lone page → nothing.
        XCTAssertEqual(FindDocumentsScope.forClick(on: "f", isFolder: true, selection: ["a", "b"]), ["f"])
        XCTAssertEqual(FindDocumentsScope.forClick(on: "p", isFolder: false, selection: ["p"]), [])

        let folders: Set<String> = ["f", "shown"]
        let isFolder = { (id: String) in folders.contains(id) }
        // The menu bar: several selected → all; one folder → it; one page → nothing.
        XCTAssertEqual(FindDocumentsScope.forSelection(["a", "b"], shownFolderId: "shown", isFolder: isFolder), ["a", "b"])
        XCTAssertEqual(FindDocumentsScope.forSelection(["f"], shownFolderId: "shown", isFolder: isFolder), ["f"])
        XCTAssertEqual(FindDocumentsScope.forSelection(["p"], shownFolderId: "shown", isFolder: isFolder), [])
        // Nothing selected → the folder the window shows, if it is one.
        XCTAssertEqual(FindDocumentsScope.forSelection([], shownFolderId: "shown", isFolder: isFolder), ["shown"])
        XCTAssertEqual(FindDocumentsScope.forSelection([], shownFolderId: "p", isFolder: isFolder), [])
        XCTAssertEqual(FindDocumentsScope.forSelection([], shownFolderId: nil, isFolder: isFolder), [])
    }

    /// Start says why it cannot act; a plan not read yet is not a reason (the press reads it).
    func testStartSaysWhyItCannotAct() {
        XCTAssertEqual(
            FocusedStartRecipeButton.disabledReason(hasProject: false, plan: nil),
            "Open a project to start its recipe"
        )
        XCTAssertNil(FocusedStartRecipeButton.disabledReason(hasProject: true, plan: nil))
    }

    func testRenameShortcutIsDeclaredOnlyOnTheFocusedButton() throws {
        let appSource = try Self.appSource("FicheroApp.swift")
        XCTAssertTrue(appSource.contains("FocusedRenameButton()"))
        XCTAssertFalse(appSource.contains("FocusedRenameButton()\n                    .keyboardShortcut(.return, modifiers: [])"))
    }

    /// The labels a person reads: the first string literal of each `Button(`, `Text(`, `Label(` and
    /// `Menu(` call.
    private static func quotedLabels(in source: String) throws -> [String] {
        let pattern = try NSRegularExpression(pattern: #"\b(?:Button|Text|Label|Menu)\(\s*"([^"]*)""#)
        let range = NSRange(source.startIndex..<source.endIndex, in: source)
        return pattern.matches(in: source, range: range).compactMap { match in
            Range(match.range(at: 1), in: source).map { String(source[$0]) }
        }
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let baseURL = try AppSource.root()
        return try String(contentsOf: baseURL.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
