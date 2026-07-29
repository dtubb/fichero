"""Knowledge graph machinery — substrate, vectors, linkage.

Phased rollup (#899):

- Phase A: rdflib — SVO claims materialized as RDF triples (pending).
- Phase B: entity_vectors — sentence-transformer embeddings of canonical
  names + descriptions in LanceDB. Drives semantic dedup in
  ``upsert_entity``. (this commit)
- Phase C: spaCy NER pre-pass (implemented via workflow NER providers).
- Phase D: splink — probabilistic record linkage (pending).
- Phase E: PyKEEN — link prediction (#377).
"""
