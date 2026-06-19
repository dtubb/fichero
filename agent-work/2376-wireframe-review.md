# Issue #2376 Wireframe Review

Date: 2026-06-19

Goal: redesign connection and capture onboarding so the product reads as human tasks, not engine plumbing.

## Ponytail / YAGNI Rules

1. Prefer native SwiftUI controls and platform defaults.
2. Only keep custom UI where the workflow truly needs it.
3. Never expose pairing internals in the default path.
4. Security and data-loss handling are part of the design, not a later polish pass.

Default UI should not show:

- Engine URL
- API base
- SPKI pin
- pairing payload
- pairing code
- localhost fallback on mobile

## State Model

### Mac host sharing

- `sharingAvailable = true`
  - The Mac has a trusted HTTPS address.
  - Show QR directly.
  - Show connected devices when any exist.
- `sharingAvailable = false`
  - The Mac has no trusted HTTPS address yet.
  - Replace the QR block with one plain warning and no pairing internals.

Exact copy:

```text
Share This Mac
Secure sharing needs HTTPS.
Use Tailscale HTTPS or another trusted HTTPS address, then Fichero can show a QR code here.
```

### Host paired devices

- `pairedDevicesEmpty = true`
  - Show an empty state under `Connected Devices`.
- `pairedDevicesEmpty = false`
  - Show a normal list with revoke/remove actions.

Exact empty-state copy:

```text
No devices have joined yet.
Devices that scan this QR will appear here.
```

### Mobile launch

- `connected = false`
  - Launch into QR-first onboarding.
  - Capture Queue is the second primary action.
- `connected = true`
  - Launch into the library.
  - Capture Queue remains one tap away in the primary toolbar/tab.

### Capture Queue

- `queueEmpty = true`
  - Show an empty state.
- `queueNonEmpty = true`
  - Show queued items.
- `offlineUploadPending = true`
  - Surface the queue count and a recovery message.
- `uploadInterruptedOnRelaunch = true`
  - Restore the item as retry-required, not silently uploaded.

Exact status copy:

```text
Uploads stay on this device until Fichero can reach the paired library again.
```

Interrupted upload copy:

```text
This upload was interrupted before it completed. Tap Retry to upload it again.
```

## Text Wireframes

### 1) Mac host settings

Use the existing Settings form, but the default surface becomes task-based:

```text
Backend Settings

Connected
Fichero is running on this Mac.

Share This Mac
Show a QR code so iPhone, iPad, Vision Pro, or another Mac can connect to this library.

[ QR CODE ]
Scan this with Fichero on another device.

[ Refresh QR ]

Connected Devices
No devices have joined yet.
Devices that scan this QR will appear here.

Nonempty example rows:

Daniel's iPad      Remove
Research MacBook   Remove

Connect This Mac to Another Fichero
Scan the QR code shown on the host Mac.

[ Scan QR Code ]

Manual link
Use this only if the camera is unavailable.
[ Paste Link ]
```

Notes:

- Keep `Share This Mac` and `Connect This Mac to Another Fichero` visible without scrolling through backend terms.
- Do not show the API base, SPKI pin, pairing payload, pairing code, or embedded engine address on the default path.
- If sharing is unavailable because HTTPS is missing, the QR block becomes the warning state above.
- If the Mac is using the explicit embedded local engine path, localhost can remain an implementation detail, not a default onboarding control.

### 2) Mac remote-client join

This is the standalone join surface for a Mac joining someone else's Fichero library:

```text
Connect This Mac to Another Fichero

Scan the QR code shown on the host Mac.

[ Scan QR Code ]

Manual link
Use this only if the camera is unavailable.
[ Paste Link ]
```

Rules:

- Manual entry accepts one complete invite link or QR payload.
- No separate URL, code, or certificate fields.
- The page should not ask the user to assemble connection data.

### 3) iPad / iPhone / visionOS launch when disconnected

First screen when no paired host is active:

```text
Fichero

Connect to your Mac
Scan the QR code shown in Fichero Settings on the host Mac.

[ Scan QR Code ]

Capture Queue
Save photos, PDFs, and web pages now. Fichero uploads them when this device connects.

[ Open Capture Queue ]

Manual link
Use only if scanning is unavailable.
[ Paste Link ]
```

Rules:

- Scan QR is the primary action.
- Capture Queue is the second primary action.
- Manual link fallback is visually secondary.
- Never mention localhost on mobile onboarding.

visionOS note:

- Keep the same launch structure.
- If camera scanning is unavailable, the manual link fallback is the only alternate path and stays secondary.

### 4) iPad / iPhone connected capture entry

Once paired, the user lands in the library, but capture remains easy to reach:

```text
Library

[ Capture ] [ Search ] [ Queue ]

Connected to Daniel's Mac
Capture Queue: 2 pending
Uploads stay on this device until Fichero can reach the paired library again.
```

Rules:

- Capture Queue stays available while connected.
- Pending uploads should be visible as a count or badge.
- No need for a separate "connection" screen once the app is already paired.

## Security and Data-Loss Handling

- QR should only appear when the host has a trusted HTTPS address.
- Mobile clients must not silently fall back to localhost.
- Queue items must survive app relaunch.
- Items that were mid-upload when the app quit should reload as retry-required.
- Offline captures must be safe to accumulate before pairing or while disconnected.
- Capture metadata is limited to the current first slice: library/folder/collection destination only. No per-photo naming/catalog expansion in this issue.

## Implementation Notes

Likely UI surfaces:

- `fichero/fichero/Views/Settings/BackendSettingsView.swift`
- `fichero/fichero/Views/Settings/BackendSettingsRemoteAccessSection.swift`
- `fichero/fichero/Views/Settings/MacRemoteClientPairingSection.swift`
- `fichero/fichero/FicheroApp_iOS.swift`
- `fichero/fichero/Views/Capture/MobileCaptureQueueView.swift`
- `fichero/fichero/Models/MobileCaptureQueue.swift`
- `fichero/fichero/Views/Library/LibraryWorkspaceRoot.swift`

Likely state helpers:

- `EngineConfig` / `RemoteAccessConfig` for host-sharing availability and localhost gating
- `RemoteClientPairing` for invite-link parsing and join flow
- `MobileCaptureQueueRouting` and `MobileCaptureQueueStore` for offline queue recovery
- `AppState` launch gating for connected vs disconnected entry

Design implications:

- Replace the editable engine-host/pairing internals in the default settings pane with task labels and short human copy.
- Use standard SwiftUI grouping, `ContentUnavailableView`, `DisclosureGroup`, `ToolbarItem`, and ordinary form rows before inventing anything custom.
- QR display belongs to the host-sharing card, not to a hidden advanced panel.
- Manual fallback belongs to join flows only, and only as a secondary action.

## Test Plan

Focus on helper and state tests, not pixels.

1. Add or extend tests that prove mobile clients reject localhost fallback.
2. Add or extend tests that prove host sharing is unavailable until HTTPS is present.
3. Add helper/state coverage for the disconnected launch decision: QR-first, Capture Queue second, manual link secondary.
4. Add queue-state coverage for:
   - empty queue
   - nonempty queue
   - pending offline uploads
   - interrupted upload recovery after relaunch
5. Add regression coverage that a mid-upload item reloads as retry-required and keeps its explicit retry behavior.

Relevant existing test areas:

- `fichero/fichero-tests/RemoteAccessConfigTests.swift`
- `fichero/fichero-tests/RemoteCertificatePinningTests.swift`
- `fichero/fichero-tests/MobileCaptureQueueTests.swift`
- `fichero/fichero-tests/AuthTokenMiddlewareStorageTests.swift`

## Remove From Default UI

- Engine URL field
- Effective API Base
- Pairing Payload
- Pairing Code
- Certificate SPKI pin
- localhost fallback for iPhone / iPad / visionOS
- "assemble the invite yourself" flows
- any pairing step that requires the user to type certificate material

## Outcome

This design keeps the onboarding surface small:

- Mac host: Share This Mac, Connected Devices, Connect This Mac to Another Fichero
- mobile disconnected: Scan QR + Capture Queue
- mobile connected: Library + always-available Queue

That matches the product direction and leaves the implementation room to stay mostly native.
