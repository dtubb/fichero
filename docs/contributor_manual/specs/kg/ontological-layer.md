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

## Beyond people: kinds as a set, agents of any kind

The sources speak of more than persons as having a history and as doing things: an object, a piece of land, a
building, a document, an image; a river, an animal, a crop, a weather event; a saint, a spirit, a demon, a devotional
image, the dead. The kinds of thing therefore reach them (below), and three rules hold.

- **Kind is a set.** An entity may be several kinds at once, as the sources give it: a devotional image that is an
  object and a spiritual being; a mill that is a building, a business and a river use; a title deed that is a
  document and an actor in a lawsuit. The life page shows every kind the sources give it, each with the lines that
  give it.
- **Agents of any kind, treated alike.** The agent, actor or doer role of a statement may be filled by an entity of any
  kind: person, thing, nature, spiritual, institution, document. There is no built-in order in which only persons act.
  "The image of the Virgin stopped the flood", "the river took the mill" and "the devil appeared to her" are each
  recorded as that source states it, attributed to that source. Fichero records the agency and never asserts it.
- **Reading agency is the historian's.** Whether such a statement is to be taken literally, as a figure of speech, as
  belief, or as a claim about who was responsible is interpretation, kept in the hermeneutic layer
  (`kg/hermeneutic-layer.md`). Translation, mediation and an obligatory point of passage are the historian's terms;
  Fichero labels nothing by them.

Worked example, a devotional image: the source says the image heals (a statement with the image as agent), a will
leaves it to a confraternity (owner), a record has it carried to another church (moved), and a lawsuit is brought
over it (a party or the thing at issue). One entity, kinds object and spiritual being, four statements, each with
its source, none of them asserted by Fichero.

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

- `ontology.kinds.small-closed-set` — **[GAP]** (#1678 → #7002) the kinds of thing are a closed list in one place in
  the engine (person, place, organisation, event, document), read by every route and view; a name's kind is set by a
  person or proposed by a labelled method and can be corrected like any reading. No project and no model adds a
  kind. *Test (to write):* test_ontology_kinds.py. **Not built:** the list is widened by `ontology.kinds.beyond-people` and an entity carries a set of kinds (`ontology.kinds.an-entity-has-a-set-of-kinds`).
- `ontology.events.kinds-are-the-sections` — **[GAP]** (#1678 → #7002) kinds of event are a list the project owns,
  seeded with a short default (birth or baptism, marriage, death or burial, sale, loan, lawsuit, appointment,
  movement), which the person can add to, rename and retire; the sections of a biography page are this list
  (`people.bio.sections-by-life-event-and-relation`). Retiring a kind hides it and changes no statement.
  *Test (to write):* test_ontology_kinds.py.
- `ontology.model-proposes-no-kind` — **[GAP]** (#1678 → #7002) no route lets a model's account create, rename or
  retire a kind of thing, a kind of event or a type of relation, and no view shows a class, type or grouping that a
  model named. *Test (to write):* test_no_model_writes_a_kind.py.
- `ontology.relations.one-list-the-person-extends` — **[GAP]** (#1678 → #7005) types of relation between people are
  one list the project owns, each with a name, a direction and its inverse, seeded with parent of, spouse of, child
  of, sibling of, witness for, godparent of, owner of, employer of; the person adds, renames and retires types. A
  relation of a type (`people.relation.typed-link-rests-on-statements`) is the historian's classification and is
  marked as such wherever it is shown. *Test (to write):* test_relation_types_list.py.
- `ontology.sources.categories-in-their-own-words` — **[GAP]** (#1678 → #7005) the word or formula a source uses for
  a person (a status, an office, a kinship term) or for a tie is kept as written, in the source language, on the
  mention or the statement it belongs to, with its stretch. It is shown beside and never in place of the historian's
  type, and it is a term like any other, with its own sheet (`terms.sheet.one-view-for-a-term-or-a-name`). No view
  groups people under a label the app supplied where the sources supply one (`explore.care.the-record-is-not-the-person`).
  *Test (to write):* test_relation_carries_source_words.py.
- `ontology.sources.mapping-is-a-persons-link` — **[GAP]** (#1678 → #7015) treating a source's category as one of
  the historian's types is a link the person makes, with its scope (which writers, which years) and the passages it
  rests on; it is stored as theirs, shown wherever it changes a count, and can be turned off in any view. Fichero
  never proposes one. *Test (to write):* test_category_mapping_is_owned.py.
- `ontology.role.is-a-position-in-a-statement` — **[GAP]** (#1678, #4842 → #7015) a role is recorded on a person's
  place in one statement or act (party, witness, spoken about, writer, and the source's own word where given), read
  from the formula's slot by a stated rule or set by a person; it is never a property of the person as a whole.
  Closes the gap named by `kg.statements.object-role`. *Test (to write):* test_role_is_a_position.py. **Not built:** the agent or doer position may be filled by an entity of any kind (`ontology.agency.any-kind-fills-the-agent-role`).
- `ontology.browse.is-a-table-of-what-is-used` — **[GAP]** (#1678 → #7015) the three lists can be read as one table
  in the Library: each kind, type and source category with how many records use it, opening to those records. It is
  a table of what the project holds, not a class diagram, and replaces the retired ontology browser.
  *Test (to write):* test_ontology_browse_table.py.

- `ontology.kinds.beyond-people` — **[GAP]** (#1678 → #NEW-P8) the closed list of kinds of thing of `ontology.kinds.small-closed-set` also holds, beside person, place, organisation, event and document: object, building, land, image, nature (river, animal, crop, weather event) and spiritual being (saint, spirit, demon, devotional image, the dead). The list is changed by a spec change only; a recipe may add its own kinds of event, as for people. *Test (to write):* test_ontology_kinds_beyond_people.py.
- `ontology.kinds.an-entity-has-a-set-of-kinds` — **[GAP]** (#1678 → #NEW-P9) an entity carries a set of kinds, not one value; each kind in the set rests on the statements or mentions that give it, and a kind a person sets is marked as theirs. A model's proposed kind is labelled and counts for nothing until a person accepts it. *Test (to write):* test_entity_kind_is_a_set.py.
- `ontology.agency.any-kind-fills-the-agent-role` — **[GAP]** (#1678 → #NEW-P9) the agent, actor or doer position of a statement, and either end of a relation, can be filled by an entity of any kind; no route, view or rule refuses an agent because it is not a person, and no ranking, count or view puts persons first. *Test (to write):* test_agent_of_any_kind.py (a statement whose agent is an image, a river and a spirit is stored and read back).
- `ontology.agency.recorded-as-stated-never-asserted` — **[GAP]** (#1678 → #NEW-P9) a statement with a non-person agent carries the source that states it and is shown as that source's statement; Fichero writes no agency of its own and no sentence in its own voice that an image, a river or a spirit did something. A historian's reading of it is stored in the hermeneutic layer (`hermeneutic.agency.reading-is-the-historians`). *Test (to write):* test_agency_is_attributed_to_its_source.py.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Backend (pytest) | y | the three lists, who may change each, roles as positions, source words kept | the files named above |
| MCP | y | the lists are read tools; a model's account cannot write one | `fichero-mcp/tests/test_mcp_generated.py` |
| Pure rule (Swift) | y | a historian's type is always marked as theirs beside the source's word | to write |

## Rules set by the owner's answers

- The seeded list of relation types is the default; a person adds to it, and a historian's own type is always marked
  as theirs beside the source's word.
- The default kinds of event are the same for every project; a recipe may add its own event kinds.
- Things, nature and the spiritual are kinds of thing; an entity may have several kinds at once; any kind can be the
  agent of a statement, recorded as its source states it and never asserted by Fichero.
- Lives of things, of nature and of the spiritual, and of words and concepts, are built in `kg/people-and-lives.md`
  and `explore/concepts-and-terms.md`.
