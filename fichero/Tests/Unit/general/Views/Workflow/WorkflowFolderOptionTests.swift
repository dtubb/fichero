@testable import Fichero
import XCTest

/// The folder picker of the Collection node and of the schema-driven Folder
/// tool: one shared tree, with each folder listed once.
/// spec: workflow-node-config `nodeconfig.fields.collection.folder-picker`,
/// `nodeconfig.fields.folder-picker.one-row-per-folder`.
final class WorkflowFolderOptionTests: XCTestCase {

    private func folder(_ id: String, _ name: String, parent: String? = nil) -> Document {
        Document(id: id, parentId: parent, docType: .folder, name: name)
    }

    func testInboxComesFirstThenRootsByNameWithChildrenIndented() {
        let documents = [
            folder("z", "Zebra"),
            folder("a", "Alpha"),
            folder("a1", "Letters", parent: "a"),
            folder("in", "Inbox"),
            Document(id: "page", parentId: "a", docType: .file, name: "0970.jpg")
        ]

        let options = WorkflowFolderOption.tree(from: documents)

        XCTAssertEqual(options.map(\.id), ["in", "a", "a1", "z"])
        XCTAssertEqual(options.map(\.depth), [0, 0, 1, 0])
        XCTAssertEqual(options[2].indentedName, "  Letters")
    }

    func testAFolderListedTwiceIsOneRow() {
        // The store's list can hold a folder twice; the Collection node built a
        // dictionary with `uniqueKeysWithValues` from these rows, which traps on
        // a repeated id.
        let documents = [folder("a", "Alpha"), folder("a", "Alpha"), folder("a1", "Letters", parent: "a")]

        let options = WorkflowFolderOption.tree(from: documents)

        XCTAssertEqual(options.map(\.id), ["a", "a1"])
    }

    /// The Collection node asks the shared rows whether its folder still
    /// exists; it keeps no id-keyed dictionary of its own.
    func testTheCollectionNodeKeepsNoDictionaryOfItsOwn() throws {
        let url = try AppSource.root()
            .appendingPathComponent("Views/Workflow/Nodes/NodeConfigs/CollectionNodeConfig.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertFalse(source.contains("uniqueKeysWithValues"))
        XCTAssertTrue(source.contains("WorkflowFolderOption.tree(from:"))
    }
}
