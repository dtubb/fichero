@testable import Fichero
import Foundation
import XCTest

/// Pins the prompt behaviors of `docs/contributor/specs/ui/workflow-node-config.md`
/// section B and the round-trip rule D.open-is-read-only.
final class NodePromptEditorTests: XCTestCase {

    // MARK: - Override reducer (the only thing that may write `config.prompt`)

    /// `nodeconfig.roundtrip.open-is-read-only` + `nodeconfig.prompt.default-is-ghost-not-text`
    /// — with no override there is nothing to write: an empty edit on a node with
    /// no config leaves the config absent, and on a node with config leaves
    /// `prompt` absent. Nothing in the editor's appearance path calls anything else.
    func testEmptyTextNeverWritesAPromptKey() {
        var absent: [String: AnyCodableValue]? = nil
        NodePromptOverride.apply("", to: &absent)
        XCTAssertNil(absent, "looking at a node must not create its config")

        var present: [String: AnyCodableValue]? = ["language": .string("es-ES")]
        NodePromptOverride.apply("", to: &present)
        XCTAssertEqual(present, ["language": .string("es-ES")])
        XCTAssertNil(present?["prompt"])
    }

    /// `nodeconfig.prompt.edit-writes-override` — a real edit writes the override;
    /// clearing it removes the key so the server default applies again.
    func testEditWritesOverrideAndClearRemovesIt() {
        var config: [String: AnyCodableValue]? = nil
        NodePromptOverride.apply("Read the marginalia too.", to: &config)
        XCTAssertEqual(config?["prompt"], .string("Read the marginalia too."))
        XCTAssertEqual(NodePromptOverride.current(in: config), "Read the marginalia too.")

        NodePromptOverride.apply("", to: &config)
        XCTAssertNil(config?["prompt"])
        XCTAssertEqual(NodePromptOverride.current(in: config), "")
    }

    // MARK: - Ghost placeholder

    /// `nodeconfig.prompt.shows-effective-prompt` — the ghost is the prompt the
    /// run would send for the CURRENT config (backend-assembled) when available.
    func testGhostPrefersBackendAssembledPrompt() {
        XCTAssertEqual(
            NodePromptOverride.ghost(backend: "Transcribe in Spanish.", registry: "Transcribe."),
            "Transcribe in Spanish."
        )
    }

    /// `nodeconfig.prompt.visible-before-registry` — before the backend answers
    /// (or when it cannot), the registry default is shown; an empty string from
    /// either source is NOT a prompt and yields no ghost rather than a blank one.
    func testGhostFallsBackToRegistryAndTreatsEmptyAsAbsent() {
        XCTAssertEqual(NodePromptOverride.ghost(backend: nil, registry: "Transcribe."), "Transcribe.")
        XCTAssertEqual(NodePromptOverride.ghost(backend: "", registry: "Transcribe."), "Transcribe.")
        XCTAssertNil(NodePromptOverride.ghost(backend: nil, registry: nil))
        XCTAssertNil(NodePromptOverride.ghost(backend: "", registry: ""))
    }

    // MARK: - What the backend prompt is built from

    /// `nodeconfig.prompt.shows-effective-prompt` — the ghost must be the DEFAULT
    /// for this config, so the node's own `prompt` override is never sent when
    /// asking the server what the default would be; every other key is.
    func testDefaultPromptInputsExcludeTheOverrideOnly() {
        let node = WorkflowNode(
            tool: "transcribe",
            config: [
                "language": .string("es-ES"),
                "return_boxes": .bool(true),
                "prompt": .string("my override")
            ]
        )
        XCTAssertEqual(
            node.promptInputsConfig,
            ["language": .string("es-ES"), "return_boxes": .bool(true)]
        )
        let dict = node.defaultPromptConfigDict
        XCTAssertNil(dict["prompt"])
        XCTAssertEqual(dict["language"] as? String, "es-ES")
        XCTAssertEqual(dict["return_boxes"] as? Bool, true)
    }

    // MARK: - Source gates: one editor, no appear-time copy, backend prompt actually fetched

    private static func source(_ relative: String) throws -> String {
        let url = try AppSource.root().appendingPathComponent(relative)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// `nodeconfig.prompt.one-editor-component` + `nodeconfig.prompt.default-is-ghost-not-text`
    /// — the three hand-rolled editors are gone: each prompt-bearing config view
    /// composes `NodePromptEditor` and keeps no `promptText` state to copy a
    /// default into (the mechanism that pinned a stale default as an override).
    func testPromptBearingConfigsUseTheOneEditorAndKeepNoPromptState() throws {
        for file in [
            "Views/Workflow/Nodes/NodeConfigs/TranscribeNodeConfig.swift",
            "Views/Workflow/Nodes/NodeConfigs/DescribeNodeConfig.swift",
            "Views/Workflow/Nodes/NodeConfigs/SummarizeFileNodeConfig.swift"
        ] {
            let source = try Self.source(file)
            XCTAssertTrue(source.contains("NodePromptEditor("), file)
            XCTAssertFalse(source.contains("promptText"), "\(file) must not copy a default into state")
            XCTAssertFalse(source.contains("config?[\"prompt\"] = "), "\(file) must not write prompt itself")
        }
    }

    /// `nodeconfig.prompt.shows-effective-prompt` — the popover FETCHES the
    /// backend prompt (the field used to be declared and never assigned).
    func testPopoverFetchesBackendPrompt() throws {
        let source = try Self.source("Views/Workflow/Nodes/NodePopover.swift")
        XCTAssertTrue(source.contains("backendPrompt = "), "backendPrompt must be assigned")
        XCTAssertTrue(source.contains("getToolPrompt("), "popover must ask the server for the effective prompt")
        XCTAssertTrue(source.contains("defaultPromptConfigDict"), "…built from the config minus the override")
    }
}
