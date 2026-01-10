import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "AutomationView")

/// Main automation view showing schedules and file triggers
struct AutomationView: View {
    @EnvironmentObject var apiClient: APIClient

    @State private var selectedTab: AutomationTab = .schedules
    @State private var schedules: [ScheduleInfo] = []
    @State private var triggers: [TriggerInfo] = []
    @State private var isLoading = false
    @State private var showingAddSheet = false

    private var automationService: AutomationService { AutomationService(apiClient: apiClient) }

    enum AutomationTab: String, CaseIterable {
        case schedules = "Schedules"
        case triggers = "File Triggers"
    }

    var body: some View {
        VStack(spacing: 0) {
            // Tab picker
            Picker("View", selection: $selectedTab) {
                ForEach(AutomationTab.allCases, id: \.self) { tab in
                    Text(tab.rawValue).tag(tab)
                }
            }
            .pickerStyle(.segmented)
            .padding()

            // Content
            switch selectedTab {
            case .schedules:
                schedulesView
            case .triggers:
                triggersView
            }
        }
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Button {
                    showingAddSheet = true
                } label: {
                    Image(systemName: "plus")
                }
            }

            ToolbarItem(placement: .automatic) {
                Button {
                    Task { await refresh() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .disabled(isLoading)
            }
        }
        .task {
            guard !Task.isCancelled else { return }
            await refresh()
        }
        .sheet(isPresented: $showingAddSheet) {
            if selectedTab == .schedules {
                AddScheduleSheet(onSave: { _ in
                    Task { await refresh() }
                })
            } else {
                AddTriggerSheet(onSave: { _ in
                    Task { await refresh() }
                })
            }
        }
    }

    // MARK: - Schedules View

    @ViewBuilder
    private var schedulesView: some View {
        if isLoading && schedules.isEmpty {
            ProgressView("Loading schedules...")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if schedules.isEmpty {
            ContentUnavailableView(
                "No Schedules",
                systemImage: "calendar.badge.clock",
                description: Text("Create a schedule to run workflows automatically")
            )
        } else {
            List(schedules) { schedule in
                ScheduleRowView(
                    schedule: schedule,
                    onAction: { action in
                        Task { await handleScheduleAction(schedule, action: action) }
                    }
                )
            }
        }
    }

    // MARK: - Triggers View

    @ViewBuilder
    private var triggersView: some View {
        if isLoading && triggers.isEmpty {
            ProgressView("Loading triggers...")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if triggers.isEmpty {
            ContentUnavailableView(
                "No File Triggers",
                systemImage: "folder.badge.gearshape",
                description: Text("Create a trigger to run workflows when files change")
            )
        } else {
            List(triggers) { trigger in
                TriggerRowView(
                    trigger: trigger,
                    onAction: { action in
                        Task { await handleTriggerAction(trigger, action: action) }
                    }
                )
            }
        }
    }

    // MARK: - Actions

    private func refresh() async {
        isLoading = true
        defer { isLoading = false }

        do {
            async let schedulesTask = automationService.listSchedules()
            async let triggersTask = automationService.listTriggers()

            let (newSchedules, newTriggers) = try await (schedulesTask, triggersTask)
            schedules = newSchedules
            triggers = newTriggers
        } catch {
            logger.error("Failed to refresh automation data: \(String(describing: error))")
        }
    }

    private func handleScheduleAction(_ schedule: ScheduleInfo, action: ScheduleAction) async {
        do {
            switch action {
            case .pause:
                _ = try await automationService.pauseSchedule(scheduleId: schedule.scheduleId)
            case .resume:
                _ = try await automationService.resumeSchedule(scheduleId: schedule.scheduleId)
            case .trigger:
                _ = try await automationService.triggerSchedule(scheduleId: schedule.scheduleId)
            case .delete:
                try await automationService.deleteSchedule(scheduleId: schedule.scheduleId)
            }
            await refresh()
        } catch {
            logger.error("Schedule action failed: \(String(describing: error))")
        }
    }

    private func handleTriggerAction(_ trigger: TriggerInfo, action: TriggerAction) async {
        do {
            switch action {
            case .pause:
                _ = try await automationService.pauseTrigger(triggerId: trigger.triggerId)
            case .resume:
                _ = try await automationService.resumeTrigger(triggerId: trigger.triggerId)
            case .delete:
                try await automationService.deleteTrigger(triggerId: trigger.triggerId)
            }
            await refresh()
        } catch {
            logger.error("Trigger action failed: \(String(describing: error))")
        }
    }
}

// MARK: - Action Types

enum ScheduleAction {
    case pause
    case resume
    case trigger
    case delete
}

enum TriggerAction {
    case pause
    case resume
    case delete
}

// MARK: - Schedule Row View

struct ScheduleRowView: View {
    let schedule: ScheduleInfo
    let onAction: (ScheduleAction) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: schedule.statusIcon)
                    .foregroundColor(colorForStatus(schedule.status))

                Text(schedule.name)
                    .font(.headline)

                Spacer()

                Text(schedule.status.uppercased())
                    .font(.caption)
                    .fontWeight(.medium)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(colorForStatus(schedule.status).opacity(0.2))
                    .foregroundColor(colorForStatus(schedule.status))
                    .cornerRadius(4)
            }

            HStack(spacing: 16) {
                Label(schedule.scheduleDescription, systemImage: scheduleTypeIcon(schedule.scheduleType))
                    .font(.caption)
                    .foregroundColor(.secondary)

                if let nextRun = schedule.nextRunAt {
                    Label(nextRun, systemImage: "clock")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                Text("\(schedule.runCount) runs")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            if let error = schedule.errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundColor(.red)
                    .lineLimit(1)
            }

            // Actions
            HStack {
                Spacer()

                if schedule.status == "active" {
                    Button("Pause") { onAction(.pause) }
                        .buttonStyle(.bordered)

                    Button("Run Now") { onAction(.trigger) }
                        .buttonStyle(.bordered)
                } else if schedule.status == "paused" {
                    Button("Resume") { onAction(.resume) }
                        .buttonStyle(.bordered)
                }

                Button("Delete") { onAction(.delete) }
                    .buttonStyle(.bordered)
                    .tint(.red)
            }
        }
        .padding(.vertical, 8)
    }

    private func colorForStatus(_ status: String) -> Color {
        switch status {
        case "active": return .green
        case "paused": return .yellow
        case "completed": return .gray
        case "error": return .red
        default: return .primary
        }
    }

    private func scheduleTypeIcon(_ type: String) -> String {
        switch type {
        case "cron": return "calendar.badge.clock"
        case "interval": return "repeat"
        case "once": return "calendar"
        default: return "clock"
        }
    }
}

// MARK: - Trigger Row View

struct TriggerRowView: View {
    let trigger: TriggerInfo
    let onAction: (TriggerAction) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: trigger.statusIcon)
                    .foregroundColor(colorForStatus(trigger.status))

                Text(trigger.name)
                    .font(.headline)

                Spacer()

                Text(trigger.status.uppercased())
                    .font(.caption)
                    .fontWeight(.medium)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(colorForStatus(trigger.status).opacity(0.2))
                    .foregroundColor(colorForStatus(trigger.status))
                    .cornerRadius(4)
            }

            HStack(spacing: 16) {
                Label(trigger.watchPath, systemImage: "folder")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .lineLimit(1)

                Label(trigger.eventsDescription, systemImage: "bolt")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Text("\(trigger.triggerCount) triggered")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            HStack(spacing: 16) {
                Label(trigger.filterDescription, systemImage: "doc.text.magnifyingglass")
                    .font(.caption)
                    .foregroundColor(.secondary)

                if trigger.recursive {
                    Label("Recursive", systemImage: "arrow.triangle.branch")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }

            if let error = trigger.errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundColor(.red)
                    .lineLimit(1)
            }

            // Actions
            HStack {
                Spacer()

                if trigger.status == "active" {
                    Button("Pause") { onAction(.pause) }
                        .buttonStyle(.bordered)
                } else if trigger.status == "paused" {
                    Button("Resume") { onAction(.resume) }
                        .buttonStyle(.bordered)
                }

                Button("Delete") { onAction(.delete) }
                    .buttonStyle(.bordered)
                    .tint(.red)
            }
        }
        .padding(.vertical, 8)
    }

    private func colorForStatus(_ status: String) -> Color {
        switch status {
        case "active": return .green
        case "paused": return .yellow
        case "error": return .red
        default: return .primary
        }
    }
}

// MARK: - Add Schedule Sheet

struct AddScheduleSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var apiClient: APIClient

    let onSave: (ScheduleInfo) -> Void

    @State private var name = ""
    @State private var workflowId = ""
    @State private var scheduleType = "interval"
    @State private var cronExpression = "0 9 * * *"
    @State private var intervalMinutes = 60
    @State private var timezone = "UTC"
    @State private var isLoading = false
    @State private var errorMessage: String?

    private var automationService: AutomationService { AutomationService(apiClient: apiClient) }

    var body: some View {
        NavigationStack {
            Form {
                Section("Basic") {
                    TextField("Name", text: $name)
                    TextField("Workflow ID", text: $workflowId)
                }

                Section("Schedule") {
                    Picker("Type", selection: $scheduleType) {
                        Text("Interval").tag("interval")
                        Text("Cron").tag("cron")
                        Text("One-time").tag("once")
                    }

                    if scheduleType == "cron" {
                        TextField("Cron Expression", text: $cronExpression)
                        Text("Example: 0 9 * * 1 (Monday 9am)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else if scheduleType == "interval" {
                        Stepper("Every \(intervalMinutes) minutes", value: $intervalMinutes, in: 1...1440)
                    }

                    TextField("Timezone", text: $timezone)
                }

                if let error = errorMessage {
                    Section {
                        Text(error)
                            .foregroundColor(.red)
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
                        Task { await createSchedule() }
                    }
                    .disabled(name.isEmpty || workflowId.isEmpty || isLoading)
                }
            }
        }
        .frame(minWidth: 400, minHeight: 350)
    }

    private func createSchedule() async {
        isLoading = true
        errorMessage = nil

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
            workflowId: workflowId,
            config: config,
            inputs: [:],
            useBatch: false,
            batchItems: [],
            maxConcurrent: 5
        )

        do {
            let schedule = try await automationService.createSchedule(request: request)
            onSave(schedule)
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }
}

// MARK: - Add Trigger Sheet

struct AddTriggerSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var apiClient: APIClient

    let onSave: (TriggerInfo) -> Void

    @State private var name = ""
    @State private var workflowId = ""
    @State private var watchPath = ""
    @State private var recursive = true
    @State private var events: Set<String> = ["created"]
    @State private var filterMode = "glob"
    @State private var filterPattern = "*.pdf"
    @State private var debounceSeconds = 1.0
    @State private var batchDelaySeconds = 5.0
    @State private var isLoading = false
    @State private var errorMessage: String?

    private var automationService: AutomationService { AutomationService(apiClient: apiClient) }

    var body: some View {
        NavigationStack {
            Form {
                Section("Basic") {
                    TextField("Name", text: $name)
                    TextField("Workflow ID", text: $workflowId)
                }

                Section("Watch Location") {
                    TextField("Folder Path", text: $watchPath)
                    Toggle("Watch Subdirectories", isOn: $recursive)
                }

                Section("Events") {
                    Toggle("File Created", isOn: Binding(
                        get: { events.contains("created") },
                        set: { if $0 { events.insert("created") } else { events.remove("created") } }
                    ))
                    Toggle("File Modified", isOn: Binding(
                        get: { events.contains("modified") },
                        set: { if $0 { events.insert("modified") } else { events.remove("modified") } }
                    ))
                    Toggle("File Deleted", isOn: Binding(
                        get: { events.contains("deleted") },
                        set: { if $0 { events.insert("deleted") } else { events.remove("deleted") } }
                    ))
                }

                Section("Filter") {
                    Picker("Filter Mode", selection: $filterMode) {
                        Text("Glob").tag("glob")
                        Text("Regex").tag("regex")
                        Text("Extension").tag("extension")
                    }
                    TextField("Pattern", text: $filterPattern)
                }

                Section("Timing") {
                    Stepper("Debounce: \(String(format: "%.1f", debounceSeconds))s", value: $debounceSeconds, in: 0.1...10.0, step: 0.5)
                    Stepper("Batch Delay: \(String(format: "%.1f", batchDelaySeconds))s", value: $batchDelaySeconds, in: 1.0...60.0, step: 1.0)
                }

                if let error = errorMessage {
                    Section {
                        Text(error)
                            .foregroundColor(.red)
                    }
                }
            }
            .navigationTitle("New File Trigger")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        Task { await createTrigger() }
                    }
                    .disabled(name.isEmpty || workflowId.isEmpty || watchPath.isEmpty || isLoading)
                }
            }
        }
        .frame(minWidth: 400, minHeight: 500)
    }

    private func createTrigger() async {
        isLoading = true
        errorMessage = nil

        let config = TriggerConfigRequest(
            watchPath: watchPath,
            recursive: recursive,
            events: Array(events),
            filterMode: filterMode,
            filterPattern: filterPattern,
            filterExtensions: [],
            excludePatterns: [],
            debounceSeconds: debounceSeconds,
            batchDelaySeconds: batchDelaySeconds
        )

        let request = CreateTriggerRequest(
            name: name,
            workflowId: workflowId,
            config: config,
            inputsTemplate: ["file_path": "{file_path}"],
            useBatch: true,
            maxConcurrent: 5
        )

        do {
            let trigger = try await automationService.createTrigger(request: request)
            onSave(trigger)
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }
}

#Preview {
    AutomationView()
        .environmentObject(APIClient())
}
