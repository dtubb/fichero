(AI generated. Not reviewed.)

# Remote Pairing Smoke Checklist

Use this checklist when validating mac-hosted QR pairing and remote clients.
It is the manual end-to-end gate for #2350.

Quick coverage summary:
- [ ] Mac host app opens, backend connected.
- [ ] Remote Access enabled.
- [ ] QR shown directly in Settings.
- [ ] iPad/iPhone scans QR.
- [ ] Pairing succeeds.
- [ ] Reconnect works.
- [ ] Content loads from configured remote host.
- [ ] No silent localhost fallback.

## Manager Build Gates
- [ ] `scripts/verify_all.sh --standard --macos --ios` run once as the combined manager gate.
- [ ] If a platform-specific failure needs isolation, rerun only the failing leg:
  `scripts/verify_all.sh --full --macos` or `scripts/verify_all.sh --full --ios`.
- [ ] Do not assume `--full` and explicit `--macos` / `--ios` should be run twice; one invocation with the intended legs is the gate.

## Preconditions
- [ ] Mac host app opens normally.
- [ ] Embedded backend is connected on the host Mac.
- [ ] Remote Access is enabled in Settings on the host Mac.
- [ ] Host `Reachable URL` is configured, non-localhost, and reachable from the client device.
- [ ] Host `Reachable URL` uses the intended production transport policy for remote pairing.
- [ ] iPad or iPhone is available on the same network / tailnet.
- [ ] Optional: second Mac is available for manual remote-client fallback coverage.

## Host Mac Checks
- [ ] Host opens into a working connected state; no external dev backend assumptions are required for the product path.
- [ ] Settings shows the pairing QR directly on the Mac host flow.
- [ ] QR generation succeeds without hidden owner/bootstrap setup.
- [ ] Refresh Devices works when the host is actually hosting remote access.
- [ ] Revoke is only shown/actionable in the owner-hosting context.

## iPhone / iPad QR Pairing
- [ ] iPhone/iPad opens directly into the QR scanning path when the backend is not already reachable locally.
- [ ] Client scans the host QR successfully.
- [ ] Pairing code exchange succeeds.
- [ ] Remote content loads from the configured remote host.
- [ ] No step silently falls back to `localhost`, `127.0.0.1`, or another loopback equivalent.
- [ ] No bootstrap/local token prompt or local-owner auth leak is observed during remote pairing.

## Reconnect / Persistence
- [ ] After app relaunch, the same client reconnects to the configured remote host without requiring manual host re-entry.
- [ ] Reconnect uses the paired remote device token path, not a localhost/bootstrap token path.
- [ ] If the host is temporarily unavailable, the app reports that cleanly instead of silently switching to localhost.
- [ ] Record whether reconnect reused the same paired record or required a fresh QR.

## Manual Fallback Paths
- [ ] Manual URL + pairing code entry works on the client as a fallback/debug path.
- [ ] Insecure remote HTTP host entry is rejected for non-local remote pairing paths.
- [ ] Explicit localhost/dev paths are only accepted where deliberately local, not as a remote-client fallback.

## Second Mac Fallback Coverage
- [ ] Second Mac can join through the macOS remote-client entry route.
- [ ] If remote host validation fails after pairing, the second Mac keeps or restores its previous session instead of being stranded on a dead host.

## Evidence To Record
- [ ] Host URL that was configured.
- [ ] Whether the host URL was HTTPS or a deliberately local/dev exception.
- [ ] Device model and OS version for each client tested.
- [ ] Whether reconnect reused the same pairing record or required a fresh QR.
- [ ] Any auth, token, or trust prompts seen during the flow.
- [ ] Any point where the UI suggested localhost, owner auth, or a different host than the configured remote target.

## Expected Result
- [ ] The Mac host, QR generation, iPhone/iPad pairing, reconnect, and remote content fetch all work end to end.
- [ ] The second-Mac fallback route works if exercised.
- [ ] No production remote-client step silently falls back to `localhost` or reuses bootstrap/local auth.
- [ ] Platform build legs and manual smoke together give one clear manager release gate for #2350.
