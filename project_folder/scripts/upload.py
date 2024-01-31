import typer
from enum import Enum
from pathlib import Path
from typing_extensions import Annotated
from escriptorium_connector import EscriptoriumConnector
from escriptorium_connector.dtos import PostProject, PostDocument, PostPart
import srsly 
from io import BytesIO

class ReadDirection(str, Enum):
    LTR = "ltr"
    RTL = "rtl"

class LineOffset(int, Enum):
    BASELINE = 0
    TOPLINE = 1
    CENTERED = 2



def upload(
        escriptorium_url: Annotated[str, typer.Argument(help="URL to eScriptorium", envvar="ESCRIPTORIUM_URL")],
        escriptorium_username: Annotated[str, typer.Argument(help="Username for eScriptorium", envvar="ESCRIPTORIUM_USERNAME")],
        escriptorium_password: Annotated[str, typer.Argument(help="Password for eScriptorium", envvar="ESCRIPTORIUM_PASSWORD")],
        escriptorium_project_name: Annotated[str, typer.Argument(help="Name of the project in eScriptorium", envvar="ESCRIPTORIUM_PROJECT_NAME")],
        collection_path: Annotated[Path, typer.Argument(help="Path to the collections",exists=True)],
):
    E = EscriptoriumConnector(
        escriptorium_url,
        escriptorium_username,
        escriptorium_password,
    )

    projects = E.get_projects()
    # check if project_name in projects 
    project_exists = (
        escriptorium_project_name in [project.name for project in projects.results]
    )
    if project_exists:
        print(f"[*] Error: Project {escriptorium_project_name} already exists")
        typer.Exit()

    if not project_exists:
        print(f"Creating project: {escriptorium_project_name}")
        project = PostProject(name=escriptorium_project_name)
        project = E.create_project(project_data=project)
    
    collections = srsly.read_jsonl(collection_path / 'collections_metadata.jsonl')
    for collection in collections:
        document = PostDocument(name=collection['label'], project=project, main_script=None, read_direction=ReadDirection('ltr'),line_offset=LineOffset(0))
        document = E.create_document(doc_data=document)
        collection_subpath = collection_path / collection["id"].split('/')[-1]
        for image in collection.get('images', []):
            image_data_info = PostPart(name=image['id'], typology=None, source=image['uri'])
            image_data = Path(collection_subpath / image['filename']).read_bytes()
            part = E.create_document_part(document_pk=document.pk, image_data_info=image_data_info, filename=image['filename'], image_data=image_data)
            #Alto data 
            file_data=Path(collection_subpath / image['alto_filename']).read_bytes()
            file_data = BytesIO(file_data)
            alto = E.upload_part_transcription(document_pk=document.pk, transcription_name='vision', filename=image['filename'], file_data=file_data, override="on")
       
if __name__ == "__main__":
    typer.run(upload)