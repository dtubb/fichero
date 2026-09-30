# Setting Up a Contributor Machine

How to bring up another Mac as a Fichero contributor machine, copying from one you already have
rather than starting from scratch: the checkouts with their unpushed branches, the Python venv, test
data, and your Claude Code setup. The machines share the work, so both keep the same paths.

A common way to use two machines: a small, always-on Mac (an 8 GB MacBook Air, say) holds the
checkouts and runs Claude Code, git, the engine and targeted tests, while a bigger Mac runs full
Xcode builds, the test gates and release DMGs. The engine alone sits at about 1.8 GB idle (most of
it the embedding model, #5283), and Xcode plus SourceKit need several gigabytes more, so full builds
swap on 8 GB. Below, **`dev-mac`** is the machine being set up and the commands run from the one
you already have.

## 1. Connect the machines

- **Tailscale** on both. The dev machine is then reachable anywhere as
  `<dev-mac>.<tailnet>.ts.net`.
- **Remote Login** on the dev machine: System Settings › General › Sharing › Remote Login, access
  for your user only.
- **A key, not a password.** From the machine you sit at:
  `ssh-copy-id -i ~/.ssh/id_ed25519.pub <user>@<dev-mac>.<tailnet>.ts.net`, where `<user>` is the
  dev machine's **macOS short name** (`whoami` there), not your Tailscale or GitHub login. Then an
  alias in `~/.ssh/config`:

  ```
  Host dev-mac
    HostName <dev-mac>.<tailnet>.ts.net
    User <user>
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 30
  ```

- **Faster link (optional).** Over a campus or office network the round trip can be ~250 ms. A
  Thunderbolt 3/4 or USB4 cable between the Macs gives a Thunderbolt Bridge network (about 1 ms);
  a USB-C charging cable does not.
- **Keep it awake.** On the dev machine: `sudo pmset -c sleep 0 displaysleep 10` (never sleep on the
  charger) and, to survive a closed lid, `sudo pmset -a disablesleep 1`. Keep a fanless Air
  ventilated.

## 2. Same paths on both machines

Keep the layout identical: `~/code/fichero` (the main checkout, with `.venv`), `~/code/fichero-worktrees/*`,
and any test data (`~/Fichero Test Corpus`, `~/Fichero Test Library`). A venv, the editable install
inside it, and git's worktree records all store **absolute paths**, so the same paths are what let
them work after a copy.

## 3. Move the work over

Copy with `rsync` over SSH; nothing needs pushing first, so unpushed branches travel too.

1. **Git history:** `rsync -a ~/code/fichero/.git/ dev-mac:code/fichero/.git/`, then on the dev
   machine `git -C ~/code/fichero reset --hard HEAD` to write the main checkout's files (it is a
   fresh folder, so nothing is lost).
2. **The venv:** `rsync -a ~/code/fichero/.venv/ dev-mac:code/fichero/.venv/`. It works as-is when
   both Macs are Apple silicon and Homebrew's `python@3.12` exists at the same path on both; this
   saves downloading gigabytes of wheels. Check with
   `~/code/fichero/.venv/bin/python -c "import duckdb, fastapi"`.
3. **Worktrees:** copy the folders (their uncommitted work comes with them), leaving out regenerable
   output: `fichero/build/`, each worktree's top-level `build/`, `fichero/fichero-api-client/.build/`,
   `.claude/worktrees/`, `.gate-snapshots/`, `__pycache__/`. Keep `fichero-server/build/` (the
   Briefcase engine bundle) unless you are happy to rebuild it, which downloads torch and friends.
4. **Library data: copy, never move, and only while no app has it open.** A copy of an open DuckDB
   library can be torn. Check with `lsof +D "<library folder>"`.

**Pitfalls we hit:**

- **`git worktree prune` before the worktree folders arrive deletes their records.** Copy the folders
  first. If it happens, copy `~/code/fichero/.git/worktrees/` again and run `git worktree repair`.
- macOS `rsync` rejects `--info=`, and a remote path with spaces must be escaped:
  `'dev-mac:Fichero\ Test\ Corpus/'`.
- Don't chain copy commands with `… | tail && echo done`: the pipe hides a failure and the `echo`
  still prints. Check sizes on the far side instead.

## 4. Tools on the dev machine

- **Xcode:** after installing, accept the licence (`sudo xcodebuild -license accept`), and **sign
  Xcode into your Apple developer account** (Settings › Accounts), or builds stop at "No profiles
  for 'app.fichero.fichero'". From the command line on a new machine, add
  `-skipPackagePluginValidation -skipMacroValidation` until the OpenAPI generator plugin has been
  trusted once.
- **GitHub:** `gh auth login` (GitHub.com, HTTPS, authenticate Git: yes). The repository remote is
  HTTPS.
- **PATH for commands over SSH:** zsh reads `~/.zshenv` for every shell but `~/.zshrc` only for
  interactive ones, so put Homebrew and `~/.local/bin` on the PATH in `~/.zshenv`, or
  `ssh dev-mac tmux …` reports "command not found".
- **Claude Code:** install with the official installer (`curl -fsSL https://claude.ai/install.sh | bash`),
  sign in with `claude`, then copy your `~/.claude` configuration (`CLAUDE.md`, `settings.json`,
  `skills/`, `agents/`, `plugins/`), not its transcripts, logs or caches. Anything your hooks call must
  exist on the dev machine too (for example `jcodemunch-mcp`, installed with `pipx`), and plugin
  marketplaces that are local folders (such as `fichero-skills`) must be copied to the same path.
  Project memory lives in `~/.claude/projects/<project>/memory/` and copies across the same way.

## 5. Drive it from where you sit

Run Claude Code on the dev machine inside **tmux**, so it keeps working when you disconnect:

```
ssh -t dev-mac tmux new -A -s claude        # start or re-attach
# detach with Ctrl-B then D; the session keeps running
```

Builds stay on the build machine: from the dev machine, run them there over SSH (the same paths make
the commands identical), or keep a build session open on the build machine in its own tmux window.
