# iPhone and iPad — Design Spec (#6754)

> Milestone: iPhone
> Manual: TBD — "Fichero on your iPhone and iPad": the phone opens a project that lives on a Mac, what it can do with no
> connection (capture, and nothing else), how to move from the list to the page, the reading and its information, and what
> each "not connected" message means and what to tap.
>
> Design-led (Testing Constitution). **Status: DRAFT, 2026-11-20.** Written from a code review of the iOS targets on
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
- On the iPhone one screen shows at a time and the person drills down: **Sidebar → Items → Source → Reader → Info**, and
  Back returns one step. On the iPad the Mac's panes sit side by side.
- With no connection the phone can still **capture** pages into a queue that uploads when the Mac is back. Nothing else is
  promised offline.
- Reading a page (turning its image into text) is done **by the Mac**. The phone asks for it and shows the result.

## Prior art

Apple's own split between a device and the Mac that holds the data (Photos on a shared library, Xcode's paired devices,
Finder's connected servers): one sidebar, the remote thing named by its machine, a plain "not connected" state with
Reconnect. For the drill-down, `NavigationSplitView` collapsing to a stack at compact width (Mail, Files, Notes), which is
what the shell already uses. For an outbox that survives being offline, Mail's Outbox. Nothing here is invented.

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
- `ios.offline.says-what-it-is` — **[GAP]** (#6754) a phone opened with no connection says "Not connected to <Mac>" and
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

- `ios.nav.drill-down` — **[PARTIAL]** (#5964; built by #6566) Sidebar → Items → Source → Reader → Info. A sidebar choice
  shows the items (`ContentView.preferredCompactColumnAfterSidebarChoice`,
  `fichero/Tests/Unit/general/Views/Shell/CompactSidebarChoiceTests.swift`); a tapped item pushes its Source; Source's bar
  offers Reader and Info, Reader's offers Info (`CompactDocumentStep.next`,
  `fichero/Tests/Unit/general/Views/Shell/CompactDocumentStepTests.swift`). Not seen on a device or a simulator. Owed: the
  Reader and Info screens are declared on the list (three `navigationDestination`s on one root), not on the screen that
  pushes them, which SwiftUI does not promise to stack in order; a UI test must show Source → Reader → Info → Back → Back
  → Back ends on the list (#4771).
- `ios.nav.back-is-one-step` — **[PARTIAL]** (#5964) Back pops one screen; leaving Source clears the selection so the list
  is clean and the same row can be tapped again (the `pushedReaderDocument` observer in `ContentView+CompactReader.swift`).
  Not seen on a device.
- `ios.nav.other-kinds` — **[PARTIAL]** (#6493) Chat, a workflow, Activity and Research are each a list that pushes its
  detail (`compactInnerModeStack`, `CompactShellPolicy.route`,
  `fichero/Tests/Unit/general/Views/Shell/CompactShellPolicyTests.swift`). Owed: the panes choice table at compact width.
- `ios.nav.page-does-not-flash` — **[BROKEN]** (#6567) a pushed page stays drawn; today it shows and then the view goes
  white.

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
- `ios.ipad.bars` — **[PARTIAL]** (#6563) the bars carry the Sidebar/Chat pair, Back/Forward, the centre island and
  search; the Inspector has its Show/Hide (#6561).
- `ios.ipad.page-images-fit-the-screen` — **[GAP]** (#6572) a page from the Mac arrives screen-sized, with tiles when
  zoomed, so a large scan opens quickly over Tailscale.

### Proof

- `ios.proof.builds-in-the-check` — **[GAP]** (#6390) the iOS app is built by the check on every change, so a
  macOS-only call in shared Swift cannot land (it has, at least five times since 2026-11-10 by the commit log).
- `ios.proof.flows-on-a-simulator` — **[GAP]** (#4771) the drill-down, a refused project and a lost connection each have a
  UI test on the iPhone and iPad plans; today those plans run a launch smoke only.

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

## Open questions (the owner's)

1. Offline reading: should pages and lists already seen be kept on the phone (`ios.offline.last-seen-pages`)? It is a
   cache with its own size, privacy and staleness rules; nothing is built.
2. Reading on the device with Apple's text recognition (`ios.read.on-device`): wanted for captures waiting in the queue,
   or is "the Mac reads" the whole story?
3. Several projects of one Mac open at once on the iPad (#2498), or one at a time as on the phone?

## Build order

#### Step 1.1 — The first project reference is the Mac's (#6754)
- Behaviours: `ios.project.never-its-own-path`, `ios.offline.says-what-it-is`
- Tests: PairedLaunchLibraryTests.swift
- Size: M

#### Step 1.2 — A refused or missing project is said, with its buttons (#6754)
- Behaviours: `ios.project.problem-is-shown`, `ios.ask.needs-the-macs-model`
- Tests: GuestLibraryProblemBannerTests.swift
- Depends on: 1.1
- Size: S

#### Step 1.3 — One way to choose a project, remembered
- Behaviours: `ios.project.one-way-to-choose`, `ios.project.pairing-with-several-asks-which`
- Tests: IOSProjectChoiceTests.swift, PairingChoosesAProjectTests.swift
- Depends on: 1.2
- Size: M

#### Step 1.4 — Every address of the link is a fallback
- Behaviours: `ios.connect.falls-back-to-the-macs-other-address`
- Tests: PairingRecordsEveryAddressTests.swift
- Size: M

#### Step 1.5 — A reconnect fetches again (#6754)
- Behaviours: `ios.project.survives-the-macs-restart`
- Tests: ReconnectReloadsTheProjectTests.swift
- Depends on: 1.1
- Size: S

#### Step 1.6 — The iOS build and three flows in the check (#6390)
- Behaviours: `ios.proof.builds-in-the-check`, `ios.proof.flows-on-a-simulator`, `ios.nav.drill-down`
- Tests: IOSDrillDownUITests.swift, IOSRefusedProjectUITests.swift
- Depends on: 1.2
- Size: M
