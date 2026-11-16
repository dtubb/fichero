# web/

`index.html` is the placeholder landing page.

## Universal links

The pairing universal link is `https://tubb.ca/apps/fichero/pair?payload=…` (owner ruling 2026-11-02; it was
`fichero.app/pair`, #3791). The `apple-app-site-association` file that tells iOS which app claims it is served from the
**tubb.ca site repository**, the one source: appID `QAPB6CWYR6.app.fichero.fichero`, path `/apps/fichero/pair`. It is not kept
here, so there is no second copy to drift.

The app also needs the Associated Domains entitlement `applinks:tubb.ca`. That is a provisioning change and the owner's.
Until it lands, only the `fichero://pair?payload=…` form opens the app from Messages.
