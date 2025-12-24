import SwiftUI
import Quartz
import PDFKit

/// Document preview/editor view
struct EditorView: View {
    let document: Document?

    var body: some View {
        Group {
            if let doc = document {
                documentPreview(doc)
            } else {
                emptyState
            }
        }
        .frame(minWidth: 300)
    }

    // MARK: - Document Preview

    @ViewBuilder
    private func documentPreview(_ doc: Document) -> some View {
        VStack(spacing: 0) {
            // Header bar
            headerBar(doc)

            Divider()

            // Preview content based on file type
            previewContent(doc)
        }
    }

    // MARK: - Header Bar

    private func headerBar(_ doc: Document) -> some View {
        HStack {
            // Icon and name
            Image(systemName: doc.fileType?.icon ?? doc.docType.icon)
                .foregroundColor(.accentColor)

            Text(doc.name)
                .font(.headline)
                .lineLimit(1)

            Spacer()

            // Actions
            HStack(spacing: 12) {
                Button(action: { openInFinder(doc) }) {
                    Image(systemName: "folder")
                }
                .buttonStyle(.plain)
                .help("Reveal in Finder")

                Button(action: { openWithDefault(doc) }) {
                    Image(systemName: "arrow.up.forward.square")
                }
                .buttonStyle(.plain)
                .help("Open with default app")
            }
        }
        .padding()
        .background(Color(.windowBackgroundColor))
    }

    // MARK: - Preview Content

    @ViewBuilder
    private func previewContent(_ doc: Document) -> some View {
        // Use Quick Look for all file types - downloads from API to temp location
        QuickLookDownloadView(document: doc)
    }

    // MARK: - Text Preview

    private func textPreview(_ doc: Document) -> some View {
        ScrollView {
            if let content = doc.pageContent {
                Text(content)
                    .font(.system(.body, design: .monospaced))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding()
            } else {
                Text("No content available")
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(Color(.textBackgroundColor))
    }

    // MARK: - Generic Preview

    private func genericPreview(_ doc: Document) -> some View {
        VStack(spacing: 16) {
            Image(systemName: doc.fileType?.icon ?? "doc")
                .font(.system(size: 64))
                .foregroundColor(.secondary)

            Text(doc.name)
                .font(.headline)

            if let fileType = doc.fileType {
                Text(fileType.rawValue.uppercased())
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.secondary.opacity(0.2))
                    .cornerRadius(4)
            }

            // Show content if available
            if let content = doc.pageContent {
                ScrollView {
                    Text(content)
                        .font(.body)
                        .padding()
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 200)
                .background(Color(.textBackgroundColor))
                .cornerRadius(8)
                .padding(.horizontal)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 48))
                .foregroundColor(.secondary)

            Text("No Document Selected")
                .font(.headline)

            Text("Double-click a document to preview")
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Actions

    private func openInFinder(_ doc: Document) {
        guard let path = doc.path else { return }
        let url = URL(fileURLWithPath: path)
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }

    private func openWithDefault(_ doc: Document) {
        guard let path = doc.path else { return }
        let url = URL(fileURLWithPath: path)
        NSWorkspace.shared.open(url)
    }
}

// MARK: - Zoomable Image View (with pinch/scroll zoom and pan)

struct ZoomableImageView: View {
    let document: Document

    @State private var scale: CGFloat = 1.0
    @State private var lastScale: CGFloat = 1.0
    @State private var offset: CGSize = .zero
    @State private var lastOffset: CGSize = .zero

    private let minScale: CGFloat = 0.5
    private let maxScale: CGFloat = 5.0

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Checkerboard background
                CheckerboardPattern()
                    .opacity(0.1)

                // Load from local path if available, otherwise from API
                if let path = document.path {
                    // Local file
                    if let nsImage = NSImage(contentsOfFile: path) {
                        Image(nsImage: nsImage)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .scaleEffect(scale)
                            .offset(offset)
                            .gesture(zoomGesture)
                            .gesture(panGesture)
                            .onTapGesture(count: 2) { toggleZoom(in: geometry.size) }
                    } else {
                        failedView
                    }
                } else {
                    // Remote API
                    AsyncImage(url: APIClient.shared.displayURL(for: document.id)) { phase in
                        switch phase {
                        case .empty:
                            loadingView
                        case .success(let image):
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .scaleEffect(scale)
                                .offset(offset)
                                .gesture(zoomGesture)
                                .gesture(panGesture)
                                .onTapGesture(count: 2) { toggleZoom(in: geometry.size) }
                        case .failure:
                            failedView
                        @unknown default:
                            failedView
                        }
                    }
                }
            }
            .frame(width: geometry.size.width, height: geometry.size.height)
            .clipped()
        }
        .background(Color(.textBackgroundColor))
        // Scroll wheel zoom
        .onContinuousHover { _ in } // Enable scroll events
        .background(ScrollWheelZoomView(scale: $scale, minScale: minScale, maxScale: maxScale))
    }

    // MARK: - Gestures

    private var zoomGesture: some Gesture {
        MagnificationGesture()
            .onChanged { value in
                let newScale = lastScale * value
                scale = min(max(newScale, minScale), maxScale)
            }
            .onEnded { _ in
                lastScale = scale
                // Reset offset if zoomed out
                if scale <= 1.0 {
                    withAnimation(.easeOut(duration: 0.2)) {
                        offset = .zero
                        lastOffset = .zero
                    }
                }
            }
    }

    private var panGesture: some Gesture {
        DragGesture()
            .onChanged { value in
                if scale > 1.0 {
                    offset = CGSize(
                        width: lastOffset.width + value.translation.width,
                        height: lastOffset.height + value.translation.height
                    )
                }
            }
            .onEnded { _ in
                lastOffset = offset
            }
    }

    private func toggleZoom(in size: CGSize) {
        withAnimation(.easeInOut(duration: 0.3)) {
            if scale > 1.0 {
                scale = 1.0
                lastScale = 1.0
                offset = .zero
                lastOffset = .zero
            } else {
                scale = 2.0
                lastScale = 2.0
            }
        }
    }

    // MARK: - Subviews

    private var loadingView: some View {
        VStack(spacing: 16) {
            ProgressView()
            Text("Loading image...")
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }

    private var failedView: some View {
        VStack(spacing: 16) {
            Image(systemName: "photo")
                .font(.system(size: 64))
                .foregroundColor(.secondary)
            Text("Failed to load image")
                .font(.headline)
                .foregroundColor(.secondary)
        }
    }
}

// MARK: - Scroll Wheel Zoom (AppKit bridge for scroll wheel)

struct ScrollWheelZoomView: NSViewRepresentable {
    @Binding var scale: CGFloat
    let minScale: CGFloat
    let maxScale: CGFloat

    func makeNSView(context: Context) -> NSView {
        let view = ScrollWheelCaptureView()
        view.onScroll = { delta in
            let newScale = scale + delta * 0.01
            scale = min(max(newScale, minScale), maxScale)
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {}
}

class ScrollWheelCaptureView: NSView {
    var onScroll: ((CGFloat) -> Void)?

    override func scrollWheel(with event: NSEvent) {
        // Use pinch gesture delta (magnification) or scroll delta
        if event.phase == .changed || event.momentumPhase == .changed {
            let delta = event.scrollingDeltaY
            onScroll?(delta)
        }
    }

    override var acceptsFirstResponder: Bool { true }
}

// MARK: - Folder Access Manager (persists security-scoped bookmarks)

class FolderAccessManager: ObservableObject {
    static let shared = FolderAccessManager()

    private let bookmarksKey = "FolderAccessBookmarks"
    @Published private(set) var accessedFolders: [URL] = []

    private init() {
        restoreBookmarks()
    }

    /// Check if we have access to a file path (is it under an accessed folder?)
    func hasAccess(to path: String) -> Bool {
        let url = URL(fileURLWithPath: path)

        // Check if directly readable
        if FileManager.default.isReadableFile(atPath: path) {
            return true
        }

        // Check if under an accessed folder
        for folder in accessedFolders {
            if url.path.hasPrefix(folder.path) {
                return true
            }
        }
        return false
    }

    /// Request access to a folder (shows NSOpenPanel)
    func requestFolderAccess(suggestedPath: String? = nil, completion: @escaping (Bool) -> Void) {
        DispatchQueue.main.async {
            let panel = NSOpenPanel()
            panel.canChooseFiles = false
            panel.canChooseDirectories = true
            panel.allowsMultipleSelection = false

            // Find the best parent folder to suggest
            var suggestedFolder: URL?
            if let path = suggestedPath {
                suggestedFolder = self.findBestParentFolder(for: path)
            }

            if let folder = suggestedFolder {
                panel.message = "Grant access to '\(folder.lastPathComponent)' folder"
                panel.prompt = "Grant Access"
                panel.directoryURL = folder.deletingLastPathComponent() // Navigate to parent so the folder is visible
            } else {
                panel.message = "Select a folder to grant Fichero access"
                panel.prompt = "Grant Access"
            }

            panel.begin { response in
                if response == .OK, let selectedURL = panel.url {
                    self.saveBookmark(for: selectedURL)
                    completion(true)
                } else {
                    completion(false)
                }
            }
        }
    }

    /// Get the parent folder for a file path
    private func findBestParentFolder(for path: String) -> URL? {
        return URL(fileURLWithPath: path).deletingLastPathComponent()
    }

    /// Save a security-scoped bookmark
    func saveBookmark(for url: URL) {
        do {
            // Start accessing to create bookmark
            _ = url.startAccessingSecurityScopedResource()

            let bookmarkData = try url.bookmarkData(
                options: .withSecurityScope,
                includingResourceValuesForKeys: nil,
                relativeTo: nil
            )

            // Save to UserDefaults
            var bookmarks = UserDefaults.standard.dictionary(forKey: bookmarksKey) as? [String: Data] ?? [:]
            bookmarks[url.path] = bookmarkData
            UserDefaults.standard.set(bookmarks, forKey: bookmarksKey)

            // Add to accessed folders
            if !accessedFolders.contains(url) {
                accessedFolders.append(url)
            }

            NSLog("[FolderAccess] Saved bookmark for: %@", url.path)

            // Don't stop accessing - we need it throughout the app session
        } catch {
            NSLog("[FolderAccess] Failed to save bookmark: %@", error.localizedDescription)
        }
    }

    /// Restore bookmarks on app launch
    private func restoreBookmarks() {
        guard let bookmarks = UserDefaults.standard.dictionary(forKey: bookmarksKey) as? [String: Data] else {
            return
        }

        for (path, bookmarkData) in bookmarks {
            do {
                var isStale = false
                let url = try URL(
                    resolvingBookmarkData: bookmarkData,
                    options: .withSecurityScope,
                    relativeTo: nil,
                    bookmarkDataIsStale: &isStale
                )

                // Start accessing the resource
                let didStart = url.startAccessingSecurityScopedResource()

                if isStale {
                    // Bookmark is stale, try to refresh it
                    NSLog("[FolderAccess] Stale bookmark for: %@, refreshing...", path)
                    saveBookmark(for: url)
                } else if didStart {
                    accessedFolders.append(url)
                    NSLog("[FolderAccess] Restored access to: %@", url.path)
                }
            } catch {
                NSLog("[FolderAccess] Failed to restore bookmark for %@: %@", path, error.localizedDescription)
            }
        }
    }

    /// Clear all bookmarks
    func clearAllAccess() {
        // Stop accessing all folders
        for url in accessedFolders {
            url.stopAccessingSecurityScopedResource()
        }
        accessedFolders.removeAll()
        UserDefaults.standard.removeObject(forKey: bookmarksKey)
    }
}

// MARK: - Quick Look Preview (with folder access for fast local file reading)

struct QuickLookDownloadView: View {
    let document: Document

    @StateObject private var folderAccess = FolderAccessManager.shared
    @State private var fileURL: URL?
    @State private var isLoading = true
    @State private var needsAccess = false
    @State private var error: String?

    var body: some View {
        Group {
            if let url = fileURL {
                SmartPreviewView(url: url)
            } else if needsAccess {
                // Prompt user to grant folder access
                accessRequiredView
            } else if isLoading {
                VStack(spacing: 16) {
                    ProgressView()
                    Text("Loading preview...")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = error {
                VStack(spacing: 16) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 48))
                        .foregroundColor(.orange)
                    Text("Preview unavailable")
                        .font(.headline)
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)

                    Button("Retry") {
                        Task { await loadFile() }
                    }
                    .buttonStyle(.bordered)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .task(id: document.id) {
            await loadFile()
        }
    }

    /// The folder we need access to (immediate parent of the file)
    private var neededFolderName: String {
        guard let path = document.path else { return "this folder" }
        return URL(fileURLWithPath: path).deletingLastPathComponent().lastPathComponent
    }

    private var accessRequiredView: some View {
        VStack(spacing: 16) {
            Image(systemName: "folder.badge.questionmark")
                .font(.system(size: 48))
                .foregroundColor(.orange)

            Text("Grant Access to \(neededFolderName)")
                .font(.headline)

            Text("Fichero needs permission to read files from this folder. You only need to do this once.")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal)

            Button("Grant Access to \(neededFolderName)...") {
                FolderAccessManager.shared.requestFolderAccess(suggestedPath: document.path) { success in
                    if success {
                        Task { await loadFile() }
                    }
                }
            }
            .buttonStyle(.borderedProminent)
            .padding(.top, 8)

            // Show currently accessible folders
            if !folderAccess.accessedFolders.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Already accessible:")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    ForEach(folderAccess.accessedFolders, id: \.path) { url in
                        HStack(spacing: 4) {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.caption2)
                                .foregroundColor(.green)
                            Text(url.lastPathComponent)
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                    }
                }
                .padding(.top, 8)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func loadFile() async {
        isLoading = true
        error = nil
        fileURL = nil
        needsAccess = false

        // First try local path if we have access
        if let path = document.path {
            let localURL = URL(fileURLWithPath: path)

            // Check if readable (either directly or via granted folder access)
            if FolderAccessManager.shared.hasAccess(to: path) {
                await MainActor.run {
                    self.fileURL = localURL
                    self.isLoading = false
                }
                return
            }

            // File exists but no access - prompt user
            if FileManager.default.fileExists(atPath: path) {
                await MainActor.run {
                    self.needsAccess = true
                    self.isLoading = false
                }
                return
            }
        }

        // No local path or file doesn't exist - download from API
        await downloadFromAPI()
    }

    private func downloadFromAPI() async {
        let sourceURL = APIClient.shared.sourceURL(for: document.id)

        do {
            // Download file from API
            let (tempURL, response) = try await URLSession.shared.download(from: sourceURL)

            // Try to get filename from Content-Disposition header
            var fileName = fileNameWithExtension()
            if let httpResponse = response as? HTTPURLResponse,
               let contentDisposition = httpResponse.value(forHTTPHeaderField: "Content-Disposition"),
               let range = contentDisposition.range(of: "filename=\""),
               let endRange = contentDisposition.range(of: "\"", range: range.upperBound..<contentDisposition.endIndex) {
                let serverFileName = String(contentDisposition[range.upperBound..<endRange.lowerBound])
                if !serverFileName.isEmpty {
                    fileName = serverFileName
                }
            }

            // Move to cache directory
            let cacheDir = FileManager.default.temporaryDirectory
                .appendingPathComponent("FicheroPreview")
            try FileManager.default.createDirectory(at: cacheDir, withIntermediateDirectories: true)

            let destURL = cacheDir.appendingPathComponent("\(document.id)_\(fileName)")

            // Remove existing
            if FileManager.default.fileExists(atPath: destURL.path) {
                try FileManager.default.removeItem(at: destURL)
            }
            try FileManager.default.moveItem(at: tempURL, to: destURL)

            NSLog("[QuickLook] Downloaded to: %@", destURL.path)

            await MainActor.run {
                self.fileURL = destURL
                self.isLoading = false
            }
        } catch {
            NSLog("[QuickLook] Download error: %@", error.localizedDescription)
            await MainActor.run {
                self.error = "Failed to load: \(error.localizedDescription)"
                self.isLoading = false
            }
        }
    }

    /// Get filename with proper extension
    private func fileNameWithExtension() -> String {
        let name = document.name
        if name.contains(".") {
            return name
        }

        if let path = document.path {
            let ext = (path as NSString).pathExtension
            if !ext.isEmpty {
                return "\(name).\(ext)"
            }
        }

        if let fileType = document.fileType {
            let ext: String
            switch fileType {
            case .image: ext = "jpg"
            case .pdf: ext = "pdf"
            case .audio: ext = "mp3"
            case .video: ext = "mp4"
            case .text: ext = "txt"
            case .word: ext = "docx"
            case .epub: ext = "epub"
            case .other: ext = "bin"
            }
            return "\(name).\(ext)"
        }

        return name
    }
}

// MARK: - Smart Preview View (uses best viewer for file type)

struct SmartPreviewView: View {
    let url: URL

    private var isImage: Bool {
        let imageExtensions = ["jpg", "jpeg", "png", "gif", "tiff", "tif", "bmp", "heic", "webp"]
        return imageExtensions.contains(url.pathExtension.lowercased())
    }

    var body: some View {
        if isImage {
            ZoomableImagePreview(url: url)
        } else {
            QuickLookPreviewView(url: url)
        }
    }
}

// MARK: - Zoomable Image Preview (with controls and magnifier)

struct ZoomableImagePreview: View {
    let url: URL

    // These settings persist across image changes using AppStorage
    @AppStorage("imagePreview.magnifierEnabled") private var magnifierEnabled = false
    @AppStorage("imagePreview.loupeEnabled") private var loupeEnabled = false
    @AppStorage("imagePreview.loupeMagnification") private var loupeMagnification: Double = 3.0
    @AppStorage("imagePreview.loupeSize") private var loupeSize: Double = 150.0
    @AppStorage("imagePreview.panelMagnification") private var panelMagnification: Double = 4.0
    @AppStorage("imagePreview.panelHeight") private var panelHeight: Double = 120.0
    @AppStorage("imagePreview.magnifierLocked") private var magnifierLocked = false

    @State private var scale: CGFloat = 1.0
    @State private var minScale: CGFloat = 0.1
    @State private var maxScale: CGFloat = 10.0
    @State private var cursorPosition: CGPoint = .zero
    @State private var lastImagePosition: CGPoint = CGPoint(x: 0.5, y: 0.5)  // Last position over image (not UI)
    @State private var lockedPosition: CGPoint = CGPoint(x: 0.5, y: 0.5)  // Position when locked
    @State private var imageSize: CGSize = .zero
    @State private var image: NSImage?
    @State private var visibleRect: CGRect = .zero  // Normalized 0-1

    /// The position to use for magnifier (locked or cursor)
    private var magnifierPosition: CGPoint {
        magnifierLocked ? lockedPosition : cursorPosition
    }

    var body: some View {
        VStack(spacing: 0) {
            // Zoom toolbar
            HStack(spacing: 12) {
                Button(action: zoomOut) {
                    Image(systemName: "minus.magnifyingglass")
                }
                .buttonStyle(.plain)
                .help("Zoom Out")

                Text("\(Int(scale * 100))%")
                    .font(.caption)
                    .monospacedDigit()
                    .frame(width: 50)

                Button(action: zoomIn) {
                    Image(systemName: "plus.magnifyingglass")
                }
                .buttonStyle(.plain)
                .help("Zoom In")

                Divider()
                    .frame(height: 16)

                Button(action: fitToWindow) {
                    Image(systemName: "arrow.up.left.and.arrow.down.right")
                }
                .buttonStyle(.plain)
                .help("Fit to Window")

                Button(action: actualSize) {
                    Image(systemName: "1.square")
                }
                .buttonStyle(.plain)
                .help("Actual Size (100%)")

                Divider()
                    .frame(height: 16)

                // Magnifier panel toggle
                Button(action: { magnifierEnabled.toggle() }) {
                    Image(systemName: magnifierEnabled ? "rectangle.bottomhalf.inset.filled" : "rectangle.bottomhalf.inset.filled")
                }
                .buttonStyle(.plain)
                .foregroundColor(magnifierEnabled ? .accentColor : .primary)
                .help("Magnifier Panel")

                // Loupe toggle with zoom controls
                HStack(spacing: 4) {
                    Button(action: { loupeEnabled.toggle() }) {
                        Image(systemName: loupeEnabled ? "magnifyingglass.circle.fill" : "magnifyingglass.circle")
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(loupeEnabled ? .accentColor : .primary)
                    .help("Loupe (click to place, drag to move, scroll/pinch to zoom, drag edge to resize)")

                    if loupeEnabled {
                        Text(String(format: "%.1fx", CGFloat(loupeMagnification)))
                            .font(.caption2)
                            .monospacedDigit()
                            .foregroundColor(.secondary)
                            .frame(width: 32)

                        Text("\(Int(loupeSize))px")
                            .font(.caption2)
                            .monospacedDigit()
                            .foregroundColor(.secondary.opacity(0.7))
                    }
                }

                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(Color(.windowBackgroundColor))

            Divider()

            // Main content area
            ZStack(alignment: .topTrailing) {
                VStack(spacing: 0) {
                    // Image view with cursor tracking and integrated loupe
                    ImageWithCursorTracking(
                        url: url,
                        scale: $scale,
                        cursorPosition: $cursorPosition,
                        imageSize: $imageSize,
                        visibleRect: $visibleRect,
                        minScale: minScale,
                        maxScale: maxScale,
                        loupeEnabled: loupeEnabled,
                        loupeMagnification: Binding(
                            get: { CGFloat(loupeMagnification) },
                            set: { loupeMagnification = Double($0) }
                        ),
                        loupeSize: Binding(
                            get: { CGFloat(loupeSize) },
                            set: { loupeSize = Double($0) }
                        ),
                        onImagePositionChanged: { pos in
                            lastImagePosition = pos
                        }
                    )

                    // Bottom magnifier panel
                    if magnifierEnabled, let img = image {
                        Divider()
                        MagnifierPanelView(
                            image: img,
                            cursorPosition: magnifierPosition,
                            imageSize: imageSize,
                            magnification: Binding(
                                get: { CGFloat(panelMagnification) },
                                set: { panelMagnification = Double($0) }
                            ),
                            panelHeight: Binding(
                                get: { CGFloat(panelHeight) },
                                set: { panelHeight = Double($0) }
                            ),
                            isLocked: $magnifierLocked,
                            onLockToggle: {
                                if !magnifierLocked {
                                    // Locking - save last valid image position (not current cursor which may be over UI)
                                    lockedPosition = lastImagePosition
                                }
                                magnifierLocked.toggle()
                            }
                        )
                        .frame(height: CGFloat(panelHeight))
                    }
                }

                // Mini-map navigator (top right) - show when zoomed in (visible rect < full) or loupe active
                if let img = image, (visibleRect.width < 0.99 || visibleRect.height < 0.99 || loupeEnabled) {
                    NavigatorMiniMap(
                        image: img,
                        cursorPosition: cursorPosition,
                        visibleRect: visibleRect
                    )
                    .frame(width: 150, height: 100)
                    .padding(8)
                }
            }
        }
        .onAppear {
            image = NSImage(contentsOf: url)
            if let img = image {
                imageSize = img.size
            }
        }
        .onChange(of: url) { _, newURL in
            image = NSImage(contentsOf: newURL)
            if let img = image {
                imageSize = img.size
            }
        }
    }

    private func zoomIn() {
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = min(scale * 1.25, maxScale)
        }
    }

    private func zoomOut() {
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = max(scale / 1.25, minScale)
        }
    }

    private func fitToWindow() {
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = 1.0
        }
    }

    private func actualSize() {
        withAnimation(.easeInOut(duration: 0.2)) {
            scale = 1.0
        }
    }
}

// MARK: - Image with Cursor Tracking and Loupe

struct ImageWithCursorTracking: NSViewRepresentable {
    let url: URL
    @Binding var scale: CGFloat
    @Binding var cursorPosition: CGPoint  // Normalized 0-1 position in image
    @Binding var imageSize: CGSize
    @Binding var visibleRect: CGRect  // Normalized 0-1 visible area
    let minScale: CGFloat
    let maxScale: CGFloat
    let loupeEnabled: Bool
    @Binding var loupeMagnification: CGFloat
    @Binding var loupeSize: CGFloat
    var onImagePositionChanged: ((CGPoint) -> Void)?  // Called when cursor moves over image

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = true
        scrollView.allowsMagnification = true
        scrollView.minMagnification = minScale
        scrollView.maxMagnification = maxScale
        scrollView.magnification = scale
        scrollView.backgroundColor = NSColor(white: 0.15, alpha: 1.0)
        scrollView.postsBoundsChangedNotifications = true

        // Add magnification gesture recognizer for pinch-to-zoom
        let magnifyGesture = NSMagnificationGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.handleMagnify(_:)))
        scrollView.addGestureRecognizer(magnifyGesture)
        context.coordinator.magnifyGesture = magnifyGesture

        // Create tracking image view with loupe
        let imageView = TrackingImageView()
        imageView.imageScaling = .scaleNone  // We'll handle sizing
        imageView.onCursorMoved = { normalizedPos in
            DispatchQueue.main.async {
                self.cursorPosition = normalizedPos
                self.onImagePositionChanged?(normalizedPos)
            }
        }
        imageView.onLoupeMagnificationChanged = { newMag in
            DispatchQueue.main.async {
                self.loupeMagnification = newMag
            }
        }
        imageView.onLoupeSizeChanged = { newSize in
            DispatchQueue.main.async {
                self.loupeSize = newSize
            }
        }
        imageView.loupeMagnification = loupeMagnification
        imageView.loupeSize = loupeSize

        if let image = NSImage(contentsOf: url) {
            imageView.image = image
            imageView.frame = NSRect(origin: .zero, size: image.size)
            DispatchQueue.main.async {
                self.imageSize = image.size
            }
        }

        scrollView.documentView = imageView
        context.coordinator.scrollView = scrollView
        context.coordinator.imageView = imageView

        // Observe scroll/zoom changes for visible rect
        NotificationCenter.default.addObserver(
            context.coordinator,
            selector: #selector(Coordinator.boundsDidChange(_:)),
            name: NSView.boundsDidChangeNotification,
            object: scrollView.contentView
        )
        context.coordinator.onVisibleRectChanged = { rect in
            DispatchQueue.main.async {
                self.visibleRect = rect
            }
        }

        // Center initially
        DispatchQueue.main.async {
            self.centerImage(scrollView: scrollView, imageView: imageView)
        }

        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        if abs(scrollView.magnification - scale) > 0.01 {
            scrollView.magnification = scale
        }

        if let imageView = context.coordinator.imageView as? TrackingImageView {
            imageView.loupeEnabled = loupeEnabled
            imageView.loupeMagnification = loupeMagnification
            imageView.loupeSize = loupeSize

            if context.coordinator.currentURL != url {
                if let image = NSImage(contentsOf: url) {
                    imageView.image = image
                    imageView.frame = NSRect(origin: .zero, size: image.size)
                    imageView.loupePosition = nil  // Reset loupe on image change
                    context.coordinator.currentURL = url
                    DispatchQueue.main.async {
                        self.imageSize = image.size
                    }
                    centerImage(scrollView: scrollView, imageView: imageView)
                }
            }
        }

        // Update visible rect
        context.coordinator.updateVisibleRect()
    }

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    private func centerImage(scrollView: NSScrollView, imageView: NSView) {
        guard let imgView = imageView as? NSImageView, let image = imgView.image else { return }

        let viewSize = scrollView.bounds.size
        let imageSize = image.size

        let scaleX = viewSize.width / imageSize.width
        let scaleY = viewSize.height / imageSize.height
        let fitScale = min(scaleX, scaleY, 1.0)

        scrollView.magnification = fitScale
    }

    class Coordinator: NSObject {
        var scrollView: NSScrollView?
        var imageView: NSView?
        var currentURL: URL?
        var onVisibleRectChanged: ((CGRect) -> Void)?
        var magnifyGesture: NSMagnificationGestureRecognizer?
        private var initialMagnification: CGFloat = 1.0

        @objc func boundsDidChange(_ notification: Notification) {
            updateVisibleRect()
        }

        @objc func handleMagnify(_ gesture: NSMagnificationGestureRecognizer) {
            guard let scrollView = scrollView else { return }

            // Check if cursor is over loupe - if so, zoom the loupe instead
            if let trackingView = imageView as? TrackingImageView,
               trackingView.loupeEnabled,
               let loupeViewPos = trackingView.loupeViewPosition {
                let location = gesture.location(in: trackingView)
                let loupeRadius = trackingView.loupeSize / 2
                let distance = hypot(location.x - loupeViewPos.x, location.y - loupeViewPos.y)
                if distance <= loupeRadius {
                    // Over loupe - zoom loupe magnification
                    switch gesture.state {
                    case .began:
                        initialMagnification = trackingView.loupeMagnification
                    case .changed:
                        let newMag = initialMagnification * (1 + gesture.magnification)
                        let clampedMag = max(1.5, min(10.0, newMag))
                        trackingView.loupeMagnification = clampedMag
                        trackingView.onLoupeMagnificationChanged?(clampedMag)
                        trackingView.needsDisplay = true
                    default:
                        break
                    }
                    return
                }
            }

            // Not over loupe - zoom main image
            switch gesture.state {
            case .began:
                initialMagnification = scrollView.magnification
            case .changed:
                let newMag = initialMagnification * (1 + gesture.magnification)
                let clampedMag = max(scrollView.minMagnification, min(scrollView.maxMagnification, newMag))
                let location = gesture.location(in: scrollView)
                scrollView.setMagnification(clampedMag, centeredAt: location)
            case .ended, .cancelled:
                break
            default:
                break
            }
        }

        func updateVisibleRect() {
            guard let scrollView = scrollView,
                  let imageView = imageView as? NSImageView,
                  let image = imageView.image else { return }

            let visibleRect = scrollView.contentView.documentVisibleRect
            let imageSize = image.size
            let magnification = scrollView.magnification

            // Calculate scaled image size
            let scaledWidth = imageSize.width * magnification
            let scaledHeight = imageSize.height * magnification

            // Calculate normalized visible rect (0-1 range)
            let normalizedX = visibleRect.origin.x / scaledWidth
            let normalizedWidth = min(1.0, visibleRect.width / scaledWidth)
            let normalizedHeight = min(1.0, visibleRect.height / scaledHeight)

            // For Y, we need to flip because NSScrollView origin is bottom-left
            // but our mini-map expects top-left origin
            let normalizedY = 1.0 - (visibleRect.origin.y / scaledHeight) - normalizedHeight

            let rect = CGRect(
                x: max(0, min(1 - normalizedWidth, normalizedX)),
                y: max(0, min(1 - normalizedHeight, normalizedY)),
                width: normalizedWidth,
                height: normalizedHeight
            )

            onVisibleRectChanged?(rect)
        }
    }
}

class TrackingImageView: NSImageView {
    var onCursorMoved: ((CGPoint) -> Void)?
    var onLoupeMagnificationChanged: ((CGFloat) -> Void)?
    var onLoupeSizeChanged: ((CGFloat) -> Void)?
    var loupeEnabled: Bool = false {
        didSet {
            if loupeEnabled {
                if loupePosition == nil {
                    // Auto-show loupe at center when enabled for the first time
                    showLoupeAtCenter()
                } else {
                    // Re-show at last position
                    needsDisplay = true
                }
            } else {
                // Hide loupe when disabled (but remember position)
                needsDisplay = true
            }
        }
    }
    var loupePosition: CGPoint? = nil  // Position in image coordinates (what we're looking at)
    var loupeViewPosition: CGPoint? = nil  // Where loupe is displayed
    private var isDraggingLoupe = false
    private var isResizingLoupe = false
    private var dragOffset: CGSize = .zero
    private var resizeStartSize: CGFloat = 0
    private var resizeStartDistance: CGFloat = 0
    private let edgeThreshold: CGFloat = 12  // How close to edge to trigger resize
    var loupeSize: CGFloat = 150 {
        didSet {
            if loupePosition != nil {
                needsDisplay = true
            }
        }
    }
    private let minLoupeSize: CGFloat = 80
    private let maxLoupeSize: CGFloat = 400
    var loupeMagnification: CGFloat = 3.0 {
        didSet {
            if loupePosition != nil {
                needsDisplay = true
            }
        }
    }
    private let minLoupeMagnification: CGFloat = 1.5
    private let maxLoupeMagnification: CGFloat = 10.0

    /// Show loupe at center of visible area
    func showLoupeAtCenter() {
        guard let scrollView = enclosingScrollView else {
            // Fallback to view center
            let centerX = bounds.width / 2
            let centerY = bounds.height / 2
            loupePosition = CGPoint(x: centerX, y: centerY)
            loupeViewPosition = CGPoint(x: centerX, y: centerY)
            needsDisplay = true
            return
        }

        // Get visible rect center
        let visibleRect = scrollView.contentView.documentVisibleRect
        let centerX = visibleRect.midX
        let centerY = visibleRect.midY

        loupePosition = CGPoint(x: centerX, y: centerY)
        loupeViewPosition = CGPoint(x: centerX, y: centerY)
        needsDisplay = true
    }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        trackingAreas.forEach { removeTrackingArea($0) }
        addTrackingArea(NSTrackingArea(
            rect: bounds,
            options: [.activeInKeyWindow, .mouseMoved, .mouseEnteredAndExited],
            owner: self,
            userInfo: nil
        ))
    }

    override func mouseMoved(with event: NSEvent) {
        let location = convert(event.locationInWindow, from: nil)
        guard bounds.width > 0, bounds.height > 0 else { return }

        // Update cursor for loupe edge resize
        if loupeEnabled, let viewPos = loupeViewPosition {
            let rect = loupeRect(at: viewPos)
            if rect.contains(location) && isOnLoupeEdge(location, loupeCenter: viewPos) {
                // On edge - show resize cursor
                NSCursor.crosshair.set()
            } else {
                NSCursor.arrow.set()
            }
        }

        // Normalize to 0-1 range
        let normalizedX = location.x / bounds.width
        let normalizedY = location.y / bounds.height

        onCursorMoved?(CGPoint(x: normalizedX, y: normalizedY))
    }

    private func loupeRect(at position: CGPoint) -> NSRect {
        return NSRect(
            x: position.x - loupeSize / 2,
            y: position.y - loupeSize / 2,
            width: loupeSize,
            height: loupeSize
        )
    }

    /// Check if point is on the edge of the loupe (for resize)
    private func isOnLoupeEdge(_ point: CGPoint, loupeCenter: CGPoint) -> Bool {
        let distance = hypot(point.x - loupeCenter.x, point.y - loupeCenter.y)
        let radius = loupeSize / 2
        // On edge if within threshold of the circle's radius
        return distance >= (radius - edgeThreshold) && distance <= (radius + edgeThreshold)
    }

    /// Distance from point to loupe center
    private func distanceToLoupeCenter(_ point: CGPoint, loupeCenter: CGPoint) -> CGFloat {
        return hypot(point.x - loupeCenter.x, point.y - loupeCenter.y)
    }

    override func mouseDown(with event: NSEvent) {
        guard loupeEnabled else {
            super.mouseDown(with: event)
            return
        }

        let clickLocation = convert(event.locationInWindow, from: nil)

        // Check if clicking on existing loupe
        if let viewPos = loupeViewPosition {
            let rect = loupeRect(at: viewPos)
            if rect.contains(clickLocation) {
                // Check if on edge for resize
                if isOnLoupeEdge(clickLocation, loupeCenter: viewPos) {
                    // Start resizing
                    isResizingLoupe = true
                    resizeStartSize = loupeSize
                    resizeStartDistance = distanceToLoupeCenter(clickLocation, loupeCenter: viewPos)
                    return
                }

                // Not on edge - start dragging
                isDraggingLoupe = true
                dragOffset = CGSize(
                    width: clickLocation.x - viewPos.x,
                    height: clickLocation.y - viewPos.y
                )
                return
            }
        }

        // Place new loupe - both the view position and what it's looking at
        loupePosition = clickLocation
        loupeViewPosition = clickLocation
        needsDisplay = true
    }

    override func mouseDragged(with event: NSEvent) {
        guard loupeEnabled else {
            super.mouseDragged(with: event)
            return
        }

        let location = convert(event.locationInWindow, from: nil)

        if isResizingLoupe, let viewPos = loupeViewPosition {
            // Resize based on distance from center
            let currentDistance = distanceToLoupeCenter(location, loupeCenter: viewPos)
            let newSize = resizeStartSize * (currentDistance / resizeStartDistance)
            loupeSize = max(minLoupeSize, min(maxLoupeSize, newSize))
            onLoupeSizeChanged?(loupeSize)
            needsDisplay = true
            return
        }

        if isDraggingLoupe {
            // Move only the view position, keep looking at the same spot
            loupeViewPosition = CGPoint(
                x: location.x - dragOffset.width,
                y: location.y - dragOffset.height
            )
            needsDisplay = true
            return
        }

        super.mouseDragged(with: event)
    }

    override func mouseUp(with event: NSEvent) {
        if isDraggingLoupe {
            isDraggingLoupe = false
        } else if isResizingLoupe {
            isResizingLoupe = false
        } else {
            super.mouseUp(with: event)
        }
    }

    override func rightMouseDown(with event: NSEvent) {
        // Right-click to remove loupe
        if loupeEnabled && loupePosition != nil {
            loupePosition = nil
            loupeViewPosition = nil
            needsDisplay = true
            return
        }
        super.rightMouseDown(with: event)
    }

    override func scrollWheel(with event: NSEvent) {
        // Check if cursor is over the loupe
        if loupeEnabled, let viewPos = loupeViewPosition {
            let location = convert(event.locationInWindow, from: nil)
            let rect = loupeRect(at: viewPos)

            if rect.contains(location) {
                // Cursor is over loupe - zoom loupe magnification
                let delta = event.scrollingDeltaY
                let newMag = loupeMagnification + delta * 0.05
                loupeMagnification = max(minLoupeMagnification, min(maxLoupeMagnification, newMag))
                onLoupeMagnificationChanged?(loupeMagnification)
                return
            }
        }
        // Cursor not over loupe - pass to scroll view for image pan/zoom
        super.scrollWheel(with: event)
    }

    // magnify(with:) is NOT overridden - we use gesture recognizers instead
    // to avoid conflicts between event handling and gesture recognition

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)

        // Draw loupe if enabled and positioned
        guard loupeEnabled,
              let targetPosition = loupePosition,
              let viewPosition = loupeViewPosition,
              let image = image else { return }

        let rect = loupeRect(at: viewPosition)

        NSGraphicsContext.current?.saveGraphicsState()

        // Draw shadow
        let shadow = NSShadow()
        shadow.shadowColor = NSColor.black.withAlphaComponent(0.5)
        shadow.shadowOffset = NSSize(width: 0, height: -3)
        shadow.shadowBlurRadius = 10
        shadow.set()

        // Clip to circle
        let path = NSBezierPath(ovalIn: rect)
        path.addClip()

        // Draw white background
        NSColor.white.setFill()
        path.fill()

        // Calculate source rect - use target position (what we're looking at)
        let sourceSize = loupeSize / loupeMagnification

        let sourceRect = NSRect(
            x: targetPosition.x - sourceSize / 2,
            y: targetPosition.y - sourceSize / 2,
            width: sourceSize,
            height: sourceSize
        )

        // Draw magnified image
        image.draw(in: rect, from: sourceRect, operation: .sourceOver, fraction: 1.0)

        // Draw border
        NSColor.white.setStroke()
        let borderPath = NSBezierPath(ovalIn: rect.insetBy(dx: 2, dy: 2))
        borderPath.lineWidth = 3
        borderPath.stroke()

        // Draw crosshair
        NSColor.black.withAlphaComponent(0.3).setStroke()
        let centerX = rect.midX
        let centerY = rect.midY
        let crosshairSize: CGFloat = 10

        let crosshair = NSBezierPath()
        crosshair.move(to: NSPoint(x: centerX - crosshairSize, y: centerY))
        crosshair.line(to: NSPoint(x: centerX + crosshairSize, y: centerY))
        crosshair.move(to: NSPoint(x: centerX, y: centerY - crosshairSize))
        crosshair.line(to: NSPoint(x: centerX, y: centerY + crosshairSize))
        crosshair.lineWidth = 1
        crosshair.stroke()

        NSGraphicsContext.current?.restoreGraphicsState()

        // Draw badge showing magnification and size hint
        let badgeText = String(format: "%.1fx · %dpx", loupeMagnification, Int(loupeSize))
        let attributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 9, weight: .medium),
            .foregroundColor: NSColor.white
        ]
        let textSize = (badgeText as NSString).size(withAttributes: attributes)
        let badgePadding: CGFloat = 4
        let badgeWidth = textSize.width + badgePadding * 2
        let badgeHeight = textSize.height + badgePadding

        let badgeRect = NSRect(
            x: rect.midX - badgeWidth / 2,
            y: rect.minY + 8,
            width: badgeWidth,
            height: badgeHeight
        )

        // Badge background
        let badgePath = NSBezierPath(roundedRect: badgeRect, xRadius: 4, yRadius: 4)
        NSColor.black.withAlphaComponent(0.7).setFill()
        badgePath.fill()

        // Badge text
        let textRect = NSRect(
            x: badgeRect.origin.x + badgePadding,
            y: badgeRect.origin.y + (badgeHeight - textSize.height) / 2,
            width: textSize.width,
            height: textSize.height
        )
        (badgeText as NSString).draw(in: textRect, withAttributes: attributes)
    }
}

// MARK: - Navigator Mini-Map (top right corner)

struct NavigatorMiniMap: View {
    let image: NSImage
    let cursorPosition: CGPoint
    let visibleRect: CGRect  // Normalized 0-1 coordinates

    @State private var isHovering = false

    var body: some View {
        ZStack(alignment: .topLeading) {
            // Thumbnail image
            Image(nsImage: image)
                .resizable()
                .aspectRatio(contentMode: .fit)

            // Visible area rectangle overlay
            GeometryReader { geometry in
                visibleRectOverlay(mapSize: geometry.size)
            }
        }
        .background(Color.black.opacity(0.7))
        .cornerRadius(6)
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(Color.white.opacity(0.3), lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.3), radius: 5, x: 0, y: 2)
        .opacity(isHovering ? 1.0 : 0.7)
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.15)) {
                isHovering = hovering
            }
        }
    }

    /// Calculate and draw the visible rect overlay
    @ViewBuilder
    private func visibleRectOverlay(mapSize: CGSize) -> some View {
        // Calculate actual image bounds within the map (accounting for aspect ratio)
        let imageAspect = image.size.width / image.size.height
        let mapAspect = mapSize.width / mapSize.height

        let imageRect = imageAspect > mapAspect
            ? CGRect(x: 0,
                     y: (mapSize.height - mapSize.width / imageAspect) / 2,
                     width: mapSize.width,
                     height: mapSize.width / imageAspect)
            : CGRect(x: (mapSize.width - mapSize.height * imageAspect) / 2,
                     y: 0,
                     width: mapSize.height * imageAspect,
                     height: mapSize.height)

        // Draw visible area indicator (when zoomed in)
        if visibleRect.width < 0.99 || visibleRect.height < 0.99 {
            let rectWidth = max(8, visibleRect.width * imageRect.width)
            let rectHeight = max(8, visibleRect.height * imageRect.height)
            let rectX = imageRect.origin.x + visibleRect.origin.x * imageRect.width + rectWidth / 2
            let rectY = imageRect.origin.y + visibleRect.origin.y * imageRect.height + rectHeight / 2

            Rectangle()
                .stroke(Color.accentColor, lineWidth: 2)
                .background(Color.accentColor.opacity(0.15))
                .frame(width: rectWidth, height: rectHeight)
                .position(x: rectX, y: rectY)
        }
    }
}

// MARK: - Magnifier Panel (bottom bar - full width with zoom controls)

struct MagnifierPanelView: View {
    let image: NSImage
    let cursorPosition: CGPoint
    let imageSize: CGSize
    @Binding var magnification: CGFloat
    @Binding var panelHeight: CGFloat
    @Binding var isLocked: Bool
    var onLockToggle: () -> Void

    private let minMagnification: CGFloat = 1.0
    private let maxMagnification: CGFloat = 16.0
    private let minHeight: CGFloat = 60
    private let maxHeight: CGFloat = 300

    var body: some View {
        VStack(spacing: 0) {
            // Resize handle at top
            ResizeHandle(height: $panelHeight, minHeight: minHeight, maxHeight: maxHeight)

            ZStack(alignment: .bottomTrailing) {
                // Full width magnified view with scroll-to-zoom
                MagnifierPanelContent(
                    image: image,
                    cursorPosition: cursorPosition,
                    magnification: $magnification,
                    minMagnification: minMagnification,
                    maxMagnification: maxMagnification
                )

                // Lock indicator overlay (top-left when locked)
                if isLocked {
                    VStack {
                        HStack {
                            Image(systemName: "lock.fill")
                                .font(.caption)
                                .foregroundColor(.white)
                                .padding(4)
                                .background(Color.accentColor)
                                .cornerRadius(4)
                                .padding(8)
                            Spacer()
                        }
                        Spacer()
                    }
                }

                // Overlay controls and info
                HStack(spacing: 12) {
                    // Lock button
                    Button(action: onLockToggle) {
                        Image(systemName: isLocked ? "lock.fill" : "lock.open")
                            .font(.caption)
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(isLocked ? .accentColor : .primary)
                    .help(isLocked ? "Unlock magnifier (follows cursor)" : "Lock magnifier (stays on current position)")

                    Divider()
                        .frame(height: 12)

                    // Height indicator
                    Text("\(Int(panelHeight))px")
                        .font(.caption2)
                        .foregroundColor(.secondary)

                    Divider()
                        .frame(height: 12)

                    // Zoom controls
                    HStack(spacing: 4) {
                        Button(action: zoomOut) {
                            Image(systemName: "minus")
                                .font(.caption)
                        }
                        .buttonStyle(.plain)
                        .disabled(magnification <= minMagnification)

                        Text("\(Int(magnification))x")
                            .font(.caption)
                            .fontWeight(.medium)
                            .monospacedDigit()
                            .frame(width: 30)

                        Button(action: zoomIn) {
                            Image(systemName: "plus")
                                .font(.caption)
                        }
                        .buttonStyle(.plain)
                        .disabled(magnification >= maxMagnification)
                    }

                    Divider()
                        .frame(height: 12)

                    // Coordinates
                    let pixelX = Int(cursorPosition.x * imageSize.width)
                    let pixelY = Int((1 - cursorPosition.y) * imageSize.height)

                    Text("X: \(pixelX)  Y: \(pixelY)")
                        .font(.caption)
                        .monospacedDigit()
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(.ultraThinMaterial)
                .cornerRadius(4)
                .padding(8)
            }
        }
        .background(Color(white: 0.1))
        .overlay(
            // Blue border when locked
            RoundedRectangle(cornerRadius: 0)
                .stroke(isLocked ? Color.accentColor : Color.clear, lineWidth: 2)
        )
    }

    private func zoomIn() {
        magnification = min(magnification * 1.5, maxMagnification)
    }

    private func zoomOut() {
        magnification = max(magnification / 1.5, minMagnification)
    }
}

// MARK: - Resize Handle for Panel

struct ResizeHandle: View {
    @Binding var height: CGFloat
    let minHeight: CGFloat
    let maxHeight: CGFloat

    @State private var isDragging = false

    var body: some View {
        Rectangle()
            .fill(Color.gray.opacity(0.3))
            .frame(height: 6)
            .overlay(
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.gray.opacity(isDragging ? 0.8 : 0.5))
                    .frame(width: 40, height: 4)
            )
            .contentShape(Rectangle())
            .gesture(
                DragGesture()
                    .onChanged { value in
                        isDragging = true
                        // Dragging up increases height (negative translation)
                        let newHeight = height - value.translation.height
                        height = max(minHeight, min(maxHeight, newHeight))
                    }
                    .onEnded { _ in
                        isDragging = false
                    }
            )
            .onHover { hovering in
                if hovering {
                    NSCursor.resizeUpDown.push()
                } else {
                    NSCursor.pop()
                }
            }
    }
}

struct MagnifierPanelContent: NSViewRepresentable {
    let image: NSImage
    let cursorPosition: CGPoint
    @Binding var magnification: CGFloat
    let minMagnification: CGFloat
    let maxMagnification: CGFloat

    func makeNSView(context: Context) -> NSView {
        let view = MagnifierPanelNSView()
        view.wantsLayer = true
        view.layer?.backgroundColor = NSColor(white: 0.1, alpha: 1.0).cgColor
        view.minMagnification = minMagnification
        view.maxMagnification = maxMagnification
        view.onMagnificationChanged = { newMag in
            DispatchQueue.main.async {
                self.magnification = newMag
            }
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        guard let panelView = nsView as? MagnifierPanelNSView else { return }
        panelView.image = image
        panelView.cursorPosition = cursorPosition
        panelView.magnification = magnification
        panelView.needsDisplay = true
    }
}

class MagnifierPanelNSView: NSView {
    var image: NSImage?
    var cursorPosition: CGPoint = .zero
    var magnification: CGFloat = 4.0
    var minMagnification: CGFloat = 1.0
    var maxMagnification: CGFloat = 16.0
    var onMagnificationChanged: ((CGFloat) -> Void)?

    override var acceptsFirstResponder: Bool { true }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        trackingAreas.forEach { removeTrackingArea($0) }
        addTrackingArea(NSTrackingArea(
            rect: bounds,
            options: [.activeInKeyWindow, .mouseEnteredAndExited],
            owner: self,
            userInfo: nil
        ))
    }

    override func scrollWheel(with event: NSEvent) {
        // Pinch-to-zoom when mouse is over magnifier panel
        let delta = event.scrollingDeltaY
        let newMag = magnification + delta * 0.1
        magnification = max(minMagnification, min(maxMagnification, newMag))
        onMagnificationChanged?(magnification)
        needsDisplay = true
    }

    override func magnify(with event: NSEvent) {
        // Handle pinch gesture
        let newMag = magnification * (1 + event.magnification)
        magnification = max(minMagnification, min(maxMagnification, newMag))
        onMagnificationChanged?(magnification)
        needsDisplay = true
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)

        guard let image = image, bounds.width > 0, bounds.height > 0 else { return }

        // The panel should show a strip of the image at the specified magnification
        // Calculate how much of the source image we need to fill the panel at this magnification
        let sourceWidth = bounds.width / magnification
        let sourceHeight = bounds.height / magnification

        // Center on cursor position
        let centerX = cursorPosition.x * image.size.width
        let centerY = cursorPosition.y * image.size.height

        var sourceRect = NSRect(
            x: centerX - sourceWidth / 2,
            y: centerY - sourceHeight / 2,
            width: sourceWidth,
            height: sourceHeight
        )

        // Clamp to image bounds
        if sourceRect.minX < 0 { sourceRect.origin.x = 0 }
        if sourceRect.minY < 0 { sourceRect.origin.y = 0 }
        if sourceRect.maxX > image.size.width { sourceRect.origin.x = image.size.width - sourceWidth }
        if sourceRect.maxY > image.size.height { sourceRect.origin.y = image.size.height - sourceHeight }

        // Draw the source region scaled up to fill the entire view
        image.draw(in: bounds, from: sourceRect, operation: .copy, fraction: 1.0)
    }
}

// MARK: - Zoomable Scroll View (legacy - kept for reference)

struct ZoomableScrollView: NSViewRepresentable {
    let url: URL
    @Binding var scale: CGFloat
    let minScale: CGFloat
    let maxScale: CGFloat

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = true
        scrollView.allowsMagnification = true
        scrollView.minMagnification = minScale
        scrollView.maxMagnification = maxScale
        scrollView.magnification = scale
        scrollView.backgroundColor = NSColor(white: 0.15, alpha: 1.0)

        // Create image view
        let imageView = NSImageView()
        imageView.imageScaling = .scaleProportionallyUpOrDown
        imageView.translatesAutoresizingMaskIntoConstraints = false

        if let image = NSImage(contentsOf: url) {
            imageView.image = image
            // Set initial size to image size
            imageView.frame = NSRect(origin: .zero, size: image.size)
        }

        scrollView.documentView = imageView
        context.coordinator.scrollView = scrollView
        context.coordinator.imageView = imageView

        // Center the image initially
        DispatchQueue.main.async {
            self.centerImage(scrollView: scrollView, imageView: imageView)
        }

        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        // Update magnification if changed from SwiftUI
        if abs(scrollView.magnification - scale) > 0.01 {
            scrollView.magnification = scale
        }

        // Update image if URL changed
        if let imageView = context.coordinator.imageView,
           context.coordinator.currentURL != url {
            if let image = NSImage(contentsOf: url) {
                imageView.image = image
                imageView.frame = NSRect(origin: .zero, size: image.size)
                context.coordinator.currentURL = url
                centerImage(scrollView: scrollView, imageView: imageView)
            }
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(scale: $scale)
    }

    private func centerImage(scrollView: NSScrollView, imageView: NSImageView) {
        guard let image = imageView.image else { return }

        let viewSize = scrollView.bounds.size
        let imageSize = image.size

        // Calculate scale to fit
        let scaleX = viewSize.width / imageSize.width
        let scaleY = viewSize.height / imageSize.height
        let fitScale = min(scaleX, scaleY, 1.0) // Don't upscale small images

        scrollView.magnification = fitScale

        // Center
        let scaledWidth = imageSize.width * fitScale
        let scaledHeight = imageSize.height * fitScale
        let offsetX = max(0, (viewSize.width - scaledWidth) / 2)
        let offsetY = max(0, (viewSize.height - scaledHeight) / 2)

        scrollView.contentView.scroll(to: NSPoint(x: -offsetX, y: -offsetY))
    }

    class Coordinator: NSObject {
        var scrollView: NSScrollView?
        var imageView: NSImageView?
        var currentURL: URL?
        @Binding var scale: CGFloat

        init(scale: Binding<CGFloat>) {
            _scale = scale
        }
    }
}

// MARK: - Quick Look Preview View (for non-image files)

struct QuickLookPreviewView: NSViewRepresentable {
    let url: URL

    func makeNSView(context: Context) -> NSView {
        let previewView = QLPreviewView(frame: .zero, style: .normal)!
        previewView.translatesAutoresizingMaskIntoConstraints = false
        previewView.previewItem = url as QLPreviewItem
        previewView.autostarts = true

        let container = NSView()
        container.wantsLayer = true
        container.addSubview(previewView)

        NSLayoutConstraint.activate([
            previewView.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            previewView.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            previewView.topAnchor.constraint(equalTo: container.topAnchor),
            previewView.bottomAnchor.constraint(equalTo: container.bottomAnchor)
        ])

        context.coordinator.previewView = previewView
        return container
    }

    func updateNSView(_ container: NSView, context: Context) {
        if let previewView = context.coordinator.previewView {
            let currentURL = previewView.previewItem as? URL
            if currentURL != url {
                previewView.previewItem = url as QLPreviewItem
            }
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    class Coordinator {
        var previewView: QLPreviewView?
    }
}

// MARK: - Checkerboard Pattern

struct CheckerboardPattern: View {
    var body: some View {
        GeometryReader { geometry in
            let size: CGFloat = 10
            let rows = Int(geometry.size.height / size) + 1
            let cols = Int(geometry.size.width / size) + 1

            Canvas { context, _ in
                for row in 0..<rows {
                    for col in 0..<cols {
                        if (row + col) % 2 == 0 {
                            let rect = CGRect(
                                x: CGFloat(col) * size,
                                y: CGFloat(row) * size,
                                width: size,
                                height: size
                            )
                            context.fill(Path(rect), with: .color(.gray.opacity(0.3)))
                        }
                    }
                }
            }
        }
    }
}

// MARK: - Preview

#Preview("Empty") {
    EditorView(document: nil)
        .frame(width: 500, height: 400)
}
