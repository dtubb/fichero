import SwiftUI

/// The shared Run Workflow submenu body (#722, deduped #4121): workflows whose
/// `folderPath` is "/" appear at the top level and workflows under any other
/// folder path are grouped into a `Menu("<folder>")` submenu, matching the
/// user's sidebar organization. Each workflow expands to Default plus the
/// available provider/model overrides. Used by BOTH the sidebar row and the
/// library grid context menus — the action closure is the only difference.
struct RunWorkflowSubmenuItems: View {
    let workflows: [WorkflowSidebarItem]
    let action: (String, String?, String?) -> Void

    @State private var providerCache = WorkflowRunProviderCache.shared

    var body: some View {
        let grouped = Dictionary(grouping: workflows.filter(\.canRunDirectly)) { workflow in
            workflow.folderPath.isEmpty ? "/" : workflow.folderPath
        }
        let topLevel = (grouped["/"] ?? []).sorted { $0.name < $1.name }
        let folderKeys = grouped.keys.filter { $0 != "/" }.sorted()

        ForEach(topLevel) { workflow in
            workflowEntry(workflow)
        }
        ForEach(folderKeys, id: \.self) { folderPath in
            Menu(Self.folderLabel(for: folderPath)) {
                let inFolder = (grouped[folderPath] ?? []).sorted { $0.name < $1.name }
                ForEach(inFolder) { workflow in
                    workflowEntry(workflow)
                }
            }
        }
    }

    @ViewBuilder
    private func workflowEntry(_ workflow: WorkflowSidebarItem) -> some View {
        // A workflow that pins its own provider/model ignores any override the
        // menu would send, so offering one is a lie about what the run will do
        // (#4494). Collapse it to a single Button that runs the default.
        if workflow.canOverrideModel {
            // Vision workflows only list vision-capable overrides (#4187), read
            // from the server-resolved per-model capability — the engine owns the
            // tri-state fallback and the UI filter is an affordance, not a gate.
            Menu(workflow.name) {
                Button("Default") { action(workflow.id, nil, nil) }
                ForEach(providerCache.providers.filter { $0.available }) { provider in
                    switch provider.runMenuEntry(requiresVision: workflow.requiresVision) {
                    case .providerOnly:
                        Button(provider.name) { action(workflow.id, provider.id, nil) }
                    case .models(let models):
                        Menu(provider.name) {
                            ForEach(models, id: \.self) { model in
                                Button(model) { action(workflow.id, provider.id, model) }
                            }
                        }
                    case nil:
                        EmptyView()
                    }
                }
            }
        } else {
            Button(workflow.name) { action(workflow.id, nil, nil) }
        }
    }

    /// "/Transcribe" → "Transcribe"; "/Catalogue/Sub" → "Sub" (last
    /// component, mirroring how Finder shows nested folders in menus).
    static func folderLabel(for path: String) -> String {
        let trimmed = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        if trimmed.isEmpty { return path }
        return String(trimmed.split(separator: "/").last ?? Substring(trimmed))
    }
}
