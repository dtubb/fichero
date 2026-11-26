import Foundation
import OSLog

// MARK: - Feature Tiers

extension FeatureTier {
    var rank: Int { rawValue }

    var environmentValue: String {
        switch self {
        case .dev: return "dev"
        case .alpha: return "alpha"
        case .beta: return "beta"
        case .release: return "release"
        }
    }
}

/// Tier resolution, release-profile defaults, and workflow-tool gating for `FeatureManager`.
/// Split out of the main class body (issue #3743) — these are methods over the persisted,
/// tier-gated stored flags declared there, so they can live in a plain `extension`.
extension FeatureManager {
    // Bumped to re-apply workflow execution release defaults on existing
    // installs (langgraph preview, run-on-selection, files toolbar, import/export).
    static let releaseProfileVersion = 32
    static let workflowV001EnabledTools =
        "files,collection,folder,aggregate,transcribe,catalogue,"
        + "extract_all,kg_writer,extract_entities,key_people,timeline,keywords,summarize_file,"
        + "describe,rewrite,"
        + "citations_extract,"
        + "people_extract,dates_extract,rivers_extract,events_extract,"
        + "mines_extract,properties_extract,legal_references_extract,"
        + "keywords_extract,quotes_extract,"
        + "people_folder_cleanup,places_folder_cleanup,organizations_folder_cleanup,"
        + "dates_folder_cleanup,events_folder_cleanup,keywords_folder_cleanup"
    static var didWarnUnknownFeatureTier = false

    /// Reset to v0.0.1 defaults
    func resetToV001() {
        allFeaturesEnabled = false
        libraryAdvancedViewsEnabledInternal = true   // 0.0.3 #517: list/table/map re-enabled
        searchEnabledInternal = true
        searchAdvancedViewsEnabledInternal = true    // 0.0.3 #517: search results in all views
        librarySearchSplitLayoutsEnabledInternal = false
        libraryFilterToolbarEnabledInternal = false
        libraryIconZoomControlsEnabledInternal = true // 0.0.3 #517: zoom controls re-enabled
        workflowsEnabledInternal = true
        workflowEditorAdvancedViewsEnabled = true
        workflowChainsEnabledInternal = true
        batchesEnabledInternal = true
        chatEnabledInternal = false
        agentsEnabledInternal = false
        automationEnabledInternal = false
        mcpEnabledInternal = true
        integrationsEnabledInternal = true
        activityEnabledInternal = true

        settingsGeneralTabEnabledInternal = true
        settingsBackendTabEnabledInternal = true
        settingsModelsTabEnabledInternal = true
        settingsEngineTabEnabledInternal = true
        settingsShareTabEnabledInternal = true
        settingsUsersTabEnabledInternal = true
        settingsCaptureTabEnabledInternal = true
        workflowToolsMCPEnabledInternal = false
        workflowToolsAgentsEnabledInternal = false
        workflowToolsAudioEnabledInternal = false
        workflowToolsVideoEnabledInternal = false
        workflowToolsTransformEnabledInternal = false
        workflowToolsConvertEnabledInternal = false
        workflowToolsLogicEnabledInternal = false
        workflowToolsOutputsEnabledInternal = false
        workflowToolsFilesEnabledInternal = true
        workflowToolsSearchEnabledInternal = false
        workflowEnabledToolsInternal = Self.workflowV001EnabledTools
        providersExtendedEnabledInternal = false
        workflowImportExportEnabledInternal = true
        workflowLangGraphPreviewEnabledInternal = true
        workflowFilesToolbarEnabledInternal = true
        workflowRunOnSelectionEnabledInternal = true
        workspaceModeEnabledInternal = false
        spatialModeEnabledInternal = false
        canvasRealityKit2DEnabledInternal = true
        canvasRealityKit3DEnabledInternal = true
        researchEnabledInternal = true
        knowledgeGraphEnabledInternal = true
        releaseProfileVersionApplied = Self.releaseProfileVersion
    }

    func isWorkflowToolExplicitlyEnabled(_ toolName: String) -> Bool {
        if allFeaturesEffectivelyEnabled {
            return true
        }
        let normalized = normalizeWorkflowToolName(toolName)
        return workflowEnabledTools.contains(normalized)
    }

    func applyReleaseProfileDefaultsIfNeeded() {
        if releaseProfileVersionApplied < 15 {
            let currentTools = workflowEnabledToolsInternal
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if currentTools.isEmpty {
                workflowEnabledToolsInternal = Self.workflowV001EnabledTools
            }
        }

        guard releaseProfileVersionApplied < Self.releaseProfileVersion else {
            return
        }
        resetToV001()
    }

    private func normalizeWorkflowToolName(_ toolName: String) -> String {
        switch toolName.lowercased() {
        case "folder", "container":
            return "collection"
        default:
            return toolName.lowercased()
        }
    }

    static func resolveFeatureTier(_ rawValue: String?) -> FeatureTier? {
        guard let rawValue else {
            return nil
        }
        let normalized = rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !normalized.isEmpty else {
            return nil
        }

        switch normalized {
        case "dev":
            return .dev
        case "alpha":
            return .alpha
        case "beta":
            return .beta
        case "release":
            return .release
        default:
            // Returns NIL, not `.dev` (#4470). This is the branch that made the
            // fail-closed default added to `activeBuildTier` ineffective: an
            // unrecognised value resolved to `.dev` — the WIDEST surface — and
            // the caller's `.release` fallback never ran, because a non-nil
            // answer looks like a successful resolution.
            //
            // The value that reaches here in practice is the literal
            // `$(FICHERO_FEATURE_TIER)`: `Info.plist` ships the unsubstituted
            // placeholder when the build setting is missing. So the most likely
            // real configuration failure was also the one that unlocked
            // everything.
            //
            // "I do not recognise this" is not an answer, and it must not be
            // dressed as one. The caller decides what to do with nil, and the
            // caller now fails closed.
            warnUnknownFeatureTierOnce(rawValue)
            return nil
        }
    }

    private static func warnUnknownFeatureTierOnce(_ rawValue: String) {
        guard !didWarnUnknownFeatureTier else {
            return
        }
        didWarnUnknownFeatureTier = true
        featureManagerTiersLogger.warning(
            "Unknown FICHERO_FEATURE_TIER value '\(rawValue, privacy: .public)'; defaulting to dev"
        )
    }
}

private let featureManagerTiersLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "FeatureManager"
)
