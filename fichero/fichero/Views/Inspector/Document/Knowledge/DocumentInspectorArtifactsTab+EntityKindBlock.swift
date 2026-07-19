import FicheroAPIClient
import SwiftUI

// MARK: - Per-kind list block

/// Finder Get Info-style block: a DisclosureGroup labelled by entity kind,
/// containing plain selectable rows. No buttons, no copy icons — clicks
/// don't trigger actions, ⌘C copies the standard text selection.
struct EntityKindBlock: View {
    let kind: EntityKind
    let items: [GroupedItem]
    var claimById: [String: Components.Schemas.KnowledgeClaim] = [:]
    var selectedClaimIds: Set<String> = []
    var claimScopeLabel: String?
    var claimContextMenuTarget: ((Components.Schemas.KnowledgeClaim) -> [Components.Schemas.KnowledgeClaim])?
    var onClaimTap: ((Components.Schemas.KnowledgeClaim) -> Void)?
    var applyClaimBulkAction: ((
        InspectorClaimBulkAction,
        InspectorEntityBulkActionScope,
        [Components.Schemas.KnowledgeClaim]
    ) async -> Void)?
    // Chosen merge plan (survivor picked in the menu), threaded to the row (#2499).
    var requestClaimMergeAction: ((InspectorClaimBulkSelection.MergePlan) -> Void)?
    var requestClaimDeleteAction: (([Components.Schemas.KnowledgeClaim]) -> Void)?
    var requestPruneTrivialAction: ((InspectorEntityBulkActionScope) -> Void)?
    var onNavigateToSource: ((String) -> Void)?
    var onClaimSelect: ((String, String?, String?, String?, Int?, Int?) -> Void)?

    @SceneStorage("inspector.kg.expandedKinds") private var expandedKindsCSV: String = ""
    @SceneStorage("inspector.kg.showAllKinds") private var showAllKindsCSV: String = ""

    private var isExpanded: Binding<Bool> {
        Binding(
            get: { isOpen },
            set: { newValue in setOpen(newValue) }
        )
    }

    private var isOpen: Bool {
        expandedKindsCSV
            .split(separator: ",")
            .contains(Substring(kind.rawValue))
            // Default open until the user explicitly collapses something
            || expandedKindsCSV.isEmpty
    }

    private func setOpen(_ open: Bool) {
        var set = Set(
            expandedKindsCSV.split(separator: ",").map(String.init)
        )
        // First explicit toggle: seed with all currently-default-open kinds
        // so collapsing one doesn't collapse them all.
        if set.isEmpty {
            set = Set(EntityKind.displayOrder.map(\.rawValue))
        }
        if open { set.insert(kind.rawValue) } else { set.remove(kind.rawValue) }
        expandedKindsCSV = set.sorted().joined(separator: ",")
    }

    private var isShowingAll: Bool {
        KnowledgeGraphInspectorSection.isKindStored(kind, in: showAllKindsCSV)
    }

    private func setShowingAll(_ show: Bool) {
        var set = Set(
            showAllKindsCSV.split(separator: ",").map(String.init)
        )
        if show { set.insert(kind.rawValue) } else { set.remove(kind.rawValue) }
        showAllKindsCSV = set.sorted().joined(separator: ",")
    }

    private var visibleItems: [GroupedItem] {
        KnowledgeGraphInspectorSection.visibleItems(items, showingAll: isShowingAll)
    }

    var body: some View {
        DisclosureGroup(isExpanded: isExpanded) {
            VStack(alignment: .leading, spacing: 0) {
                if kind == .concept {
                    // Keywords as wrapping lozenges. Use the same EntityLozenge
                    // component as the inspector + list-view so tap-to-search
                    // works consistently and styling is uniform across all
                    // entity rendering paths in the app. EntityKind.concept
                    // maps to the 'keywords' artifact type — pass that so
                    // taps fire `keywords:"<term>"` scoped queries.
                    FlowLayout(spacing: 4) {
                        ForEach(visibleItems) { item in
                            EntityLozenge(name: item.displayName, entityType: "keywords")
                        }
                    }
                    .padding(.leading, 16)
                    .padding(.top, 4)
                    .contextMenu {
                        Button("Copy all keywords") {
                            PlatformPasteboard.writeString(
                                items.map(\.displayName).joined(separator: "; ")
                            )
                        }
                    }
                } else {
                    LazyVStack(alignment: .leading, spacing: 2) {
                        ForEach(visibleItems) { item in
                            EntityKindRow(
                                item: item,
                                kind: kind,
                                claimById: claimById,
                                selectedClaimIds: selectedClaimIds,
                                claimScopeLabel: claimScopeLabel,
                                claimContextMenuTarget: claimContextMenuTarget,
                                onClaimTap: onClaimTap,
                                applyClaimBulkAction: applyClaimBulkAction,
                                requestClaimMergeAction: requestClaimMergeAction,
                                requestClaimDeleteAction: requestClaimDeleteAction,
                                requestPruneTrivialAction: requestPruneTrivialAction,
                                onNavigateToSource: onNavigateToSource,
                                onClaimSelect: onClaimSelect
                            )
                        }
                    }
                    .padding(.leading, 16)
                    .padding(.top, 4)
                }
                if let title = KnowledgeGraphInspectorSection.showAllButtonTitle(
                    itemCount: items.count,
                    showingAll: isShowingAll
                ) {
                    bottomLoadMoreButton(title: title) {
                        setShowingAll(!isShowingAll)
                    }
                }
            }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: kind.systemImage)
                    .foregroundStyle(.secondary)
                    .font(.caption)
                Text(kind.label)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundStyle(.primary)
                Text("(\(items.count))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private func bottomLoadMoreButton(title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack {
                Text(title)
                    .font(.caption)
                Spacer()
                Image(systemName: isShowingAll ? "chevron.up" : "chevron.down")
                    .font(.caption2)
            }
            .foregroundStyle(Color.accentColor)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 4)
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 16)
        .padding(.top, 4)
    }
}
