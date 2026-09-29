"""The knowledge graph's namespace IRIs, as plain strings.

Kept apart from `triples` so a module that only needs the IRIs (the JSON-LD context, which the
SPARQL route imports at app build) does not load rdflib with them (#5228: ~80 ms of every launch).
"""

# Fichero's own namespace for IDs and predicates that don't have a
# standard schema.org / FOAF equivalent. Stable URI — don't rename
# after the first export ships, or external consumers' queries break.
FICHERO_IRI = "https://fichero.app/ns#"

# schema.org — vocab for events, places, organizations.
SCHEMA_IRI = "https://schema.org/"
