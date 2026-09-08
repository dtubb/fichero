@testable import Fichero
import FicheroAPIClient
import Foundation
import XCTest

/// Pins the cross-surface invariant from `docs/contributor/specs/workflow-node-config.md`:
/// the node popover's model picker lists EXACTLY what AI Settings lists for a
/// provider — the user-configured models, labelled by their configured name.
/// HARD GATE (Testing Constitution): a drift here reintroduces the runtime-404
/// class Settings was fixed to prevent (catalog models the provider's API does
/// not serve).
final class NodeModelListParityTests: XCTestCase {

    private static func row(_ modelId: String, name: String, caps: [String] = ["text"]) -> Components.Schemas.UserModelResponse {
        .init(
            id: "row-\(modelId)",
            providerId: "prov-1",
            name: name,
            modelId: modelId,
            capabilities: caps,
            isDefault: false,
            enabled: true,
            inputCost: nil,
            outputCost: nil
        )
    }

    /// `nodeconfig.model.same-list-as-settings` + `nodeconfig.model.same-labels-as-settings`
    /// — one mapping from a configured-model row to a picker choice; the popover
    /// path and the Settings path must produce identical choices for the same rows.
    func testPopoverChoicesEqualSettingsChoicesForSameConfiguredRows() {
        let rows = [
            Self.row("gpt-4o", name: "GPT-4o", caps: ["text", "vision"]),
            Self.row("gpt-4o-mini", name: "GPT-4o mini"),
            Self.row("qwen2.5-vl-7b", name: "Qwen 2.5 VL 7B", caps: [])
        ]

        // Popover path (NodePopover+Comparison.loadProviders).
        let popover = ModelPicker.ModelChoice.configured(rows)

        // Settings path (AISettingsView.settingsModelPicker): rows → ModelInfo → choice by fullName.
        let settings = AISettingsView.configuredModelInfos(from: rows, providerType: "openai")
            .map { ModelPicker.ModelChoice.configured(modelId: $0.modelId, label: $0.fullName) }

        XCTAssertEqual(popover, settings)
        XCTAssertEqual(popover.map(\.id), ["gpt-4o", "gpt-4o-mini", "qwen2.5-vl-7b"])
        // Labels are the configured NAME, never the raw id.
        XCTAssertEqual(popover.map(\.name), ["GPT-4o", "GPT-4o mini", "Qwen 2.5 VL 7B"])
    }

    /// `nodeconfig.model.same-list-as-settings` — a provider with no configured
    /// models offers nothing in the popover, exactly as in Settings.
    func testNoConfiguredRowsMeansNoChoices() {
        XCTAssertTrue(ModelPicker.ModelChoice.configured([]).isEmpty)
    }

    /// `nodeconfig.model.same-list-as-settings` — source gate: the popover loads
    /// the user-configured list (`listProviderModels(providerId:)`), not the
    /// catalog (`listAvailableModels(providerType:)`), and never labels by raw id.
    func testPopoverLoadsConfiguredModelsNotCatalog() throws {
        let url = try AppSource.root()
            .appendingPathComponent("Views/Workflow/Nodes/NodePopover+Comparison.swift")
        let source = try String(contentsOf: url, encoding: .utf8)

        XCTAssertTrue(source.contains("listProviderModels(providerId:"),
                      "popover must load the same configured-model list Settings shows")
        XCTAssertFalse(source.contains("listAvailableModels("),
                       "popover must not offer catalog models Settings withholds")
        XCTAssertTrue(source.contains("ModelPicker.ModelChoice.configured("),
                      "popover must use the one shared row→choice mapping")
        XCTAssertFalse(source.contains("name: $0.modelId"),
                       "labels come from the configured name, as in Settings")
    }

    /// `nodeconfig.model.same-labels-as-settings` — source gate on the Settings
    /// side: it goes through the same shared mapping, so neither surface can
    /// drift its label rule alone.
    func testSettingsUsesSharedMapping() throws {
        let url = try AppSource.root()
            .appendingPathComponent("Views/Settings/AI/AISettingsView+Helpers.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(source.contains("ModelPicker.ModelChoice.configured("))
    }
}
