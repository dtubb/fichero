# iPhone and iPad — Design Spec (#6754)

> Milestone: iPhone
> Manual: TBD — "Fichero on your iPhone and iPad": the phone opens a project that lives on a Mac, what it can do with no
> connection (capture, and nothing else), how to move from the list to the page, the reading and its information, and what
> each "not connected" message means and what to tap.
>
> Design-led (Testing Constitution). **Status: DRAFT, 2026-11-21.** The iPhone navigation ("iPhone: one screen at a time",
> the item's pages, the titles) was rewritten on 2026-11-21 from the owner's rulings of 2026-11-13 and 2026-11-21 and a
> second review, which built the iOS app for the simulator and measured the push fault in a small SwiftUI program (see
> "What was measured (2026-11-21)"); no screen of the app was seen on a simulator or a device. The rest was written from a code review of the iOS targets on
> integration at 6192c54e5e (no simulator or device run: every Swift claim below is from reading the code and is tagged no
> higher than **[PARTIAL]** unless a unit test pins it), the engine's own tests (60 passed, see "What was measured"), and the
> owner's rulings already recorded in `ui/modes-to-panes.md` (the iOS shell section), `transport/library-sharing.md`,
> `transport/ios-sign-in.md`, `transport/transport-http-uds.md` and `source/sharing-two-macs.md`. Those files keep their
> lines; this page is the one place that says what the phone and the tablet do as a whole, and it names their ids where a
> rule already lives there.
> Tags: **[OK]** built and pinned by a test · **[PARTIAL]** built, unproven on a device or incomplete · **[GAP]** not
> built · **[BROKEN]** the code contradicts the rule. Paths are relative to `fichero/fichero/` unless they say otherwise.

## Intent (the design)

A scholar's iPhone or iPad is a window onto a project that lives on their Mac. It has no engine and no project of its own:
it pairs with a Mac once, and from then on it opens that Mac's project wherever the Mac can be reached (the same Wi-Fi, or
Tailscale from anywhere). What the person can observe:

- The phone always shows **a project of the Mac**, or says in words why it cannot, with a button that fixes it. It never
  shows an empty project with no explanation, and it never asks the Mac about a path on the phone.
- On the iPhone one screen shows at a time and the person **drills down**: the sidebar, then each folder (its subfolders
  and its items), then one item. Every tap on a folder or an item pushes a screen, and Back returns exactly one level.
  Nothing expands in place. Once on an item, the person **swipes sideways** between that item's pages: the image
  (Source), the Reader, the Segments and the Info (the Inspector). A small header says which page is showing and a tap
  on it goes straight to a page. On the iPad the Mac's panes sit side by side.
- A screen shows its name **once at most**: in the bar, never again inside the view. A screen whose content already says
  what it is (the image) shows no name at all.
- With no connection the phone can still **capture** pages into a queue that uploads when the Mac is back. Nothing else is
  promised offline.
- Reading a page (turning its image into text) is done **by the Mac**. The phone asks for it and shows the result.

## Prior art

Apple's own split between a device and the Mac that holds the data (Photos on a shared library, Xcode's paired devices,
Finder's connected servers): one sidebar, the remote thing named by its machine, a plain "not connected" state with
Reconnect. For the drill-down, Files and Mail on the iPhone: a folder is a pushed screen that lists its subfolders and its items, and
Back goes up one folder; no disclosure triangles. For the item's pages, Photos' and Weather's paged views: a horizontal
paged container with a small indicator, where a zoomed picture keeps its own pan. For an outbox that survives being offline, Mail's Outbox. Nothing here is invented.

## What exists today (code read 2026-11-20)

- **Entry point**: `FicheroApp_iOS.swift`. One connect path, `reconnectToConfiguredHost()`, for launch, Retry and pairing.
  The root gate (`Views/Components/BackendRootGate.swift`) shows the Connect screen only when nothing is paired and the
  workspace in every other state, including while it is still connecting and while the Mac is unreachable.
- **No engine on the device**: `EngineConfig.iosLaunchPhase` never probes loopback; an unpaired install is `setupNeeded`.
- **The project the phone asks for**: `RemoteAccessConfig.pairedLibraryPath` (one path, in the app's defaults), adopted
  into the always-there slot by `LibraryManager.adoptPairedRemoteLibrary` (`Models/LibraryManager+Helpers.swift`).
- **Connection watch**: a 5 s heartbeat (`App/AppState/AppState+Heartbeat.swift`), a 3 s grace before the launch says it is
  still connecting (`Services/LaunchProbePolicy.swift`), a recovery bar with Reconnect and Change Server
  (`Views/Connect/IOSConnectionRecoveryBar.swift`), a Connection menu (`Views/Connect/IOSConnectionMenu.swift`).
- **Drill-down**: `Views/Shell/ContentView/Layout/ContentView+CompactReader.swift` and `CompactDocumentStep`
  (`Views/Shell/ShellLayoutPolicy.swift`).
- **Capture queue**: `Models/MobileCaptureQueue*.swift`, `Views/Capture/`.
- **Apple frameworks on the device**: VisionKit's document camera and the QR scanner only. No text is read on the device.

## Behaviors

### The project the phone asks the Mac for

- `ios.project.never-its-own-path` — **[BROKEN]** (#6754; the same fault as #5965 and #6555, which fixed the load and the
  two pollers but not the window) from its first frame, a paired iPhone or iPad addresses only a project of the Mac it is
  paired with. A path inside the device's own container is never sent to a Mac as the project, by any view, at launch,
  after the app was put away and reopened, or after the Mac restarted. Today `LibraryManager.loadGlobalLibrary`
  (`Models/LibraryManager.swift`) always builds the always-there slot from the device's own Application Support path, and
  the Mac's project replaces it only on the connected edge (`refreshAfterBackendBecameReady`, reached from the
  `isBackendRunning` change in `FicheroApp_iOS.swift`). Until then the window is mounted on the device's own reference
  (the gate draws the workspace while connecting), and `LibraryWorkspaceRoot`'s task, keyed on the same
  `isBackendRunning` flip, starts the change stream, the Activity poll and the font loads in the same turn the replacement
  is queued in, so which runs first is not decided by the code. Every call that goes out with the device's path is a 403
  (`library_outside_allowed_locations`; measured below). iOS ends a put-away app freely, so "after a relaunch" is the
  common case, not a rare one. Rule: on a device with no engine, when a project is paired the always-there slot is BUILT
  from the paired path, before any view mounts; when none is paired there is no project reference at all and the window
  shows `ios.project.problem-is-shown`. The replacement by a same-id reference (and the "re-watch the replaced stores"
  repairs that followed it) is then not needed on the device. Test (not yet written):
  `PairedLaunchLibraryTests.swift` (a paired device's first always-there reference has
  the paired path; an unpaired one has none; no request built from the first reference carries a container path).
- `ios.project.problem-is-shown` — **[BROKEN]** (#6754) when the Mac refuses the project the phone asked for, serves none
  to this device, or cannot be asked, the phone says which in one sentence where the items would be, with the buttons that
  fix it: **Choose Project…** (the Mac's list for this device), **Reconnect**, and **Pair Again…** when the Mac no longer
  knows the device. Today the sentences exist and are set in four places (`LibraryManager.guestLibraryProblem`, from
  `GuestLibraryChoice.noneServedWords`, `problemWords(for:)` and `refusedWords`) and **no view reads the property**: the
  load stops, nothing is retried, and the person sees an empty project. Test (not yet written):
  `GuestLibraryProblemBannerTests.swift` (each of the three causes yields its
  sentence and its buttons; a source check that a view reads `guestLibraryProblem`).
- `ios.project.survives-the-macs-restart` — **[GAP]** (#6754) a project the Mac listed to this device is still served to
  it after the Mac's app or engine restarts, with nothing done on the phone: the phone's heartbeat sees the Mac again
  (within 5 s of it answering), the connected edge runs once, the change stream and Activity start again, and the lists
  are fetched again (today a project already marked loaded is not loaded again after a reconnect:
  `loadLibraryDataIfNeeded` returns early on `loadedLibraryIds`, so what changed while the Mac was away is not shown until
  the change stream says so). When the Mac no longer has that project open for this device, the Mac's answer says so (not
  "outside every location this engine may open", which is the answer to a wrong path) and the phone shows
  `ios.project.problem-is-shown` with Choose Project. The Mac's half (what its engine allows after a restart) belongs to
  `sharing.guest-addresses-the-hosts-library`; this line is the phone's half. Test (not yet written):
  `ReconnectReloadsTheProjectTests.swift`.
- `ios.project.one-way-to-choose` — **[BROKEN]** (#6124, its CRUD review; its own issue → #6796) the phone has ONE way to change project: a list of the
  projects the paired Mac shares with this device (the Mac's own answer, `GET /api/authz/libraries`), and choosing one
  makes it the remembered project, loads it, and it is the one shown at the next launch. Today there are two controls with
  the same books glyph in the same bar: **Libraries** (`FicheroApp_iOS.swift`, the chooser over the saved paired-Mac
  list, which writes the paired path and loads: `SharedLibraryOpener.openOnDevice`) and **Projects**
  (`Views/Library/LibraryPickerMenuIOS.swift`, the Mac's live list, which calls `switchToRemoteLibrary` and writes
  nothing). A project picked from **Projects** is not the paired path, so `GuestLibraryChoice.mayLoad` refuses its load
  without a word, and it is forgotten at the next launch. Test (not yet written):
  `IOSProjectChoiceTests.swift` (a choice writes the remembered path; `mayLoad` then
  allows it; the first reference of the next launch has it).
- `ios.project.pairing-with-several-asks-which` — **[GAP]** (#3371; its own issue → #6797) pairing with a Mac that shares more than one
  project, by a code or a nearby Mac (no project in the link), ends on the same list and the person picks. Today
  `PairingSequence.confirmLibrary` returns `.choose`, the device row is discarded on the Mac after its code was spent, and
  the phone is told to ask for a new link from the project it wants (`RemoteClientPairing.pairAndPersistHost`). Test (not
  yet written): `PairingChoosesAProjectTests.swift`.
- `ios.project.one-mac-one-project-at-a-time` — **[PARTIAL]** (#2498) the phone shows one project of one Mac at a time;
  pairing with another Mac replaces the first (`PairedHostEndpointStore.clear()` in `persistPairedHost`). Several Macs or
  several projects side by side is not built and not promised here.

### Connecting, and saying what is wrong

- `ios.connect.never-a-silent-failure` — **[PARTIAL]** (#5999, #6124; the rule of `m2p.ios.connect-failure-offers-recovery`)
  in every state where the Mac cannot be used the phone shows one sentence and Reconnect / Change Server above whatever
  screen is showing (`IOSConnectionRecoveryPolicy.offersRecovery`: port conflict, access refused, unreachable, failed;
  pinned by `fichero/Tests/Unit/general/Views/Connect/IOSConnectionRecoveryPolicyTests.swift`). Owed: a refused project is
  not one of those states, so it shows nothing (`ios.project.problem-is-shown`); not seen on a device.
- `ios.connect.says-still-connecting-after-3s` — **[PARTIAL]** (#5999) a launch that has had no answer after 3 s says it is still
  connecting to the named Mac and keeps trying every 5 s in the background, never holding the screen for the transport's
  60 s (`LaunchProbePolicy.firstProbeGrace`, `fichero/Tests/Unit/general/Services/LaunchProbePolicyTests.swift`). Not
  timed on a device.
- `ios.connect.other-version-says-so` — **[PARTIAL]** (#6723) a Mac whose engine speaks another contract version is
  refused before anything is loaded, and the phone names both versions and says to update
  (`AppState.acceptHealth`, `ContractCompatibility`, `fichero/Tests/Unit/general/Transport/ContractCompatibilityTests.swift`).
  Owed: the sentence is shown as "unreachable", with Reconnect, which cannot help.
- `ios.connect.falls-back-to-the-macs-other-address` — **[BROKEN]** (#3098, closed as built; its own issue → #6798) a phone
  paired at home on the Mac's local name keeps working on Tailscale away from home, and back, with no re-pairing: every
  address the pairing link carried is an address the phone may fall back to, with the one device credential. Today the
  fallback list (`PairedHostEndpointStore`, `Models/PairedHostEndpoints.swift`) holds only addresses that have already
  been the active one: pairing clears it and records the single address that answered, the link's other addresses go to
  a different store (`PairedMachineStore.record(addresses:)`) that the fallback never reads
  (`AppState.attemptEndpointFailover`), and the device token is stored per address
  (`AuthTokenMiddleware.persistRemoteToken(hostString:)`), so an address never used has no token. The fallback therefore
  has nothing to try. Test (not yet written): `PairingRecordsEveryAddressTests.swift`
  (after a pairing whose link has two addresses, both are fallback candidates and both resolve the device's token).
- `ios.connect.tailscale-off-says-so` — **[PARTIAL]** (→ #5049) see `sharing.ios-tailscale-not-on-the-phone`: a `.ts.net`
  name that does not resolve says Tailscale is off on this device and offers to open it.

### With no connection

- `ios.offline.capture-only` — **[PARTIAL]** (#3278, #2353) with no connection the phone captures (camera scan or
  Photos) into a queue kept on the device, shows the queue and its count, and uploads when the Mac is next reachable (the
  connected edge calls `resumePendingUploads`; `fichero/Tests/Unit/general/Models/MobileCaptureQueueTests.swift` and its
  siblings). It promises nothing else offline: no project of its own, no reading, no search. Owed: the same capture can
  be imported twice (#5884); capture is not offered before the first pairing.
- `ios.offline.says-what-it-is` — **[GAP]** (#6754; its own issue → #6868) a phone opened with no connection says "Not connected to <Mac>" and
  that captures will wait, in place of an empty project. Today the workspace is drawn over the device's own empty
  reference with the recovery bar above it. Test (not yet written): with `ios.project.never-its-own-path`.
- `ios.offline.last-seen-pages` — **[GAP]** (#3278) pages and lists already seen are kept for reading with no connection.
  Not built: nothing is stored on the device on purpose. An owner decision (see Open questions), not a step.

### Reading on the phone

- `ios.read.runs-on-the-mac` — **[PARTIAL]** (#3278) a reading asked for from the phone is run by the Mac's engine and
  shown on the phone when it lands (the shared workflow and Activity views; the change stream). No text is read on the
  device: the only Apple vision framework in the iOS app is VisionKit's document camera and the QR scanner
  (`Views/Capture/MobileCapturePickers.swift`, `Views/Connect/ConnectQRScannerIOS.swift`). Not seen on a device.
- `ios.read.on-device` — **[GAP]** (#2060) reading a captured page on the phone itself with Apple's text recognition, so a
  capture is searchable before it reaches the Mac. Not built; an owner decision (see Open questions).

### iPhone: one screen at a time

Owner rulings: 2026-11-13 (#6566: the iPhone is ONE drill-down stack, Sidebar → Items → Source → Reader → Info, Back one
level, not a segmented control) and 2026-11-21, which refines it: the sidebar and the folders drill by PUSH down to an
item, and on an item the person swipes sideways between its pages. The Reader and Info push buttons of #6566 become the
paging. The screens, in order:

| Level | Screen | Its name, shown once | A tap | Back |
|---|---|---|---|---|
| 0 | Sidebar: the projects, each project's top folders, Activity and the other app rows | none (the app) | a folder or project pushes level 1; an app row pushes its own list | — |
| 1…n | A folder: its subfolders first, then its items | the folder's name, in the bar | a subfolder pushes another level; an item pushes the item view | up one folder; from the first folder, the sidebar |
| n+1 | The item view: pages Source · Reader · Segments · Info | none in the bar: the page header is there; the item's name is the first line of Info | swipe or the header changes page | the folder it was opened from |

#### The drill-down

- `ios.nav.one-path` — **[BROKEN]** (#6566, closed as built; its own issue → #6944) the iPhone's navigation is ONE `NavigationStack` with
  ONE ordered path of typed steps held on the window (`WindowState`): `folder(id)` any number of times, then at most one
  `item(id)`. Every push and every Back is a change to that path, so the path can be tested with no view. Today the stack
  has no path: `compactLibraryReaderStack` (`Views/Shell/ContentView/Layout/ContentView+CompactReader.swift:85`) declares
  THREE destinations on the list root, `navigationDestination(item:)` for the file (:101) and two
  `navigationDestination(isPresented:)` for Reader (:120) and Info (:123). Destinations declared on one view all present
  at the same depth, so presenting Reader REPLACES the file: SwiftUI writes the file's binding back to nil, and the
  observer at :128-134 answers nil by clearing the Reader and Info flags, the detail document and the selection. A tap on
  Reader or Info therefore lands the person back on the list with nothing selected. Measured 2026-11-21 in a 100-line
  SwiftUI program of the same shape (below). Tests (not yet written): `CompactPathTests.swift` (the path after each tap
  and each Back, with no view); `IOSDrillDownUITests.swift` (the real app on a simulator).
- `ios.nav.item-opens-from-its-folder` — **[PARTIAL]** (#5964, #2666; → #6567 for the white flash) a tap on an item in a
  folder pushes the item view on its Source page, and the picture stays drawn. By the code the push is wired: the tap
  writes the selection (`LibraryView.handleTap`, `Views/Library/LibraryView+Selection.swift:220`), the stack's observers
  resolve the leaf (`resolveCompactReaderLeaf`, `ContentView+CompactReader.swift:36`) and push it; the leaf map is tested
  (`fichero/Tests/Unit/general/Views/Shell/CompactReaderLeafTests.swift`). It has never been run: no UI test drives it,
  and the owner's phone shows the page for a moment and then a white view (#6567, open since 2026-11-12, unassigned).
  Two things in the code can take a pushed file away again, both of which write the detail document to a FOLDER while a
  file is showing, which the leaf rule (a folder never pushes) turns into a pop: a folder not yet in the store is cleared
  and fetched, and its answer is applied whenever the Mac replies (`ContentView+StateEvents.swift:105-113`); and a folder's
  children finishing their load promote the folder unless the focus is a direct child (`MainContentModifiers+ViewMode.swift:
  68-79`: a page of a PDF or a group inside the folder is not a direct child). Over a slow link both land seconds after
  the tap. Not proven to be the cause of #6567; the path rule removes both, because with a path a pushed item is popped
  only by Back. Acceptance (UI test, real root view, seeded project): from a folder, tap an image → the item view's
  Source page exists and the image element still exists 5 s later, with the Mac's answers delayed by 3 s.
- `ios.nav.folders-push` — **[BROKEN]** (#5964; its own issue → #6945) a folder tapped in a folder's list PUSHES that folder's screen, and Back
  returns to the folder it was tapped in. Today a folder tap at compact width re-roots the SAME screen
  (`LibraryView+Selection.swift:250-256` → `navigateToDocument`, `ContentView+SourceNavigation.swift:9-13`: it sets the
  view mode and the sidebar's selection, and pushes nothing), so however deep the person is, the system Back leaves the
  whole list for the sidebar, and there is no way up one folder. A group (a document of pages) and a PDF with pages are
  folders here: they push a level that lists their pages, and never the item view at the same time (today a group or PDF
  both re-roots the list and is pushed as a file, because the leaf rule excludes only `docType == .folder`,
  `ContentView+CompactReader.swift:47`). Acceptance: Sidebar → folder A → subfolder B → Back shows A's list (B's row
  there) → Back shows the sidebar. Tests: `CompactPathTests.swift`, `IOSDrillDownUITests.swift`.
- `ios.nav.sidebar-drills` — **[BROKEN]** (#5964; its own issue → #6946; owner 2026-11-21) on the iPhone the sidebar never expands a row in
  place: no disclosure triangle, no child rows under a folder. A tap on a project or a folder pushes that folder's screen
  (`ios.nav.folders-push`); its subfolders and items are there. Today the iPhone gets the Mac's tree unchanged: every
  folder row with children is a `DisclosureGroup` (`Views/Sidebar/ItemRow/SidebarItemRow+Presentation+Body.swift:174`),
  each project is one (`Views/Sidebar/Sections/SidebarView+UnifiedLibrarySections.swift:87`) and so is the Models node
  (`Views/Sidebar/Sections/SidebarModelsNode.swift:24`); none of the three has an iOS branch, and the click fallbacks
  that make a folder's name select on the Mac are compiled out on touch (`SidebarView+UnifiedRows.swift:248-265`,
  `SidebarView+FallbackTap.swift:10-16`), so what a tap on a folder's name does on the phone is the system's choice
  (expand, by the owner's report). Rule: at the phone idiom the sidebar's rows are flat: projects (with their top-level
  folders under each, one level, not collapsible), then the app rows; sources are never sidebar rows on the phone. The
  iPad keeps the Mac's tree (it has the width for it, and a pointer and keyboard use it as on the Mac). Acceptance: no
  element with the disclosure trait exists in the sidebar on an iPhone; tapping a folder shows a screen titled with the
  folder's name whose Back button is the sidebar. Tests: `SidebarPhoneRowsTests.swift` (the phone's row list for a
  seeded tree has no expandable row and no source row), `IOSDrillDownUITests.swift`.
- `ios.nav.back-is-one-step` — **[BROKEN]** (#5964; → #6945) Back, and the edge swipe, pop exactly one screen: item view → its
  folder → the folder above → … → the sidebar. Leaving the item view clears the list's selection so the same row can be
  tapped again. Today Back from a nested folder goes to the sidebar (`ios.nav.folders-push`) and "Back" from Reader or
  Info is never reached (`ios.nav.one-path`). Tests: `CompactPathTests.swift` (Back from every depth).
- `ios.nav.phone-in-every-orientation` — **[BROKEN]** (#2408; its own issue → #6949) an iPhone uses the drill-down in portrait and in
  landscape; turning the phone keeps the screen, the page and the place. Today the drill-down is chosen by
  `horizontalSizeClass == .compact` alone (`Views/Shell/ShellLayoutPolicy.swift:20-26`; no source reads the device
  idiom), and a large iPhone in landscape reports a regular width: the window switches to the Mac's pane row, the stack
  and its pushed screen are torn down, and turning back starts from the list. Rule: the phone idiom always drills; an
  iPad drills only while its window is compact (Slide Over, a narrow Split View) and returns to panes when it widens,
  keeping the item. Tests: `CompactShellPolicyTests.swift` (phone × regular width → the drill-down); UI: rotate on the
  item view, the page header still shows the same page.
- `ios.nav.other-kinds` — **[PARTIAL]** (#6493) Chat, a workflow, Activity and Research are each a list that pushes its
  detail (`compactInnerModeStack`, `CompactShellPolicy.route`,
  `fichero/Tests/Unit/general/Views/Shell/CompactShellPolicyTests.swift`). Owed: each is its own `NavigationStack` today;
  they join the one path with the same step type when `ios.nav.one-path` lands.

#### The item view: pages you swipe between

- `ios.item.pages` — **[GAP]** (#6566; → #6947; owner 2026-11-21) the item view is a horizontal paged container with four
  pages, in this order: **Source** (the image or the PDF page), **Reader** (its text), **Segments** (the page with its
  segments and the selected segment's text), **Info** (the Inspector's sections for the item). The order is the order of
  the work: look, read, check the pieces, then the facts; it is also the Mac's pane order. More pages are added at the
  end. Pages are mounted when first shown, never all four on push (a Reader that loads text nobody asked for is a call to
  the Mac). A page with nothing to show says why in one sentence (the Mac's empty-pane words), it is never skipped, so
  the count and the order never change under the person's thumb. Built from the panes the Mac already has
  (`previewView`, `widescreenReadingPane()`, the Segments pane, `inspectorView`); no second Reader or Inspector.
  Acceptance, one per page: Source shows the item's image element; Reader shows the transcript's first line for the
  seeded letter, or the empty sentence for the photograph; Segments lists the seeded letter's three lines; Info shows
  the item's name and kind. Tests: `ItemPagesTests.swift` (the page list and order; the empty sentence per kind),
  `IOSItemPagesUITests.swift`.
- `ios.item.swipe-changes-page` — **[GAP]** (#6566; → #6947) a horizontal swipe moves one page; at the first page a swipe from
  the screen's left edge is Back, anywhere else it does nothing; at the last page a swipe left does nothing. Acceptance:
  from Source, three swipes left show Reader, Segments, Info in turn and a fourth changes nothing; three swipes right
  return to Source; an edge swipe on Source pops to the folder. Tests: `IOSItemPagesUITests.swift`.
- `ios.item.header-says-where` — **[GAP]** (#6566; → #6947) the bar's centre holds one small segmented header, Source · Reader ·
  Segments · Info, with the showing page selected; a tap on a name goes to that page with no swipe. It is the only title
  the item view has (`ios.titles.once-at-most`). It replaces the Reader and Info bar buttons of #6566
  (`compactDocumentStepToolbar`, `ContentView+CompactReader.swift:150-163`), which are removed with `CompactDocumentStep`.
  On the narrowest phone at the largest text size the header shows glyphs with the names as accessibility labels.
  Tests: `ItemPagesTests.swift` (header selection follows the page and the reverse), `IOSItemPagesUITests.swift` (tap
  Info from Source).
- `ios.item.page-is-remembered-per-window` — **[GAP]** (#6566; → #6947; a default the owner may change, Open question 4) the
  page last used is remembered for the WINDOW, not per item: a person reading through a folder in the Reader opens the
  next item in the Reader. It lasts while the app runs; a fresh launch starts on Source. Per-item memory was considered
  and not chosen: it makes the page the person lands on depend on what they did to that item last week. Tests:
  `ItemPagesTests.swift`.
- `ios.item.zoom-wins-over-paging` — **[GAP]** (#6566; → #6947) on the Source page a picture at fit pages with a horizontal
  swipe; a zoomed picture pans, and a horizontal drag NEVER changes page while it is zoomed, even at the picture's edge
  (the paged container's scrolling is off while the zoom is above fit). Pinch and double-tap zoom as they do now
  (`Views/Preview/ImageViewer/ZoomableImagePreviewIOS.swift`); double-tap again returns to fit, where swiping pages
  again; the header works at any zoom. Acceptance: pinch to 2×, drag left three times: still Source; double-tap; swipe
  left: Reader. Tests: `IOSItemPagesUITests.swift`.
- `ios.item.segments-own-their-gestures` — **[GAP]** (#6566; → #6947; Open question 5) on the Segments page a drag belongs to
  the page (select, and later the editor's tools), so a swipe does not change page there: the person leaves Segments by
  the header or by Back. On the phone the page first ships as look-and-select (tap a segment, read its text below); the
  drawing tools (Brush, Knife, Marker, Order) stay on the Mac and the iPad until the owner asks for them on the phone.
  Tests: `IOSItemPagesUITests.swift` (a horizontal drag on Segments leaves Segments showing).
- `ios.item.next-and-previous-item` — **[GAP]** (#6566; → #6947; Open question 6) the sideways swipe is taken by the pages, so
  the next and previous item in the folder are two buttons at the bottom of the item view (and VoiceOver actions), which
  replace the item in place: the path's last step changes, nothing is pushed, Back still returns to the folder, and the
  page stays the same page. Tests: `CompactPathTests.swift`.
- `ios.item.voiceover-reaches-every-page` — **[GAP]** (#6566; → #6947) with VoiceOver on, every page is reachable without the
  swipe gesture: the header is a tab group whose four tabs are named and say "selected" and "1 of 4"; the paged
  container is adjustable (swipe up or down moves a page) and answers the three-finger scroll; changing page moves the
  VoiceOver focus to the new page's first element and announces its name. Tests: `IOSItemPagesUITests.swift` (the four
  header buttons exist with their labels and one has the selected trait; activating each shows its page).

#### Names and titles

- `ios.titles.once-at-most` — **[BROKEN]** (#4416; its own issue → #6948; owner 2026-11-21) every iPhone and iPad screen shows its name once
  at most. Today, by the code: the folder's list has the name in the bar (`.navigationTitle(toolbarTitle)`, set on both
  the split view, `ContentView+RootLayout.swift:386`, and the stack's root, `ContentView+CompactReader.swift:94`) and again
  in the Items pane's own head inside the view (`showsPaneHead`, on by default, `Views/Library/LibraryView+Body.swift:137`;
  the compact mount does not turn it off) and in the path row of its bottom inset where that is shown; the pushed file has its name in the bar
  (`ContentView+CompactReader.swift:106`) and again in the editor's header row directly under it (`EditorView.headerBar`,
  `Views/Preview/EditorView.swift:60-62`, on because the compact mount does not pass `showHeader: false`,
  `ContentView+DetailLayout.swift:508`); the Reader and Info screens say "Reader" and "Info" in the bar above panes that
  carry their own heads (the Reader's `PaneHead`, `Views/Reader/Page/ReadingPaneView.swift:472`). The rule, per screen: **sidebar** no title (the bar holds the connection item only); **a folder**
  its name in the bar, inline, once, and no pane head or path row in the view (sort, filter and view mode stay, in the
  bottom bar); **the item view** no name in the bar (the page header is there), the item's name is the first line of the
  Info page; **Source** nothing over the picture; **Reader, Segments, Info** no second head inside the page. On the iPad
  a pane keeps its pane head and the bar's centre island names the item, so the bar's own title is empty there.
  What a hidden title still does: every screen keeps its `navigationTitle` (the folder's or the item's name) even when
  the bar does not draw it, because the Back button of the NEXT screen and the long-press Back menu read it, and
  VoiceOver reads it when the screen appears. So Back from the item view says the folder's name, and Back from a folder
  says the folder above or "Projects" for the sidebar (today the sidebar's title is the empty string,
  `Views/Sidebar/SidebarView+ObservedChain.swift:41`, so that Back button has no words). Acceptance: on each of the
  screens above, the folder's or item's name appears as at most one static text; each Back button has a non-empty label.
  Tests: `IOSTitlesUITests.swift`; `CompactTitlesTests.swift` (the title and back-title per path step).
- `ios.source.no-dead-open-button` — **[BROKEN]** (#1881; its own issue → #6950) the phone offers no button that cannot work. The editor's
  header shows "Open with default app" on iOS, which opens a file URL built from the item's path ON THE MAC
  (`EditorView.swift:119-127`, `openWithDefault` :318); on a phone it opens nothing. It goes with the header row.
  Tests: `IOSTitlesUITests.swift` (no such button on the item view).

#### What a first-time person meets

- `ios.nav.page-does-not-flash` — **[BROKEN]** (#6567) a pushed page stays drawn; today it shows and then the view goes
  white. See `ios.nav.item-opens-from-its-folder` for the two candidate causes; settled by its acceptance test.
- `ios.wait.says-what-it-waits-for` — **[PARTIAL]** (#6572, #6559) while a folder's list or a page's picture is coming
  from the Mac the screen shows what is already in hand (the row's thumbnail, enlarged, for a page) under a progress
  mark, never an empty white view, and after 3 s says it is still loading from the named Mac. The list has a spinner
  with words (`LibraryView+FilterAndBatch.swift:294-297`); the page's spinner landed with #6559; neither names the Mac or
  the wait. Screen-sized images and tiles are #6572 (`ios.ipad.page-images-fit-the-screen`), for the phone too.
- `ios.a11y.text-sizes` — **[PARTIAL]** (#3686; its own issue → #6951) the drill-down's screens follow the system text size up to the
  accessibility sizes: rows grow, nothing is cut off without a way to read it. By the code 71 text styles under `Views/`
  are fixed point sizes (16 of them in the Items views, 27 in the shell) and four places use a scaled metric. Not seen at
  any size. Tests: `IOSTitlesUITests.swift` run at the largest accessibility size (every row's name is hittable and not
  truncated to nothing).
- `ios.a11y.rows-say-what-a-tap-does` — **[PARTIAL]** (#5763; → #6951) a row's VoiceOver words are its name, its kind and what
  a double tap does ("opens the folder", "opens the page"). Rows and tiles have a combined label and a selected trait
  (`Views/Library/LibraryViewComponents.swift:351-355`, `LibraryThumbnailViews.swift:292-296`); the hint on touch says
  only "Double tap and hold for actions", and a folder row in the sidebar reads "expanded" or "collapsed", which goes
  with `ios.nav.sidebar-drills`.

### Search and Ask on the phone

- `ios.search.one-field` — **[PARTIAL]** (#6563) the system search field in the content bar (a magnifier until tapped)
  runs the same search as the Mac's field, on the Mac, and its results replace the items list; a tapped result pushes its
  Source like any item (`iOSToolbarSearchable`, `resolveCompactReaderLeaf` reads the shown results:
  `fichero/Tests/Unit/general/Views/Shell/CompactReaderLeafTests.swift`). Ask / Keyword and where it looks are in the
  bar's overflow menu. Not seen on a device.
- `ios.ask.needs-the-macs-model` — **[PARTIAL]** (#6754) Ask and Chat use the models set up on the Mac; when the Mac has
  none, or the call is refused, the phone says so. Today the providers call was one of those refused in #6754 and the
  phone said nothing.

### iPad: panes side by side

- `ios.ipad.the-macs-panes` — **[PARTIAL]** (#5762, #6564) the iPad shows the Mac's panes (Projects, Items, Source,
  Inspector, Reader, Segments) and drops panes by width, never by a measured collapse (`WidescreenPanePlan`,
  `m2p.ios.no-measured-collapse`); each window in Stage Manager has its own selection and project
  (`m2p.ios.window-state-per-scene`). Owed: a narrow pane drawing over its neighbour (#6564); rotation is slow (#2408).
- `ios.ipad.reaches-source-reader-inspector` — **[PARTIAL]** (#5762) at regular width a tap on an item in the Items pane
  selects it, and the Source, Reader and Inspector panes that are open follow the selection, as on the Mac; a pane that
  is not open is opened from the bar's Workspaces menu (it lists the panes with a check, `showsWorkspacesMenu`,
  `Views/Shell/ContentView/ContentView+Toolbar.swift:243`) or the Inspector's Show/Hide (#6561). That is what the code
  does (the regular branch of `centerContentRouting`, `ContentView+SidebarLayout.swift:233-248`, is the Mac's one
  renderer); it was NOT seen on an iPad or a simulator in either review, and the owner is not sure it works, so it is
  not claimed broken or working. In a compact iPad window (Slide Over, a narrow Split View) the iPad takes the iPhone's
  drill-down and has its faults (`ios.nav.one-path`). Acceptance (UI test, iPad plan): tap an item → an image element
  exists in the Source pane; open Reader and Inspector from the menu → each shows the item. Tests:
  `IPadPanesFollowSelectionUITests.swift`.
- `ios.ipad.bars` — **[PARTIAL]** (#6563) the bars carry the Sidebar/Chat pair, Back/Forward, the centre island and
  search; the Inspector has its Show/Hide (#6561).
- `ios.ipad.page-images-fit-the-screen` — **[GAP]** (#6572) a page from the Mac arrives screen-sized, with tiles when
  zoomed, so a large scan opens quickly over Tailscale.

### Proof

- `ios.proof.builds-in-the-check` — **[GAP]** (#6390) the iOS app is built by the check on every change, so a
  macOS-only call in shared Swift cannot land (it has, at least five times since 2026-11-10 by the commit log).
- `ios.proof.flows-on-a-simulator` — **[GAP]** (#4771, #5982, #4782) the drill-down, the item's pages, a refused project
  and a lost connection each have a UI test that drives the app's REAL root view on a simulator, against the seeded
  harness engine, and the lane runs them. Today nothing can: the iPhone UI plan lists three tests (launch smoke, the
  socket check, the idiom canary: `fichero/Tests/plans/fichero-ui-ios.xctestplan`); the one navigation test,
  `fichero/Tests/UI/ios/IOSSidebarToLibraryUITests.swift`, is in no plan, says of itself that it was written and not run,
  and skips unless the app is already paired; no shared scheme carries the iPhone or iPad UI plan (`xcodebuild
  -showTestPlans` on the Dev Local scheme lists fichero, fichero-ui-general and fichero-ui-mac only), so
  `scripts/run_ios_ui_sim.sh`, which asks that scheme for `fichero-ui-ios`, cannot start; and the iOS launch needs a
  paired project (`EngineConfig.iosLaunchPhase`), which the script never gives it. The unit tests that pass
  (`CompactDocumentStepTests`, `CompactReaderLeafTests`, `CompactSidebarChoiceTests`, `CompactShellPolicyTests`) each
  test a pure function's table; none mounts a view, so none could see three destinations replacing one another. The
  recipe that launches the real root on a simulator with a project, worked out on 2026-11-21 (the app started; no
  screen was seen before the test Mac ran out of memory): the harness engine on a `/tmp` socket
  (`fichero-server/scripts/test_engine_harness.py --seed-mode full`), the app launched with `--uitesting`, the
  environment `FICHERO_FORCE_UDS_PATH=<socket>` and the launch arguments `-fichero.remote_access.paired_library_path
  <the seeded project>`.

## What was measured (2026-11-20)

- Engine tests for pairing, the device's project list and the project-path check: 60 passed in 13.7 s
  (`tests/unit/security/test_authz_accessible_libraries.py`, `test_a_device_revokes_its_own_pairing_6133.py`,
  `tests/unit/api/test_library_path_allowlist.py`, `test_owner_opened_library_is_served.py`,
  `tests/unit/transport/test_link_grants_its_project_to_spec.py`, `test_two_macs_end_to_end_to_spec.py`).
- The engine's answer to a device's own container path as the project, on a scratch engine: refused,
  `library_outside_allowed_locations`. The first refusal on a fresh engine took 4.7 s (it loads the owner's opened
  projects first); later ones about 1 ms. A project on an external volume that the owner has not opened in the app is
  refused the same way; one under Documents is allowed.
- No Swift test, simulator or device was run (the Mac was in use): every Swift line above is from reading the code.

## What was measured (2026-11-21)

- **The push fault, in SwiftUI itself.** A 100-line SwiftUI program with the shape on integration (one
  `NavigationStack`; on its root one `navigationDestination(item:)` and two `navigationDestination(isPresented:)`; the
  same "item became nil → clear the flags and the selection" observer), driven by writing the same state the taps write,
  on the macOS 27 SDK (the stack's model is shared with iOS; this is not an iPhone run):
  - tap an item: Source appears;
  - tap Reader: the Reader flag goes true, SwiftUI sets the item to nil in the same update, the observer clears the
    selection and the flag, the Reader disappears. End state: list, nothing selected. 10 ms from tap to cleared;
  - without the observer: Reader replaces Source (item nil), then Info replaces Reader (Reader flag false). One screen
    deep, never two;
  - with each destination declared on the screen that pushes it (Source's on the list, Reader's on Source, Info's on
    Reader): Source, Reader, Info stack three deep, and Back pops Info, then Reader, with the item kept.
- **The iOS app builds** for the simulator at integration b6fd967 (Debug, arm64), app and the iPhone UI test bundle.
- **The Dev Local scheme's test plans**: fichero, fichero-ui-general, fichero-ui-mac. No iPhone or iPad UI plan.
- **No screen was seen.** One build Mac has no simulator runtime installed and no desktop session for the build user;
  the other (8 GB) had its memory taken by other work, and the simulator drove its load average past 800 before the
  first frame, so the run was stopped and removed. Every line about what the phone SHOWS is from the code.

## Open questions (the owner's)

1. Offline reading: should pages and lists already seen be kept on the phone (`ios.offline.last-seen-pages`)? It is a
   cache with its own size, privacy and staleness rules; nothing is built.
2. Reading on the device with Apple's text recognition (`ios.read.on-device`): wanted for captures waiting in the queue,
   or is "the Mac reads" the whole story?
3. Several projects of one Mac open at once on the iPad (#2498), or one at a time as on the phone?
4. The item's page is remembered for the window while the app runs (`ios.item.page-is-remembered-per-window`). Is that
   right, or should every item open on Source?
5. Segments on the phone: look and select only at first, with the drawing tools left to the Mac and the iPad
   (`ios.item.segments-own-their-gestures`)?
6. With the sideways swipe given to the pages, the next and previous item are two buttons
   (`ios.item.next-and-previous-item`). On the iPad the sideways swipe turns the page (#6559) and up/down flips
   renditions (#6573); should the phone's Source page use up/down for the next item instead of buttons?
7. A compact iPad window (Slide Over, a narrow Split View) uses the iPhone's drill-down
   (`ios.nav.phone-in-every-orientation`). Agreed, or should the iPad always keep panes?
8. On the phone's sidebar each project lists its top-level folders, one level, under its name
   (`ios.nav.sidebar-drills`). Or should a project be one row that pushes its top level?

## Build order

The iPhone's navigation comes first (owner, 2026-11-21): the person cannot get from a folder to the picture, the Reader
or the Inspector, so nothing else on the phone can be judged. Each step is one builder step of 25 files or fewer, and
each ends with a test that drives the app's real root view on a simulator, not an injected one.

### Stage 1 — The iPhone drill-down

#### Step 1.1 — The iPhone UI lane runs, and the file's pushes stack
- Behaviours: `ios.proof.flows-on-a-simulator`, `ios.nav.one-path`, `ios.nav.item-opens-from-its-folder`, `ios.nav.page-does-not-flash`
- Tests: IOSDrillDownUITests.swift, CompactPathTests.swift
- Size: M

#### Step 1.2 — Folders push, the sidebar drills, Back is one level
- Behaviours: `ios.nav.folders-push`, `ios.nav.sidebar-drills`, `ios.nav.back-is-one-step`
- Tests: CompactPathTests.swift, SidebarPhoneRowsTests.swift, IOSDrillDownUITests.swift
- Depends on: 1.1
- Size: M

#### Step 1.3 — The item view: four pages, a header, swipe
- Behaviours: `ios.item.pages`, `ios.item.swipe-changes-page`, `ios.item.header-says-where`, `ios.item.page-is-remembered-per-window`, `ios.item.voiceover-reaches-every-page`
- Tests: ItemPagesTests.swift, IOSItemPagesUITests.swift
- Depends on: 1.2
- Size: M

#### Step 1.4 — Zoom, the Segments page and the next item keep their gestures
- Behaviours: `ios.item.zoom-wins-over-paging`, `ios.item.segments-own-their-gestures`, `ios.item.next-and-previous-item`
- Tests: IOSItemPagesUITests.swift, CompactPathTests.swift
- Depends on: 1.3
- Size: M

#### Step 1.5 — One name per screen at most
- Behaviours: `ios.titles.once-at-most`, `ios.source.no-dead-open-button`
- Tests: IOSTitlesUITests.swift, CompactTitlesTests.swift
- Depends on: 1.3
- Size: S

#### Step 1.6 — The phone drills in every orientation; the other lists join the path
- Behaviours: `ios.nav.phone-in-every-orientation`, `ios.nav.other-kinds`
- Tests: CompactShellPolicyTests.swift, IOSDrillDownUITests.swift
- Depends on: 1.2
- Size: S

#### Step 1.7 — Waiting, text sizes and VoiceOver words on the drill-down
- Behaviours: `ios.wait.says-what-it-waits-for`, `ios.a11y.text-sizes`, `ios.a11y.rows-say-what-a-tap-does`
- Tests: IOSTitlesUITests.swift
- Depends on: 1.5
- Size: M

#### Step 1.8 — The iPad's panes follow a tapped item, seen on a simulator
- Behaviours: `ios.ipad.reaches-source-reader-inspector`
- Tests: IPadPanesFollowSelectionUITests.swift
- Depends on: 1.1
- Size: S

### Stage 2 — The project and the connection

#### Step 2.1 — The first project reference is the Mac's (#6754, #6868)
- Behaviours: `ios.project.never-its-own-path`, `ios.offline.says-what-it-is`
- Tests: PairedLaunchLibraryTests.swift
- Size: M

#### Step 2.2 — A refused or missing project is said, with its buttons (#6754)
- Behaviours: `ios.project.problem-is-shown`, `ios.ask.needs-the-macs-model`
- Tests: GuestLibraryProblemBannerTests.swift
- Depends on: 2.1
- Size: S

#### Step 2.3 — One way to choose a project, remembered (#6796, #6797)
- Behaviours: `ios.project.one-way-to-choose`, `ios.project.pairing-with-several-asks-which`
- Tests: IOSProjectChoiceTests.swift, PairingChoosesAProjectTests.swift
- Depends on: 2.2
- Size: M

#### Step 2.4 — Every address of the link is a fallback (#6798)
- Behaviours: `ios.connect.falls-back-to-the-macs-other-address`
- Tests: PairingRecordsEveryAddressTests.swift
- Size: M

#### Step 2.5 — A reconnect fetches again (#6754)
- Behaviours: `ios.project.survives-the-macs-restart`
- Tests: ReconnectReloadsTheProjectTests.swift
- Depends on: 2.1
- Size: S

#### Step 2.6 — The iOS build and the refused-project flow in the check (#6390)
- Behaviours: `ios.proof.builds-in-the-check`
- Tests: IOSRefusedProjectUITests.swift
- Depends on: 2.2
- Size: M
