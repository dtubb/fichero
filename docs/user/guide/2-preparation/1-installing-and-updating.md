# Chapter 2. Installing and Updating

*Drafted by AI.*

### System Requirements

- macOS 26 Tahoe or later
- Apple Silicon (M1 or later)

Fichero does not run on Intel Macs or on any macOS before 26. It is built against the current macOS frameworks, and on Apple Silicon it can run AI models directly on the Mac — so a recent machine is not just a formality: it is the basis for the free, private, on-device models described in Chapter 9.

### Downloading Fichero for Mac

Download the latest release from the releases page:

<https://github.com/dtubb/fichero/releases/latest>

Download the `.dmg` file, open it, and drag Fichero to your Applications folder. Everything Fichero needs is inside that one app bundle — there is nothing else to install.

Release builds are signed macOS app bundles. On first launch, macOS may show a Gatekeeper alert because Fichero was downloaded from outside the App Store. If that happens:

1. Right-click (or Control-click) the Fichero icon in Applications.
2. Choose **Open** from the menu.
3. Click **Open** in the confirmation dialog.

You only need to do this once. (If you install from the Mac App Store or through TestFlight instead, macOS trusts the app directly and this step does not apply.)

### TestFlight, iPhone, and iPad

Fichero is also available through TestFlight for Mac, iPhone, and iPad:

<https://github.com/dtubb/fichero#testflight>

The iPhone and iPad apps connect to an engine running on a Mac. They are companions to the Mac app rather than standalone: the library and its processing live on the Mac, and the iOS apps read and drive it over your own network. See “iPad and remote access” in Chapter 9 for how to make a Mac engine reachable from another device.

### First Launch

When Fichero starts, its engine (`fichero-server`) launches automatically in the background. You may briefly see a short status message — “Connecting to the engine…”, “Loading runtime libraries…” — while it starts; this is normal, and takes a few seconds the first time. No separate Python installation is required: the engine is embedded in the app, runs on your own Mac, and by default listens only on your machine (see Chapter 9).

If the app cannot connect to the engine, the window shows a connection error with **Retry** and **Quit**.

### Updating

Releases are dated builds, and how Fichero updates depends on how you installed it:

- **Direct download (`.dmg`).** The app updates itself: when a new release is published, Fichero offers the update in place (through the Sparkle update mechanism), and you can also check any time from **Fichero ▸ Check for Updates…**. You can always re-download the latest `.dmg` from the releases page and replace the app in Applications instead.
- **Mac App Store.** Updates arrive through the App Store, like any other app.
- **TestFlight.** Updates arrive through the TestFlight app.

### Alpha Software

Fichero is in active development. The library format may change between releases. Keep original copies of any documents you import, and do not use Fichero as your only copy of anything.

To report bugs, ask questions, or request features, use GitHub Discussions at <https://github.com/dtubb/fichero/discussions>. GitHub Issues are the development backlog.

### Quickstart: Your First Ten Minutes

1. Open Fichero. It starts with a ready-to-use local library — no setup.

2. Drag a folder of PDFs or scans onto the window. The import runs in the background; watch progress in Activity.

3. Click a document. The Reader shows the page; the inspector on the right shows what Fichero knows about it.

4. Select a few pages, right-click, and run a transcription preset. (Set up an AI provider first in Settings \> AI — a local model works without an account.)

5. When the run finishes, open the inspector's Artifacts section to see what was produced, and the Knowledge section for extracted people and places.

6. Search from the toolbar — results include matches by meaning, not just exact words.

That is the whole loop: import, read, run a workflow, inspect, search. Everything else in this manual is detail.
