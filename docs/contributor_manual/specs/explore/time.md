# Explore: by time — timelines, storylines, arcs, animation — Design Spec (#5032)

> Milestone: explore
> Manual: TBD — a section of "Exploring a project": reading a timeline whose dates are
> uncertain; the "as of" slider; playing a year; a diary's people as lines through the year.
>
> **Status: DRAFT — first pass, 2026-09-20.** Foundation, words and common rules: `explore.md`.

## Intent (the design)

Almost everything in a project happened WHEN: a diary entry, a claim, a relation between two
people. This family makes time something a researcher can look along, slide through, and play.
Its hard part is honesty: a historian's dates are uncertain, approximate, open-ended, periods
rather than points, sometimes relative to another event, sometimes in another calendar. A
timeline that draws "about 1790" as a dot on 1 January 1790 is lying.

Lives in: the Library's existing Timeline and Calendar view modes
(`Views/Library/ViewModes/Dataset/`), the knowledge-graph timeline
(`Views/Library/ViewModes/Graph/KGTimelineView.swift`, Swift Charts) promoted from the Reader
to a Library view mode for claims and entities, and two new view modes of their own
(storylines, arcs). None of these is an arrangement of the Canvas or the Space. "As
of" is a control shared with `networks.md` and `place.md`.

## Prior art

nodegoat's temporal model (uncertain, open-ended, periods, relative dates, calendars) is the
standard for what a research database must hold; the Extended Date/Time Format (EDTF, now part
of ISO 8601-2) is the standard way to WRITE such dates and is what exports should use. xkcd 657
storylines and the D3 arc diagram are the models for co-presence. The Digital Panopticon's
life-course charts are the model for one person's life. Deliberately different: every bar and
line opens its evidence.

## What exists

- Document dates: `histdate.py`: Julian Day Number ranges, several calendars, and three
  distinct states (dated; explicitly undated; none found). Built.
- Claim dates: `time_start`, `time_end`, `time_precision`, and `date_values` with open start,
  open end, circa, precision, basis (asserted, source-anchored, inferred), confidence and the
  source excerpt. Built in the model. **Not modelled:** a date relative to another event; the
  calendar a claim's date was written in.
- Two timelines, neither complete: the dataset Timeline for a folder's dated entries (sort and
  "show full text" controls BROKEN, → #4598; no multi-selection) and the knowledge-graph timeline,
  reachable only in the Reader for one document, capped at 500 claims, which already draws
  asserted dates solid and inferred dates hollow.
- Calendar mode: no zoom from day to century (#4599).
- Nothing animates through time.
- #5008: a DATE was extracted as a sentence's subject. Time must be WHEN, never an entity in
  the subject slot; this family depends on that being fixed.

## Behaviors

Honest dates
- `explore.time.a-date-is-a-span` — **[PARTIAL]** (#5032) every dated thing is drawn as the span
  it may occupy: a day is a tick, "March 1791" a month-wide bar, "about 1790" a bar with soft
  ends, "after 1802" a bar open to the right. The model holds all of this; the knowledge-graph
  timeline draws only solid against hollow.
- `explore.time.basis-and-confidence-are-visible` — **[PARTIAL]** (#5032) a date stated in the
  source, a date anchored to a place on the page, and a date inferred are drawn differently,
  and the confidence control of `explore.inferred.filter-by-confidence-and-asserter` applies.
  Asserted against inferred is built; the three-way basis and the control are not.
- `explore.time.undated-is-counted` — **[PARTIAL]** (#5032) the undated, the explicitly undated
  ("n.d.") and the never-examined are three separate counts beside the timeline, each opening to
  its list. The dataset modes have a Dated / Undated facet; the three-way distinction the engine
  keeps is not shown.
- `explore.time.several-dates-one-claim` — **[GAP]** (#5032) a claim with competing dates shows
  all of them, tied together, not only the first.
- `explore.time.relative-dates` — **[GAP]** (#5032) "three days after the fire" is held as a date
  relative to another event and drawn from that event, moving if the event's date is corrected.
  Needs a model change; PROPOSED, not yet ruled (see Open questions below).
- `explore.time.calendar-is-kept` — **[PARTIAL]** (#5032) a date written in another calendar
  keeps what was written beside its converted span. Built for document dates; not for claims.
- `explore.time.when-is-not-an-entity` — **[BROKEN]** (→ #5008) a date is never the subject of a
  claim; it is the claim's WHEN. No time view is honest until extraction obeys this.

The timeline
- `explore.time.timeline-of-any-set` — **[PARTIAL]** (#5032) a timeline can be asked for on a
  folder's entries, a search result, a collection of claims, or one entity's claims, as a
  Library view mode. Built for folder entries; the claims timeline exists only as a Reader tab.
- `explore.time.one-timeline` — **[GAP]** (#5032) the dataset timeline and the knowledge-graph
  timeline become one drawing with two kinds of row (entries, claims), not two code paths.
- `explore.time.zoom-day-to-century` — **[GAP]** (→ #4599, #5032) the time axis zooms from days to
  centuries; an archive spanning decades is readable at both ends.
- `explore.time.bins-when-large` — **[GAP]** (#5032) above a stated size the timeline draws
  counts per period (stacked by kind, group or asserter) and individual marks only where zoomed
  in. This replaces the 500-claim cap: nothing is dropped, it is counted.
- `explore.time.rows-by-any-field` — **[GAP]** (#5032) the timeline can be split into rows by
  person, place, kind of source, hand, or group by meaning, so change across them can be
  compared (topics over time is this, with groups as the rows).
- `explore.time.controls-work` — **[BROKEN]** (→ #4598) sort, "show full text" and multi-selection
  work in the timeline as in every other mode.

As of, and animation
- `explore.time.as-of-control` — **[GAP]** (#5032) every time-aware view (network, place map,
  storylines) has one "as of" control: a moment or a window on the time axis. What did not yet
  hold, or no longer held, is not drawn; what MAY have held (uncertain span) is drawn as
  uncertain.
- `explore.time.as-of-is-shared-when-linked` — **[GAP]** (#5032, → #4881; BLOCKED on the
  pane-linking design session) a linked group of view modes shares one "as of". Not to be
  built before that design exists.
- `explore.time.play` — **[GAP]** (#5032) "as of" can be played forward and back at a chosen
  speed, and stopped on any frame; marks move, appear and fade rather than jump. Stopping always
  leaves a view that can be selected from. Motion respects the system's Reduce Motion setting
  (it steps instead).
- `explore.time.every-frame-is-true` — **[GAP]** (#5032) animation never invents positions
  between two known states that a reader could mistake for evidence (a person is not drawn
  half-way between two towns on a day nothing records them).

Storylines and arcs
- `explore.time.storylines` — **[GAP]** (#5032) for a set with dates and people (a diary year),
  each person is a line along time; lines run together while the sources place them together
  (a dinner, a journey, a meeting) and part when they do not. Choosing a meeting opens the
  entries that record it.
- `explore.time.storylines-say-what-together-means` — **[GAP]** (#5032) "together" is a named
  method with its rule shown (named in the same entry; in the same place on the same day;
  joined by a claim of a chosen kind), because the picture changes entirely with the rule.
- `explore.time.storylines-limit-the-cast` — **[GAP]** (#5032) a storyline draws the people who
  matter most to the set (by a stated measure) and gathers the rest into "others", which opens
  to a list. Twenty lines can be read; two hundred cannot.
- `explore.time.arc-diagram` — **[GAP]** (#5032) entities along one axis in an order that can be
  chosen (time, or page order through a volume), with arcs joining those that appear together;
  arc weight is how often. Choosing an arc opens the passages where both appear.
- `explore.time.life-course` — **[GAP]** (#5032) one person's dated claims as a single life line
  (born, moved, married, tried, died), as a Reader rendition of that person. Gaps are shown as
  gaps.

## How it is drawn (decided per kind; RULED 2026-09-20)

- **Timeline, bins, life course: native.** Swift Charts already draws the knowledge-graph
  timeline; binning keeps any set small enough for it. Nothing here needs the web.
- **Storylines and arcs: HTML is a fair first choice; native if the memory cost is judged too
  high.** For HTML: the storyline layout (ordering lines so that they cross as little as
  possible) is a hard problem with open, tested solutions in the web libraries, and arcs are a
  few lines of D3; the sets are small (a year, a volume); these are the views most likely to
  be published, and the published HTML drawing has to be written anyway, so it would be written
  once. Against: about 500 MB for its WebKit process, as measured on the 16 GB M1 the app is tested on (#4999, #4997), for as long as the view mode is open, and a message bridge for
  selection. For native: no extra process, the Pencil, animation that is the app's own. Against:
  the layout must be written by hand, or computed by the engine and only drawn natively, which
  is the middle road if memory decides it. The rules of `explore.panes.html-view-mode-rules`
  apply either way, and both routes draw the same data.

Published saved views are drawn by HTML from the same data (`experiments-and-sharing.md`).

## Test matrix (legs this family touches)

Pure Swift (span drawing rule for each kind of uncertainty; binning; the cast limit); backend
(spans from every date shape, the three undated states, co-presence by each rule, all with
evidence ids); availability; click-around (choose a bar, the Source view shows the dated words);
load (a project's claims bin without a cap and without pegging the machine).

## Open questions for the creative director

Not blocking: relative dates and claim calendars (extend the claim model now, or later?); what
"together" means by default in a storyline; HTML or native for storylines and arcs (a
recommendation is given above; the memory cost is the deciding fact).

**Answered** (design lead 2026-10-04, applying the spec's lean): Storylines and arcs follow the spec's recommendation (HTML first), decided by the measured memory cost.
