# Known launch log noise

Fichero embeds a WKWebView (the Knowledge Graph pane) and runs sandboxed on
macOS, both of which produce a predictable set of system-level Console
messages on launch and first reader/KG use. None of the patterns below are
app bugs — each is standard macOS/WebKit framework behavior that appears
for effectively any sandboxed app in the same situation, not something
Fichero's code path triggers or can silence from the app side. (The one
thing that WAS ours — no recovery when a WebContent process dies — is fixed;
see the 2026-08-04 section.)

Filed as #3378–#3381, #3383 ("Log Errors" milestone) asking for exactly this
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

## WebContent bootstrap-denial storm + `CRASHSTRING: XPC_ERROR_CONNECTION_INVALID` (2026-08-04)

```
Sandbox restriction: deny mach-lookup com.apple.pasteboard.1 ... rdar://28724618
[WebContent] unable to lookup launchservicesd/coreservicesd/RunningBoard/networkd/AudioComponentRegistrar
CRASHSTRING: XPC_ERROR_CONNECTION_INVALID
RBS assertion failure ... webkit entitlements
Unable to create bundle at URL ((null))
```

Seen in a Dev Local (Debug, sandboxed) ⌘R console: every WebContent child
(6+ PIDs per session) emits a burst of bootstrap-lookup denials and some die
with `CRASHSTRING: XPC_ERROR_CONNECTION_INVALID`.

**What was verified, and how.**

- *Minimal-host reproduction (empirical, 2026-08-04, macOS 26.3.1).* A
  ~40-line sandboxed WKWebView host (swiftc-built, `com.apple.security.app-sandbox`
  + `get-task-allow`, zero configuration beyond `loadHTMLString`) had its
  WebContent process **terminate once during startup** —
  `webViewWebContentProcessDidTerminate(_:)` fired — after which WebKit
  respawned the renderer and the page rendered normally. WebContent
  early-life death under a sandboxed Debug-style host is therefore
  reproducible with no Fichero code involved.
- *The denial chatter is WebKit's own.* The `rdar://28724618` marker in the
  `Sandbox restriction` lines is baked into WebKit's own WebContent sandbox
  profile (WebKit logs-and-denies those lookups deliberately); the pboard /
  launchservicesd family is already classified in #3381/#3383 above. The
  storm text appears in the **Xcode debug console** (the debugger relays
  child-process stderr) — during the same window the unified system log
  contains none of it, which is why a `log show` sweep looks clean while ⌘R
  looks like a crisis.
- *Entitlements are NOT the fix (documented).* `com.apple.security.inherit`
  is for helper executables the app itself embeds and spawns, and is
  explicitly **incompatible with `get-task-allow`** — i.e. with every Debug
  build (Apple: "Embedding a command-line tool in a sandboxed app").
  WebContent/GPU/Networking children are Apple's own XPC services
  (`com.apple.WebKit.WebContent`) launched by launchd with their own sandbox
  profiles and entitlements; nothing in the host app's entitlements file
  configures them. The Debug target's sandbox comes from
  `ENABLE_APP_SANDBOX = YES` plus the capability build settings in
  `project.pbxproj`, and that is correct as-is.

**What Fichero does about it.** The real defect on our side was that **no
surface implemented `webViewWebContentProcessDidTerminate(_:)`** — Apple's
documented recovery hook — so a renderer death (which demonstrably happens
even in a minimal host) left the reader/preview pane blank until the user
changed documents. Every web surface (KG reader pane both platforms,
`FicheroWebView`, `WebContentCanvas`) now reloads through the shared bounded
policy in `WebContentProcessRecovery` and logs each death under the
`WebContentRecovery` category, so a real crash-loop is visible as OUR log
line rather than inferred from Apple's console residue.

**Residue that remains and is inherent:** the per-WebContent bootstrap-denial
burst, the `rdar://28724618` lines, `Unable to create bundle at URL ((null))`
(the AFPreferences probe, #3378), and teardown `XPC_ERROR_CONNECTION_INVALID`
when a WKWebView (and thus its renderer) is deallocated. A session in which
`WebContentRecovery` stays quiet had no renderer deaths, whatever the Xcode
console storm looks like.

## WebKit resource/network sandbox noise in reader views (#3383)

```
WebContent Unable to filter tracking query parameters (missing data)
networkd_settings_read_from_file Sandbox is preventing this process from reading /Library/Preferences/com.apple.networkd.plist
AudioComponentRegistrar connection invalidated: Operation not permitted
Unable to hide query parameters from script (missing data)
nw_path_necp_check_for_updates Failed to copy updated result (22)
```

Same family as #3381: the sandboxed `WebContent` process is denied reading
system-wide `networkd`/audio-registrar preference files it has no
entitlement for, and its built-in tracking-query-parameter filter (a WebKit
privacy feature, not something the KG pane configures) has nothing to work
with over the app's own local-engine scheme handler, which is what "missing
data" reports. None of this reflects a request Fichero's code made — every
line is WebKit's own subsystems probing capabilities the sandbox correctly
withholds from a renderer process, the same for any WKWebView-embedding app.
