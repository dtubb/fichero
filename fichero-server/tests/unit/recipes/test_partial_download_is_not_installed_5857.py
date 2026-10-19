

def test_start_offers_the_download_of_a_partial_reader_and_a_run_refuses_it_in_words(folder, client, tmp_path,
                                                                                     monkeypatch):
    """Review 330 MED: Start's check (`_kraken_reader_here`) and the run's resolver trusted a stale marker, so a run
    still picked a partial reader. Every path now asks the one installed check."""
    from fichero_server.recipes import start
    from tests.unit.recipes.test_kraken_reader_offered_before_start import (LINES, READ, REAL_CHECK, _recipe, _save)

    monkeypatch.setattr(start, "_kraken_reader_here", REAL_CHECK)  # the real look at the model store
    (folder / "medium.safetensors.part").write_bytes(b"x" * 13)
    _marker(folder / "medium.safetensors")  # stale: names a file that was never completed
    assert kr.recognition_model_path(READER) is None

    _save(client, _recipe(tmp_path, LINES, READ))
    plan = client.get("/api/recipes/project/start").json()
    (offer,) = plan["downloads"]
    assert (offer["runtime"], offer["model"]) == ("kraken", READER)

    with pytest.raises(RuntimeError) as refused:
        kr.resolve_recognition_model(READER)
    said = str(refused.value)
    assert "not downloaded whole" in said and "its model file is missing" in said and READER not in said


def test_a_whole_reader_still_resolves(folder):
    weights = folder / "medium.safetensors"
    weights.write_bytes(b"w" * 100)
    _marker(weights, bytes=100)
    assert kr.recognition_model_path(READER) == str(weights)
    assert kr.resolve_recognition_model(READER) == (str(weights), READER)
