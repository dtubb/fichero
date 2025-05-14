//
//  ContentView.swift
//  fichero
//
//  Created by Daniel Tubb on 2025-05-11.
//

import SwiftUI
import Yams

struct LogEntry: Identifiable {
    let id = UUID()
    let timestamp: String
    let event: String
    let workflow: String?
    let step: String?
    let status: String?
    let message: String?
}

struct ContentView: View {
    @State private var projectFolder: URL?
    @State private var workflows: [String] = []
    @State private var selectedWorkflow: String?
    @State private var isRunning = false
    @State private var statusMessage: String = "Ready"
    @State private var showLog = false
    @State private var showManifest = false

    var body: some View {
        ZStack {
            Color(.windowBackgroundColor)
                .ignoresSafeArea()
            VStack(spacing: 0) {
                Spacer().frame(height: 40)
                HStack(alignment: .center, spacing: 0) {
                    // Icon
                    Group {
                        if let folder = projectFolder {
                            Image(nsImage: NSWorkspace.shared.icon(forFile: folder.path))
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .frame(width: 64, height: 64)
                                .padding(.leading, 32)
                        } else {
                            Image(systemName: "folder.questionmark")
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .frame(width: 64, height: 64)
                                .foregroundColor(.gray)
                                .padding(.leading, 32)
                        }
                    }
                    // Chooser and info
                    VStack(spacing: 16) {
                        Button(action: pickFolder) {
                            Text(projectFolder == nil ? "Choose Project…" : "Change Project…")
                                .font(.title2.bold())
                                .padding(.vertical, 12)
                                .padding(.horizontal, 36)
                                .background(Color(NSColor.controlBackgroundColor))
                                .cornerRadius(8)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 8)
                                        .stroke(Color.gray.opacity(0.3), lineWidth: 1)
                                )
                        }
                        if let folder = projectFolder {
                            Text(folder.lastPathComponent)
                                .font(.title3)
                                .foregroundColor(.primary)
                                .padding(.top, 2)
                        }
                        if workflows.count > 1 {
                            Picker("Workflow", selection: $selectedWorkflow) {
                                ForEach(workflows, id: \ .self) { wf in
                                    Text(wf)
                                }
                            }
                            .pickerStyle(MenuPickerStyle())
                            .frame(width: 220)
                        }
                        Button(action: runWorkflow) {
                            Text(isRunning ? "Running…" : "Run")
                                .font(.title2)
                                .frame(maxWidth: .infinity)
                        }
                        .disabled(isRunning || selectedWorkflow == nil)
                        .padding(.top, 8)
                        .padding(.horizontal, 36)
                        .padding(.vertical, 8)
                        .background(isRunning || selectedWorkflow == nil ? Color.gray.opacity(0.3) : Color.accentColor)
                        .foregroundColor(.white)
                        .cornerRadius(8)
                        Text(statusMessage)
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                            .padding(.top, 4)
                    }
                    .padding(.horizontal, 40)
                    Spacer()
                }
                .frame(height: 160)
                .background(
                    RoundedRectangle(cornerRadius: 18)
                        .fill(Color.gray.opacity(0.12))
                        .shadow(radius: 2)
                )
                .padding(.horizontal, 120)
                .padding(.bottom, 32)
                // Description
                VStack(alignment: .leading, spacing: 12) {
                    Text("Fichero searches for documents in your project folder and processes them using advanced AI workflows. It can crop, split, enhance, remove backgrounds, and transcribe text from archival images, then export them to Word documents with side-by-side layout.")
                        .font(.body)
                        .foregroundColor(.primary)
                        .padding(.top, 32)
                    Text("To start, choose a project folder using the button above. Then select a workflow and click Run.")
                        .font(.callout)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: 700)
                .padding(.top, 16)
                Spacer()
            }
            .frame(width: 165.5, height: 107.5)
        }
        .toolbar {
            ToolbarItemGroup(placement: .automatic) {
                Button("Show Log") { showLog = true }
                Button("Show Manifest") { showManifest = true }
            }
        }
        .sheet(isPresented: $showLog) {
            Text("Log window coming soon!")
                .frame(width: 400, height: 300)
        }
        .sheet(isPresented: $showManifest) {
            Text("Manifest window coming soon!")
                .frame(width: 400, height: 300)
        }
    }

    // MARK: - Folder Picker
    func pickFolder() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK {
            projectFolder = panel.url
            loadWorkflows()
        }
    }

    // MARK: - Load Workflows from project.yml
    func loadWorkflows() {
        guard let folder = projectFolder else { return }
        let ymlURL = folder.appendingPathComponent("project.yml")
        do {
            let ymlString = try String(contentsOf: ymlURL)
            if let dict = try Yams.load(yaml: ymlString) as? [String: Any],
               let wfs = dict["workflows"] as? [String: Any] {
                workflows = Array(wfs.keys)
                selectedWorkflow = workflows.first
            }
            statusMessage = "Ready to run"
        } catch {
            workflows = []
            selectedWorkflow = nil
            statusMessage = "No workflows found in project.yml"
        }
    }

    // MARK: - Run Workflow
    func runWorkflow() {
        guard let folder = projectFolder, let workflow = selectedWorkflow else { return }
        isRunning = true
        statusMessage = "Running…"

        let pythonPath = "/usr/bin/python3" // Adjust if needed
        let cliPath = folder.appendingPathComponent("../fichero_cli/fichero_cli.py").standardized.path
        let ymlPath = folder.appendingPathComponent("project.yml").path
        let logPath = folder.appendingPathComponent("fichero_cli.log").path
        let manifestPath = folder.appendingPathComponent("manifest.jsonl").path

        let process = Process()
        process.executableURL = URL(fileURLWithPath: pythonPath)
        process.arguments = [cliPath, "run-workflow", ymlPath, workflow, "--log-file", logPath, "--manifest-file", manifestPath]

        do {
            try process.run()
            statusMessage = "Running workflow: \(workflow)"
        } catch {
            statusMessage = "Failed to launch CLI: \(error.localizedDescription)"
            isRunning = false
            return
        }

        // Optionally, you can poll for completion and update statusMessage/isRunning
        // For now, just simulate completion after a delay
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            self.isRunning = false
            self.statusMessage = "Done!"
        }
    }
}

#Preview {
    ContentView()
}
