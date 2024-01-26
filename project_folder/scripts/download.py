import typer
from zipfile import ZipFile
from io import BytesIO
from escriptorium_connector import EscriptoriumConnector
from typing_extensions import Annotated


def download(
    escriptorium_url: Annotated[str, typer.Argument(help="Escriptorium URL")],
    username: Annotated[str, typer.Argument(help="Escriptorium username")],
    password: Annotated[str, typer.Argument(help="Escriptorium password")],
    project_name: Annotated[str, typer.Argument(help="Escriptorium project name")],
    collection_path: Annotated[str, typer.Argument(help="Path to the collections", exists=True)],
    transcription: Annotated[str, typer.Argument(help="Escriptorium transcription name")],
):
    E = EscriptoriumConnector(
            escriptorium_url,
            username,
            password,
        )
    
    projects = E.get_projects()
    project = [p for p in projects.results if p.name == project_name][0]
    
    documents = E.get_documents()
    documents = [d for d in documents.results if d.project == project.slug]

    transcription = [t for t in documents[0].transcriptions if t.name == transcription][0]

    existing_images = list(collection_path.glob("**/*.jpg"))
    existing_image_names = [i.name for i in existing_images]

    for document in documents:
        parts = E.get_document_parts(document.pk)
        for part in parts.results:
            
            if part.filename not in existing_image_names:
                part_Path = (collection_path / part.filename)
                # download the image
                image = E.download_part_image(document.pk, part.pk)
                # save the image
                part_Path.write_bytes(image)
            
            if part.filename in existing_image_names:
                part_Path = [i for i in existing_images if i.name == part.filename][0]

            alto_xml = E.download_part_alto_transcription(
                    document.pk, part.pk, transcription.pk
            )
            # You will need to unzip these bytes in order to access the XML data (zipfile can do this).
            with ZipFile(BytesIO(alto_xml)) as z:
                with z.open(z.namelist()[0]) as f:
                    alto_xml = f.read()
            # save the alto
            part_Path.with_suffix('.xml').write_bytes(alto_xml)
    

if __name__ == "__main__":
    typer.run(download)
