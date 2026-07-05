import SwiftUI

// MARK: - Per-user capture policy

struct CapturePolicy: Codable {
    var captureEnabled: Bool = false
    var libraryId: String = ""
    var libraryName: String = ""
    var workflowId: String = ""
    var workflowName: String = ""
}

// MARK: - Capture Settings (overview)

/// Mac decides capture policy: which user maps to which library + workflow.
/// Mobile devices capture and upload only — they never see this screen.
struct CaptureSettingsView: View {
    @Environment(AppState.self) var appState
    @Environment(LibraryManager.self) var libraryManager

    @State private var policies: [String: CapturePolicy] = [:]
    @State private var managingUser: String?

    private var users: [String] {
        let accountNames = appState.usersStore.users.map(\.username)
        if !accountNames.isEmpty {
            return accountNames
        }
        if let currentUser = appState.usersStore.currentUser {
            return [currentUser.username]
        }
        return []
    }

    var body: some View {
        Group {
            if let user = managingUser {
                CaptureUserManageView(
                    username: user,
                    policy: policyBinding(for: user),
                    libraries: libraryManager.openLibraries,
                    onBack: { managingUser = nil }
                )
            } else {
                overviewForm
            }
        }
        .task {
            await appState.usersStore.load()
            loadPolicies()
        }
    }

    private var overviewForm: some View {
        Form {
            Section("Incoming Captures") {
                if appState.usersStore.isLoading && users.isEmpty {
                    ProgressView()
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(.vertical, 8)
                } else if let error = appState.usersStore.loadError, users.isEmpty {
                    ContentUnavailableView(
                        "Couldn't load accounts",
                        systemImage: "person.2.slash",
                        description: Text(error)
                    )
                } else if users.isEmpty {
                    Text("No user accounts found.")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(users, id: \.self) { username in
                        userRow(username)
                    }
                }
            }
        }
        .formStyle(.grouped)
    }

    @ViewBuilder
    private func userRow(_ username: String) -> some View {
        let policy = policies[username] ?? CapturePolicy()
        LabeledContent {
            Button("Manage") { managingUser = username }
                .buttonStyle(.borderless)
        } label: {
            VStack(alignment: .leading, spacing: 2) {
                Text(username)
                    .fontWeight(.medium)
                if policy.captureEnabled, !policy.libraryName.isEmpty {
                    let subtitle = policy.workflowName.isEmpty
                        ? policy.libraryName
                        : "\(policy.libraryName) · \(policy.workflowName)"
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    Text("No capture access")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private func policyBinding(for username: String) -> Binding<CapturePolicy> {
        Binding(
            get: { policies[username] ?? CapturePolicy() },
            set: { updated in
                policies[username] = updated
                persist(updated, for: username)
            }
        )
    }

    // MARK: Persistence

    private func loadPolicies() {
        for username in users {
            guard let data = UserDefaults.standard.data(forKey: policyKey(username)),
                  let policy = try? JSONDecoder().decode(CapturePolicy.self, from: data)
            else { continue }
            policies[username] = policy
        }
    }

    private func persist(_ policy: CapturePolicy, for username: String) {
        guard let data = try? JSONEncoder().encode(policy) else { return }
        UserDefaults.standard.set(data, forKey: policyKey(username))
    }

    private func policyKey(_ username: String) -> String {
        "fichero.capture.policy.\(username)"
    }
}

// MARK: - Per-user manage view

struct CaptureUserManageView: View {
    let username: String
    @Binding var policy: CapturePolicy
    let libraries: [LibraryManager.LibraryReference]
    let onBack: () -> Void

    @State private var availableWorkflows: [WorkflowSidebarItem] = []
    @State private var showingLibraryPicker = false
    @State private var showingWorkflowPicker = false

    var body: some View {
        Form {
            Section {
                Toggle("Capture", isOn: $policy.captureEnabled)
                    .onChange(of: policy.captureEnabled) { _, enabled in
                        if !enabled {
                            policy.libraryId = ""
                            policy.libraryName = ""
                            policy.workflowId = ""
                            policy.workflowName = ""
                        }
                    }

                if policy.captureEnabled {
                    libraryRow
                    workflowRow
                }
            }

            Section {
                Button("Back") { onBack() }
                    .buttonStyle(.borderless)
            }
        }
        .task(id: policy.libraryId) { await loadWorkflows() }
        .sheet(isPresented: $showingLibraryPicker) { libraryPickerSheet }
        .sheet(isPresented: $showingWorkflowPicker) { workflowPickerSheet }
    }

    private var libraryRow: some View {
        LabeledContent("Library") {
            HStack {
                Text(policy.libraryName.isEmpty ? "None" : policy.libraryName)
                    .foregroundStyle(policy.libraryName.isEmpty ? .secondary : .primary)
                Spacer()
                Button("Change") { showingLibraryPicker = true }
                    .buttonStyle(.borderless)
            }
        }
    }

    private var workflowRow: some View {
        LabeledContent("Workflow") {
            HStack {
                Text(policy.workflowName.isEmpty ? "None" : policy.workflowName)
                    .foregroundStyle(policy.workflowName.isEmpty ? .secondary : .primary)
                Spacer()
                Button("Change") { showingWorkflowPicker = true }
                    .buttonStyle(.borderless)
                    .disabled(policy.libraryId.isEmpty)
            }
        }
    }

    private var libraryPickerSheet: some View {
        NavigationStack {
            List {
                ForEach(Array(libraries.enumerated()), id: \.element.id) { _, lib in
                    Button {
                        policy.libraryId = lib.id.uuidString
                        policy.libraryName = lib.displayName
                        policy.workflowId = ""
                        policy.workflowName = ""
                        showingLibraryPicker = false
                    } label: {
                        HStack {
                            Text(lib.displayName)
                            Spacer()
                            if lib.id.uuidString == policy.libraryId {
                                Image(systemName: "checkmark")
                                    .foregroundStyle(Color.accentColor)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
            .navigationTitle("Choose Library")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { showingLibraryPicker = false }
                }
            }
        }
        .frame(minWidth: 300, minHeight: 280)
    }

    private var workflowPickerSheet: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if availableWorkflows.isEmpty {
                    ContentUnavailableView(
                        "No Workflows",
                        systemImage: "arrow.triangle.branch",
                        description: Text("Add workflows to this library first.")
                    )
                } else {
                    List {
                        ForEach(Array(availableWorkflows.enumerated()), id: \.element.id) { _, workflow in
                            Button {
                                policy.workflowId = workflow.id
                                policy.workflowName = workflow.name
                                showingWorkflowPicker = false
                            } label: {
                                HStack {
                                    Text(workflow.name)
                                    Spacer()
                                    if workflow.id == policy.workflowId {
                                        Image(systemName: "checkmark")
                                            .foregroundStyle(Color.accentColor)
                                    }
                                }
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .navigationTitle("Choose Workflow")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { showingWorkflowPicker = false }
                }
            }
        }
        .frame(minWidth: 300, minHeight: 280)
    }

    private func loadWorkflows() async {
        guard let lib = libraries.first(where: { $0.id.uuidString == policy.libraryId }) else {
            availableWorkflows = []
            return
        }
        if lib.workflowStore.workflows.isEmpty {
            await lib.workflowStore.loadWorkflows()
        }
        availableWorkflows = lib.workflowStore.workflows
    }
}

// MARK: - Preview

#Preview("Capture Settings") {
    CaptureSettingsView()
        .environment(AppState())
        .environment(LibraryManager.shared)
}
