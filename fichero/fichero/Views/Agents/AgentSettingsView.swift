import OSLog
import Observation
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "AgentSettingsView")

/// Settings view for configuring agent defaults (similar to Model Provider settings)
/// This is accessed from the Fichero menu
struct AgentSettingsView: View {
    @State private var settings = AgentSettings.shared
    @State private var selectedAgentType: AgentType? = .react
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationSplitView {
            // Sidebar with agent types
            List(AgentType.allCases, id: \.self, selection: $selectedAgentType) { type in
                Label {
                    Text(type.displayName)
                } icon: {
                    Image(systemName: type.icon)
                        .foregroundColor(.purple)
                }
            }
            .navigationTitle("Agent Types")
            .listStyle(.sidebar)
        } detail: {
            // Detail view for selected agent type
            if let selectedAgentType {
                AgentTypeSettingsView(
                    agentType: selectedAgentType,
                    settings: settings
                )
            } else {
                ContentUnavailableView(
                    "No Agent Selected",
                    systemImage: "person.crop.circle.badge.questionmark",
                    description: Text("Select an agent type to configure its defaults.")
                )
            }
        }
        .frame(minWidth: 700, minHeight: 500)
    }
}

/// Settings for a specific agent type
struct AgentTypeSettingsView: View {
    let agentType: AgentType
    @Bindable var settings: AgentSettings

    var body: some View {
        Form {
            Section("General") {
                HStack {
                    Image(systemName: agentType.icon)
                        .font(.largeTitle)
                        .foregroundColor(.purple)
                    VStack(alignment: .leading) {
                        Text(agentType.displayName)
                            .font(.title2)
                            .fontWeight(.bold)
                        Text(agentType.description)
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                }
                .padding(.vertical, 8)
            }

            Section("Default Configuration") {
                // System Prompt
                VStack(alignment: .leading, spacing: 4) {
                    Text("Default System Prompt")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                    MacPlainTextEditor(text: binding(for: \.systemPrompt), font: .preferredFont(forTextStyle: .body))
                        .frame(minHeight: 80)
                        .padding(4)
                        .background(Color(.textBackgroundColor))
                        .cornerRadius(4)
                }

                // Max Iterations
                Stepper(
                    "Max Iterations: \(settings.config(for: agentType).maxIterations)",
                    value: binding(for: \.maxIterations),
                    in: 1...100
                )

                // Timeout
                Stepper(
                    "Timeout (seconds): \(settings.config(for: agentType).timeoutSeconds)",
                    value: binding(for: \.timeoutSeconds),
                    in: 5...300,
                    step: 5
                )
            }

            Section("Default Tools") {
                Toggle("Enable File Operations", isOn: binding(for: \.enableFileTools))
                Toggle("Enable Web Tools", isOn: binding(for: \.enableWebTools))
                Toggle("Enable Transform Tools", isOn: binding(for: \.enableTransformTools))

                Text("Additional tools can be assigned per-node in the workflow editor.")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Section("Behavior") {
                Toggle("Verbose Logging", isOn: binding(for: \.verboseLogging))
                Toggle("Include Intermediate Steps", isOn: binding(for: \.includeIntermediateSteps))
                Toggle("Allow Parallel Tool Calls", isOn: binding(for: \.allowParallelCalls))
            }
        }
        .formStyle(.grouped)
        .navigationTitle(agentType.displayName)
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Button("Reset to Defaults") {
                    settings.resetToDefaults(for: agentType)
                }
            }
        }
    }

    // MARK: - Binding Helpers

    private func binding<T>(for keyPath: WritableKeyPath<AgentTypeConfig, T>) -> Binding<T> {
        Binding(
            get: { settings.config(for: agentType)[keyPath: keyPath] },
            set: { settings.updateConfig(for: agentType, keyPath: keyPath, value: $0) }
        )
    }
}

// AgentType is defined in WorkflowTypes.swift

/// Configuration for a specific agent type
struct AgentTypeConfig: Codable {
    var systemPrompt: String
    var maxIterations: Int
    var timeoutSeconds: Int
    var enableFileTools: Bool
    var enableWebTools: Bool
    var enableTransformTools: Bool
    var verboseLogging: Bool
    var includeIntermediateSteps: Bool
    var allowParallelCalls: Bool

    static func defaults(for type: AgentType) -> AgentTypeConfig {
        switch type {
        case .react:
            return AgentTypeConfig(
                systemPrompt: """
                    You are a helpful assistant that thinks step-by-step. \
                    Consider the problem carefully and use the available tools to help solve it.
                    """,
                maxIterations: 10,
                timeoutSeconds: 60,
                enableFileTools: true,
                enableWebTools: false,
                enableTransformTools: true,
                verboseLogging: false,
                includeIntermediateSteps: true,
                allowParallelCalls: false
            )
        case .toolCalling:
            return AgentTypeConfig(
                systemPrompt: "You are a helpful assistant. Use the available tools to complete the user's request.",
                maxIterations: 5,
                timeoutSeconds: 30,
                enableFileTools: true,
                enableWebTools: true,
                enableTransformTools: true,
                verboseLogging: false,
                includeIntermediateSteps: false,
                allowParallelCalls: true
            )
        case .planAndExecute:
            return AgentTypeConfig(
                systemPrompt: """
                    You are a helpful assistant that plans carefully before acting. \
                    First create a step-by-step plan, then execute each step using the available tools.
                    """,
                maxIterations: 20,
                timeoutSeconds: 120,
                enableFileTools: true,
                enableWebTools: true,
                enableTransformTools: true,
                verboseLogging: true,
                includeIntermediateSteps: true,
                allowParallelCalls: false
            )
        }
    }
}

/// Singleton for managing agent settings
@MainActor
@Observable
class AgentSettings {
    static let shared = AgentSettings()

    private var configs: [AgentType: AgentTypeConfig] = [:]

    private let userDefaultsKey = "AgentSettings"

    private init() {
        loadFromUserDefaults()
    }

    func config(for type: AgentType) -> AgentTypeConfig {
        configs[type] ?? AgentTypeConfig.defaults(for: type)
    }

    func updateConfig<T>(for type: AgentType, keyPath: WritableKeyPath<AgentTypeConfig, T>, value: T) {
        var config = configs[type] ?? AgentTypeConfig.defaults(for: type)
        config[keyPath: keyPath] = value
        configs[type] = config
        saveToUserDefaults()
    }

    func resetToDefaults(for type: AgentType) {
        configs[type] = AgentTypeConfig.defaults(for: type)
        saveToUserDefaults()
    }

    private func loadFromUserDefaults() {
        guard let data = UserDefaults.standard.data(forKey: userDefaultsKey),
              let decoded = try? JSONDecoder().decode([String: AgentTypeConfig].self, from: data) else {
            return
        }

        for (key, value) in decoded {
            if let type = AgentType(rawValue: key) {
                configs[type] = value
            }
        }
    }

    private func saveToUserDefaults() {
        var stringConfigs: [String: AgentTypeConfig] = [:]
        for (type, config) in configs {
            stringConfigs[type.rawValue] = config
        }

        if let data = try? JSONEncoder().encode(stringConfigs) {
            UserDefaults.standard.set(data, forKey: userDefaultsKey)
        }
    }
}

#Preview {
    AgentSettingsView()
}
