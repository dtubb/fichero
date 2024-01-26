import asyncio
from typing import Optional
from pathlib import Path
from spacy.cli._util import Arg, Opt, import_code
import typer
from rich.progress import track, Progress
import httpx
import srsly 
from asyncio import run as aiorun

async def fetch_image(image_uri: str, output_path: Path, output_subpath: Path, image_name: str, image_task: int, progress: Progress):
    try:
        async with httpx.AsyncClient() as client:
            image_response = await client.get(image_uri, timeout=None)  # Increase the timeout value as needed
            if image_response.status_code == 200:
                (output_subpath / image_name).write_bytes(image_response.content)
                progress.update(image_task, advance=1)
    except httpx.ReadTimeout:
        print(f"Timeout occurred while fetching image: {image_uri}")

async def fetch_manifest(uri: str, output_path: Path, manifest_task: int, progress: Progress):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(uri, timeout=None)  # Increase the timeout value as needed
            manifest = response.json()
            progress.update(manifest_task, advance=1)
            return manifest
    except httpx.ReadTimeout or httpx.ConnectError:
        print(f"Error occurred while fetching manifest: {uri}")


def fetch_iiif(
    # fmt: off
    iiif_collections: Path = Arg(..., help="Path to the collections.txt file", exists=True),
    output_path: Path = Arg(..., help="Path where fetches images are saved"),
):
    async def _fetch_iiif():

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

        with Progress() as progress:
            manifest_task = progress.add_task("[blue]Manifests...", total=len(manifest_uris))
            image_task = progress.add_task("[blue]Images and metadata...")
            while not progress.finished:
                # use httpx to fetch each manifest
                tasks = []
                for uri in manifest_uris:
                    tasks.append(fetch_manifest(uri, output_path, manifest_task, progress))
                manifests = await asyncio.gather(*tasks)

                # loop through each manifest
                image_count = 0
                for manifest in manifests:
                    images = manifest["sequences"][0]["canvases"]
                    image_count += len(images)
                print(f"Found {image_count} images")
                progress.tasks[1].total = image_count
                
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
                    image_tasks = []
                    for image in images:
                        id = image["images"][0]["resource"]["service"]["@id"]
                        # https://images.eap.bl.uk/EAP1477/EAP1477_1_1_6/1.jp2
                        image_name = id.split('/')[-2] + "_" +  id.split('/')[-1]
                        image_name = image_name.split('.')[0] + ".jpg"
                        if not (output_subpath / image_name).exists():
                            image_uri = image["images"][0]["resource"]["@id"]
                            image_tasks.append(fetch_image(image_uri, output_path, output_subpath, image_name, image_task, progress))
                    await asyncio.gather(*image_tasks)

    aiorun(_fetch_iiif())

if __name__ == "__main__":
    typer.run(fetch_iiif)
