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
                List(filteredChains, selection: $selectedChainIds) { chain in
                    ChainListRow(
                        chain: chain,
                        isExecuting: executingChainId == chain.id
                    )
                    .tag(chain.id)
                    .contentShape(Rectangle())
                    .onTapGesture(count: 2) {
                        onSelectChain(chain.id)
                    }
                    .contextMenu {
                        Button {
                            onSelectChain(chain.id)
                        } label: {
                            Label("View Details", systemImage: "info.circle")
                        }

                        Button {
                            onExecuteChain(chain)
                        } label: {
                            Label("Execute", systemImage: "play.fill")
                        }

                        Divider()

                        Button(role: .destructive) {
                            if selectedChainIds.contains(chain.id) {
                                onConfirmDeleteSelection()
                            } else {
                                onConfirmDelete(chain)
                            }
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
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
        .onDeleteCommand(perform: onConfirmDeleteSelection)
    }
}
