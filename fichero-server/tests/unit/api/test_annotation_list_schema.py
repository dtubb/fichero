from fichero_server.api.routes.document.annotations import AnnotationListResponse


def test_annotation_list_schema_has_typed_items():
    items = AnnotationListResponse.model_json_schema()["properties"]["items"]
    assert items["items"]["$ref"].endswith("/Annotation")
