from fichero_server.workflows.tools.output_quality import detect_page_contamination_warnings


def test_detect_page_contamination_flags_outlier_pages():
    result = {
        "page_records": [
            {"doc_id": "p1", "text": "Juzgado del Trabajo de Istmina, demanda laboral de Francisco Urrutia."},
            {"doc_id": "p2", "text": "Compañía Minera Chocó Pacífico, Andagoya y Quibdó."},
            {"doc_id": "p3", "text": "Guardia Civil en Alicante 1950."},
            {"doc_id": "p4", "text": "We the People of the United States, Article I."},
        ]
    }

    warnings = detect_page_contamination_warnings(result)
    warned_ids = {w["doc_id"] for w in warnings}
    assert "p3" in warned_ids
    assert "p4" in warned_ids
    assert "p1" not in warned_ids
    assert "p2" not in warned_ids


def test_detect_page_contamination_ignores_consistent_pages():
    result = {
        "page_records": [
            {"doc_id": "p1", "text": "Juzgado laboral de Istmina."},
            {"doc_id": "p2", "text": "Demanda contra compañía minera en Andagoya."},
            {"doc_id": "p3", "text": "Tribunal de Quibdó, proceso laboral."},
        ]
    }

    warnings = detect_page_contamination_warnings(result)
    assert warnings == []


def test_detect_page_contamination_carries_page_number_context():
    result = {
        "page_records": [
            {"doc_id": "p1", "page_number": 1, "text": "Juzgado laboral de Istmina."},
            {"doc_id": "p2", "page_number": 2, "text": "Demanda contra compañía minera."},
            {"doc_id": "p3", "page_number": 3, "text": "We the People of the United States."},
        ]
    }

    warnings = detect_page_contamination_warnings(result)
    us_warning = next(w for w in warnings if w["doc_id"] == "p3")
    assert us_warning["page_number"] == 3
