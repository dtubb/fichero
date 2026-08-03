# Overnight plan, Monday 2026-08-03 → Tuesday 2026-08-04

Daniel is out until tomorrow. Standing instruction: work steadily, follow open
issues and milestones, close what completes, no more questions tonight.

## Already answered by Daniel today (do not re-ask)

- **Geometry storage: word-level everywhere.** Shipped; do not "optimise" to
  line-level later without asking.
- **Presets: validate then drop the `(Untested)` label** (#4501). Not invert.
- **Paid spend: ONE gold-page ensemble run.** Does not renew.
- **If the ensemble loses to free Apple Vision, make Vision the default tier.**
- **iPad: add an iPad-specific test target** (#4472).
- **Box libraries (#4498): Daniel checks those himself.**
- **Release: tomorrow morning, not today.**

## Order of work tonight

1. **Build the pending Swift and push `main`.** Blocked on disk: DerivedData
   was cleared at Daniel's request, so the next build is COLD and needs room.
   Snapshots are expiring steadily. `main` stays at the last build-verified
   commit until then — that is the point of holding it.
2. **The authorised gold-page run**, then act on the result without waiting.
3. **OpenAPI regen for `CreateBatchRequest.selection`** (#4500) — mine, needs a
   Swift package build, so it queues behind disk too.
4. **#4472 — add the iPad-specific test target.** A pbxproj change, done
   carefully: Xcode rewrites that file, so verify the diff and revert anything
   the tool touched beyond the target.
5. **#4501 phase 1** — validate every preset reachable free (on-device or
   fixtures), then produce a per-preset cost estimate for the rest. Do not
   spend against it.
6. **MLX on-device models** — Daniel's last ask. Two parts: (a) do they work,
   and has anything ever tested them; (b) their settings belong in the AI
   models & providers screen, not a separate one.

## Deliberately NOT doing tonight

- Cutting a release (Daniel: tomorrow morning).
- Surveying the Box libraries (his).
- Anything under #4421 marked "not blocking" — toolbar/chrome placement, the
  canvas and 3D surfaces, chat IA, multi-level cataloguing, lint.

## Standing rules that cost real time when broken tonight

- A fix is not landed because its tests pass — it is landed when the caller
  that matters invokes it (#4415 taught this twice).
- Every count in an issue is a hypothesis. Six were wrong today, in both
  directions.
- `swiftc -parse` is not a build: it caught nothing that the type-checker later
  caught, twice.
- Deleting disk frees nothing while snapshots pin it. Only expiry works.
