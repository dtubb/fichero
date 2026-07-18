import OSLog
import SwiftUI

// MARK: - Schedule Type Fields

extension ScheduleEditorView {
    @ViewBuilder
    var scheduleTypeFields: some View {
        switch scheduleType {
        case "interval":
            VStack(alignment: .leading, spacing: 8) {
                Stepper("Every \(intervalMinutes) minutes", value: $intervalMinutes, in: 1...1440)

                Text(formatInterval(intervalMinutes * 60))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

        case "cron":
            VStack(alignment: .leading, spacing: 8) {
                TextField("Cron Expression", text: $cronExpression)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(.body, design: .monospaced))

                Text(describeCron(cronExpression))
                    .font(.caption)
                    .foregroundStyle(.secondary)

                cronPresets
            }

        case "once":
            DatePicker("Run At", selection: $runAtDate, displayedComponents: [.date, .hourAndMinute])

        default:
            EmptyView()
        }
    }

    @ViewBuilder
    var cronPresets: some View {
        HStack(spacing: 8) {
            ForEach(cronPresetOptions, id: \.cron) { preset in
                Button(preset.label) {
                    cronExpression = preset.cron
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        }
    }

    @ViewBuilder
    var advancedOptions: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Date range
            Toggle("Start Date", isOn: Binding(
                get: { startDate != nil },
                set: { startDate = $0 ? Date() : nil }
            ))

            if startDate != nil {
                DatePicker("", selection: Binding(
                    get: { startDate ?? Date() },
                    set: { startDate = $0 }
                ), displayedComponents: [.date, .hourAndMinute])
            }

            Toggle("End Date", isOn: Binding(
                get: { endDate != nil },
                set: { endDate = $0 ? Date().addingTimeInterval(86400 * 30) : nil }
            ))

            if endDate != nil {
                DatePicker("", selection: Binding(
                    get: { endDate ?? Date() },
                    set: { endDate = $0 }
                ), displayedComponents: [.date, .hourAndMinute])
            }

            // Max runs
            Toggle("Maximum Runs", isOn: Binding(
                get: { maxRuns != nil },
                set: { maxRuns = $0 ? 100 : nil }
            ))

            if maxRuns != nil {
                Stepper("Max \(maxRuns ?? 100) runs", value: Binding(
                    get: { maxRuns ?? 100 },
                    set: { maxRuns = $0 }
                ), in: 1...10000)
            }

            Divider()

            // Batch settings
            Toggle("Batch Mode", isOn: $useBatch)

            if useBatch {
                Stepper("Max \(maxConcurrent) concurrent", value: $maxConcurrent, in: 1...100)
                    .padding(.leading)
            }
        }
    }
}

// MARK: - Preview Panel

extension ScheduleEditorView {
    @ViewBuilder
    var previewPanel: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Schedule Preview
                VStack(alignment: .leading, spacing: 12) {
                    Text("Schedule Preview")
                        .font(.headline)

                    if !name.isEmpty {
                        previewField("Name", name)
                    }

                    if let workflow = workflowStore.workflows.first(where: { $0.id == selectedWorkflowId }) {
                        previewField("Workflow", workflow.name)
                    }

                    previewField("Type", scheduleType.capitalized)

                    switch scheduleType {
                    case "interval":
                        previewField("Runs", "Every \(formatInterval(intervalMinutes * 60))")
                    case "cron":
                        previewField("Cron", cronExpression)
                        previewField("Description", describeCron(cronExpression))
                    case "once":
                        previewField("Run At", runAtDate.formatted())
                    default:
                        EmptyView()
                    }

                    previewField("Timezone", timezone)

                    if useBatch {
                        previewField("Batch Mode", "Enabled (max \(maxConcurrent) concurrent)")
                    }
                }

                Divider()

                // Help section
                helpSection
            }
            .padding()
        }
        .background(Color(platformColor: .controlBackgroundColor))
    }

    @ViewBuilder
    func previewField(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(width: 80, alignment: .trailing)

            Text(value)
                .font(.body)
        }
    }

    @ViewBuilder
    var helpSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Cron Expression Help")
                .font(.headline)

            Text("Format: minute hour day-of-month month day-of-week")
                .font(.caption)
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 4) {
                Text("* = any value")
                Text("*/n = every n units")
                Text("n-m = range from n to m")
                Text("n,m = specific values n and m")
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
    }
}

// MARK: - Helpers

extension ScheduleEditorView {
    var commonTimezones: [String] {
        [
            "America/New_York",
            "America/Chicago",
            "America/Denver",
            "America/Los_Angeles",
            "America/Halifax",
            "America/Toronto",
            "Europe/London",
            "Europe/Paris",
            "Europe/Berlin",
            "Asia/Tokyo",
            "Asia/Shanghai",
            "Australia/Sydney",
            "UTC"
        ] + [TimeZone.current.identifier].filter { !$0.isEmpty }
    }

    var cronPresetOptions: [(label: String, cron: String)] {
        [
            ("Hourly", "0 * * * *"),
            ("Daily", "0 0 * * *"),
            ("Weekly", "0 0 * * 0"),
            ("Monthly", "0 0 1 * *")
        ]
    }

    // Thin delegates to the pure, unit-testable `ScheduleFormatting` (#1993).
    func formatInterval(_ seconds: Int) -> String {
        ScheduleFormatting.formatInterval(seconds)
    }

    func describeCron(_ cron: String) -> String {
        ScheduleFormatting.describeCron(cron)
    }
}

/// Pure schedule-formatting helpers, extracted from `ScheduleEditorView` so they
/// can be unit-tested without constructing the view (#1993). Behaviour is
/// unchanged — the view's `formatInterval` / `describeCron` now delegate here.
enum ScheduleFormatting {
    /// Human-readable interval, e.g. "45 seconds", "1 minute", "3 hours", "2 days".
    static func formatInterval(_ seconds: Int) -> String {
        if seconds < 60 {
            return "\(seconds) seconds"
        } else if seconds < 3600 {
            let mins = seconds / 60
            return "\(mins) minute\(mins == 1 ? "" : "s")"
        } else if seconds < 86400 {
            let hours = seconds / 3600
            return "\(hours) hour\(hours == 1 ? "" : "s")"
        } else {
            let days = seconds / 86400
            return "\(days) day\(days == 1 ? "" : "s")"
        }
    }

    /// Plain-language description of a 5-field cron expression for common
    /// patterns; "Invalid cron expression" for the wrong field count and
    /// "Custom schedule" for anything not specially recognised.
    static func describeCron(_ cron: String) -> String {
        let parts = cron.split(separator: " ")
        guard parts.count == 5 else { return "Invalid cron expression" }

        // Simple descriptions for common patterns
        let (minute, hour, dom, month, dow) = (parts[0], parts[1], parts[2], parts[3], parts[4])

        if minute == "0" && hour == "*" && dom == "*" && month == "*" && dow == "*" {
            return "Every hour at minute 0"
        }
        if minute == "0" && hour == "0" && dom == "*" && month == "*" && dow == "*" {
            return "Every day at midnight"
        }
        if minute == "0" && hour == "0" && dom == "*" && month == "*" && dow == "0" {
            return "Every Sunday at midnight"
        }
        if minute == "0" && hour == "0" && dom == "1" && month == "*" && dow == "*" {
            return "First day of every month at midnight"
        }

        return "Custom schedule"
    }
}

// MARK: - Actions

extension ScheduleEditorView {
    func populateFromExisting() {
        guard let schedule = existingSchedule else { return }

        name = schedule.name
        selectedWorkflowId = schedule.workflowId
        scheduleType = schedule.scheduleType
        timezone = schedule.timezone
        useBatch = schedule.useBatch
        maxConcurrent = schedule.maxConcurrent

        if let cron = schedule.cronExpression {
            cronExpression = cron
        }

        if let interval = schedule.intervalSeconds {
            intervalMinutes = interval / 60
        }
    }

    func saveSchedule() async {
        guard isValid else { return }
        isSaving = true
        error = nil

        do {
            let config = ScheduleConfigRequest(
                scheduleType: scheduleType,
                cronExpression: scheduleType == "cron" ? cronExpression : nil,
                intervalSeconds: scheduleType == "interval" ? intervalMinutes * 60 : nil,
                runAt: scheduleType == "once" ? ISO8601DateFormatter().string(from: runAtDate) : nil,
                timezone: timezone,
                startDate: startDate.map { ISO8601DateFormatter().string(from: $0) },
                endDate: endDate.map { ISO8601DateFormatter().string(from: $0) },
                maxRuns: maxRuns
            )

            let request = CreateScheduleRequest(
                name: name,
                workflowId: selectedWorkflowId,
                config: config,
                inputs: [:],
                useBatch: useBatch,
                batchItems: [],
                maxConcurrent: maxConcurrent
            )

            let service = AutomationService(apiClient: apiClient)
            let savedSchedule = try await service.createSchedule(request: request)

            scheduleEditorLogger.info("Saved schedule: \(name)")

            // Callback for parent to refresh (SidebarView manages data via Combine)
            onSave?(savedSchedule)

        } catch {
            scheduleEditorLogger.error("Failed to save schedule: \(error.localizedDescription)")
            self.error = error.localizedDescription
        }

        isSaving = false
    }
}
