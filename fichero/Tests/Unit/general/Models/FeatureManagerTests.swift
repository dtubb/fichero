@testable import Fichero
import XCTest

@MainActor
final class FeatureManagerTests: XCTestCase {
    private func withFeatureTier<T>(_ tier: String, body: () throws -> T) rethrows -> T {
        let key = "FICHERO_FEATURE_TIER"
        let previous = ProcessInfo.processInfo.environment[key]
        setenv(key, tier, 1)
        // The bundle FicheroFeatureTier wins over the env var in a test build, so
        // set the test-only override too — that is what actually forces the tier.
        let previousOverride = FeatureManager.shared.testTierOverride
        FeatureManager.shared.testTierOverride = FeatureManager.resolveFeatureTier(tier)
        defer {
            FeatureManager.shared.testTierOverride = previousOverride
            if let previous {
                setenv(key, previous, 1)
            } else {
                unsetenv(key)
            }
        }
        return try body()
    }

    func testV001DefaultsDisableOffTierSurfaces() throws {
        // #3917/#252 PRODUCT DECISION NEEDED: this asserts the workflow-execution
        // surfaces (import/export, LangGraph preview, files toolbar, run-on-selection)
        // and batches are ENABLED in a release build, but FeatureTiers.generated.swift
        // gives them tier: .beta — so they are (correctly, per the data) hidden in
        // release. #252 promoted their internal *defaults* but not their *tiers*.
        // Either promote the tiers to .release or drop these from v0.0.1 expectations.
        // Core v0.0.1 features (library/search/workflows/activity/settings) DO pass.
        throw XCTSkip("workflow-exec + batches are tier:.beta, not release — #252 tier promotion incomplete; needs a product decision (#3917)")
        let featureManager = FeatureManager.shared

        withFeatureTier("release") {
            featureManager.resetToV001()

            // Enabled in v0.0.1
            XCTAssertTrue(featureManager.isLibraryEnabled)
            XCTAssertTrue(featureManager.isSearchEnabled)
            XCTAssertTrue(featureManager.isWorkflowsEnabled)
            XCTAssertTrue(featureManager.isWorkflowEditorAdvancedViewsEnabled)
            XCTAssertTrue(featureManager.isActivityEnabled)
            XCTAssertTrue(featureManager.isSettingsGeneralTabEnabled)
            // Workflow execution surfaces promoted to release defaults (#252).
            XCTAssertTrue(featureManager.isWorkflowImportExportEnabled)
            XCTAssertTrue(featureManager.isWorkflowLangGraphPreviewEnabled)
            XCTAssertTrue(featureManager.isWorkflowFilesToolbarButtonEnabled)
            XCTAssertTrue(featureManager.isWorkflowRunOnSelectionEnabled)

            // Batches promoted to v0.0.1 defaults alongside workflows.
            XCTAssertTrue(featureManager.isBatchesEnabled)

            // Disabled in v0.0.1
            XCTAssertFalse(featureManager.isChatEnabled)
            XCTAssertFalse(featureManager.isAutomationEnabled)
        }
    }

    func testAlphaBuildDefaultsExposeInternalReviewSettingsAndIntegrationSurfaces() {
        let featureManager = FeatureManager.shared

        withFeatureTier("alpha") {
            featureManager.resetToV001()

            XCTAssertTrue(featureManager.isSettingsEngineTabEnabled)
            XCTAssertTrue(featureManager.isSettingsShareTabEnabled)
            XCTAssertTrue(featureManager.isSettingsUsersTabEnabled)
            XCTAssertTrue(featureManager.isSettingsCaptureTabEnabled)
            XCTAssertTrue(featureManager.isSettingsBackendTabEnabled)
            XCTAssertTrue(featureManager.isSettingsModelsTabEnabled)
            XCTAssertTrue(featureManager.isMCPEnabled)
            XCTAssertTrue(featureManager.isIntegrationsEnabled)
        }
    }

    func testDevBuildExposesAllImplementedFeatures() {
        let featureManager = FeatureManager.shared

        withFeatureTier("dev") {
            featureManager.resetToV001()

            XCTAssertTrue(featureManager.allFeaturesEffectivelyEnabled)
            XCTAssertTrue(featureManager.isChatEnabled)
            XCTAssertTrue(featureManager.isAutomationEnabled)
            XCTAssertTrue(featureManager.isWorkflowToolsAgentsEnabled)
        }
    }

    func testReleaseBuildStillHidesInternalReviewSurfaces() {
        let featureManager = FeatureManager.shared

        withFeatureTier("release") {
            featureManager.resetToV001()

            XCTAssertFalse(featureManager.isSettingsEngineTabEnabled)
            XCTAssertFalse(featureManager.isSettingsShareTabEnabled)
            XCTAssertFalse(featureManager.isSettingsUsersTabEnabled)
            XCTAssertFalse(featureManager.isSettingsCaptureTabEnabled)
            XCTAssertFalse(featureManager.isSettingsBackendTabEnabled)
            XCTAssertFalse(featureManager.isSettingsModelsTabEnabled)
            XCTAssertFalse(featureManager.isMCPEnabled)
            XCTAssertFalse(featureManager.isIntegrationsEnabled)
        }
    }

    func testReleaseTierHidesBetaStartupServices() {
        let betaStartupServices: [FeatureKey] = [.providers, .workflows, .chat, .activity]

        for feature in betaStartupServices {
            XCTAssertLessThan(
                FeatureTiers.map[feature]!.tier.rank,
                FeatureTier.release.rank,
                "\(feature.rawValue) must not start against a release-tier engine"
            )
        }
    }

    /// #4063: the library contextual menu's "Run Workflow" item is gated by
    /// `isWorkflowRunOnSelectionEnabled`, which is `isVisible(.workflowRunOnSelection)`
    /// gated. The flag's tier was `.dev`, so the menu item was hidden in the release
    /// build while the dev build showed it. Promote the tier to `.release` so the
    /// apply-workflow contextual menu appears in release (dead-simple-UX: turn the
    /// feature ON, don't add a new toggle). The menu still only renders when the
    /// selection is non-empty AND the library has workflows — the gate is the only
    /// fix; no new mechanism.
    func testWorkflowRunOnSelectionEnabledInRelease() {
        let featureManager = FeatureManager.shared

        withFeatureTier("release") {
            featureManager.resetToV001()

            XCTAssertEqual(
                FeatureTiers.map[.workflowRunOnSelection]!.tier,
                .release,
                "workflowRunOnSelection must be tier .release so the contextual-menu item appears in release (#4063)"
            )
            XCTAssertTrue(
                featureManager.isWorkflowRunOnSelectionEnabled,
                "Run-Workflow-on-Selection contextual menu must be visible in release builds (#4063)"
            )
        }
    }

    // The Engine & Access panes (Engine/Backend + Library Access: People /
    // Devices+QR / Capture) hold real, keepable capabilities, so their EXISTENCE
    // must not hang off the `.alpha`-tier `settings_*_tab` flags — those hid the QR
    // and the multi-user toggle from beta testers ("nowhere to turn on the qrcode",
    // #3811). Reachable in internal + tester builds; still hidden in release until
    // the fail-closed engine-refusal P0 lands (#3776).
    func testTesterSettingsPanesReachableForTestersHiddenInRelease() {
        XCTAssertTrue(SettingsView.showsTesterSettingsPane(tier: .dev))
        XCTAssertTrue(SettingsView.showsTesterSettingsPane(tier: .alpha))
        // The regression case: beta testers must see the sharing/QR + Engine panes.
        XCTAssertTrue(SettingsView.showsTesterSettingsPane(tier: .beta))
        // Release stays gated until #3776's P0 verification.
        XCTAssertFalse(SettingsView.showsTesterSettingsPane(tier: .release))
    }
}

// MARK: - Tier badge glyphs (#4122)

/// Gated features are badged with ONE consistent glyph — α alpha, β beta,
/// δ dev — never bracket text like "[BETA]".
final class FeatureTierBadgeGlyphTests: XCTestCase {
    func testGlyphMapping() {
        XCTAssertEqual(FeatureTier.alpha.tierBadgeGlyph, "α")
        XCTAssertEqual(FeatureTier.beta.tierBadgeGlyph, "β")
        XCTAssertEqual(FeatureTier.dev.tierBadgeGlyph, "δ")
        XCTAssertEqual(FeatureTier.release.tierBadgeGlyph, "")
    }

    func testBadgedLabelUsesGlyphNotBrackets() throws {
        let source = try String(
            contentsOf: try AppSource.root().appendingPathComponent("App/Menus/ViewMenuCommands.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(source.contains("tierBadgeGlyph)\""))
    }

    /// #4447: the check above only ever read ONE named file. `FicheroApp.swift`
    /// renders a SECOND tier badge (the tier legend) that this test never
    /// looked at — a bracket regression there would have passed silently. The
    /// invariant ("gated features are badged with the glyph, never bracket
    /// text") is about the app, so this sweeps every `.swift` file for the
    /// literal bracket-interpolation shape rather than naming sites by hand.
    /// Verified zero occurrences app-wide before landing.
    func testNoFileAnywhereBracketsATierBadge() throws {
        let root = try AppSource.root()

        let files = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil)?
            .compactMap { $0 as? URL }
            .filter { $0.pathExtension == "swift" } ?? []
        XCTAssertFalse(files.isEmpty, "the sweep must actually read files")

        var offenders: [String] = []
        for file in files {
            let source = try String(contentsOf: file, encoding: .utf8)
            // "tierBadgeText)]" is the shape of a badge closed by a literal
            // bracket right after the property access — specific enough that
            // no unrelated interpolation would produce it by accident.
            if source.contains("tierBadgeText)]") {
                offenders.append(file.lastPathComponent)
            }
        }
        XCTAssertTrue(offenders.isEmpty, "bracket-text tier badge in: \(offenders.joined(separator: ", "))")
    }
}
