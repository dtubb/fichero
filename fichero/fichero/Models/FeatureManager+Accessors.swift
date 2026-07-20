import Foundation

// MARK: - Feature Visibility & Gating

/// Computed feature-flag accessors for `FeatureManager`. Split out of the main class body
/// (issue #3743) — these read the persisted, tier-gated stored flags declared there and stay
/// pure computed properties/methods, so they can live in a plain `extension`.
extension FeatureManager {
    /// Development builds deliberately expose every implemented feature.
    var allFeaturesEffectivelyEnabled: Bool {
        allFeaturesEnabled || activeBuildTier == .dev
    }

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
        return .dev
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
