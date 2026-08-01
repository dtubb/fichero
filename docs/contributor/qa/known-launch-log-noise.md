# Known launch log noise

Fichero embeds a WKWebView (the Knowledge Graph pane) and runs sandboxed on
macOS, both of which produce a predictable set of system-level Console
messages on launch and first reader/KG use. None of the four patterns below
are app bugs — each is standard macOS/WebKit framework behavior that appears
for effectively any sandboxed app in the same situation, not something
Fichero's code path triggers or can silence from the app side.

Filed as #3378–#3381 ("Log Errors" milestone) asking for exactly this
classification. Recorded here rather than left as four open "investigate"
issues, so the next log sweep doesn't re-open the same question.

## Apple Intelligence / Assistant entitlement noise (#3378)

```
-[AFPreferences _languageCodeWithFallback:] No language code saved, but Assistant is enabled
AFIsDeviceGreymatterEligible Missing entitlements for os_eligibility lookup
Unable to create bundle at URL ((null)): normalized URL null
```

`AFPreferences`/`AFIsDeviceGreymatterEligible` are Apple's internal Assistant
Framework running a system-wide Apple Intelligence eligibility probe on
process launch — on macOS with Apple Intelligence available, this fires for
essentially every app regardless of whether it uses Siri/AI features at all.
It is not gated by any entitlement Fichero could add; the "missing
entitlements" message is the framework's own internal probe failing
gracefully, not a request Fichero made.

## WebKit process launch latency (#3379)

```
GPU process took 2.585230 seconds to launch
Networking process took 2.194497 seconds to launch
WebContent process took 2.139281 seconds to launch
```

WebKit's multi-process architecture spins up dedicated helper processes
(GPU, Networking, WebContent) the first time a `WKWebView` is created in a
process — this is a one-time cold-start cost of the framework, not
per-window or per-use. Worth re-checking if a future profiling pass shows
these processes relaunching repeatedly within one app session (that WOULD
be actionable — eager/repeated `WKWebView` creation), but the raw multi-second
first-launch cost itself is inherent to WebKit, not a Fichero regression.

## Metal/CoreFSCache flock contention (#3380)

```
flock failed to lock list file (.../com.apple.metal/.../functions.list): errno = 35
fopen failed for data file: errno = 2 (No such file or directory)
Errors found! Invalidating cache...
flock failed to lock list file (.../com.apple.metal/32024/libraries.list): errno = 35
```

`errno = 35` is `EWOULDBLOCK` — another process (or another launch of
Fichero itself) held the same shared, per-user Metal shader cache lock at
the same moment. Metal's own cache layer detects the contention, invalidates
the stale entry, and rebuilds it — this is documented, self-healing OS cache
behavior for a system-wide shared resource, not an app-specific failure.

## WebContent sandbox pasteboard / LaunchServices denial noise (#3381)

```
WebContent Connection to 'pboard' server had an error: XPCErrorDescription = Connection invalid
Failed to set up CFPasteboardRef 'Apple CFPasteboard general'
Process unable to create connection because the sandbox denied the right to lookup com.apple.coreservices.launchservicesd
Missing the com.apple.linkd.autoShortcut mach-lookup entitlement
Error registering app with intents framework
```

The `WebContent` process is Apple's own sandboxed WebKit renderer, deny-listed
from pasteboard/LaunchServices/intents access by WebKit's own sandbox
profile unless the hosting app explicitly opts in — Fichero's KG pane does
not need clipboard or LaunchServices access from inside the renderer, so
these are the sandbox correctly denying capabilities nothing asked for, the
same chatter any app embedding `WKWebView` sees.
