"""What the user pointed at when they started a run (#4397 #4396 #4427).

`selected_doc_ids` rode untyped inside `ExecuteWorkflowRequest.inputs`, a
`dict[str, Any]`. There was no schema for the selection at all — not a weak
contract, an absent one. That is *why* #4396 was possible: a client sent a
whole folder when the user had picked one file, and nothing in the contract
could reject it, because there was no contract to violate.

The important part is not that the field is typed. It is that it describes
**what the user pointed at** rather than a pre-resolved list of ids.

A flat `list[str]` would fix the type and keep the wrong division of labour:
the client would still be the thing deciding what a folder means, and the
server would still have to trust it. With a declared *kind*, the server
resolves scope — which is #4427's rule, and what turns #4396 from a bug that
was fixed into a request that cannot be expressed.

Concretely: a client that claims `kind=folder` and sends 47 ids is now
rejected at the boundary. A client that sends 47 ids can only honestly call
them `documents`, at which point the server's own expansion is the authority
and there is nothing left for the client to get wrong.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class SelectionKind(str, Enum):
    """What sort of thing the user selected.

    An enum, not a string, for the same reason `artifact_type` is being made
    one (#4426): the generated Swift client gets a compile error instead of a
    silent mismatch. A vocabulary the client can misspell is a vocabulary that
    will eventually be misspelled.
    """

    #: An explicit set of documents the user picked. The ids ARE the scope.
    documents = "documents"
    #: One folder. The server expands it — the client must not.
    folder = "folder"
    #: One collection. As above.
    collection = "collection"


#: Kinds that name a single container the server expands. Sending more than
#: one id for these is the #4396 shape stated in the request itself.
_SINGLE_CONTAINER_KINDS = frozenset({SelectionKind.folder, SelectionKind.collection})


class WorkflowSelection(BaseModel):
    """The declared scope of a run.

    Validation is the whole point: this is the first place in the system that
    can say "that request does not describe a coherent selection" and refuse,
    rather than running and discovering the scope was wrong from its effects
    on real archival data.
    """

    kind: SelectionKind
    ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_shape(self) -> "WorkflowSelection":
        cleaned = [str(i).strip() for i in self.ids if str(i).strip()]
        if not cleaned:
            raise ValueError(
                f"selection.kind={self.kind.value} requires at least one id; "
                "an empty selection is not a scope, it is a missing argument"
            )
        if self.kind in _SINGLE_CONTAINER_KINDS and len(cleaned) != 1:
            # The #4396 assertion, made structural: a folder run is scoped to
            # ONE folder. A client sending the folder's contents alongside (or
            # instead of) the folder is describing a different run than the
            # user asked for, and that is now unrepresentable rather than
            # merely discouraged.
            raise ValueError(
                f"selection.kind={self.kind.value} names a single container "
                f"but {len(cleaned)} ids were sent. The server expands a "
                "container; a client that has already expanded it should say "
                f"kind={SelectionKind.documents.value} instead."
            )
        object.__setattr__(self, "ids", cleaned)
        return self

    @property
    def container_id(self) -> str | None:
        """The container this run is scoped to, when it is scoped to one."""
        if self.kind in _SINGLE_CONTAINER_KINDS and self.ids:
            return self.ids[0]
        return None
