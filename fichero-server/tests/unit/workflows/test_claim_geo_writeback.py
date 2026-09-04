"""The map has coordinates to plot, and they say where they came from (#4668).

Daniel: "the map doesn't really map." `KGMapView` has been a real MapKit
surface since #1267 and plotted nothing, because NOTHING in the extraction
pipeline ever wrote `KnowledgeClaim.claim_geo`: `extract_geo` geocoded place
names and returned the points as tool OUTPUT, which no one consumed.

Two integrity rules ride with the fix and are pinned here:

* a geocoded point is INFERRED, never asserted — a gazetteer hit is not
  evidence from the manuscript, it is an inference about a name the manuscript
  contains, and the map draws an open pin for exactly that;
* the row records which geocoder resolved which string, because "Condoto" is
  ambiguous across countries and an untraceable coordinate cannot be checked.

An unresolved name stays unresolved. It is never approximated onto the map.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration._seedlib import seed

from fichero_server.db import db_manager
from fichero_server.media import geo
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import (
    EvidenceBasis,
    GeoPoint,
    KnowledgeClaim,
    PlaceGeometryType,
)
from fichero_server.workflows.tools._entity_writer import (
    attach_geocoded_places,
    save_claim,
)


@pytest.fixture
def library(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    library_path = tmp_path / "geo.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)
    db.save(Document(id="d1", name="page.txt", doc_type=DocType.page))
    return db


def _claim(db, **kwargs):
    claim_id = save_claim(
        db,
        text=kwargs.pop("text", "Pedro travelled to Popayán."),
        source_document_id="d1",
        source_page_label="1r",
        **kwargs,
    )
    return db.get(KnowledgeClaim, claim_id)


class TestSaveClaimRoundTrip:
    def test_a_point_round_trips_onto_the_claim(self, library):
        claim = _claim(
            library,
            claim_location="Popayán",
            claim_geo=GeoPoint(lat=2.4448, lon=-76.6147, place_name="Popayán"),
        )
        assert claim.claim_geo is not None
        assert claim.claim_geo.lat == pytest.approx(2.4448)
        assert claim.claim_geo.lon == pytest.approx(-76.6147)

    def test_a_hand_placed_point_stays_asserted(self, library):
        # The manual claim-create route's meaning must not change: a person
        # placing a pin IS the assertion.
        claim = _claim(
            library,
            claim_location="Popayán",
            claim_geo=GeoPoint(lat=2.4448, lon=-76.6147),
        )
        place = next(p for p in claim.place_values if p.lat is not None)
        assert place.basis == EvidenceBasis.asserted
        assert place.created_by == "extractor"

    def test_a_geocoded_point_is_inferred_and_names_its_geocoder(self, library):
        claim = _claim(
            library,
            claim_location="Popayán",
            claim_geo=GeoPoint(lat=2.4448, lon=-76.6147),
            claim_geo_basis=EvidenceBasis.inferred,
            claim_geo_source='Geocoded from "Popayán" by the offline gazetteer.',
        )
        place = next(p for p in claim.place_values if p.lat is not None)
        assert place.basis == EvidenceBasis.inferred
        assert place.created_by == "geocoder"
        assert "offline gazetteer" in (place.rationale or "")


class TestWriteBack:
    def test_a_resolved_place_lands_on_the_run_s_claims(self, library):
        claim = _claim(library, claim_location="Popayán")
        assert claim.claim_geo is None, "fixture must start unplaced"

        result = attach_geocoded_places(
            library,
            document_ids=["d1"],
            points_by_name=geo.geocode_places_with_source(["Popayán"]),
        )
        assert result["updated"] == 1

        placed = library.get(KnowledgeClaim, claim.id)
        assert placed.claim_geo is not None
        assert placed.claim_geo.lat == pytest.approx(2.4448, abs=0.01)
        place = next(p for p in placed.place_values if p.lat is not None)
        assert place.basis == EvidenceBasis.inferred
        assert place.geometry_type == PlaceGeometryType.point
        assert place.created_by == "geocoder"
        # The provenance sentence names the string AND the service, so the pin
        # can be checked without re-running anything.
        assert "Popayán" in place.rationale
        assert geo.SOURCE_GAZETTEER in place.rationale
        assert "Not attested by the source" in place.rationale

    def test_an_unresolved_name_leaves_the_claim_unplaced(self, library):
        claim = _claim(
            library,
            text="Pedro travelled to Opogodó.",
            claim_location="Opogodó",
        )
        sourced = geo.geocode_places_with_source(["Opogodó"])
        # Deliberately absent from the gazetteer: a model-recalled coordinate
        # would pin a mining claim into the wrong river valley and look exactly
        # as confident as a correct one.
        assert sourced == {}

        attach_geocoded_places(library, document_ids=["d1"], points_by_name=sourced)
        assert library.get(KnowledgeClaim, claim.id).claim_geo is None

    def test_accents_and_case_do_not_stop_a_match(self, library):
        claim = _claim(library, claim_location="popayan")
        attach_geocoded_places(
            library,
            document_ids=["d1"],
            points_by_name=geo.geocode_places_with_source(["Popayán"]),
        )
        assert library.get(KnowledgeClaim, claim.id).claim_geo is not None

    def test_a_claim_that_is_already_placed_is_left_alone(self, library):
        claim = _claim(
            library,
            claim_location="Popayán",
            claim_geo=GeoPoint(lat=1.0, lon=1.0),
        )
        result = attach_geocoded_places(
            library,
            document_ids=["d1"],
            points_by_name=geo.geocode_places_with_source(["Popayán"]),
        )
        assert result["updated"] == 0
        assert result["already_placed"] == 1
        # A person's placement outranks a fresh lookup.
        assert library.get(KnowledgeClaim, claim.id).claim_geo.lat == pytest.approx(1.0)

    def test_a_name_matching_no_claim_is_reported_not_invented(self, library):
        _claim(library, claim_location="Popayán")
        result = attach_geocoded_places(
            library,
            document_ids=["d1"],
            points_by_name=geo.geocode_places_with_source(["Popayán", "Quito"]),
        )
        assert result["updated"] == 1
        assert result["unmatched_names"] == 1

    def test_the_subject_is_matched_when_it_is_the_place(self, library):
        # The entities path: a location-typed subject IS the claim's place.
        claim = _claim(
            library,
            text="Quito is a city.",
            subject_canonical="Quito",
        )
        attach_geocoded_places(
            library,
            document_ids=["d1"],
            points_by_name=geo.geocode_places_with_source(["Quito"]),
        )
        assert library.get(KnowledgeClaim, claim.id).claim_geo is not None


class TestGeocoderProvenance:
    def test_the_gazetteer_tier_is_named(self):
        sourced = geo.geocode_places_with_source(["Madrid"])
        assert sourced["Madrid"][1] == geo.SOURCE_GAZETTEER

    def test_a_miss_is_absent_rather_than_guessed(self):
        assert geo.geocode_places_with_source(["???nowhere???"]) == {}
