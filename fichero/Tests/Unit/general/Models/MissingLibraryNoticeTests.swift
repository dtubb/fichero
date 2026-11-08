import Foundation
import Testing

@testable import Fichero

/// A saved library that is not on disk at launch is one alert with Locate and Remove (`app.library.missing-says-so`, #6384).
@MainActor
struct MissingLibraryNoticeTests {
    @Test("the alert names the missing library and shows until it is answered")
    func namesTheLibrary() {
        let notice = MissingLibraryNotice()
        #expect(!notice.isShowing)
        notice.report("/Volumes/Files/Fichero Libraries/GHG Box 12.fichero")
        #expect(notice.isShowing && notice.currentName == "GHG Box 12")
        notice.remove()
        #expect(!notice.isShowing)
    }

    @Test("several missing libraries are asked one at a time, and one path is asked once")
    func oneAtATime() {
        let notice = MissingLibraryNotice()
        notice.report("/a/One.fichero")
        notice.report("/a/One.fichero")
        notice.report("/a/Two.fichero")
        #expect(notice.currentName == "One")
        notice.remove()
        #expect(notice.currentName == "Two")
        notice.remove()
        #expect(notice.current == nil)
    }
}
