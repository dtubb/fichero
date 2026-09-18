import Foundation

/// The single sidebarMode → viewMode normalization policy (#4705 increment
/// 0). Pure: no environment, no state, so every writer of `sidebarMode`
/// (the View menu, "Show in Graph", the AppleScript `kg` command, restore)
/// that routes its change through the ONE `onChange(of: sidebarMode)`
/// handler (`MainContentModifiers.handleSidebarModeChange` in
/// `ContentViewModifiers.swift`) normalizes identically. Before this, the
/// inspector kept rendering a surface that belonged to the OLD sidebar
/// mode — e.g. switching to Research (⌃⌘8) while a chat was selected left
/// `ChatInspector` ("Chat Scope") on screen, because `viewMode` was
/// deliberately left untouched for that mode. (The Knowledge Graph mode
/// this originally also named retired in #4705 increment 3.)
enum ViewModeNormalization {
    /// If `current` already carries a meaningful selection in `sidebarMode`'s
    /// family (the #1475 preservation rule: a mode flip must never stomp the
    /// editor the same click just selected), it is returned unchanged.
    /// Otherwise the new mode's neutral default view is returned.
    static func normalizedViewMode(
        current: AppViewMode,
        forNewSidebarMode sidebarMode: SidebarMode
    ) -> AppViewMode {
        if preservesExistingSelection(current, forNewSidebarMode: sidebarMode) { return current }
        return defaultViewMode(forNewSidebarMode: sidebarMode)
    }

    /// The neutral view mode a sidebar-mode switch resets to when nothing in
    /// `current` is worth preserving. Shared by `normalizedViewMode` (the
    /// fallback) and `belongs` (the value a mode "agrees with" even with no
    /// selection at all) — factored out so the two can never drift apart.
    private static func defaultViewMode(forNewSidebarMode sidebarMode: SidebarMode) -> AppViewMode {
        switch sidebarMode {
        case .library: return .library(nil)
        case .chat: return .chat(nil)
        case .workflows: return .workflow(nil)
        case .automation: return .automation
        case .activity: return .activity(nil)
        case .research:
            // No dedicated AppViewMode case for this takeover mode, but
            // viewMode still MUST be reset to a neutral default — leaving a
            // stale .chat/.workflow view behind is exactly the "Chat Scope
            // leak" this normalization exists to close, because
            // Preview/Inspector switch on viewMode independently of
            // sidebarMode. contentView intercepts on sidebarMode itself for
            // the actual Research surface, and DocumentInspector (what
            // `.library(nil)` renders) is an honest, correctly-kinded
            // fallback there — never a WRONG surface the way ChatInspector
            // was — so .library(nil) (the same neutral default every other
            // reset falls back to) is safe here. (`.knowledgeGraph` DELETED,
            // #4705 increment 3 — the KG sidebar mode retired.)
            return .library(nil)
        }
    }

    /// The #1475 preservation-rule check ONLY: true when `view` already
    /// carries an EXPLICIT, meaningful selection in `sidebarMode`'s family —
    /// never true for a family's own empty placeholder (an unselected
    /// `.chain(nil)` "Create Chain" stub must still reset to `.workflow(nil)`
    /// when the sidebar switches to Workflows, not be kept as "fine as is").
    /// Deliberately narrower than `belongs` below: this is the gate that
    /// decides whether to preserve `current` at all, not the general
    /// "is this a valid view for this mode" question.
    private static func preservesExistingSelection(
        _ view: AppViewMode, forNewSidebarMode sidebarMode: SidebarMode
    ) -> Bool {
        switch sidebarMode {
        case .library:
            if case .library = view { return true }
            return false
        case .chat:
            if case .chat = view { return true }
            if case .comparison = view { return true }
            return false
        case .workflows:
            return workflowsFamilyHolds(view)
        case .automation:
            return automationFamilyHolds(view)
        case .activity:
            if case .activity(let selected) = view { return selected != nil }
            return false
        case .research:
            return false
        }
    }

    /// Whether `view` is a NON-STALE view mode for `sidebarMode` — either a
    /// preserved selection (`preservesExistingSelection`) or exactly the
    /// neutral default `normalizedViewMode` would have produced with no
    /// selection to preserve. This is total and, by construction, always
    /// true of whatever `normalizedViewMode` actually returns — the bug this
    /// fixes (found by the gate, #4705) was using the preservation-only
    /// check for this broader question: `.activity(nil)`, `.workflow(nil)`
    /// and `.library(nil)` (research/KG's own default) are legitimate,
    /// non-stale defaults, not "not yet selected" failures, so they must
    /// read as belonging even though `preservesExistingSelection` correctly
    /// says no selection exists to preserve.
    static func belongs(_ view: AppViewMode, to sidebarMode: SidebarMode) -> Bool {
        preservesExistingSelection(view, forNewSidebarMode: sidebarMode)
            || view == defaultViewMode(forNewSidebarMode: sidebarMode)
    }

    private static func workflowsFamilyHolds(_ view: AppViewMode) -> Bool {
        if case .workflow(let selected) = view { return selected != nil }
        if case .chain(let selected) = view { return selected != nil }
        if case .batches = view { return true }
        return false
    }

    private static func automationFamilyHolds(_ view: AppViewMode) -> Bool {
        if case .automation = view { return true }
        if case .schedule(let selected) = view { return selected != nil }
        if case .trigger(let selected) = view { return selected != nil }
        return false
    }
}
