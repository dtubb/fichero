"""What every `*_id` an action or route accepts NAMES, for access control (#5177).

`authz` checks a request against the ids it names: a document id walks up its folders, and an id of
a kind in `_DOCUMENT_ID_RESOLVERS` is first resolved to the document it belongs to. An id of any
other kind is checked AS ITSELF -- so a deny on a page never reaches a record of that kind unless
the kind has a resolver. Archive found an editor denied a page could still withdraw its hand
attribution (b75cac9ef); this declaration is how the whole class stays closed.

`tests/unit/security/test_every_id_param_reaches_its_document.py` enumerates every `*_id` across the
registered actions and routes and FAILS on a name not declared here, on a declared record kind that
belongs to a document but has no resolver, and on any schema model pointing at a document that is
neither resolved nor declared library-scoped below.

* `RECORD` -- the name holds the id of these record kinds (model class names). Each must be
  `Document` (walked directly) or have a resolver.
* `LIBRARY` -- the name holds the id of something that belongs to no document: a person, a
  device, a provider, a workflow, a knowledge-graph record, a project. The reason says why a deny
  on a page has nothing to reach.
"""

from __future__ import annotations

RECORD = "record"
LIBRARY = "library"

_DOC = ("Document",)
_SEGMENT = ("Segment",)
_KG = "a knowledge-graph record: its source document is evidence, not its owner, and KG permissions are library-level (#4917 kept claims and entities itself-only; a ruling would change this, not a resolver)"
_ACCOUNT = "an account, session or device of the app database, not library content"
_CONFIG = "library or app configuration (a provider, model, profile, rule or setting), not content of any document"
_WORKFLOW = "a workflow, batch, run or job: library-level machinery whose targets are checked by their own ids"
_RESEARCH = "a research project, plan, task, step or checklist: library-level planning records"

#: name -> (RECORD, model names) | (LIBRARY, reason)
ID_PARAMS: dict[str, tuple[str, object]] = {
    # --- documents, folders and pages: Document rows, walked directly -------------------------
    **{name: (RECORD, _DOC) for name in (
        "doc_id", "doc_ids", "document_id", "document_ids", "page_id", "folder_id", "parent_id",
        "target_document_id", "source_document_id", "source_document_ids", "linked_document_id",
        "linked_document_ids", "realized_as_document_id", "library_destination_folder_id", "group_id",
        # document.group (#5303): the pages and documents gathered into a new group node.
        "child_ids",
    )},
    # --- the page model ------------------------------------------------------------------------
    **{name: (RECORD, _SEGMENT) for name in (
        "segment_id", "segment_ids", "parent_segment_id", "keep_id", "from_segment_id", "to_segment_id",
        "source_segment_id", "picture_segment_id", "new_segment_ids", "mask_id",
    )},
    "pass_id": (RECORD, ("SegmentPass",)),
    **{name: (RECORD, ("Artifact",)) for name in ("artifact_id", "source_artifact_id", "derived_from_artifact_id")},
    "match_id": (RECORD, ("SegmentMatch",)),
    "carry_ids": (RECORD, ("SegmentCarry",)),
    "fact_id": (RECORD, ("EditorialFact",)),
    "attribution_id": (RECORD, ("HandAttribution",)),
    # Slice 14 letterforms and campaigns (8b6a8b7bc, de90ff63f): each resolves to its document.
    "description_id": (RECORD, ("LetterformDescription",)),
    # stale-keeps-your-words (24c16562b): the reading a typed edit was based on; resolves to its document.
    "expected_counting_id": (RECORD, ("ContentRepresentation",)),
    "restore_id": (RECORD, ("LetterformDescription",)),
    "campaign_id": (RECORD, ("Campaign",)),
    "campaign_ids": (RECORD, ("Campaign",)),
    **{name: (RECORD, ("ContentRepresentation",)) for name in (
        "representation_id", "representation_ids", "corrects_representation_id",
        "derived_from_representation_id", "read_id", "written_id",
    )},
    "order_id": (RECORD, ("ReadingOrder",)),
    **{name: (RECORD, ("ReadingOrderEntry",)) for name in ("entry_id", "after_entry_id", "parent_entry_id")},
    "choice_id": (RECORD, ("SegmentPassChoice", "ReadingChoice")),
    **{name: (RECORD, ("Rendition",)) for name in ("rendition_id", "read_from_rendition_id")},
    # --- records anchored to a document when they are anchored at all -------------------------
    "annotation_id": (RECORD, ("Annotation",)),
    "interpretation_id": (RECORD, ("Interpretation",)),
    "note_id": (RECORD, ("Note", "DocumentNote", "AgentNote")),
    "linked_note_ids": (RECORD, ("Note",)),
    **{name: (RECORD, ("CanvasItem", "CanvasLayout")) for name in ("item_id", "source_item_id", "target_item_id", "current_item_ids", "node_ids")},
    "link_id": (RECORD, ("TypedLink", "LibraryItemLink")),
    "inclusion_id": (RECORD, ("ProjectInclusion",)),
    "citation_id": (RECORD, ("DocumentCitation",)),
    # Ends of a typed link, and generic targets: any id at all, each resolved by its own kind.
    **{name: (RECORD, ("*",)) for name in ("from_id", "to_id", "end_id", "target_id", "source_id", "source_ids", "id", "remove_ids", "reorder_ids", "bookmark_id")},
    # --- rights (#5177: archive's semantics) ---------------------------------------------------------
    "record_id": (RECORD, ("RightsRecord",)),   # agent audit records are app-database rows, checked by their own route
    # --- the knowledge graph ---------------------------------------------------------------------
    **{name: (LIBRARY, _KG) for name in (
        "claim_id", "claim_ids", "absorbed_claim_ids", "surviving_claim_id", "related_claim_id",
        "target_claim_id", "resulting_claim_id", "linked_claim_id", "linked_claim_ids",
        "entity_id", "entity_ids", "absorbed_entity_ids", "absorbing_entity_id", "candidate_entity_id",
        "editor_entity_id", "primary_entity_id", "scribe_entity_id", "source_entity_id",
        "speaker_entity_id", "split_off_entity_ids", "subject_entity_id", "subject_of_inquiry_entity_id",
        "survivor_entity_id", "target_entity_id", "linked_entity_id", "linked_entity_ids",
        "pattern_id", "framework_id", "value_id", "review_id", "pair_id", "reference_id",
        "authority_id", "property_id", "linked_structure_node_id", "linked_source_ids",
        "focus_id", "state_id",
    )},
    "allograph_id": (LIBRARY, "an allograph of the project's letterform list: its DESCRIPTIONS on characters are resolved (description_id)"),
    "hand_id": (LIBRARY, "a hand of the project's hand list: the ATTRIBUTION of a hand to a segment is resolved (attribution_id)"),
    "sign_id": (LIBRARY, "a sign of the project's sign list (slice 14): a sign's INSTANCES are segments, resolved as segments"),
    # --- accounts and configuration --------------------------------------------------------------
    **{name: (LIBRARY, _ACCOUNT) for name in ("user_id", "session_id", "device_id", "invite_id", "actor_id", "agent_id", "initiator_id")},
    **{name: (LIBRARY, _CONFIG) for name in ("provider_id", "model_id", "profile_id", "ref_id", "rule_id", "rule_ids", "cluster_id", "port_id")},
    **{name: (LIBRARY, _WORKFLOW) for name in (
        "workflow_id", "workflow_ids", "batch_id", "run_id", "job_id", "thread_id", "thread_ids", "action_id",
        "activity_id", "audit_id", "chain_id", "execution_id", "schedule_id", "trigger_id", "comparison_id",
    )},
    "server_id": (LIBRARY, _CONFIG),
    "external_id": (LIBRARY, "an item's id in ANOTHER application (Bookends, Tinderbox): nothing in this library"),
    "mutation_id": (LIBRARY, _KG),
    # maps D6/D7 (9205a2f25): a name or a dated geometry ON a place entity -- part of that KG record.
    "name_id": (LIBRARY, _KG),
    "place_id": (LIBRARY, _KG),
    "prediction_id": (LIBRARY, _KG),
    **{name: (LIBRARY, _RESEARCH) for name in ("project_id", "plan_id", "task_id", "step_id", "checklist_id", "workspace_id")},
    "conversation_id": (LIBRARY, "a chat conversation: library-level, not document content"),
    **{name: (LIBRARY, "a saved search: library-level") for name in ("search_id", "search_ids")},
    "snapshot_id": (LIBRARY, "a storage snapshot of the whole library"),
}

#: Schema models that point at a document (a `document_id`, `segment_id`, `page_id`, ... field) and
#: are NOT resolved to it, with why a deny on the page has nothing to reach.
LIBRARY_SCOPED_MODELS: dict[str, str] = {
    "KnowledgeClaim": _KG,
    "BookStructureNode": "a node of the book-structure outline built over many documents; its source document is where it was read from",
}
