import SwiftUI

// MARK: - Creation Buttons

/// Button that creates a new search
struct FocusedNewSearchButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions
    let featureManager = FeatureManager.shared

    var body: some View {
        if featureManager.isSearchEnabled {
            Button("New Search") {
                sidebarActions?.createSearch()
            }
            .keyboardShortcut("n", modifiers: [.command, .option])
            .disabled(sidebarActions == nil)
        }
    }
}

/// Button that creates a new chat
struct FocusedNewChatButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions
    let featureManager = FeatureManager.shared

    var body: some View {
        Button(featureManager.badgedLabel("New Chat", for: .chat)) {
            sidebarActions?.createChat()
        }
        .keyboardShortcut("n", modifiers: [.command, .control])
        .disabled(sidebarActions == nil)
    }
}

/// Button that creates a new workflow
struct FocusedNewWorkflowButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions

    var body: some View {
        Button("New Workflow") {
            sidebarActions?.createWorkflow()
        }
        .keyboardShortcut("n", modifiers: [.command, .control, .shift])
        .disabled(sidebarActions == nil)
    }
}

/// Button that creates a new chain
struct FocusedNewChainButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions

    var body: some View {
        Button("New Chain") {
            sidebarActions?.createChain()
        }
        .disabled(sidebarActions == nil)
    }
}

/// Button that creates a new comparison
struct FocusedNewComparisonButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions

    var body: some View {
        Button("New Comparison") {
            sidebarActions?.createComparison()
        }
        .disabled(sidebarActions == nil)
    }
}

/// Button that creates a new schedule
struct FocusedNewScheduleButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions
    let featureManager = FeatureManager.shared

    var body: some View {
        Button(featureManager.badgedLabel("New Schedule", for: .automation)) {
            sidebarActions?.createSchedule()
        }
        .disabled(sidebarActions == nil)
    }
}
