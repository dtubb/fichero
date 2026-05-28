import AppKit
import OSLog
import SwiftUI
import WebKit

private let logger = Logger(subsystem: "com.fichero.fichero", category: "ResearchBrowserPane")

// TRUST BOUNDARY — CAPABILITY ISOLATION
// The WKWebView in this pane has free internet egress (user-controlled browser).
// Its only crossing point INTO the library is saveToLibrary(), which sends
// {url, project_id, folder_id} to POST /api/research/tools/browser-save.
// No library document content, KG data, or user corpus ever flows outward through
// this pane. If an AI sub-agent is added to drive browsing, it must be isolated:
// internet-only tools (search/fetch/navigate), no library-read or KG-read tools.
// See research_tools.py module docstring for the full data-diode contract.

// MARK: - WKWebView representable

struct WebBrowserView: NSViewRepresentable {
    @Binding var urlString: String
    @Binding var pageTitle: String
    @Binding var isLoading: Bool

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        context.coordinator.webView = webView
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        let target = context.coordinator.lastLoadedURL
        if target != urlString, let url = URL(string: urlString), url.scheme != nil {
            context.coordinator.lastLoadedURL = urlString
            webView.load(URLRequest(url: url))
        }
    }

    @MainActor
    class Coordinator: NSObject, WKNavigationDelegate {
        var parent: WebBrowserView
        weak var webView: WKWebView?
        var lastLoadedURL: String = ""

        init(_ parent: WebBrowserView) {
            self.parent = parent
        }

        func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
            parent.isLoading = true
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            parent.isLoading = false
            parent.pageTitle = webView.title ?? ""
            if let currentURL = webView.url?.absoluteString {
                lastLoadedURL = currentURL
                parent.urlString = currentURL
            }
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: any Error) {
            parent.isLoading = false
        }
    }
}

// MARK: - Browser Pane

struct ResearchBrowserPane: View {
    var project: ResearchProject
    @EnvironmentObject var researchService: ResearchService

    @State private var urlString: String = "https://www.google.com"
    @State private var addressBarText: String = "https://www.google.com"
    @State private var pageTitle: String = ""
    @State private var isLoading = false
    @State private var isSaving = false
    @State private var saveMessage: String?

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()
            WebBrowserView(urlString: $urlString, pageTitle: $pageTitle, isLoading: $isLoading)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var toolbar: some View {
        HStack(spacing: 8) {
            TextField("URL", text: $addressBarText)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color(NSColor.controlBackgroundColor))
                .clipShape(RoundedRectangle(cornerRadius: 6))
                .onSubmit { navigate() }

            if isLoading {
                ProgressView().scaleEffect(0.7)
            }

            saveButton
        }
        .padding(.horizontal, 10)
        .frame(height: 36)
    }

    private var saveButton: some View {
        Button {
            Task { await saveToLibrary() }
        } label: {
            HStack(spacing: 4) {
                if isSaving {
                    ProgressView().scaleEffect(0.6)
                } else {
                    Image(systemName: "arrow.down.doc")
                }
                Text("Save to Library")
                    .font(.system(size: 12))
            }
        }
        .buttonStyle(.bordered)
        .controlSize(.small)
        .disabled(isSaving || urlString.isEmpty)
        .help("Download this page or file into your Fichero library")
        .overlay(saveMessageOverlay, alignment: .bottom)
    }

    @ViewBuilder
    private var saveMessageOverlay: some View {
        if let msg = saveMessage {
            Text(msg)
                .font(.caption2)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(.thinMaterial)
                .clipShape(RoundedRectangle(cornerRadius: 4))
                .offset(y: 20)
        }
    }

    private func navigate() {
        var raw = addressBarText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !raw.contains("://") {
            raw = "https://" + raw
        }
        urlString = raw
        addressBarText = raw
    }

    private func saveToLibrary() async {
        guard !urlString.isEmpty else { return }
        isSaving = true
        saveMessage = nil
        do {
            let result = try await researchService.browserSave(
                url: urlString,
                projectId: project.id,
                suggestedName: pageTitle.isEmpty ? nil : pageTitle,
                parentFolderId: project.libraryDestinationFolderId
            )
            if result.success {
                saveMessage = "Saved: \(result.documentName ?? "document")"
                logger.info("Browser save succeeded: \(result.documentId ?? "?")")
            } else {
                saveMessage = "Error: \(result.error ?? "unknown")"
            }
        } catch {
            saveMessage = "Error: \(error.localizedDescription)"
        }
        isSaving = false
        // Clear the message after a few seconds
        try? await Task.sleep(for: .seconds(3))
        saveMessage = nil
    }
}
