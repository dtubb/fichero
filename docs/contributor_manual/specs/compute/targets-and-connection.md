# Remote Compute — Targets, installing and connecting — Design Spec (#TBD)

> Milestone: remote-compute
> Manual: TBD — "Adding a place to run work": the four kinds of place; what you need before you
> start (an account, a key, Docker on the far machine); what Fichero does for you and the one
> thing it cannot (your second factor); what the coloured dot on a row means; sessions and
> their time limit; removing a place and what is cleaned up.
>
> Design-led (Testing Constitution). **Status: DRAFT — first pass, 2026-09-20.** A slice of the
> compute set: read `remote-compute.md` first. Behaviours carry **no tag and no issue yet**, by
> the rule stated there. **VERIFIED / INFERRED** for our code; **CITED / UNVERIFIED** for
> outside services, with S-numbers from "Sources" in `remote-compute.md`.

## Intent

A researcher adds a place to run work once, in Settings, in words they recognise: *a Linux
machine*, *a cluster*, *Hugging Face*. Fichero does everything it honestly can: fetches the
right version of the server, starts it, pairs with it, checks what it can run. Where a person
must act (approving a second factor, pasting a public key into a cluster's account page) it
says exactly what to do and waits. A row never shows green unless Fichero has just reached the
place and had an answer. On a cluster, Fichero never pretends a server is there: it shows
jobs, and sessions with their time left.

## What exists today

- **A cluster as a reference, never a secret.** `HpcClusterConfig`: SSH host alias, username,
  remote base folder, partition, account, port (VERIFIED
  `workflows/remote_jobs.py:147-168`). It assumes the person's own `~/.ssh/config`, agent and
  keys.
- **Saved as one JSON value** in the app settings table under `hpc.clusters`, keyed by cluster
  id; no table, no migration (VERIFIED `api/routes/ai/hpc.py:50-53`, `:68-81`). Saving and
  deleting need the owner (`:207-250`). A change is broadcast as `hpc.updated` (`:84-91`).
- **"Test" does not test.** `POST /api/hpc/clusters/{id}/test` returns the `ssh … sinfo` command
  it would run and `ok: true` whenever the form is valid (VERIFIED `:253-285`). The
  provider-keys spec exists because of this same fault in another place (#4816: a green check
  that checked nothing).
- **Five MCP tools** wrap these routes (VERIFIED `fichero-mcp/tests/test_mcp_server.py:78-82`).
  **No app screen** does. Issue #4907 (open): the test route has no undo surface.
- **A remote mode for the server** that refuses any bind but loopback and reports itself on
  the health route (VERIFIED `security/remote_backend.py:92-133`).
- **A manual recipe** for a far server over an SSH forward, which overwrites the Mac's own
  token file because the app has nowhere to keep a second one (VERIFIED
  `docs/contributor_manual/remote-backend-acenet.md:82-96`).
- **Pairing exists**: a one-time link or QR code carrying a short-lived code and a certificate
  pin; a paired device gets its own token (`guide/15-remote-engines.md`, the Tailscale section;
  `scripts/create_tailscale_pairing_link.sh`).
- **Where keys live is ruled**: for a local engine, the app's own Keychain, pushed to the
  engine on connect (`ai/provider-keys.md`, "Two stores of truth").
- **A host for each library** is not built (#2573, open). Today the app has one engine address
  for everything.
- **The release build is sandboxed**; only the debug build is not (project record, corrected
  on disk 2026-09-19: `FicheroRelease.entitlements`). INFERRED consequence: the engine, a child
  of the app, cannot read `~/.ssh` or reach the person's SSH agent.

## The design (proposed)

### One list of machines

A **compute target** is a record in one list. The same list is, later, the list of machines a
collection can live on (#2573), so there is never a second "remote machine" setting.

| Field | Meaning |
|---|---|
| `target_id`, `name` | identity; the name the person gave it |
| `kind` | `this-mac` · `local-container` · `linux-machine` · `slurm-cluster` · `huggingface` |
| `address` | how it is reached: nothing; a tailnet name; an SSH host, user and port; nothing (Hugging Face) |
| `credential_ref` | the *name* of a secret in the one key store. Never the secret. |
| `remote_base_dir` | where Fichero may write there (`<base>/fichero/…`); absolute |
| `scheduler` | for a cluster: partition, account, default GPU request, default time limit |
| `operator_note` | who runs the place and where it is, in a sentence the consent sheet shows ("Digital Research Alliance of Canada; hosted in Canada; not designated for sensitive data") |
| `last_checked`, `last_result`, `capabilities` | the last real check, its outcome, and what the server there reported |

`this-mac` always exists and cannot be removed. It is the far side of the no-network job loop
(`remote-compute.md`, "How this is tested").

### What Fichero does on each kind

| Step | A Linux machine | A Slurm cluster | Hugging Face |
|---|---|---|---|
| Needs beforehand | SSH access; Docker installed there. Fichero does **not** install Docker or Tailscale: it checks and says what is missing. | an account and an allocation; Apptainer (the clusters provide it) | an account with credit; a fine-grained token |
| Credential | a key Fichero makes, for install and upkeep; then a paired-device token for the API | a key Fichero makes; the public half goes on the cluster's account page; **the second factor stays with the person** | the token |
| Install | pull the image of **this app's engine version**; start it with the port mapped to the machine's loopback and a data folder mounted; read back a one-time pairing link; pair | on a login node (which has the internet): pull the image once as an Apptainer file into `<base>/fichero/images/<version>.sif`; make the model cache folder. Nothing is started. | nothing |
| Reach | `tailscale serve` on that machine if it is on the person's tailnet; otherwise an SSH forward Fichero keeps open | SSH for submit, poll and fetch; an SSH forward through the login node for a session | HTTPS |
| Check | health route answers; versions match; `capabilities` read | SSH login succeeds; `sinfo` answers for the partition; the `.sif` of this version is present; the base folder is writable | token is valid; has permission to run jobs; credit is not zero |
| Remove | stop and remove the container; ask before deleting the data folder | ask before deleting `<base>/fichero/`; cancel nothing silently: running jobs are listed first | revoke nothing; forget the token |

### The key Fichero keeps

The person's own SSH set-up is out of reach of a sandboxed app (INFERRED), and a cluster's
unattended path needs a dedicated, restricted key in any case (CITED, S4). So, for each target
that uses SSH, Fichero makes a key pair. The private half is a secret in the one key store.
The public half is shown with a Copy button and the words for where to put it (the far
machine's `authorized_keys`; or the Alliance account page). Fichero's server speaks SSH itself,
in process, through a library; it does not shell out to the system's `ssh`. **This is the
largest unproven step in this slice and is tried first** (question 1).

### The second factor

On Alliance clusters a second factor is required for every SSH login and cannot be turned off
(CITED, S3). So:

- The **first** connection of a working session needs the person. Fichero shows "Approve the
  sign-in on your phone" (or asks for the code) and waits. It never stores a factor.
- Fichero keeps **one** connection open and runs everything through it, so the person is asked
  once, not once for each command.
- When that connection drops, work that needs it **pauses and says why**. Jobs already on the
  cluster keep running; they do not need the Mac.
- **Automation nodes** are the cluster's sanctioned unattended path: by written request, a key
  restricted to named commands from named addresses, no port forwarding (CITED, S4). Fichero
  can use one for submit, poll and fetch, so that overnight batch work needs no person. It
  cannot use one for a session. Fichero supports this as a setting on the target
  (`automation_host`), and the manual says how to ask for it. It is not required.

### Sessions

A session is a job that serves a model and is reached through a forward. Its row shows
*queued*, *starting*, *ready, 2 h 41 min left*, *ended*. When it ends, its provider row goes
with it, and anything that was using it fails with "the session on *name* ended", never with a
timeout. Details of what is served are in `jobs-and-fine-tuning.md`.

### Versions

A target's server is always the image of the **same engine version as the app**. After an app
update, a Linux machine's row reads "Server is 2026.09.19, this app is 2026.10.02: Update",
and work is refused until it is updated, because a job's package and its results are only
guaranteed to mean the same thing at one version. On a cluster, the new `.sif` is fetched
beside the old; old ones are removed when no job names them.

## Behaviors

All untagged and unbuilt unless stated.

### The list

- `compute.target.one-list` — **[GAP]** (#5238) compute targets live in one list, read and written through one
  set of routes (`/api/compute/targets`), with `kind` telling them apart. *Data:* one app-wide
  settings value `compute.targets` (JSON, keyed by `target_id`), the same shape of storage the
  clusters use today; a table only when #2573 needs it. *Existing data:* see the next line.
  *Test:* save, list, read, delete for each kind; owner required for save and delete.
- `compute.target.saved-clusters-carry-over` — **[GAP]** (#5238) on first read after the change, every entry
  under `hpc.clusters` becomes a target of kind `slurm-cluster` with the **same id**, its
  `host_alias` kept as the SSH host, `credential_ref` empty (so its row reads "Needs a key"),
  and the old value is left in place until one successful save of the new one, then removed.
  The `/api/hpc/*` routes and the five `fichero_hpc_*` MCP tools are renamed to the new ones;
  no alias is kept (foundation question 14). *Existing data:* converted, never dropped.
  *Test:* a settings table seeded with two old clusters yields two targets with the same ids;
  a second read changes nothing; a malformed old value is reported and left untouched.
- `compute.target.this-mac-is-a-target` — **[GAP]** (#5238) a target of kind `this-mac` always exists, cannot be
  removed, and runs a job by the same steps as any other target, with a local folder as the far
  side. *Data:* `<server state dir>/compute/this-mac/`. *Test:* the whole job loop in `pytest`
  with no network and no container.
- `compute.target.no-secret-in-the-record` — **[GAP]** (#5238) a target record holds the name of a secret and
  never the secret; the routes never return one; the change broadcast never carries one.
  *Test:* save a target with a credential; assert the stored JSON, the route's answer, the
  `compute.updated` event and the server log contain no part of it.
- `compute.target.lives-in-ai-settings` — **[GAP]** (#5238) targets appear in Settings, AI, in a section titled
  "Where work runs", as rows that each carry their own controls, in the way provider rows do
  (`settings.provider-detail-carries-its-own-controls`). *Routed:* the section's place in the
  window is `ai/ai-settings.md`'s. *Test:* availability leg: the section and its Add control are
  reachable.
- `compute.target.change-is-audited-and-undoable` — **[GAP]** (#5238) adding, changing and removing a target are
  registered actions with an inverse; "check" and "install" are recorded as non-undoable, by
  name, with the reason. This closes the part of #4907 that concerns these routes. *Test:*
  `scripts/check_undo_coverage.py` is green for every `/api/compute/*` route.

### Checking

- `compute.connect.check-really-checks` — **[GAP]** (#5238) "Check" reaches the target and reports what answered.
  `ok` is true only if every step for that kind (the table above) succeeded just now. The
  answer lists each step with *passed*, *failed: reason* or *not tried*. It never returns a
  command it "would" run as if that were a result. *Existing data:* the present dishonest
  `test` route is replaced by this one. *Test:* against the SSH-and-Slurm fixture: all pass; with
  the fixture's scheduler stopped: SSH passes, `sinfo` fails, `ok` is false.
- `compute.connect.dot-means-checked` — **[GAP]** (#5238) a row is green only when the last check passed **and**
  is recent; otherwise it shows when it last passed, or what failed. Opening Settings does not
  by itself contact a cluster (that would trigger a second-factor prompt). *Test:* pure Swift
  rule over `last_checked` and `last_result`.
- `compute.connect.version-must-match` — **[GAP]** (#5238) work is refused on a target whose server version is
  not this app's engine version, with a message naming both and offering "Update". *Data:* the
  version stamp both sides already carry (`harness/release-and-versioning.md`). *Test:* a fake
  target reporting another version refuses a job before anything is sent.

### A Linux machine

- `compute.target.add-linux-machine` — **[GAP]** (#5238) adding a Linux machine takes: a name, an SSH host, a
  user. Fichero makes the key, shows the public half and where to put it, waits for "Done",
  then checks. *Test:* click-around against a local SSH container.
- `compute.connect.install-on-linux-machine` — **[GAP]** (#5238) "Install" pulls the image of this engine
  version, starts it with the port mapped to `127.0.0.1` on that machine and a data folder
  mounted, reads back a one-time pairing link from the container, pairs, and stores the paired
  token as the target's API credential. If Docker is missing it stops at the first step and
  says "Docker is not installed on *host*"; Fichero installs neither Docker nor Tailscale.
  *Test:* in automation, against a Docker-in-Docker host: ends paired and green; with Docker
  absent: stops with that message and changes nothing.
- `compute.connect.reach-by-tailnet-or-forward` — **[GAP]** (#5238) if the machine's tailnet name is given and
  answers, Fichero uses `https://<name>` through `tailscale serve`, as the transport rules
  allow; otherwise it opens and keeps an SSH forward to the machine's loopback. It never uses
  `tailscale funnel` and never asks the machine to listen on a public interface. *Test:* pure
  test on the choice; a guardrail greps the install commands for `funnel` and `0.0.0.0`.
- `compute.target.add-local-container` — **[GAP]** (#5238) "This Mac, in a container (for testing)" is one
  button: it needs Docker Desktop running, fetches the cpu image, starts it, pairs, and ends
  green with "No GPU". If the sandboxed build may not drive Docker (foundation question 9), the
  same sheet instead shows one command with a Copy button and an address field. *Test:* the
  click-around leg of the walkthrough.

### A Slurm cluster

- `compute.secret.fichero-makes-the-key` — **[GAP]** (#5238) for an SSH target Fichero makes an Ed25519 key pair;
  the private half is stored only in the one key store (`ai/provider-keys.md`); the public half
  is shown with Copy, and can be shown again. Removing the target deletes the private half.
  *Existing data:* none; saved clusters have no key and read "Needs a key". *Test:* create,
  read public half twice (same), remove target, assert the secret is gone.
- `compute.connect.ssh-in-process` — **[GAP]** (#5238) the server connects over SSH itself and does not run the
  system's `ssh`, so it works inside the app's sandbox. *Existing data:*
  `remote_jobs.build_ssh_command` and the three `*_command` builders stay as the **description**
  of what is run (they are what "show me what will run" displays) but are no longer the way it
  is run. *Test:* in the sandboxed build, a check against the SSH fixture passes.
- `compute.connect.second-factor-passes-through` — **[GAP]** (#5238) when the far side asks for a second factor,
  Fichero shows the far side's own prompt text and waits for the person; it stores no factor;
  a refusal or a time-out ends the attempt with that reason. *Test:* the SSH fixture configured
  with a keyboard-interactive second step: the prompt text reaches the caller; a wrong answer
  yields a typed failure.
- `compute.connect.one-connection-reused` — **[GAP]** (#5238) all commands to one cluster go through one open
  connection, so the person is asked for a second factor once for each working session. When
  it drops, anything that needs it pauses with "Sign in to *name* again"; jobs already on the
  cluster are unaffected. *Test:* ten commands, one authentication on the fixture's log; drop
  the connection mid-poll: job state becomes *waiting for sign-in*, not *failed*.
- `compute.connect.automation-host-optional` — **[GAP]** (#5238) a cluster target may name an automation host.
  Then submit, poll and fetch use it with the restricted key and need no person; sessions and
  anything needing a forward still use the ordinary login. *Test:* with the fixture's
  restricted-key account: submit and fetch pass; opening a forward is refused and reported as
  "this cluster's automation path does not allow sessions".
- `compute.connect.stage-on-the-login-node` — **[GAP]** (#5238) "Install" on a cluster runs on a login node:
  fetch the image of this version as `<base>/fichero/images/<version>.sif`; create
  `<base>/fichero/models/` and `<base>/fichero/jobs/`. It starts nothing, and it does no work
  there beyond the fetch. If the cluster refuses the fetch on a login node, Fichero says so and
  offers to upload a `.sif` from the Mac instead (UNVERIFIED whether Alliance login nodes permit
  the fetch; S1). *Test:* on the fixture: the three paths exist afterwards; a second install is
  a no-op.
- `compute.connect.models-staged-before-a-job` — **[GAP]** (#5238) a model a job needs is fetched into the
  target's model cache from a login node **before** the job is submitted, never from inside the
  job. The card's licence rule applies to this fetch exactly as to a fetch on the Mac. *Test:*
  a job naming an absent model triggers one staging step first; with the fixture's compute
  container cut off from the network, the job still runs.

### Hugging Face

- `compute.target.add-huggingface` — **[GAP]** (#5238) adding Hugging Face takes a fine-grained token. Check
  reports the account name, whether the token may run jobs and write to the person's own
  repositories, and whether there is credit. The token is a secret in the one key store.
  *Test:* against a recorded API: a read-only token reads "cannot run jobs".
- `compute.target.huggingface-says-where` — **[GAP]** (#5238) the Hugging Face target's `operator_note` is fixed
  text: a company in the United States; material sent is held on its servers. The consent
  sheet shows it. *Test:* pure.

### Sessions

- `compute.session.is-a-job-with-a-clock` — **[GAP]** (#5238) starting a session submits a job with a time limit
  the person chose (default 3 hours, because short interactive jobs start soonest; CITED, S2).
  The row shows *queued*, *starting*, *ready, time left*, *ended*. *Data:* a job record of kind
  `session` (see `jobs-and-fine-tuning.md`). *Test:* fixture: states in order; the clock counts
  from the scheduler's start time, not the submit time.
- `compute.session.forward-to-loopback` — **[GAP]** (#5238) a session's model server listens on the compute
  node's loopback. Fichero reaches it by a forward that jumps through the login node to that
  node. If the cluster does not allow that jump, the session is refused with that reason; the
  server is **not** made to listen more widely as a way round it. *Test:* fixture: the
  forward works; the model server's socket is loopback only.
- `compute.session.ends-cleanly` — **[GAP]** (#5238) when a session ends (time limit, cancel, or the cluster
  ends it) its provider row disappears, anything using it fails with "the session on *name*
  ended", and the forward is closed. *Test:* cancel mid-request: the caller gets that typed
  error within the poll interval.
- `compute.session.never-silently-restarted` — **[GAP]** (#5238) Fichero does not start a new session on its own
  when one ends. It offers "Start again". A session costs an allocation, and on Hugging Face
  money. *Test:* after end, no job is submitted without a call.

### Removing

- `compute.target.remove-lists-what-is-there` — **[GAP]** (#5238) removing a target first lists what Fichero put
  there (images, cached models, job folders, a running container, running or queued jobs) with
  sizes, and asks what to delete. Queued and running jobs are never cancelled without being
  named. *Test:* fixture with one running job: removal is refused until the job is cancelled
  or the person chooses "leave it running and forget this target".

## Accessibility identifiers

- `compute.targets.section` — **[GAP]** (#5238) the "Where work runs" section
- `compute.targets.add` — **[GAP]** (#5238) the Add… control; `compute.targets.add.kind.<kind>` — each kind
- `compute.target.row.<id>` — a row; `compute.target.row.<id>.status` — its dot and text
- `compute.target.<id>.check`, `.install`, `.update`, `.remove`, `.copy-public-key`
- `compute.session.<id>.start`, `.cancel`, `.time-left`

## UX completeness

| Control (a11y id) | Label | Tooltip/help text | Verified by |
|---|---|---|---|
| `compute.targets.add` | Add… | Add a place to run work | [unbuilt] |
| `compute.target.<id>.check` | Check | Connect now and report what answered | [unbuilt] |
| `compute.target.<id>.install` | Install | Put this version of the Fichero server there | [unbuilt] |
| `compute.target.<id>.copy-public-key` | Copy Public Key | Copy the key to paste into the other machine | [unbuilt] |
| `compute.target.<id>.remove` | Remove… | See what Fichero put there, then remove it | [unbuilt] |
| `compute.session.<id>.start` | Start Session… | Serve a model there for a few hours | [unbuilt] |

Every string goes through the String Catalog. No needless toggles: a target has no "enabled"
switch; it is there or it is removed.

## Test matrix

| Leg | This slice? | Pins | File |
|-----|-------------|------|------|
| Pure rule (Swift) | y | row status from `last_checked`/`last_result`; reach choice; version refusal wording | a new `compute` group under the Swift unit tests |
| Availability (Swift) | y | the section and Add are reachable | same |
| Backend (pytest) | y | the list; carry-over of saved clusters; no secret in record, answer, event or log; real check against fakes | `fichero-server/tests/unit/api/`, `tests/unit/workflows/` |
| Fixture (continuous integration) | y | SSH with a second step; one connection reused; restricted key; staging; sessions | `.github/workflows/` with the Slurm-and-SSH containers (CITED, S18) |
| MCP / CLI | y | renamed tools and generated commands reach the new routes | `fichero-mcp/tests/`, `fichero-cli/tests/` |
| Click-around (Mac) | y | add the local container; add a Linux machine against a local SSH container | `fichero/Tests/UI/` |

## Open questions

1. **Trial first: SSH from the sandboxed build, in process, with a key from the Keychain, and
   a second factor passed through.** Half a day, against a throwaway SSH server. If it fails,
   the fallback is a small helper outside the sandbox, which is a release question. *Proposal:
   run the trial before cutting the cluster slice.*
2. **May a person SSH to a compute node where their job runs, on Alliance clusters?** The
   session design depends on it. *Proposal: the maintainer, or whoever holds the account, tries
   it once and we record the answer by cluster.*
3. **May an Apptainer image be fetched on a login node?** *Proposal: same one-time trial; the
   upload-from-the-Mac fallback is specified either way.*
4. **Fichero does not install Docker or Tailscale on someone else's machine.** *Proposal:
   agreed; it checks, and says what is missing.*
5. **Default session length: three hours.** *Proposal: agreed; changeable when starting one.*
