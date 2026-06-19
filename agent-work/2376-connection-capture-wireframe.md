# Connection and Capture UX Wireframe

Date: 2026-06-19

## Product Rule

Fichero should explain connection in user terms, not backend terms. A person should understand:

- This Mac can share its Fichero library.
- Another device can scan a QR code to connect.
- A phone or iPad can still capture material while offline, then upload later.

Security remains strict, but certificate pins, device tokens, and API base URLs are implementation details unless the user opens an advanced/debug view.

## Mac: Backend Settings

Default surface:

```text
Backend

[ Connected ] Fichero is running on this Mac

Share This Mac
  Let your iPhone, iPad, Vision Pro, or another Mac connect to this Fichero library.

  [ QR CODE ]
  Scan this with Fichero on another device.

  Address: fichero.local or https://<tailscale-name>
  [ Copy Link ] [ Refresh QR ]

Connected Devices
  Daniel's iPad                         [ Remove ]
  Research MacBook                      [ Remove ]

Connect This Mac to Another Fichero
  [ Scan QR ] [ Enter Link ]
```

Advanced/debug disclosure:

```text
Advanced
  Engine mode: Embedded Local Engine
  Local engine address: http://127.0.0.1:8765
  Remote access address: https://...
  Trust: verified secure connection
  [ Regenerate device trust ] [ Reset local engine ]
```

What disappears from the default surface:

- Editable "Engine URL" field.
- "Effective API Base".
- "Pairing Payload".
- "Pairing Code".
- "Certificate SPKI pin".
- "Apply and Restart Engine" as a normal pairing step.

If a secure QR cannot be shown, show one plain message:

```text
Secure sharing needs an HTTPS address.
Use Tailscale HTTPS or another trusted HTTPS address, then Fichero can show a QR code.
```

## Mac: Connect to Another Mac

Entry point:

```text
Connect to Another Fichero

Scan the QR code shown in Fichero Settings on the host Mac.

[ Scan QR Code ]

Manual link
  Use this only if the camera is unavailable.
  [ Paste Link ]
```

Manual mode accepts a full pairing link or QR payload. It should not require users to assemble URL, code, and trust material manually.

## iPhone, iPad, visionOS Launch

First screen when no host is connected:

```text
Fichero

Connect to your Mac
Scan the QR code shown in Fichero Settings on your Mac.

[ Scan QR Code ]

Capture Queue
Save photos, PDFs, and web pages now. Fichero uploads them when this device connects.

[ Open Capture Queue ]

Manual link
Use only if scanning is unavailable.
[ Paste Link ]
```

When connected:

```text
Library

[ Capture ] [ Search ] [ ... ]

Capture Queue remains available from the primary toolbar or tab.
```

## Capture Queue First Slice

The first implementation should be deliberately small:

- The user chooses the destination library and folder/collection once.
- Captures are queued locally when offline.
- Photos, PDFs, and web captures upload to that destination when connected.
- Queued uploads survive app relaunch.
- Uploads stuck in "uploading" after a crash are retried.

Do not add per-photo naming, catalog templates, entity watching, or workflow selection yet. Those are later layers.

## Acceptance Criteria

- Mac host Settings shows the QR code directly when secure sharing is available.
- A user can find the QR without scrolling through backend internals.
- Default UI never shows SPKI, token, API base, or pairing payload jargon.
- iPhone/iPad/visionOS starts with QR scan and Capture Queue.
- Manual entry is visually secondary and accepts one link/payload.
- iOS/iPadOS/visionOS never falls back to localhost.
- Mac localhost is used only for the explicit embedded local engine path.
- Capture Queue is available both before and after connection.
- Capture Queue retries stale in-flight uploads after relaunch.

## Proposed Issues

1. Redesign Mac Backend Settings around Share This Mac and Connect to Another Fichero.
2. Replace manual URL/code/SPKI fields with a single advanced manual pairing link flow.
3. Make iPhone/iPad/visionOS launch QR-first with Capture Queue as the second primary action.
4. Keep Capture Queue reachable while connected, not only on the disconnected screen.
5. Make capture uploads recover stale in-flight items after app quit or crash.
6. Add focused tests for connection-mode policy and capture queue relaunch recovery.

