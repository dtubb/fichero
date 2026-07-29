(AI generated. Not reviewed.)

# Installing Fichero

## System requirements

- macOS 26 Tahoe or later
- Apple Silicon (M1 or later)

Fichero does not run on Intel Macs or on macOS 14 or earlier.

---

## Download

Download the latest release from the Fichero releases page:

[https://github.com/dtubb/fichero-releases/releases/latest](https://github.com/dtubb/fichero-releases/releases/latest)

Download the `.dmg` file, open it, and drag Fichero to your Applications folder.

---

## First launch

Current release builds are distributed as signed macOS app bundles. On first
launch, macOS may show a Gatekeeper alert because Fichero was downloaded from
outside the App Store. If that happens:

1. Right-click (or Control-click) the Fichero icon in Applications.
2. Choose **Open** from the menu.
3. Click **Open** in the confirmation dialog.

You only need to do this once. After that, Fichero should open normally.

When Fichero starts, fichero-server launches automatically in the background. You may see "Connecting to backend…" briefly in the title bar while it starts. This is normal, and it takes a few seconds the first time.

No separate Python installation is required. The engine is embedded in the app.

---

## Alpha software

Fichero is in active development. The library format may change between releases. Keep original copies of any documents you import, and do not use Fichero as your only copy of anything.
