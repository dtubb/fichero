from typing import Optional
from pathlib import Path
from spacy.cli._util import Arg, Opt, import_code
import typer
from rich.progress import track, Progress
import httpx
import srsly 

def fetch_iiif(
    # fmt: off
    iiif_collections: Path = Arg(..., help="Path to the collections.txt file", exists=True),
    output_path: Path = Arg(..., help="Path where fetches images are saved"),
):
    """
    Process a txt file that contains IIIF manifest URIs. Fetch each manifest, parse it and find the URL for each image 
    in the collection. Then download each image and save it to a folder.
    """
    
    # load txt file and get manifest URIs
    manifest_uris = Path(iiif_collections).read_text().splitlines()
    # ignore lines with comments and blank lines
    manifest_uris = [uri for uri in manifest_uris if not uri.startswith("#") and uri != ""]
    print(f"Found {len(manifest_uris)} manifest URIs")
    
    # output_path does not exist, create it 
    if not output_path.exists():
        output_path.mkdir(parents=True)

    # use httpx to fetch each manifest
    manifests = []
    for uri in track(manifest_uris):
        response = httpx.get(uri)
        # parse the manifest
        manifest = response.json()
        manifests.append(manifest)

    # loop through each manifest
    image_count = 0
    for manifest in manifests:
        images = manifest["sequences"][0]["canvases"]
        image_count += len(images)

    with Progress() as progress:
        task1 = progress.add_task("[blue]Downloading images and metadata...", total=image_count)
        while not progress.finished:
            for manifest in manifests:    
                # get the metadata
                metadata = {}
                metadata["id"] = manifest.get("@id", None)

                # make a subfolder for each manifest
                output_subpath = output_path / metadata["id"].split('/')[-1]
                if not output_subpath.exists():
                    output_subpath.mkdir(parents=True)

                metadata["label"] = manifest.get("label", None)
                metadata["description"] = manifest.get("description", None)
                manifest_metadata = manifest.get("metadata", None)
                if manifest_metadata:
                    for item in manifest_metadata:
                        metadata[item["label"]] = item["value"]
                srsly.write_json(output_subpath / "metadata.json", metadata)

                # get the images
                images = manifest["sequences"][0]["canvases"]
                # get the image URIs
                for image in images:
                    id = image["images"][0]["resource"]["service"]["@id"]
                    # https://images.eap.bl.uk/EAP1477/EAP1477_1_1_6/1.jp2
                    image_name = id.split('/')[-2] + "_" +  id.split('/')[-1]
                    image_name = image_name.split('.')[0] + ".jpg"
                    if not (output_subpath / image_name).exists():
                        image_uri = image["images"][0]["resource"]["@id"]
                        # fetch the image
                        image_response = httpx.get(image_uri)
                        # save the image
                        if image_response.status_code == 200:
                            (output_subpath / image_name).write_bytes(image_response.content)
                    progress.update(task1, advance=1)

if __name__ == "__main__":
    typer.run(fetch_iiif)
