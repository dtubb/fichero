import asyncio
import typer 
import requests
import srsly
from pathlib import Path
from typing_extensions import Annotated
from rich.progress import track


def metadata(
        iiif_collections: Annotated[Path, typer.Argument(help="Path to the collections.txt file",exists=True)],
        output_path: Annotated[Path, typer.Argument(help="Path where fetched images were saved")],
):
    # read the manifests 
    # load txt file and get manifest URIs
    manifest_uris = Path(iiif_collections).read_text().splitlines()
    # ignore lines with comments and blank lines
    manifest_uris = [uri for uri in manifest_uris if not uri.startswith("#") and uri != ""]
    manifests = []
    for uri in track(manifest_uris, description="Fetching manifests..."):
        response = requests.get(uri)
        manifest = response.json()
        manifests.append(manifest)

    collections_data = []
    for manifest in track(manifests, description="Processing manifests..."):
        # get the metadata
        metadata = {}
        metadata['images'] = []
        metadata["id"] = manifest.get("@id", None)
        output_subpath = output_path / metadata["id"].split('/')[-1]
        metadata["label"] = manifest.get("label", None)
        metadata["description"] = manifest.get("description", None)
        manifest_metadata = manifest.get("metadata", None)
        if manifest_metadata:
            for item in manifest_metadata:
                metadata[item["label"]] = item["value"]
        
        images = manifest["sequences"][0]["canvases"]

        for image in images:
            img = {}
            img['id'] = image["images"][0]["resource"]["service"]["@id"]
            img['uri'] = image["images"][0]["resource"]["@id"]
            
            img['filename'] = img['id'].split('/')[-2] + "_" +  img['id'].split('/')[-1]
            img['filename'] = img['filename'].split('.')[0] + ".jpg"
            img['alto_filename'] = img['filename'].split('.')[0] + ".xml"
            metadata['images'].append(img)
        collections_data.append(metadata)
    srsly.write_jsonl(f'{str(output_path)}/collections_metadata.jsonl', collections_data)

if __name__ == "__main__":
    typer.run(metadata)
