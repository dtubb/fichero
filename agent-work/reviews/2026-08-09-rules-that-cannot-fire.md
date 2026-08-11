# Rules that cannot fire — a cross-cutting pass (2026-08-09)

Read-only sweep for the one class where a reviewer beats the author: checks,
guardrails and conditions that are **structurally incapable of failing**. An
author reads their rule and sees what it means; a reader can only see what it
does.

`file:line` for every instance. Inferences marked. Nothing was executed — the
counts below come from reading, not running.

---

## The pattern, stated precisely

Two forms, same illusion — code shaped like a decision that cannot decide.

**Form 1 — a rule written where it cannot be enforced.** The intent is real and
usually correct; the mechanism cannot reach a violation. A prohibition in a
comment. A scan whose roots exclude the place the violation lives. A list that
was never extended past its first entry.

**Form 2 — a condition that cannot vary.** A `Bool` that reads as policy and
returns a constant. Harmless until someone gives it a body, at which point
whatever it guards wakes up.

Both cost the same way: they buy confidence without buying protection, and the
confidence is what stops anyone looking again.

---

## Confirmed instances

### 1. `SelectionGrammar` forbids `Set.first` — in a comment

`fichero/fichero/Models/Selection/SelectionGrammar.swift:93-94`:

> Never `selection.first` — that is `Set` hash order, which would make the same
> gesture produce different ranges on different runs.

Seven violations accumulated under it (enumerated in the Preview/Reader/Inspector
review). Comments do not fail builds.

### 2. …and the guardrail that exists to enforce it cannot see them

This is the sharpest instance of the night, because the check is *good*.

`scripts/check_selection_grammar.py` is, in most respects, a model guardrail. It
has a blindness guard (`require_scan_floor(len(files), 36, …)`, `:202`), a
distinct exit code 2 for BLIND, named rather than pattern-holed exemptions, and
— remarkably — a section headed **"WHAT THIS CHECK CANNOT SEE, stated plainly
because it was GREEN throughout the period when #4377's last two gaps were
open"** (`:25-45`). That is exactly the honesty this whole document is asking
for, written by the author, unprompted.

And it still cannot catch the seven `.first` sites, for a reason it does not
mention. Its scan roots are:

```python
VIEW_MODES    = ROOT/"fichero"/"fichero"/"Views"/"Library"/"ViewModes"   # :67
LIBRARY_VIEWS = ROOT/"fichero"/"fichero"/"Views"/"Library"               # :68
```

Every violation lives in `Views/Shell/ContentView/` — `StateEvents.swift:160`
and `:182`, `StatePreview.swift:52` and `:150`, `StateSelection.swift:31`,
`Layout/ContentView+CompactReader.swift:53` — plus `Models/LayoutMode.swift:295`.
**Not one is under either root.**

The check looks in the right way at the wrong place. It is the same defect as
instance 4 below, in a file whose docstring is otherwise the best example of the
opposite habit in the repo. The remedy is not a new check; it is widening the
roots to include the shell, which is where the selection is *consumed* even
though the library is where it is *written*.

### 3. `check_environment_forwarding.py` printed "no new gaps" through three crashes

Mine, fixed tonight in `f9512ec80`. Its `MIRROR_HOSTS` list held exactly one
entry, `DocumentTabView.swift`, and none of the three `No Observable object`
crashes were in it. The check ran, passed, and reported a clean bill three times
while the app was dying of the thing it guards.

Recorded here because the shape — *a scope list that was never extended past its
first member* — is instance 2's shape, and finding the same failure twice in one
night in two unrelated files is the argument that this is a habit rather than an
accident.

*Its self-test is still the weakest of the four (it mutates real source files and
restores in a `finally`); rewrite assigned to the code lane.*

### 4. A preflight check that always failed, and a bookmark mint that could never throw

The two the code lane hit earlier today, before this audit. Included for the
count; I did not read either, so they are **reported, not verified by me**.

### 5. Form 2 — two conditions that cannot vary

Both `Bool` properties in `Views/` whose body is a bare constant. I searched for
the shape; **these two are the only instances**, which is worth stating so nobody
inflates it into a sweep:

- `shouldShowBottomToolbar` — `fichero/fichero/Views/Sidebar/Sections/SidebarView+ViewComponents.swift:38-40`, returns `true`. Reads as a policy hook; is a constant. (#3404 says the bar should go or be library-scoped, so the constant is also the wrong answer.)
- `showInspectorToggle` — `fichero/fichero/Views/Shell/ContentView/ContentView+StateSelection.swift:75-77`, returns `true`. This one is load-bearing: it wraps a **`ToolbarItem` itself** in an `if` (`Layout/ContentView+InspectorContainer.swift:47`, `:64`), which is precisely what `Views/Shell/Toolbar/EngineStatusToolbarItem.swift:31-35` documents as the thing never to do — *"Never gate the `ToolbarItem` itself… risks the #3163 double-insert crash."* Not a live crash **only** because the condition is constant. Its name invites an implementation, and its neighbour `showViewModePicker` (`:81-87`) has one.

### 6. The `.searchable` rule is enforced by construction, not by a guard

Detailed in the sidebar/toolbars addendum. Exactly one `.searchable(` call
exists in the app (`Views/Components/MiniToolbar.swift:250`), inside
`conditionalSearchable`, gated by one testable predicate
(`Views/Components/SplittablePane.swift:57-61`). The duplicate-identifier
toolbar crash cannot happen from current code.

But the rule that keeps it that way lives in doc comments
(`SplittablePane.swift:29-32`, `:48-56`). A new mode view writing
`.searchable(placement: .toolbar)` directly compiles, ships, and crashes in a
split pane. This is Form 1 waiting to happen rather than Form 1 already
happened — and it is the cheapest of all of these to close.

---

## How exposed is the guardrail suite, in numbers

Of 86 `scripts/check_*.py`:

| property | count |
|---|---|
| has a blindness guard (`_check_floor` / `require_scan_floor`) | **52** |
| has a `--self-test` proving it fires | **21** |
| has **neither** | **25** |

The honest reading, and I want to be careful not to overstate it: **61 checks
lack a self-test, but that is not 61 broken guardrails.** Many are
straightforward greps whose firing is obvious from three lines of code, and a
fixture for those would be ceremony. Absence of a fixture is not evidence of
vacuity.

**The 25 with neither is the real risk set.** Those can be silently vacuous in
both directions at once — no proof they fire on a violation, and no floor to
notice if their scan population collapses to zero. That is the exact
configuration in which instance 3 reported clean through three crashes.

The encouraging half: **52 of 86 already have a blindness guard**, and
`_check_floor` is a shared helper. This is not a practice the codebase needs to
invent — it is one it already has and has applied to a majority. Finishing the
job is a bounded task, not a cultural change.

---

## What I would do, in order

1. **Widen `check_selection_grammar.py`'s roots to include `Views/Shell/`.**
   Highest value per line changed in this whole document: the rule, the
   violations, and the check all already exist — they just do not overlap. Pair
   with a fixture, since the seven known sites make writing one trivial (revert
   one, assert it fires).
2. **A guardrail forbidding a raw `.searchable(`** outside
   `conditionalSearchable`'s own definition. One rule, one fixture, closes a
   known crash class permanently. Cheapest item here.
3. **A guardrail forbidding `ToolbarItem(id:)` inside a conditional.** Catches
   instance 5's live trap and keeps catching it. The rule is already written
   prose in `EngineStatusToolbarItem.swift:31-35`; this makes it fireable.
4. **Triage the 25 checks with neither guard.** Not "add 25 self-tests" — read
   each, and for anything whose firing is not obvious in three lines, add a
   floor (cheap, shared helper) or a fixture (only where the logic is real).
5. **Delete the two constant `Bool`s** or give them bodies. Either is fine;
   leaving a policy-shaped constant is what produced instance 5.

**The standing rule worth adopting**, which the codebase has already
demonstrated it can meet: *a guardrail ships with a fixture proving it fires on
a real regression, and a floor proving it is still looking at something.*
`check_environment_forwarding.py --self-test` and
`check_selection_grammar.py`'s `require_scan_floor` are the two halves, both
already in the tree. And `check_selection_grammar.py`'s
"WHAT THIS CHECK CANNOT SEE" section should be the third: **a guardrail that
states its own blind spots is worth more than one that implies it has none.**

---

## What I did not check

- I did not execute any check, self-test, or fixture — several self-tests mutate
  real source files, and another agent is editing this worktree.
- I read `check_selection_grammar.py` and `check_environment_forwarding.py`
  closely, and the three other guardrails added tonight (audit A6). The
  remaining 81 I classified **only** by the presence or absence of a self-test
  and a floor — a structural signal, not a judgement that any individual check
  works or does not.
- Instance 4 is reported from the code lane's account, not verified by me.
- I searched for Form 2 only as `var …: Bool {` followed by a bare `true`/`false`
  under `Views/`. A constant reached through a longer body, or one outside
  `Views/`, would not have shown up. **Inferred** that two is the true count;
  the honest claim is "two of that exact shape".
