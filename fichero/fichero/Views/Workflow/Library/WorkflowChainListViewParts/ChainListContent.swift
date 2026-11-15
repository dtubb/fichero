import SwiftUI

struct ChainListContent: View {
    let filteredChains: [WorkflowChain]
    let isLoading: Bool
    let chainsEmpty: Bool
    let searchText: String
    let executingChainId: String?
    let onNewChain: () -> Void
    @Binding var selectedChainIds: Set<String>
    let onSelectChain: (String) -> Void
    let onExecuteChain: (WorkflowChain) -> Void
    let onConfirmDelete: (WorkflowChain) -> Void
    let onConfirmDeleteSelection: () -> Void
    let onRefresh: () -> Void

    var body: some View {
        Group {
            if isLoading && chainsEmpty {
                ProgressView("Loading chains...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if filteredChains.isEmpty {
                ContentUnavailableView {
                    Label("No Chains", systemImage: "link")
                } description: {
                    if searchText.isEmpty {
                        Text("Create your first chain to connect workflows together")
                    } else {
                        Text("No chains match your search")
                    }
                } actions: {
                    if searchText.isEmpty {
                        Button("New Chain") {
                            onNewChain()
                        }
                        .buttonStyle(.borderedProminent)
                    }
                }
            } else {
                // Native List selection + a selection-aware context menu with a
                // primaryAction (double-click on Mac, tap-to-open on touch). No
                // custom tap gesture — a `.onTapGesture(count:2)` on a
                // `List(selection:)` row fought the built-in selection (#2806).
                List(filteredChains, selection: $selectedChainIds) { chain in
                    ChainListRow(
                        chain: chain,
                        isExecuting: executingChainId == chain.id
                    )
                    .tag(chain.id)
                }
                .contextMenu(forSelectionType: String.self) { ids in
                    chainContextMenu(for: ids)
                } primaryAction: { ids in
                    if let id = ids.first {
                        onSelectChain(id)
                    }
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    onNewChain()
                } label: {
                    Label("New Chain", systemImage: "plus")
                }
            }

            ToolbarItem(placement: .automatic) {
                Button(role: .destructive) {
                    onConfirmDeleteSelection()
                } label: {
                    Label("Delete Selection", systemImage: "trash")
                }
                .disabled(selectedChainIds.isEmpty)
            }

            ToolbarItem(placement: .automatic) {
                Button {
                    onRefresh()
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
            }
        }
        #if os(macOS)
        .onDeleteCommand(perform: onConfirmDeleteSelection)
        #endif
    }

    /// Context menu for the current List selection. A single row offers its
    /// details / execute / delete; a multi-selection offers delete-all.
    @ViewBuilder
    private func chainContextMenu(for ids: Set<String>) -> some View {
        if ids.count == 1, let id = ids.first {
            Button {
                onSelectChain(id)
            } label: {
                Label("View Details", systemImage: "info.circle")
            }

            if let chain = filteredChains.first(where: { $0.id == id }) {
                Button {
                    onExecuteChain(chain)
                } label: {
                    Label("Execute", systemImage: "play.fill")
                }
            }

            Divider()

            Button(role: .destructive) {
                if let chain = filteredChains.first(where: { $0.id == id }) {
                    onConfirmDelete(chain)
                }
            } label: {
                Label("Delete", systemImage: "trash")
            }
        } else if !ids.isEmpty {
            Button(role: .destructive) {
                onConfirmDeleteSelection()
            } label: {
                Label("Delete \(ids.count) Chains", systemImage: "trash")
            }
        }
    }
}
