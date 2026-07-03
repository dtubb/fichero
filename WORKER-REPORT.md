2026-07-03 #2837: serialized Database._ensure_table under the existing DB lock to eliminate concurrent claim/entity lazy-column races; test_mutation_concurrency.py now fully passes (`6 passed`).
