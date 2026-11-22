# Ontological layer — what kinds of things and relations exist, and whose categories they are — Design Spec (#1678)

> Milestone: people-and-lives
> Spec: kg/ontological-layer.md
> Manual: TBD — a short "Kinds and categories" section: the few kinds of thing Fichero keeps (person, place,
> organisation, event, document), the kinds of tie between people, that the words the sources themselves use for
> people and ties are kept as written and never replaced by the historian's or the app's, and how a historian adds
> a type of their own.
>
> Design-led (Testing Constitution). **Status: DRAFT 2026-11-21** (from the owner's rulings of 2026-11-21; the owner
> approves). This file replaces the one line that used to stand for this layer, `kg.enrich.ontology-layer` in
> `kg/kg-enrichment.md`, which is kept there with a pointer here. It has no build order: its lines are built in the
> steps of `kg/people-and-lives.md`, which cites them. Its neighbour is `kg/hermeneutic-layer.md`: this layer says
> what KINDS of thing a project holds; that layer holds what the historian THINKS about them.
> Tags: **[OK]** built and pinned · **[PARTIAL]** exists in part · **[GAP]** designed, not built. Every non-[OK] line
> cites an issue; "→ #NEW-Pn" is the step issue of `kg/people-and-lives.md` that builds it.

## For a historian

When you explore your archive (`explore/explore.md`) you meet people, places, events and the ties between them. This
layer is the short list of what kinds of thing those are. It matters for one reason: the sources have their own
categories, and they are not yours. A register calls someone by a status word; a notary uses a formula for a kind of
tie. Fichero keeps those words exactly as written, shows who used them and about whom, and keeps your own analytic
types in a separate place. It never quietly translates one into the other, and it never invents a category.

## Ruled 2026-11-21 (owner; paraphrased)

The ontological layer says what kinds of things and relations exist: person, place, event, role, the types of
relation, and the sources' own categories, which are kept distinct from the historian's. A model does not propose
classes, types or higher-order structures. The earlier line asked for a layer of proposed classes and structures
that a person would accept or reject; that is withdrawn.

## Intent (the design)

Three lists, kept apart, each small and each visible:

| List | Whose it is | Examples | Who can change it |
|---|---|---|---|
| **kinds of thing** | the app's, fixed | person, place, organisation, event, document | nobody in a project; a change is a spec change |
| **the historian's types** | the project's | kinds of event (baptism, sale, lawsuit); types of relation (parent of, spouse of, witness for, owner of) | the person: add, rename, retire |
| **the sources' categories** | the sources' | the status, kinship, office and legal words written on the pages, in their language | nobody: they are read, never edited; variants are grouped by proposals a person accepts |

A **role** is not a kind of thing. It is the position someone holds in one statement or one act (party, witness, the
one spoken about, the writer), and where the source names it, the source's word for it.

A tie between a source's category and a historian's type ("this status word, in these registers, I treat as that
type") is something the historian makes, with the passages it rests on. It belongs to them and is stored in the
hermeneutic layer. Fichero follows it in counts only where the view says so.

## Prior art (what we adopt)

- **Event-centred models of cultural heritage data**: an event has participants in roles, a time-span and a place,
  and is distinct from the documents that witness it. Adopted for events and roles; the full class hierarchy of such
  standards is not shown to the person and is used only as an export mapping (`kg.jsonld.export`).
- **The factoid model**: what a source says is kept as the source's, apart from what the editor concludes.
- **Emic and etic** in anthropology: the actors' categories and the analyst's are both needed and must not be
  confused. Adopted as the wall between the second and third lists.
- **Not adopted:** ontology learning, where a model induces classes from data.

## What exists today (read 2026-11-21)

Entity types exist as an enum (`kg.names.types` [PARTIAL]); statements have a free predicate with a canonical form;
a date and a place are qualifiers (`kg.qualifier.qualifiers-are-not-edges` [PARTIAL]); there is no event record
(`record.event.groups-statements-and-keeps-contradiction` [GAP]), no role on the object of a statement
(`kg.statements.object-role` [GAP]), no list of relation types, and nowhere that a source's own word for a person or
a tie is kept as a thing that can be counted. The ontology browser the earlier line mentioned was removed with the
knowledge-graph browser and is not coming back in that form.

## Behaviours

- `ontology.kinds.small-closed-set` — **[GAP]** (#1678 → #NEW-P2) the kinds of thing are a closed list in one place in
  the engine (person, place, organisation, event, document), read by every route and view; a name's kind is set by a
  person or proposed by a labelled method and can be corrected like any reading. No project and no model adds a
  kind. *Test (to write):* test_ontology_kinds.py.
- `ontology.events.kinds-are-the-sections` — **[GAP]** (#1678 → #NEW-P2) kinds of event are a list the project owns,
  seeded with a short default (birth or baptism, marriage, death or burial, sale, loan, lawsuit, appointment,
  movement), which the person can add to, rename and retire; the sections of a biography page are this list
  (`people.bio.sections-by-life-event-and-relation`). Retiring a kind hides it and changes no statement.
  *Test (to write):* test_ontology_kinds.py.
- `ontology.model-proposes-no-kind` — **[GAP]** (#1678 → #NEW-P2) no route lets a model's account create, rename or
  retire a kind of thing, a kind of event or a type of relation, and no view shows a class, type or grouping that a
  model named. *Test (to write):* test_no_model_writes_a_kind.py.
- `ontology.relations.one-list-the-person-extends` — **[GAP]** (#1678 → #NEW-P5) types of relation between people are
  one list the project owns, each with a name, a direction and its inverse, seeded with parent of, spouse of, child
  of, sibling of, witness for, godparent of, owner of, employer of; the person adds, renames and retires types. A
  relation of a type (`people.relation.typed-link-rests-on-statements`) is the historian's classification and is
  marked as such wherever it is shown. *Test (to write):* test_relation_types_list.py.
- `ontology.sources.categories-in-their-own-words` — **[GAP]** (#1678 → #NEW-P5) the word or formula a source uses for
  a person (a status, an office, a kinship term) or for a tie is kept as written, in the source language, on the
  mention or the statement it belongs to, with its stretch. It is shown beside and never in place of the historian's
  type, and it is a term like any other, with its own sheet (`terms.sheet.one-view-for-a-term-or-a-name`). No view
  groups people under a label the app supplied where the sources supply one (`explore.care.the-record-is-not-the-person`).
  *Test (to write):* test_relation_carries_source_words.py.
- `ontology.sources.mapping-is-a-persons-link` — **[GAP]** (#1678 → #NEW-P14) treating a source's category as one of
  the historian's types is a link the person makes, with its scope (which writers, which years) and the passages it
  rests on; it is stored as theirs, shown wherever it changes a count, and can be turned off in any view. Fichero
  never proposes one. *Test (to write):* test_category_mapping_is_owned.py.
- `ontology.role.is-a-position-in-a-statement` — **[GAP]** (#1678, #4842 → #NEW-P14) a role is recorded on a person's
  place in one statement or act (party, witness, spoken about, writer, and the source's own word where given), read
  from the formula's slot by a stated rule or set by a person; it is never a property of the person as a whole.
  Closes the gap named by `kg.statements.object-role`. *Test (to write):* test_role_is_a_position.py.
- `ontology.browse.is-a-table-of-what-is-used` — **[GAP]** (#1678 → #NEW-P14) the three lists can be read as one table
  in the Library: each kind, type and source category with how many records use it, opening to those records. It is
  a table of what the project holds, not a class diagram, and replaces the retired ontology browser.
  *Test (to write):* test_ontology_browse_table.py.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Backend (pytest) | y | the three lists, who may change each, roles as positions, source words kept | the files named above |
| MCP | y | the lists are read tools; a model's account cannot write one | `fichero-mcp/tests/test_mcp_generated.py` |
| Pure rule (Swift) | y | a historian's type is always marked as theirs beside the source's word | to write |

## Open questions for the owner

1. Is the seeded list of relation types right, and should "owner of" between persons carry a different name?
2. Should the default kinds of event be chosen per recipe (a notarial project and a diary project differ)?
