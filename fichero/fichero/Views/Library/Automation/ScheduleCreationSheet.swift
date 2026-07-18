import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ScheduleCreationSheet")

/// Sheet for creating a new schedule
struct ScheduleCreationSheet: View {
    @Environment(APIClient.self) var apiClient
    @Environment(WorkflowStore.self) var workflowStore
    @Environment(\.dismiss) private var dismiss

    @State private var name = ""
    @State private var selectedWorkflowId = ""
    @State private var scheduleType = "interval"
    @State private var cronExpression = "0 0 * * *"
    @State private var intervalMinutes = 60
    @State private var timezone = TimeZone.current.identifier
    @State private var isCreating = false
    @State private var errorMessage: String?

    let onCreate: () -> Void

    var body: some View {
        NavigationStack {
            Form {
                Section("Basic Information") {
                    TextField("Name", text: $name)

                    Picker("Workflow", selection: $selectedWorkflowId) {
                        Text("Select workflow...").tag("")
                        ForEach(workflowStore.workflows) { workflow in
                            Text(workflow.name).tag(workflow.id)
                        }
                    }
                }

                Section("Schedule") {
                    Picker("Type", selection: $scheduleType) {
                        Text("Interval").tag("interval")
                        Text("Cron").tag("cron")
                        Text("One-time").tag("once")
                    }

                    if scheduleType == "interval" {
                        Stepper("Every \(intervalMinutes) minutes", value: $intervalMinutes, in: 1...1440)
                    } else if scheduleType == "cron" {
                        TextField("Cron Expression", text: $cronExpression)
                        Text("e.g., '0 0 * * *' for daily at midnight")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    Picker("Timezone", selection: $timezone) {
                        ForEach(TimeZone.knownTimeZoneIdentifiers, id: \.self) { timezoneID in
                            Text(timezoneID).tag(timezoneID)
                        }
                    }
                }

                if let error = errorMessage {
                    Section {
                        Text(error)
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("New Schedule")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }

                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        createSchedule()
                    }
                    .disabled(name.isEmpty || selectedWorkflowId.isEmpty || isCreating)
                }
            }
        }
        .frame(minWidth: 400, minHeight: 350)
    }

    private func createSchedule() {
        guard !isCreating else { return }
        isCreating = true
        errorMessage = nil

        Task {
            do {
                let config = ScheduleConfigRequest(
                    scheduleType: scheduleType,
                    cronExpression: scheduleType == "cron" ? cronExpression : nil,
                    intervalSeconds: scheduleType == "interval" ? intervalMinutes * 60 : nil,
                    runAt: nil,
                    timezone: timezone,
                    startDate: nil,
                    endDate: nil,
                    maxRuns: nil
                )

                let request = CreateScheduleRequest(
                    name: name,
                    workflowId: selectedWorkflowId,
                    config: config,
                    inputs: [:],
                    useBatch: false,
                    batchItems: [],
                    maxConcurrent: 1
                )

                let automationService = AutomationService(apiClient: apiClient)
                _ = try await automationService.createSchedule(request: request)

                logger.info("Created schedule: \(name)")
                onCreate()
                dismiss()
            } catch {
                logger.error("Failed to create schedule: \(error.localizedDescription)")
                errorMessage = error.localizedDescription
            }
            isCreating = false
        }
    }
}
