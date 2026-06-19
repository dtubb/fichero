# Second-Opinion UX Review: #2376 Connection & Capture Flow

Date: 2026-06-19  
Reviewer: Claude (second opinion)  
Source docs: `2376-connection-capture-wireframe.md`, `2376-wireframe-review.md`

---

## Quick Verdict

Both prior docs land the right direction: QR-first, Capture Queue as offline backstop, jargon
behind a disclosure. Three things need sharper treatment before implementation starts:

1. **"Backend Settings" is still jargon.** The section title should be "Sharing" (Mac) and the
   disconnected mobile screen should be called nothing — it's just the first screen of the app.
2. **Neither doc draws the QR error path or the capture-item row.** Those are the two states
   users will spend the most anxious time in. Wireframes below fill that gap.
3. **visionOS is different enough from iPhone to need its own rule.** The camera assumption
   breaks there.

---

## What the Existing Wireframes Get Right

- QR as primary pairing action — correct
- Capture Queue visible before connection — correct
- Single invite link / payload for manual entry — correct
- Removing SPKI, pairing code, API base, and localhost from the default surface — correct
- "No devices have joined yet." empty-state copy — correct

These should not change.

---

## Changes by Surface

### Mac: Settings Section Title

**Change:** "Backend Settings" → rename the section to **"Sharing"**.

"Backend" is an engineering term. The section contains two user tasks: share this Mac, and
connect to another Mac. "Sharing" names both without leaking the implementation model. This
matches iCloud / AirDrop naming conventions in System Settings.

### Mac: Remove the "[ Connected ]" Status Badge

The original wireframe opens with:

```
[ Connected ] Fichero is running on this Mac
```

Cut this. If the user is in Fichero settings, Fichero is running. A "connected" label adds no
information and primes the user to worry about connection states before there is one. If the
engine genuinely stops, surface an error then — not a normal-state badge.

### Mac: "Share This Mac" Needs a Toggle

The existing wireframe shows the QR code unconditionally. Add a single on/off toggle so the
user can stop sharing without removing their paired devices. Default state is on when HTTPS is
available, off when it is not (HTTPS-unavailable state auto-disables it and shows the
fallback warning). This matches the AirDrop model and makes it easy to pause access without
revoking it.

### Mac: "Refresh QR" Is Not a Default Action

"Refresh QR" implies to the user that the QR can expire or break. If the QR needs periodic
rotation (it should), rotate it silently in the background. Only surface a "Refresh" control
if the QR has visibly expired and the automatic refresh failed — that is an error state, not
a toolbar button.

If a manual refresh is needed for the host to revoke outstanding invitations, name it
**"Reset invite"** under the Advanced panel, not in the default card.

### Mac: "Copy Link" Placement

Keep the "Copy Link" action, but make it a secondary text button below the QR — not a
primary button. It is a fallback for the host who cannot show their Mac screen to the
connecting device. Keep it in the host card, not in the join flow.

### visionOS: Manual Link Is the Primary Path

visionOS does not have a rear camera suitable for QR scanning. On visionOS, the disconnected
launch screen should show the manual link field as the primary action and QR scan as the
secondary (or absent). The copy should change to:

```
Enter the link from Fichero Settings on your Mac.
```

This is the one platform where the hierarchy inverts.

### Connected Devices: Use Platform Icons

Use SF Symbols beside each device name to help users recognise their own hardware:
`iphone`, `ipad`, `laptopcomputer`, `applevisionpro`. These are all system-available in
visionOS 2 / iOS 18 / macOS 26. No custom artwork needed.

The "Remove" action label is fine. "Revoke" and "Disconnect" both sound more alarming than
the action warrants — the user is just removing a paired device.

### Mobile: The Disconnected Screen Has No Title

Neither wireframe names this screen explicitly. Do not give it a title like "Welcome" or
"Get Started". On iOS/iPadOS, the full-bleed launch treatment (centred logo, two primary
actions stacked) reads correctly without a header. A navigation title would shrink this into
a settings panel. Leave the title bar empty or use the app name from the bundle.

### Capture Queue: Define the Item Row

The existing docs describe the queue state machine but do not draw an individual item. The
row is where the user will interact during a failed or pending upload. Define it now so the
implementation doesn't invent something ad-hoc.

---

## Wireframes

### 1 — Mac Sharing Panel (default)

```
Settings > Sharing
──────────────────────────────────────────────────────────────────────

  Share This Mac                             [  On  ]
  Let iPhone, iPad, Vision Pro, or another Mac
  connect to this Fichero library.

  ┌─────────────────────────────────────────────────────────────────┐
  │                                                                 │
  │                       ▓▓▓▓▓▓▓▓▓▓▓                             │
  │                       ▓▓       ▓▓                              │
  │                       ▓▓  ███  ▓▓                              │
  │                       ▓▓       ▓▓                              │
  │                       ▓▓▓▓▓▓▓▓▓▓▓                             │
  │                                                                 │
  │           Scan this code with Fichero on another device.        │
  │                                                                 │
  │                    [ Copy invite link ]                         │
  │                                                                 │
  └─────────────────────────────────────────────────────────────────┘

  Connected Devices
  ┌─────────────────────────────────────────────────────────────────┐
  │  📱  Daniel's iPhone                             Remove         │
  │  💻  Research MacBook                            Remove         │
  └─────────────────────────────────────────────────────────────────┘

  Connect to Another Mac
  ─────────────────────────────────────────────────────────────────
  [ Scan QR Code ]

  Manual
  Use this only if the camera is not available.
  [ Paste invite link ]

  ▸ Advanced

```

**"Share This Mac" toggle OFF state** (HTTPS unavailable or user turned it off):

```
  Share This Mac                             [  Off  ]
  ┌─────────────────────────────────────────────────────────────────┐
  │                                                                 │
  │  Secure sharing needs HTTPS.                                    │
  │  Use Tailscale HTTPS or another trusted HTTPS address,          │
  │  then Fichero can show an invite code here.                     │
  │                                                                 │
  └─────────────────────────────────────────────────────────────────┘
```

**Advanced panel** (hidden by default, `▸ Advanced` DisclosureGroup):

```
  Advanced
  ──────────────────────────────────────────────────────────────────
  Engine            Embedded local engine
  Local address     http://127.0.0.1:8765
  Remote access     https://daniel-mac.tail12345.ts.net

  Trust             Verified secure connection

  [ Reset invite ]        [ Reset local engine ]
```

---

### 2 — Mac Connect to Another Fichero

This is a sheet or separate section, not a standalone window:

```
  Connect This Mac to Another Fichero
  ──────────────────────────────────────────────────────────────────

  Scan the QR code shown in Fichero Settings on the host Mac.

  [ Scan QR Code ]
  ─ or ─
  Paste invite link
  ┌─────────────────────────────────────────────────────────────────┐
  │ https://daniel-mac.tail12345.ts.net/fichero/join/…             │
  └─────────────────────────────────────────────────────────────────┘
  [ Connect ]

  ──────────────────────────────────────────────────────────────────
  Error state (wrong link / expired):

  ┌─────────────────────────────────────────────────────────────────┐
  │  ⚠  Couldn't connect                                           │
  │  The invite link may have expired or belong to a different      │
  │  library. Ask the host to share the code again.                 │
  └─────────────────────────────────────────────────────────────────┘
  [ Try Again ]
```

Rules:
- The paste field accepts one complete invite link — no separate URL, code, or certificate
  fields.
- "Connect" is inactive until the field is non-empty.
- Error copy does not mention certificate, token, or SPKI.

---

### 3 — iPhone / iPad: Disconnected Launch Screen

```
  ┌──────────────────────────────────────────┐
  │                                          │
  │                                          │
  │              [Fichero logo]              │
  │                                          │
  │                                          │
  │   Connect to your Mac                    │
  │   Scan the code shown in Fichero         │
  │   Settings on your Mac.                  │
  │                                          │
  │   ┌─────────────────────────────────┐   │
  │   │        Scan QR Code             │   │   ← filled primary button
  │   └─────────────────────────────────┘   │
  │                                          │
  │   ──────── or save for later ──────────  │
  │                                          │
  │   ┌─────────────────────────────────┐   │
  │   │        Capture Queue            │   │   ← secondary button (outline)
  │   └─────────────────────────────────┘   │
  │   Save photos and pages now.             │
  │   Fichero uploads them when connected.   │
  │                                          │
  │   Enter invite link manually             │   ← tappable text, not a button
  │                                          │
  └──────────────────────────────────────────┘
```

Rules:
- Scan QR: primary filled button, top half of screen.
- Capture Queue: secondary button below a divider, so it reads as a different path.
- Manual entry: plain tappable text at the bottom. Not a button. Harder to tap accidentally.
- No navigation bar title. No "Welcome to Fichero."

---

### 4 — visionOS: Disconnected Launch (inverted hierarchy)

```
  ┌───────────────────────────────────────────────────────────────┐
  │                                                               │
  │                     [Fichero logo]                            │
  │                                                               │
  │  Connect to your Mac                                          │
  │  Enter the invite link from Fichero Settings on your Mac.     │
  │                                                               │
  │  ┌────────────────────────────────────────────────────────┐   │
  │  │  Paste invite link                                     │   │
  │  └────────────────────────────────────────────────────────┘   │
  │  [ Connect ]                                                   │
  │                                                               │
  │  Scan QR Code (if a camera is available)                      │   ← secondary / conditional
  │                                                               │
  │  ──────────────────────────────────────────────────────────   │
  │                                                               │
  │  [ Open Capture Queue ]                                       │
  │  Save items now. Fichero uploads them when connected.         │
  │                                                               │
  └───────────────────────────────────────────────────────────────┘
```

---

### 5 — iPhone / iPad / visionOS: Connected, Capture Queue Entry

**Library toolbar (connected state):**

```
  Library                              🔍  📥 2  ···
                                       ↑         ↑
                                    Search   Queue badge (pending count)
```

**Capture Queue view:**

```
  ┌──────────────────────────────────────┐
  │  Capture Queue                   ✕  │
  │                                      │
  │  Connected to Daniel's Mac           │
  │                                      │
  │  ┌────────────────────────────────┐  │
  │  │ 🖼  DSC_0042.jpg               │  │
  │  │     Photos › 2026-06-19        │  │
  │  │     Uploading…                 │  │   ← progress indicator (spinner)
  │  └────────────────────────────────┘  │
  │                                      │
  │  ┌────────────────────────────────┐  │
  │  │ 📄  Borges - Labyrinths.pdf   │  │
  │  │     Books › Imports            │  │
  │  │     Waiting to upload          │  │   ← muted secondary text
  │  └────────────────────────────────┘  │
  │                                      │
  │  ┌────────────────────────────────┐  │
  │  │ 🌐  The Library of Babel       │  │
  │  │     saklatvala.com             │  │
  │  │     ⚠ Upload interrupted       │  │   ← warning colour
  │  │     [ Retry ]                  │  │   ← inline action button
  │  └────────────────────────────────┘  │
  │                                      │
  └──────────────────────────────────────┘
```

**Empty queue state (use `ContentUnavailableView`):**

```
  ┌──────────────────────────────────────┐
  │  Capture Queue                   ✕  │
  │                                      │
  │                                      │
  │              [inbox icon]            │
  │                                      │
  │         Nothing queued               │
  │   Photos and pages you capture       │
  │   will appear here until uploaded.   │
  │                                      │
  │                                      │
  └──────────────────────────────────────┘
```

**Disconnected state with pending items:**

```
  Uploads stay on this device until
  Fichero can reach the paired library again.    ← banner, not a modal
```

The banner should appear at the top of the queue list, not as a blocking sheet. The user can
still browse and add to the queue while offline.

---

## Implementation Slices

Ordered from least risk to most visible. Each slice is independently shippable and does not
require the next.

### Slice 1 — Mac Sharing Panel Copy and Section Title (pure copy / structure)

- Rename the settings section to "Sharing".
- Remove the "[ Connected ]" status badge from the default surface.
- Hide the QR refresh button unless QR is expired.
- Move SPKI / engine URL / API base / pairing payload behind a `DisclosureGroup("Advanced")`.
- Wire the "Share This Mac" toggle to the existing `sharingAvailable` state.

Files: `BackendSettingsView.swift`, `BackendSettingsRemoteAccessSection.swift`  
No new models, no new network code.

### Slice 2 — Connected Devices List with SF Symbol Icons

- Add device-type icons to each paired device row.
- Show the empty state when `pairedDevices.isEmpty`.
- Keep "Remove" as the action label.

Files: `BackendSettingsView.swift`  
Depends on: Slice 1 (same file pass).

### Slice 3 — Mac Join Flow (sheet or section)

- Implement the "Connect to Another Mac" join surface.
- Accept one paste field (full invite link).
- Show the error state with plain copy on connection failure.

Files: `MacRemoteClientPairingSection.swift` (new or extend)  
No new backend changes if the invite-link parser already exists.

### Slice 4 — iPhone / iPad Disconnected Launch Screen

- Replace the current mobile launch entry point with QR-first / Capture Queue second layout.
- Wire the "Enter invite link manually" tappable text to the existing paste flow.
- Ensure no localhost address appears anywhere on this surface.

Files: `FicheroApp_iOS.swift`, launch entry view  
Depends on: no backend changes; requires existing `AppState` connected/disconnected flag.

### Slice 5 — visionOS Disconnected Launch (inverted hierarchy)

- Fork the disconnected launch screen for visionOS.
- Paste field is primary; QR scan is conditional / secondary.

Files: launch entry view, visionOS conditional compilation block  
Depends on: Slice 4 structure.

### Slice 6 — Capture Queue State Machine and Persistence

- Model: `CaptureQueueItem` with states `waiting`, `uploading`, `interrupted`, `done`.
- Persist to disk (no backend required); items survive app relaunch.
- On relaunch, any item in state `uploading` transitions to `interrupted` automatically.

Files: `MobileCaptureQueueStore.swift` (new), `MobileCaptureQueueRouting.swift`  
This is the first slice that needs a test: prove the relaunch transition, prove
the offline accumulation, prove items are not silently dropped.

### Slice 7 — Capture Queue View

- `MobileCaptureQueueView`: item rows, empty state (`ContentUnavailableView`), offline banner.
- Queue accessible from toolbar badge while connected.
- Inline "Retry" for `interrupted` items.

Files: `MobileCaptureQueueView.swift`, toolbar wiring in `LibraryWorkspaceRoot.swift`  
Depends on: Slice 6 (state machine must exist first).

### Slice 8 — Upload to Library When Connected

- Upload items from the queue to the paired library on connection.
- Transition item to `done` on success; to `interrupted` on failure.
- Show progress inline in the queue row.

Files: `MobileCaptureQueueStore.swift`, network upload logic  
Depends on: Slice 6 and 7. This is the first slice that touches the backend API.

---

## What to Skip Until Later

- Per-item destination selector (folder / collection) — default to a single configured
  destination for the entire queue in this issue. Per-item routing is a second issue.
- Catalog templates, entity watching, workflow selection on capture — later layers.
- Re-pairing / device rotation UI — cover in a separate security-hygiene issue.
- Notifications for completed uploads — add after the queue is stable.
- Capture-while-connected (Share Sheet / Photos picker on iOS) — Slice 8 unblocks this but
  it should ship separately once the offline path is tested.

---

## Native Controls Checklist

Before adding any custom component, confirm the platform equivalent is unavailable:

| Need | Use |
|---|---|
| Settings section | `Form` + `Section` |
| Toggle | `Toggle("Share This Mac", isOn:)` |
| Empty state | `ContentUnavailableView` |
| Advanced disclosure | `DisclosureGroup` |
| Device list | `List` with `Label(deviceName, systemImage: deviceIcon)` |
| Inline error | `Section` footer text or inline `.foregroundStyle(.secondary)` |
| Queue item progress | `ProgressView()` inline |
| Offline banner | plain `Text(…)` in a `Section` header, not a sheet |
| QR display | `Image(uiImage:)` from `CIFilter` — no third-party QR lib needed |

---

## Copy Reference

For ease of implementation, all human-facing strings in one place:

| Context | String |
|---|---|
| Section title (Mac) | Sharing |
| Share toggle label | Share This Mac |
| QR subtitle | Scan this code with Fichero on another device. |
| QR secondary action | Copy invite link |
| No HTTPS warning | Secure sharing needs HTTPS. Use Tailscale HTTPS or another trusted HTTPS address, then Fichero can show an invite code here. |
| Empty devices | No devices have joined yet. Devices that scan this code will appear here. |
| Join section title | Connect to Another Mac |
| Join instruction | Scan the code shown in Fichero Settings on the host Mac. |
| Join manual label | Manual — use this only if the camera is not available. |
| Join error | Couldn't connect. The invite link may have expired or belong to a different library. Ask the host to share the code again. |
| Mobile disconnected headline | Connect to your Mac |
| Mobile disconnected body | Scan the code shown in Fichero Settings on your Mac. |
| Mobile capture headline (secondary) | Capture Queue |
| Mobile capture body | Save photos and pages now. Fichero uploads them when connected. |
| Mobile manual link | Enter invite link manually |
| visionOS instruction | Enter the invite link from Fichero Settings on your Mac. |
| Queue offline banner | Uploads stay on this device until Fichero can reach the paired library again. |
| Queue interrupted | Upload interrupted. Tap Retry to upload this again. |
| Queue empty title | Nothing queued |
| Queue empty body | Photos and pages you capture will appear here until uploaded. |
