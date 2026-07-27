import OSLog
import SwiftUI

let scheduleEditorLogger = Logger(subsystem: "app.fichero.fichero", category: "ScheduleEditorView")

/// Full-page editor for creating and editing schedules
/// Similar to workflow canvas - used instead of dialog sheets
struct ScheduleEditorView: View {
    @Environment(APIClient.self) var apiClient
    @Environment(WorkflowStore.self) var workflowStore

    /// Existing schedule to edit, or nil for new schedule creation
    let existingSchedule: ScheduleInfo?

    /// Callback when schedule is saved
    var onSave: ((ScheduleInfo) -> Void)?

    // Form state
    @State var name = ""
    @State var selectedWorkflowId = ""
    @State var scheduleType = "interval"
    @State var cronExpression = "0 0 * * *"
    @State var intervalMinutes = 60
    @State var runAtDate = Date()
    @State var timezone = TimeZone.current.identifier
    @State var startDate: Date?
    @State var endDate: Date?
    @State var maxRuns: Int?
    @State var useBatch = false
    @State var maxConcurrent = 1

    // UI state
    @State var isSaving = false
    @State var error: String?
    @State var showAdvanced = false

    var isEditing: Bool { existingSchedule != nil }
    var isValid: Bool { !name.isEmpty && !selectedWorkflowId.isEmpty }

    var body: some View {
        PlatformHSplitView {
            // Left panel - Form
            formPanel
                .frame(minWidth: 350, idealWidth: 400, maxWidth: 500)

            // Right panel - Preview/Help
            previewPanel
                .frame(minWidth: 300, idealWidth: 350)
        }
        .navigationTitle(isEditing ? "Edit Schedule" : "New Schedule")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task { await saveSchedule() }
                } label: {
                    if isSaving {
                        ProgressView()
                            .scaleEffect(0.8)
                    } else {
                        Label("Save", systemImage: "checkmark.circle")
                    }
                }
                .disabled(!isValid || isSaving)
            }
        }
        .onAppear {
            populateFromExisting()
        }
    }

    // MARK: - Form Panel

    @ViewBuilder
    var formPanel: some View {
        Form {
            // Basic Information
            Section("Basic Information") {
                TextField("Name", text: $name)
                    .textFieldStyle(.roundedBorder)

                Picker("Workflow", selection: $selectedWorkflowId) {
                    Text("Select workflow...").tag("")
                    ForEach(workflowStore.directlyRunnableWorkflows) { workflow in
                        Text(workflow.name).tag(workflow.id)
                    }
                }
            }

            // Schedule Type
            Section("Schedule") {
                Picker("Type", selection: $scheduleType) {
                    Text("Interval").tag("interval")
                    Text("Cron Expression").tag("cron")
                    Text("One-time").tag("once")
                }
                .pickerStyle(.segmented)

                scheduleTypeFields
            }

            // Timezone
            Section("Timezone") {
                Picker("Timezone", selection: $timezone) {
                    ForEach(commonTimezones, id: \.self) { timezoneID in
                        Text(timezoneID).tag(timezoneID)
                    }
                }
            }

            // Advanced Options
            DisclosureGroup("Advanced Options", isExpanded: $showAdvanced) {
                advancedOptions
            }

            // Error display
            if let error = error {
                Section {
                    HStack {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundStyle(.orange)
                        Text(error)
                            .foregroundStyle(.red)
                    }
                }
            }
        }
        .formStyle(.grouped)
    }
}

// MARK: - Preview

#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    ScheduleEditorView(existingSchedule: nil)
        .environment(library.automationService)
        .environment(library.workflowStore)
        .frame(width: 600, height: 500)
}
