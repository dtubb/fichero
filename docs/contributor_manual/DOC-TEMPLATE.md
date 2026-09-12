# Doc Template — the docs every feature owes each audience

> Companion to `TEST-TEMPLATE.md`. Same idea, different legs: a feature isn't done when it
> works and is tested — it's done when each **audience** who meets it can find out how.
> Nobody reads all of it, but *someone* reads each: a user reads the user manual, an AI
> reads the tool description, a scripter reads `--help`, a contributor reads the dev docs.
> Copy the matrix below into a spec's *Documentation matrix* section; create/So the doc
> systems already exist — this says which ones a given feature must touch.

## Per-feature documentation matrix (copy into the spec)

| Audience | Doc leg | Required when… | Lives in |
|----------|---------|----------------|----------|
| **User** | User manual + **screenshots** | a person operates the feature in the app | `docs/user_manual/guide/**` — **the maintainer's own**, authored in Tinderbox. The agent does NOT write the prose; it supplies the accurate **screenshots** (see rule below) and keeps the facts true. |
| **Contributor** | Developer docs | the feature has architecture/decisions others build on | `docs/contributor_manual/**` (+ its `specs/<surface>.md`) |
| **AI / agent** | MCP tool description | the capability is exposed as an MCP tool | the `description=`/docstring on the tool in `fichero-mcp/**` |
| **Scripter** | CLI `--help` | the capability is a CLI command | the `help=` on the typer command (`fichero-cli/**`) |
| **Reference** | Capability/endpoint reference | it adds an endpoint/capability | generated reference (`check_capability_reference_current` keeps it fresh) |

Not every feature touches every audience (a pure-backend job has no user-manual entry; an
internal helper has no CLI). The matrix says which, so none is silently skipped.

## What each leg contains (skeletons)

### User manual (`docs/user_manual/guide/<area>.md`) — the one with screenshots
```markdown
## <Feature, in the user's words>
<One line: what it lets you do.>
1. <step> — <what the user clicks/sees>   ![<surface>](../../assets/<milestone>/<surface>.png)
2. <step>
> Tip / limitation the user should know.
```
Screenshot rule: capture the surface **deterministically** — Xcode `RenderPreview`, or the
`.xctestplan` screenshot **capture** from a UI-test run (TEST-TEMPLATE §2b). Capture, not
pixel-diff (Apple ships no snapshot assertion). Store shots under **`docs/assets/<milestone>/`** — a subfolder named for
the spec/milestone — and name each for its surface. The **agent produces the screenshot**
(it owns the tested surface); the maintainer places it in the Tinderbox-authored chapter.
A user-manual section with no screenshot of a visual feature is incomplete.

### Developer docs (`docs/contributor_manual/<area>.md` + the spec)
```markdown
## <Feature> — how it works
Where it lives (files/types), the data flow, the decisions and why, the invariants tests
pin (link the spec's behavior ids). Grounded in what is BUILT (docs-grounded-in-code).
```

### MCP tool description (AI-facing — `fichero-mcp/**`)
The tool's `description`/docstring IS the AI's doc: say what it does, when to use it, and
what each argument means, in the terms an agent needs to choose it correctly. Treat it with
the same care as user copy — it's read by a different kind of user.

### CLI help (`help=` on the typer command)
One line the scripter sees in `fichero <group> <command> --help`: what it does + the shape
of its inputs. Mirrors the MCP description for the same capability so the two agree.

## The process (folds into the design-led crank)
1. In the spec, fill the **Documentation matrix** alongside the Test matrix — tick the
   audiences this feature meets.
2. As you build: write the user-manual section (+ screenshot), the dev-doc/spec section,
   the MCP `description`, the CLI `help=`.
3. Guardrails keep them honest: `check_docs_paths` (no doc names a dead path),
   `check_docs_publication`, `check_capability_reference_current` (reference stays fresh).
   A future `check_doc_matrix` can assert an APPROVED surface has the audience docs it
   ticked — the doc analogue of the spec↔test guardrail.

## Why this matters
The same feature is met by four kinds of reader who never read each other's docs. Covering
one (say, the dev doc) and skipping the user manual or the MCP description means a whole
audience hits the feature blind. The matrix is how you *see* which audience you'd otherwise
leave in the dark — the documentation analogue of the click-around leg being the one that's
"unproven in the way the reader actually experiences it".
