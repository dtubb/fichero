import FicheroAPIClient
import OSLog
import SwiftUI

// The pinned bottom mini-toolbar for KnowledgeGraphInspectorSection — the KG
// tab's prune / filter / view-mode / refresh controls and the on-selection
// claim-action menus. Split out of the core file for file length.
extension KnowledgeGraphInspectorSection {
    private var kgToolbarStatusText: String {
        let count = grouped.reduce(0) { $0 + $1.1.count }
        return "\(count) entit\(count == 1 ? "y" : "ies")"
    }

    // Promoted `private` → internal: rendered by `body` in the core file.
    /// Pinned bottom mini-toolbar — the single home for the KG tab's controls
    /// (prune / filter / view-mode / refresh) plus the on-selection claim
    /// actions, matching the other inspector panes (#3461).
    var kgMiniToolbar: some View {
        InspectorBottomMiniToolbar(statusText: kgToolbarStatusText) {
            Menu("Prune trivial") {
                pruneTrivialScopeButtons()
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .disabled(isMutatingClaims)

            kgFilterMenu

            Button {
                displayMode = .text
            } label: {
                Image(systemName: "text.alignleft")
            }
            .buttonStyle(.plain)
            .foregroundStyle(displayMode == .text ? Color.accentColor : Color.secondary)
            .help("Text digest — entities as a dense prose summary, one paragraph per kind")
            .accessibilityLabel("Text digest")

            Button {
                displayMode = .list
            } label: {
                Image(systemName: "list.bullet")
            }
            .buttonStyle(.plain)
            .foregroundStyle(displayMode == .list ? Color.accentColor : Color.secondary)
            .help("List view — entities as grouped, expandable rows you can click through to the source")
            .accessibilityLabel("List view")

            if displayMode == .list {
                rowDetailMenu
            }

            Button {
                Task { await loadStatements() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.plain)
            .help("Reload — re-fetch the knowledge-graph entities for this document")
            .accessibilityLabel("Reload entities")

            if claimSelection.count > 1 {
                claimBulkActionMenu(title: "Approve", systemImage: "checkmark.circle", action: .approve)
                claimBulkActionMenu(title: "Reject", systemImage: "xmark.circle", action: .reject)
                claimBulkActionMenu(title: "Suppress", systemImage: "eye.slash", action: .suppress)
                claimMergeActionMenu(targetClaims: selectedClaims, menuTitle: "Merge")
                deleteActionButton(targetClaims: selectedClaims)
            }
        }
    }

    /// "Row Detail" menu (#3466), Xcode-console-style: toggle which metadata each
    /// claim row renders. Persisted via @AppStorage (shared keys with EntityKindRow).
    private var rowDetailMenu: some View {
        Menu {
            Toggle("Confidence", isOn: $rowShowConfidence)
            Toggle("Page reference", isOn: $rowShowPageRef)
            Toggle("Context", isOn: $rowShowContext)
            Toggle("Source excerpt", isOn: $rowShowExcerpt)
        } label: {
            Image(systemName: "slider.horizontal.3")
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Row detail — choose which metadata each claim row shows")
        .accessibilityLabel("Row detail")
    }

    // Filter Menu — Tinderbox-style "displayed attributes" picker. Each entity
    // kind has its own checkbox; persistence lives in @AppStorage so the choice
    // survives restarts and applies to every doc the user inspects.
    private var kgFilterMenu: some View {
        Menu {
            Section("Scope") {
                Button {
                    includeChildren = false
                } label: {
                    HStack {
                        Text("This item only")
                        Spacer(minLength: 0)
                        if !includeChildren {
                            Image(systemName: "checkmark")
                        }
                    }
                }
                Button {
                    includeChildren = true
                } label: {
                    HStack {
                        Text("Include children")
                        Spacer(minLength: 0)
                        if includeChildren {
                            Image(systemName: "checkmark")
                        }
                    }
                }
            }
            ForEach(EntityKind.displayOrder, id: \.self) { kind in
                let isHidden = hiddenKinds.contains(kind)
                Button {
                    setHidden(kind, hidden: !isHidden)
                } label: {
                    Label(kind.label, systemImage: isHidden ? "" : "checkmark")
                }
            }
            Divider()
            Button("Show all") { hiddenKindsCSV = "" }
            Button("Hide all") {
                hiddenKindsCSV = EntityKind.displayOrder
                    .map(\.rawValue)
                    .sorted()
                    .joined(separator: ",")
            }
        } label: {
            Image(systemName: hiddenKinds.isEmpty
                    ? "line.3.horizontal.decrease.circle"
                    : "line.3.horizontal.decrease.circle.fill")
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Filter — choose which entity kinds (people, places, organizations…) appear in this list")
        .accessibilityLabel("Filter entity kinds")
    }

    private func claimBulkActionMenu(
        title: String,
        systemImage: String,
        action: InspectorClaimBulkAction
    ) -> some View {
        Menu {
            claimBulkScopeButtons(action: action, targetClaims: selectedClaims)
        } label: {
            Label(title, systemImage: systemImage)
        }
        .menuStyle(.borderlessButton)
        .disabled(isMutatingClaims || selectedClaims.isEmpty)
    }

    private func claimMergeActionMenu(
        targetClaims: [Components.Schemas.KnowledgeClaim],
        menuTitle: String
    ) -> some View {
        // One destination choice per candidate so the user picks which claim
        // the others fold INTO (#2499). Heuristic survivor marked Recommended.
        let recommendedId = InspectorClaimBulkSelection.mergeSurvivor(in: targetClaims)?.id
        let canMerge = InspectorClaimBulkSelection.mergePlan(for: targetClaims) != nil
        return Menu {
            if canMerge {
                // Precompute the mergeable claims with NON-optional identity, off the
                // view body: no per-render `.filter { $0.id != nil }` and no optional
                // `id: \.id` (#3863).
                ForEach(identifiedClaims(from: targetClaims)) { identified in
                    if let plan = InspectorClaimBulkSelection.mergePlan(
                        for: targetClaims, survivorId: identified.id) {
                        Button(mergeDestinationLabel(
                            name: identified.claim.displayMergeName,
                            isRecommended: identified.id == recommendedId
                        )) {
                            pendingMergePlan = plan
                        }
                    }
                }
            } else {
                Button("Requires 2+ live claims") {}
                    .disabled(true)
            }
        } label: {
            Label(menuTitle, systemImage: "arrow.triangle.merge")
        }
        .menuStyle(.borderlessButton)
        .disabled(isMutatingClaims || !canMerge)
    }

    /// Menu-button title for a merge destination (#2499). Marks the heuristic
    /// survivor as "(Recommended)" so the sensible default is one click away.
    private func mergeDestinationLabel(name: String, isRecommended: Bool) -> String {
        isRecommended ? "Into \"\(name)\" (Recommended)" : "Into \"\(name)\""
    }

    private func deleteActionButton(
        targetClaims: [Components.Schemas.KnowledgeClaim]
    ) -> some View {
        Button(role: .destructive) {
            requestDeleteAction(for: targetClaims)
        } label: {
            Label("Delete", systemImage: "trash")
        }
        .buttonStyle(.borderless)
        .disabled(isMutatingClaims || targetClaims.isEmpty)
    }

    @ViewBuilder
    private func claimBulkScopeButtons(
        action: InspectorClaimBulkAction,
        targetClaims: [Components.Schemas.KnowledgeClaim]
    ) -> some View {
        Button(documentScopeLabel) {
            Task {
                await applyBulkAction(
                    action,
                    scope: .pageOrFolderOnly,
                    targetClaims: targetClaims
                )
            }
        }
        Button("Library-wide") {
            Task {
                await applyBulkAction(
                    action,
                    scope: .libraryWide,
                    targetClaims: targetClaims
                )
            }
        }
    }

    @ViewBuilder
    private func pruneTrivialScopeButtons() -> some View {
        Button(documentScopeLabel) {
            requestPruneTrivialAction(.pageOrFolderOnly)
        }
        Button("Library-wide") {
            requestPruneTrivialAction(.libraryWide)
        }
    }
}
