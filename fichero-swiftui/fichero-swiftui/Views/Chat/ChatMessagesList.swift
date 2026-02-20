import SwiftUI

/// Messages list display supporting four view modes
struct ChatMessagesList: View {
    let conversation: Conversation
    let displayMode: ViewDisplayMode
    let isLoading: Bool
    let errorMessage: String?
    @Binding var inputText: String
    
    var body: some View {
        Group {
            if conversation.messages.isEmpty {
                ChatEmptyStateView(inputText: $inputText)
            } else {
                switch displayMode {
                case .icon:
                    iconView
                case .list:
                    bubbleView
                case .table:
                    tableView
                case .map:
                    mapView
                }
            }
        }
    }
    
    // MARK: - Icon View
    
    private var iconView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVGrid(
                    columns: [GridItem(.adaptive(minimum: 200, maximum: 280))],
                    spacing: 16
                ) {
                    ForEach(conversation.messages) { message in
                        MessageCard(message: message)
                            .id(message.id)
                    }
                }
                .padding()
                
                if isLoading {
                    ChatLoadingIndicator()
                }
                
                if let error = errorMessage {
                    ChatErrorView(message: error)
                }
            }
            .onChange(of: conversation.messages.count) { _, _ in
                if let lastMessage = conversation.messages.last {
                    withAnimation {
                        proxy.scrollTo(lastMessage.id, anchor: .bottom)
                    }
                }
            }
        }
        .background(Color(.textBackgroundColor))
    }
    
    // MARK: - Bubble View
    
    private var bubbleView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 16) {
                    ForEach(conversation.messages) { message in
                        MessageBubble(message: message)
                            .id(message.id)
                    }
                    
                    if isLoading {
                        ChatLoadingIndicator()
                    }
                    
                    if let error = errorMessage {
                        ChatErrorView(message: error)
                    }
                }
                .padding()
            }
            .onChange(of: conversation.messages.count) { _, _ in
                if let lastMessage = conversation.messages.last {
                    withAnimation {
                        proxy.scrollTo(lastMessage.id, anchor: .bottom)
                    }
                }
            }
        }
        .background(Color(.textBackgroundColor))
    }
    
    // MARK: - Table View
    
    private var tableView: some View {
        VStack(spacing: 0) {
            Table(conversation.messages) {
                TableColumn("Role") { message in
                    Text(message.role == .user ? "User" : "Assistant")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .width(min: 60, ideal: 80)
                
                TableColumn("Content") { message in
                    Text(message.content)
                        .lineLimit(3)
                }
                
                TableColumn("Sources") { message in
                    if let sources = message.sources, !sources.isEmpty {
                        Text("\(sources.count) source(s)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        Text("—")
                            .foregroundColor(.secondary)
                    }
                }
                .width(min: 80, ideal: 100)
            }
            
            if isLoading {
                Divider()
                ChatLoadingIndicator()
                    .padding()
            }
            
            if let error = errorMessage {
                Divider()
                ChatErrorView(message: error)
                    .padding()
            }
        }
        .background(Color(.textBackgroundColor))
    }
    
    // MARK: - Map View
    
    private var mapView: some View {
        GeometryReader { geometry in
            ScrollView([.horizontal, .vertical]) {
                ZStack {
                    // Grid background
                    ChatMapGrid()
                        .stroke(Color.gray.opacity(0.2), lineWidth: 0.5)
                        .allowsHitTesting(false)
                    
                    // Message cards positioned on canvas
                    ForEach(Array(conversation.messages.enumerated()), id: \.element.id) { index, message in
                        MessageMapCard(message: message)
                            .position(messagePosition(for: index, role: message.role, in: geometry.size))
                    }
                    
                    if isLoading {
                        ChatLoadingIndicator()
                            .position(x: geometry.size.width / 2, y: geometry.size.height - 50)
                    }
                }
                .frame(width: max(geometry.size.width, 1000), height: max(geometry.size.height, 600))
            }
        }
        .background(Color(.textBackgroundColor))
    }
    
    /// Position messages in a flowing conversation layout
    private func messagePosition(for index: Int, role: ChatRole, in size: CGSize) -> CGPoint {
        let ySpacing: CGFloat = 120
        let xOffset: CGFloat = role == .user ? size.width * 0.7 : size.width * 0.3
        return CGPoint(x: min(max(xOffset, 150), size.width - 150), y: CGFloat(index) * ySpacing + 80)
    }
}
