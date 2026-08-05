# Profile Review — aug4.trace (2026-08-04)

Daniel captured `/Users/danieltubb/code/fichero/profile/aug4.trace` (356 MB)
while using the app: sidebar interaction, opening documents, importing.

**Read this as a starting point, not a diagnosis.** The hang *counts* below are
measured. The *attribution* is not — see "What is not established".

## What is in the trace

EMPIRICAL — `xcrun xctrace export --input <trace> --toc`:

One run. Schemas present include `time-profile`, `time-sample`,
`potential-hangs`, `hang-risks`, the `hitches-*` family, `os-log`,
`runloop-events`, and a SwiftUI group (`swiftui-updates`, `swiftui-causes`,
`swiftui-changes`, `swiftui-update-groups`, `SwiftUIFilteredUpdates`).

That last group matters: this capture can answer *which view bodies
re-evaluate and why*, which a plain Time Profiler cannot. It has not been
exported yet.

## Measured: main-thread hangs

EMPIRICAL — export of `table[@schema="potential-hangs"]`, 160 rows:

| | |
|---|---|
| Hang events | **160** |
| Total main-thread stall | **106.3 s** |
| Worst single hang | **7.22 s** |
| Longest flagged "Severe Hang" | **5.68 s** at 02:10.028 |

Top durations: 7.22 s, 5.68 s, 2.44 s, 2.34 s, 2.32 s, 1.87 s, 1.72 s,
1.68 s, 1.50 s, 1.37 s.

Note the cluster between **04:28 and 05:42**: eleven of the top fifteen hangs
fall in that ~75-second window, seven of them between 04:28 and 04:52. That is
one activity, not scattered slowness, and identifying what Daniel was doing then
is the cheapest next step.

## Suggestive, NOT established: where the time goes

An aggregation of `time-profile` backtraces was attempted and **the sampling
loop was too coarse to trust** — it captured only tens of samples out of
millions. The frames below are what surfaced and are recorded as *leads to
verify*, explicitly NOT as findings:

- `ObservationTracking._AccessList.addAccess(keyPath:context:)`
- `static AnyKeyPath.== infix(_:_:)`
- `_NativeDictionary._copyOrMoveAndResize(capacity:moveElements:)`
- `FicheroApp.body.getter` and several `closure #N in closure #2 in
  FicheroApp.body.getter`
- `FicheroClient.streamingResponse(pathComponents:queryItems:)`

Key-path comparison plus access-list growth is the shape of `@Observable`
tracking overhead, and `FicheroApp.body` is the **scene root** — if that
re-evaluates, everything below it is invalidated. If that were confirmed it
would be a large finding. It is not confirmed.

## What is not established

- Which code causes the 160 hangs. No verified symbol attribution.
- Whether launch is inside the capture.
- Whether the SwiftUI update storm suspected at launch appears here.
- Main-thread vs background split of CPU time.

## Next step (one shell-capable pass)

```bash
T=/Users/danieltubb/code/fichero/profile/aug4.trace
S=$(mktemp -d)
xcrun xctrace export --input "$T" --toc > "$S/toc.xml"
xcrun xctrace export --input "$T" \
  --xpath '/trace-toc/run[@number="1"]/data/table[@schema="swiftui-updates"]' \
  --output "$S/swiftui.xml"
```

Do the SwiftUI tables FIRST, not the time profile: `swiftui-updates` and
`swiftui-causes` name the view types and the reason for each update directly,
in a file orders of magnitude smaller than the 2.7 GB `time-profile` export.
For a UI-hang question that is the higher-signal, cheaper source.

Then correlate the 04:28–05:42 hang cluster against `os-log` for the same
window to recover what the app was doing.

## Method note

The agent first dispatched for this had no shell tool, so `xctrace` was never
run; its blocked report is superseded by this document. The numbers above were
produced directly. The unverified frame list is kept, clearly labelled, because
a lead recorded as a lead is useful and a lead recorded as a finding is not.
