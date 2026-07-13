@testable import Fichero
import Foundation
import Testing

/// #3208: audio/video stream via AVPlayer; formats AVFoundation can't play fall
/// back to the QuickLook download. `canStream` is the gate that decides which.
@MainActor
@Suite("MediaStreamPreview.canStream")
struct MediaStreamPreviewTests {

    private func doc(_ name: String, _ type: FileType) -> Document {
        var d = Document(id: "d", parentId: "root", docType: .file, name: name)
        d.fileType = type
        return d
    }

    @Test("AVFoundation-native audio streams")
    func nativeAudioStreams() {
        #expect(MediaStreamPreview.canStream(doc("recording.mp3", .audio)))
        #expect(MediaStreamPreview.canStream(doc("voice.m4a", .audio)))
        #expect(MediaStreamPreview.canStream(doc("take.wav", .audio)))
    }

    @Test("AVFoundation-native video streams")
    func nativeVideoStreams() {
        #expect(MediaStreamPreview.canStream(doc("clip.mp4", .video)))
        #expect(MediaStreamPreview.canStream(doc("scene.mov", .video)))
    }

    @Test("containers AVFoundation can't play fall back (not streamable)")
    func unsupportedFallsBack() {
        #expect(!MediaStreamPreview.canStream(doc("movie.mkv", .video)))
        #expect(!MediaStreamPreview.canStream(doc("old.avi", .video)))
        #expect(!MediaStreamPreview.canStream(doc("clip.webm", .video)))
        #expect(!MediaStreamPreview.canStream(doc("song.ogg", .audio)))
    }

    @Test("extension match is case-insensitive")
    func caseInsensitive() {
        #expect(MediaStreamPreview.canStream(doc("LOUD.MP3", .audio)))
        #expect(MediaStreamPreview.canStream(doc("Clip.MP4", .video)))
    }
}
