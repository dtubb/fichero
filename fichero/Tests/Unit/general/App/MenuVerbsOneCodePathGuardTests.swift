import Foundation
@testable import Fichero
import Testing

/// #5652: the menu verbs that every surface renders as ONE item (Activity's Stop and Read Again, a trained model's
/// Make Available in Every Project) reach the engine from ONE place: the shared target. These are absence and
/// uniqueness scans over the whole app tree, because "no other view calls the store for it" is a claim about every
/// file at once; what each item does is the behaviour tests' (`ActivityRunMenuTests`, `ProjectTrainMenuTests`,
/// `TrainedModelNodeActionsTests`).
@Suite("Menu verbs keep one code path (#5652)")
struct MenuVerbsOneCodePathGuardTests {
    private static let activityItems = "App/Menus/FocusedCommands/FocusedCommandButtons+Activity.swift"
    private static let trainItems = "App/Menus/FocusedCommands/FocusedCommandButtons+Train.swift"

    /// Every app source file, by its path under the app root, with its text.
    private static func appFiles() throws -> [(path: String, text: String)] {
        let root = try AppSource.root().standardizedFileURL
        guard let walker = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil) else { return [] }
        var files: [(String, String)] = []
        for case let url as URL in walker where url.pathExtension == "swift" {
            let path = String(url.standardizedFileURL.path.dropFirst(root.path.count + 1))
            files.append((path, try String(contentsOf: url, encoding: .utf8)))
        }
        // Blind, not clean: a walk that found next to nothing read the wrong tree.
        #expect(files.count > 500, "read only \(files.count) app files from \(root.path)")
        return files
    }

    /// The files that contain `pattern`, outside the store that defines the call.
    private static func callers(of pattern: String, definedIn store: String) throws -> Set<String> {
        Set(try appFiles().filter { $0.path != store && $0.text.contains(pattern) }.map(\.path))
    }

    @Test("only the shared Activity target asks the store to stop a job or read pages again")
    func activityVerbsHaveOneCaller() throws {
        #expect(try Self.callers(of: "readPagesAgain(runThreadId", definedIn: "Models/ActivityStore.swift")
            == [Self.activityItems])
        #expect(try Self.callers(of: "cancelJob(jobId", definedIn: "Models/ActivityStore.swift")
            == [Self.activityItems])
    }

    @Test("only the shared model target makes a model available in every project")
    func makeGlobalHasOneCaller() throws {
        #expect(try Self.callers(of: "makeAvailableEverywhere(", definedIn: "Models/TrainedModelsStore.swift")
            == [Self.trainItems])
        #expect(try Self.callers(of: "makeGlobal(model", definedIn: "Models/TrainedModelsStore.swift").isEmpty)
    }

    @Test("no Activity view draws a Stop or Read Again button of its own")
    func noHandMadeActivityButtons() throws {
        let activityViews = try Self.appFiles().filter { $0.path.hasPrefix("Views/Activity/") }
        #expect(!activityViews.isEmpty)
        for file in activityViews {
            #expect(!file.text.contains("Button(\"Stop\")"), "\(file.path) draws its own Stop")
            #expect(!file.text.contains("Button(offer)"), "\(file.path) draws its own Read Again")
        }
    }

    /// #5652 slice 4, group 1: the item verbs' words are spelled once, in the shared items, so a context menu cannot
    /// grow a second Bookmark… or Exclude that drifts from Edit's. Exclude still has two surfaces not yet on the shared
    /// item (the dataset rows' menu and the Inspector's header, later groups): a shrinking allowlist.
    @Test("the item verbs' words are spelled only in the shared items")
    func itemVerbWordsLiveInOnePlace() throws {
        let shared = "App/Menus/FocusedCommands/FocusedCommandButtons+ItemVerbs.swift"
        let files = try Self.appFiles()
        func spelling(_ word: String) -> Set<String> {
            Set(files.filter { $0.text.contains("\"\(word)\"") }.map(\.path))
        }
        for word in ["Bookmark…", "Add to Workspace…", "Export a Copy…", "Exclude Everywhere", "Include in Search"] {
            #expect(spelling(word) == [shared], "\(word) is spelled outside the shared items")
        }
        #expect(spelling("Exclude from Processing") == [
            shared, "Views/Library/ViewModes/Dataset/DatasetRowMenu.swift",
            "Views/Inspector/Source/Info/DocumentInspectorInfoTab+Header.swift",
        ])
        #expect(spelling("Group as Stack").isEmpty, "Group is one item, named Group")
    }

    @Test("the shared Activity and Train items take no chord")
    func noChordsOnTheSharedItems() throws {
        for path in [Self.activityItems, Self.trainItems] {
            let text = try String(contentsOf: AppSource.root().appendingPathComponent(path), encoding: .utf8)
            #expect(!text.contains(".keyboardShortcut"), "\(path) mints a chord")
        }
    }
}
