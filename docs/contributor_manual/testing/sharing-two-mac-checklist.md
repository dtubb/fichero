# Sharing: two Macs, two people — tester checklist (spec `sharing.two-macs-end-to-end`)

Host A = this Mac. Guest B = the M4 (`ssh m4`; Tailscale). Use a throwaway library and two throwaway
accounts (never ~/Fichero or ~/Fichero Projects). Note the build sha on both. Record PASS/FAIL + one line per step.
Each FAIL: file or update an issue (milestone "Sharing & Pairing — Dead-Simple UX"), cite the spec id.

## Setup
1. A: launch the app (Dev Local from Xcode is fine). Settings › Users: Multi-user ON; create owner `alice`, editor `bob`. [ ]
2. A: create library "Share Test", import 3 pages. [ ]
3. B: `ssh m4 'tailscale status | head -3; sw_vers -productVersion'` — tailnet up, same app build installed. [ ]

## Steps (id = spec behaviour)
| # | Where | Do | Look at | Spec id | Result |
|---|-------|----|---------|---------|--------|
| 1 | A | Settings › Sharing: switch On | A pairing card with QR + code + address appears within ~10 s; no "Preparing the security certificate" hang | sharing.toggle-restarts-engine, sharing.pairing-over-uds | |
| 2 | A | `lsof -iTCP -sTCP:LISTEN \| grep 8765`; `dns-sd -B _fichero._tcp` | only 127.0.0.1 + one LAN/tailnet address (never `*`); record visible | sharing.listener, sharing.bonjour-advertises | |
| 3 | B | Settings › Sharing › connect to a Mac | B lists A (or accept the pasted link if browse missing = FAIL on mac-finds-host) | sharing.mac-finds-host | |
| 4 | B | Enter the code | pairs; no certificate error; Keychain entry made | sharing.mac-pairs, sharing.certificate-pinned | |
| 5 | B | Sign in as `bob` | picker shows people; bob must authenticate | sharing.device-chooses-person | |
| 6 | B | Open "Share Test" | library opens, 3 documents listed | sharing.opens-the-library | |
| 7 | B | Rename a document; edit a line | A shows it within ~3 s without refresh | sharing.edits-both-ways | |
| 8 | A | Edit a different note as alice | B shows it | sharing.edits-both-ways | |
| 9 | A | Inspector/audit (or `fichero actions list-audit-log`) | rows say `bob on <M4>` and `alice on <A>`; none `system` | sharing.who-did-it, sharing.names-on-edits | |
| 10 | B | Start a read run on one page | A › Activity shows the run live, started by bob on the M4, ends there | sharing.remote-run-in-host-activity | |
| 11 | A | Edit a note in window 1, edit another in window 2, Cmd-Z in window 1 | only window 1's step is undone | undo-everywhere, sharing.undo-after-remote-edit | |
| 12 | B then A | B edits note N; A (stale) edits N, then A Cmd-Z | A's stale edit gets keep-mine/take-theirs; undo refused with a sentence naming bob + time | sharing.stale-edit-both-ways | |
| 13 | A | Settings › Sharing: revoke the M4 | B's next action is refused with a re-pair message | sharing.revoke | |
| 14 | A,B | Re-pair; as bob pair a second device (if possible); revoke bob's first device | the devices it paired are listed first and revoked too | sharing.revoke-cascades | |
| 15 | B (tailnet) | Turn Wi-Fi off / use the .ts.net address | pair and edit over `tailscale serve` still work | sharing.tailscale-serve | |
| 16 | A | Switch Sharing Off | B shows one sentence ("A stopped sharing…"), closes shared windows, returns to its own projects; no "Can't Reach the Server" | sharing.off-closes-the-guest | |
| 17 | A | `lsof -iTCP -sTCP:LISTEN \| grep 8765` | nothing on the LAN address; loopback engine still alive | sharing.listener | |

## Collect
`log show --last 30m --predicate 'process == "Fichero"' > /tmp/A.log` on A; same on B via ssh; attach to issues.
Do not run xcodebuild test on A while testing (it quits the running app).
