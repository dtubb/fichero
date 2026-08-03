@testable import Fichero
import XCTest

/// #4494: a workflow that pins its own provider/model ignores any per-run
/// override, so the Run Workflow menu must not offer one. Offering it is a
/// lie about what the run will do — the user picks a model, the engine
/// discards it, and nothing says so.
final class RunWorkflowSubmenuOverrideTests: XCTestCase {

    // MARK: - The decision the menu branches on

    func testFlagFalseMeansNoOverride() {
        let workflow = WorkflowSidebarItem(name: "Pinned", acceptsModelOverride: false)
        XCTAssertFalse(workflow.canOverrideModel)
    }

    func testFlagTrueMeansOverride() {
        let workflow = WorkflowSidebarItem(name: "Open", acceptsModelOverride: true)
        XCTAssertTrue(workflow.canOverrideModel)
    }

    /// Unknown fails OPEN. Losing a control the user had is worse than
    /// offering one the engine may ignore, and the engine stays the
    /// enforcement point either way.
    func testUnknownFlagKeepsOverride() {
        var workflow = WorkflowSidebarItem(name: "Unknown")
        workflow.acceptsModelOverride = nil
        XCTAssertTrue(workflow.canOverrideModel)
    }

    /// The flag must survive the sidebar item's own Codable round-trip under
    /// the wire key — the store persists these, and a dropped key would
    /// resurrect the submenu on the next load.
    func testFlagRoundTripsUnderWireKey() throws {
        let workflow = WorkflowSidebarItem(name: "Pinned", acceptsModelOverride: false)
        let data = try JSONEncoder().encode(workflow)
        let dict = try XCTUnwrap(
            JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        XCTAssertEqual(dict["accepts_model_override"] as? Bool, false)

        let decoded = try JSONDecoder().decode(WorkflowSidebarItem.self, from: data)
        XCTAssertFalse(decoded.canOverrideModel)
    }

    // MARK: - What the menu renders for each branch

    /// SwiftUI bodies are not inspectable here, so this asserts the branch
    /// structure at the source level. It fails if the flag is ignored — the
    /// `if workflow.canOverrideModel` split is what makes the assertions
    /// below distinguishable, so deleting it fails every one of them rather
    /// than quietly passing on the true-branch default.
    func testMenuBranchesOnTheFlag() throws {
        let source = try Self.submenuSource()

        let branch = try XCTUnwrap(
            source.range(of: "if workflow.canOverrideModel {"),
            "The Run menu must read canOverrideModel, not assume every workflow takes one."
        )
        let split = try XCTUnwrap(
            source.range(of: "} else {", range: branch.upperBound..<source.endIndex)
        )
        let overridable = String(source[branch.upperBound..<split.lowerBound])
        let pinned = String(source[split.upperBound...])

        // Flag true: the existing submenu is untouched — Default plus the
        // available providers.
        XCTAssertTrue(overridable.contains("Menu(workflow.name)"))
        XCTAssertTrue(overridable.contains("Button(\"Default\")"))
        XCTAssertTrue(overridable.contains("providerCache.providers"))

        // Flag false: a plain Button that runs the workflow's own model, and
        // NO provider entries anywhere in that branch.
        XCTAssertTrue(pinned.contains("Button(workflow.name) { action(workflow.id, nil, nil) }"))
        XCTAssertFalse(pinned.contains("providerCache"))
        XCTAssertFalse(pinned.contains("Button(\"Default\")"))
        XCTAssertFalse(pinned.contains("Menu("))
    }

    // MARK: - The store must not drop the flag on the way through

    /// Every WorkflowStore path that builds a row from a server response had
    /// been listing arguments up to `isSystem` and stopping, so `untested`,
    /// `direct_runnable` and now `accepts_model_override` silently reverted to
    /// their defaults on save, update, rename, duplicate, move and import —
    /// visible as a pinned workflow regaining its override submenu until the
    /// next full load. Asserting on every construction site rather than the
    /// six known ones so a new one cannot reintroduce the omission.
    func testEveryStoreRebuildCarriesTheFlag() throws {
        let models = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Models")

        let storeFiles = try FileManager.default
            .contentsOfDirectory(atPath: models.path)
            .filter { $0.hasPrefix("WorkflowStore") && $0.hasSuffix(".swift") }
            .sorted()
        XCTAssertFalse(storeFiles.isEmpty, "Store files moved — this guardrail would pass vacuously.")

        // Counting rather than parsing argument lists: one `acceptsModelOverride:`
        // per `WorkflowSidebarItem(` is exactly the invariant, and it cannot be
        // fooled by formatting the way brace-matching can.
        var constructions = 0
        var carried = 0
        for file in storeFiles {
            let source = try String(
                contentsOf: models.appendingPathComponent(file), encoding: .utf8
            )
            constructions += source.components(separatedBy: "WorkflowSidebarItem(").count - 1
            carried += source.components(separatedBy: "acceptsModelOverride:").count - 1
        }
        XCTAssertGreaterThanOrEqual(constructions, 6, "Expected every known store rebuild to be scanned.")
        XCTAssertEqual(
            carried, constructions,
            "A WorkflowStore path builds a WorkflowSidebarItem without acceptsModelOverride — "
            + "it will silently default to true and re-offer overrides the engine ignores."
        )
    }

    private static func submenuSource() throws -> String {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // Components
            .deletingLastPathComponent()   // Views
            .deletingLastPathComponent()   // fichero-tests
            .deletingLastPathComponent()   // fichero
            .appendingPathComponent("fichero/Views/Components/Menus/RunWorkflowSubmenuItems.swift")
        return try String(contentsOf: root, encoding: .utf8)
    }
}
