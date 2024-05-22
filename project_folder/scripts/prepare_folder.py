import asyncio
import typer 
import requests
import srsly
from pathlib import Path
from typing_extensions import Annotated
from rich.progress import track


def prepare_folder(
        image_folder: Annotated[Path, typer.Argument(help="Path to the folder of images",exists=True)],
        output_path: Annotated[Path, typer.Argument(help="Path where fetched images are saved")],
):
    for file in track(list(image_folder.iterdir()), description="Processing images..."):
        if file.is_file():
            print(file)
        
if __name__ == "__main__":
    typer.run(prepare_folder)
