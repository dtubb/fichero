import Foundation
import OSLog

/// Diagnostics for the build-tier resolution below. Its own logger rather than
/// a shared one: the single message it emits is a build-configuration failure,
/// and it should be findable without reading everything else the app logs.
let featureTierLogger = Logger(subsystem: "app.fichero.fichero", category: "FeatureTier")

// MARK: - Feature Visibility & Gating

/// Computed feature-flag accessors for `FeatureManager`. Split out of the main class body
/// (issue #3743) — these read the persisted, tier-gated stored flags declared there and stay
/// pure computed properties/methods, so they can live in a plain `extension`.
extension FeatureManager {
    /// One-shot guard for `reportUnresolvableTierOnce`. `FeatureManager` is
    /// `@MainActor`, so this static inherits that isolation and needs no lock.
    static var hasReportedUnresolvableTier = false

    /// Development builds deliberately expose every implemented feature.
    var allFeaturesEffectivelyEnabled: Bool {
        allFeaturesEnabled || activeBuildTier == .dev
    }

    /// The feature tier this build runs at.
    ///
    /// **Fails CLOSED.** An unresolvable tier returns `.release` — the
    /// NARROWEST surface — not `.dev`.
    ///
    /// The direction is the whole point. This used to fall back to `.dev`,
    /// which meant "I could not determine the tier, so assume maximum
    /// privilege" — the inverse of every other safety decision here:
    /// loopback-only transport, the canvas's strict-when-unloaded conversion
    /// table, the engine refusing a zero-resolution run. A configuration
    /// failure should not be the thing that unlocks features.
    ///
    /// It is also unreachable in practice, which is why changing it is safe
    /// rather than merely principled: all 16 build configurations in
    /// `project.pbxproj` define `FICHERO_FEATURE_TIER` (4 × each of dev /
    /// alpha / beta / release), `Info.plist` substitutes it, and the test
    /// bundle is hosted in `Fichero.app` — so `Bundle.main` carries a
    /// resolvable value in shipped builds, dev builds and test runs alike.
    ///
    /// So this returning at all means something is wrong with the build, and
    /// it says so once rather than silently choosing. Silently choosing a tier
    /// is how nobody notices.
    var activeBuildTier: FeatureTier {
        if let testTierOverride {
            return testTierOverride
        }
        if let tier = Self.resolveFeatureTier(
            Bundle.main.infoDictionary?["FicheroFeatureTier"] as? String
        ) {
            return tier
        }
        if let tier = Self.resolveFeatureTier(
            ProcessInfo.processInfo.environment["FICHERO_FEATURE_TIER"]
        ) {
            return tier
        }
        Self.reportUnresolvableTierOnce()
        return .release
    }

    /// Log the unresolvable tier exactly once.
    ///
    /// `activeBuildTier` is a computed property read on many render paths, so
    /// an unguarded log would emit thousands of identical lines and bury
    /// itself — a diagnostic nobody can read is the silence it was meant to
    /// replace.
    static func reportUnresolvableTierOnce() {
        guard !hasReportedUnresolvableTier else { return }
        hasReportedUnresolvableTier = true
        featureTierLogger.error(
            """
            Build tier unresolvable: neither Info.plist FicheroFeatureTier nor \
            FICHERO_FEATURE_TIER resolved. Falling back to .release (narrowest \
            surface). Every build configuration should define \
            FICHERO_FEATURE_TIER — if you are seeing this, the build settings \
            or Info.plist substitution is broken, not the app.
            """
        )
    }

    @available(*, deprecated, message: "use activeBuildTier == .dev")
    static var isDevFeatureTier: Bool { shared.activeBuildTier == .dev }

    func isVisible(_ key: FeatureKey) -> Bool {
        FeatureTiers.map[key]!.tier.rank >= activeBuildTier.rank
    }

    private func isEnabled(_ key: FeatureKey, _ enabled: Bool) -> Bool {
        isVisible(key) && (allFeaturesEffectivelyEnabled || enabled)
    }

    var isWorkflowsEnabled: Bool { isEnabled(.workflows, workflowsEnabledInternal) }
    var isSearchEnabled: Bool { isEnabled(.search, searchEnabledInternal) }
    var isWorkflowEditorAdvancedViewsEnabled: Bool {
        isEnabled(.workflowEditorAdvancedViews, workflowEditorAdvancedViewsEnabled)
    }
    var isWorkflowChainsEnabled: Bool { isEnabled(.workflowChains, workflowChainsEnabledInternal) }
    var isBatchesEnabled: Bool { isEnabled(.batches, batchesEnabledInternal) }
    var isChatEnabled: Bool { isEnabled(.chat, chatEnabledInternal) }
    var isAgentsEnabled: Bool { isEnabled(.agents, agentsEnabledInternal) }
    var isAutomationEnabled: Bool { isEnabled(.automation, automationEnabledInternal) }
    var isMCPEnabled: Bool { isEnabled(.mcpUi, mcpEnabledInternal) }
    var isIntegrationsEnabled: Bool { isEnabled(.integrations, integrationsEnabledInternal) }
    var isActivityEnabled: Bool { isEnabled(.activity, activityEnabledInternal) }
    var isLibraryAdvancedViewsEnabled: Bool {
        isEnabled(.libraryAdvancedViews, libraryAdvancedViewsEnabledInternal)
    }
    var isSearchAdvancedViewsEnabled: Bool {
        isEnabled(.searchAdvancedViews, searchAdvancedViewsEnabledInternal)
    }
    var isLibrarySearchSplitLayoutsEnabled: Bool {
        isEnabled(.librarySearchSplitLayouts, librarySearchSplitLayoutsEnabledInternal)
    }
    var isLibraryFilterToolbarEnabled: Bool {
        isEnabled(.libraryFilterToolbar, libraryFilterToolbarEnabledInternal)
    }
    var isLibraryIconZoomControlsEnabled: Bool {
        isEnabled(.libraryIconZoomControls, libraryIconZoomControlsEnabledInternal)
    }
    var isSettingsGeneralTabEnabled: Bool {
        isEnabled(.settingsGeneralTab, settingsGeneralTabEnabledInternal)
    }
    var isSettingsBackendTabEnabled: Bool {
        isEnabled(.settingsBackendTab, settingsBackendTabEnabledInternal)
    }
    var isSettingsModelsTabEnabled: Bool {
        isEnabled(.settingsModelsTab, settingsModelsTabEnabledInternal)
    }
    var isSettingsEngineTabEnabled: Bool {
        isEnabled(.settingsEngineTab, settingsEngineTabEnabledInternal)
    }
    var isSettingsShareTabEnabled: Bool {
        isEnabled(.settingsShareTab, settingsShareTabEnabledInternal)
    }
    var isSettingsUsersTabEnabled: Bool {
        isEnabled(.settingsUsersTab, settingsUsersTabEnabledInternal)
    }
    var isSettingsCaptureTabEnabled: Bool {
        isEnabled(.settingsCaptureTab, settingsCaptureTabEnabledInternal)
    }
    var isWorkflowToolsMCPEnabled: Bool {
        isEnabled(.workflowToolsMcp, workflowToolsMCPEnabledInternal)
    }
    var isWorkflowToolsAgentsEnabled: Bool {
        isEnabled(.workflowToolsAgents, workflowToolsAgentsEnabledInternal)
    }
    var isWorkflowToolsAudioEnabled: Bool {
        isEnabled(.workflowToolsAudio, workflowToolsAudioEnabledInternal)
    }
    var isWorkflowToolsVideoEnabled: Bool {
        isEnabled(.workflowToolsVideo, workflowToolsVideoEnabledInternal)
    }
    var isWorkflowToolsTransformEnabled: Bool {
        isEnabled(.workflowToolsTransform, workflowToolsTransformEnabledInternal)
    }
    var isWorkflowToolsConvertEnabled: Bool {
        isEnabled(.workflowToolsConvert, workflowToolsConvertEnabledInternal)
    }
    var isWorkflowToolsLogicEnabled: Bool {
        isEnabled(.workflowToolsLogic, workflowToolsLogicEnabledInternal)
    }
    var isWorkflowToolsOutputsEnabled: Bool {
        isEnabled(.workflowToolsOutputs, workflowToolsOutputsEnabledInternal)
    }
    var isWorkflowToolsFilesEnabled: Bool {
        isEnabled(.workflowToolsFiles, workflowToolsFilesEnabledInternal)
    }
    var isWorkflowToolsSearchEnabled: Bool {
        isEnabled(.workflowToolsSearch, workflowToolsSearchEnabledInternal)
    }
    var isProvidersExtendedEnabled: Bool {
        isEnabled(.providersExtended, providersExtendedEnabledInternal)
    }
    var isProvidersEnabled: Bool {
        isVisible(.providers)
            && (allFeaturesEnabled || providersExtendedEnabledInternal || activeBuildTier == .dev)
    }
    var isWorkflowImportExportEnabled: Bool {
        isEnabled(.workflowImportExport, workflowImportExportEnabledInternal)
    }
    var isWorkflowLangGraphPreviewEnabled: Bool {
        isEnabled(.workflowLangGraphPreview, workflowLangGraphPreviewEnabledInternal)
    }
    var isWorkflowFilesToolbarButtonEnabled: Bool {
        isEnabled(.workflowImportExport, workflowFilesToolbarEnabledInternal)
    }
    var isWorkflowRunOnSelectionEnabled: Bool {
        isEnabled(.workflowRunOnSelection, workflowRunOnSelectionEnabledInternal)
    }
    var workflowEnabledTools: Set<String> {
        Set(
            workflowEnabledToolsInternal
                .split(separator: ",")
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
                .filter { !$0.isEmpty }
        )
    }
    /// PDF scroll → grid/inspector sync. Defaulted OFF; enable via Settings or `FICHERO_ALL_FEATURES=1`.
    /// Guards the NSScrollView live-scroll observer added in PDFPageView (#591/#592).
    var isPdfScrollGridSyncEnabled: Bool {
        isEnabled(.pdfScrollGridSync, pdfScrollGridSyncEnabledInternal)
    }
    /// Bidirectional claim highlight sync across PDF, Content, and Inspector panes. Defaulted OFF.
    var isClaimHighlightSyncEnabled: Bool {
        isEnabled(.claimHighlightSync, claimHighlightSyncEnabledInternal)
    }
    var isWorkspaceModeEnabled: Bool { isEnabled(.workspaceMode, workspaceModeEnabledInternal) }
    var isSpatialModeEnabled: Bool { isEnabled(.spatialMode, spatialModeEnabledInternal) }
    var isCanvasRealityKit2DEnabled: Bool {
        isEnabled(.canvasRealityKit2D, canvasRealityKit2DEnabledInternal)
    }
    var isCanvasRealityKit3DEnabled: Bool {
        isEnabled(.canvasRealityKit3D, canvasRealityKit3DEnabledInternal)
    }
    var isResearchEnabled: Bool { isEnabled(.research, researchEnabledInternal) }
    /// Knowledge Graph / Ontology browser (#498). Defaulted ON — the view is complete.
    var isKnowledgeGraphEnabled: Bool {
        isEnabled(.knowledgeGraph, knowledgeGraphEnabledInternal)
    }
}
