# Remote Pairing Smoke Checklist

Use this checklist when validating mac-hosted QR pairing and remote clients.
It is the manual end-to-end gate for #2350.

## Preconditions
- [ ] Mac host is signed in and the Fichero app opens normally.
- [ ] The embedded backend is connected.
- [ ] A reachable private URL is configured for the host, not a localhost-only URL.
- [ ] An iPad or iPhone is available on the target network or tailnet.

## Smoke Steps
- [ ] Mac host app opens, backend connected.
- [ ] Remote Access enabled.
- [ ] QR shown directly in Settings.
- [ ] iPad/iPhone scans QR.
- [ ] pairing succeeds.
- [ ] reconnect works.
- [ ] content loads from configured remote host.
- [ ] no silent localhost fallback.

## Evidence To Record
- [ ] Host URL that was configured.
- [ ] Device model and OS version of the client.
- [ ] Whether the reconnect used the same pairing record or required a fresh QR.
- [ ] Any auth or token prompts seen during the flow.

## Expected Result
- [ ] The Mac host, QR pairing flow, reconnect, and remote content fetch all work end to end.
- [ ] No step silently falls back to `localhost` or `127.0.0.1`.
