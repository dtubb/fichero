# fichero.app static hosting (#3791)

Universal links need **only static files** — no server. Host this directory on
any HTTPS static host (GitHub Pages / Cloudflare Pages, free). The only cost is
the domain (~$10–15/yr).

## Files

- `.well-known/apple-app-site-association.template` — the AASA the OS fetches to
  learn which app claims `fichero.app`. Shipped with a `.template` suffix ON
  PURPOSE: it still contains the `TEAMID` placeholder, and a placeholder AASA
  served live is worse than none — Apple's CDN caches it for ~24h and every
  `https://fichero.app/pair` link silently fails until it flushes. **Substitute
  the real team ID, then rename to exactly `apple-app-site-association`** (no
  extension) before deploying. Serve it as `application/json`, over HTTPS, with
  NO redirects.
- `index.html` — the "get Fichero" landing page for someone who taps an invite
  without the app installed (currently a tapped link just dies).

## Before it works — two things NOT done here

1. **Replace `TEAMID`** in `apple-app-site-association.template` with the real
   Apple Developer Team ID (the app's bundle id is already correct:
   `app.fichero.fichero`), then **rename the file to `apple-app-site-association`**
   (drop the `.template` suffix). Do not deploy the placeholder version.
2. **Add the Associated Domains entitlement** to the app targets — NOT done in
   this lane because editing `*.entitlements` without matching provisioning
   profiles can break the signing gate. Add to `Fichero.entitlements`,
   `FicheroAppStore.entitlements`, and `FicheroRelease.entitlements`:

   ```xml
   <key>com.apple.developer.associated-domains</key>
   <array>
     <string>applinks:fichero.app</string>
   </array>
   ```

   …and enable the Associated Domains capability on each target's provisioning
   profile.

## What IS done in this lane (Swift side)

`RemoteClientPairing.isPairingInviteLink(_:)` now recognises
`https://fichero.app/pair?payload=…` as well as `fichero://pair?payload=…`, and
both `onOpenURL` handlers route through it — so once the two steps above are
done, a tapped universal link reaches the exact same pairing flow as the custom
scheme. The token is still redeemed peer-to-peer against the host in the payload,
never against this domain.

## Do not close #3791 on "the file is deployed"

Test the round trip on a **real device** (AASA is classic silent-failure
territory — see #2399). The link must actually open the app AND reach the
engine.
