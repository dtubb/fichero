# Chapter 2. Installing and Updating


### System Requirements

- 
- 

macOS 26 Tahoe or laterApple Silicon (M1 or later)Fichero does not run on Intel Macs or on any macOS before 26.

### Downloading Fichero for Mac

Download the latest release from the releases page:

<https://github.com/dtubb/fichero/releases/latest>

Download the `.dmg` file, open it, and drag Fichero to your Applications folder.

Release builds are signed macOS app bundles. On first launch, macOS may show a Gatekeeper alert because Fichero was downloaded from outside the App Store. If that happens:

1.  
2.  
3.  

Right-click (or Control-click) the Fichero icon in Applications.Choose **Open** from the menu.Click **Open** in the confirmation dialog.You only need to do this once.

### TestFlight, iPhone, and iPad

Fichero is also available through TestFlight for Mac, iPhone, and iPad:

<https://github.com/dtubb/fichero#testflight>

The iPhone and iPad apps connect to an engine running on a Mac. See “iPad and remote access” in Chapter 9 for how to make a Mac engine reachable from another device.

### First Launch

When Fichero starts, its engine (`fichero-server`) launches automatically in the background. You may briefly see “Connecting to backend…” in the title bar while it starts; this is normal and takes a few seconds the first time. No separate Python installation is required — the engine is embedded in the app.

If the app cannot connect to the engine, the window shows a connection error with **Retry** and **Quit**.

### Updating

Releases are dated builds, and the Mac app updates itself: when a new release is published, Fichero offers the update in the app (via the Sparkle update mechanism). You can also always download the latest `.dmg` from the releases page and replace the app in Applications, or update through TestFlight if that is how you installed it.

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
