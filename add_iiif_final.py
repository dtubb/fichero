#!/usr/bin/env python3
"""
Final script to add IIIF functionality
"""

# Read the current file
with open('src/fichero/cli/commands/library_commands.py', 'r') as f:
    content = f.read()

# Add imports
old_imports = '''import asyncio
import json
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional, Dict, Any
from unittest.mock import Mock
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich.text import Text
from rich.syntax import Syntax'''

new_imports = '''import asyncio
import json
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional, Dict, Any
from unittest.mock import Mock
import typer
import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich.text import Text
from rich.syntax import Syntax
from rich.progress import Progress, track'''

content = content.replace(old_imports, new_imports)

# Add IIIF command after structure command
structure_cmd = '''@library_app.command("structure")
def structure(collection_id: str, depth: int = 3):
    """Preview collection structure"""
    asyncio.run(_structure_collection(collection_id, depth))'''

iiiif_cmd = '''@library_app.command("structure")
def structure(collection_id: str, depth: int = 3):
    """Preview collection structure"""
    asyncio.run(_structure_collection(collection_id, depth))

@library_app.command("iiif-import")
def iiif_import(
    manifest_path: Path = typer.Argument(..., help="Path to IIIF manifest file or single manifest URL"),
    collection_name: str = typer.Option(..., "--name", "-n", help="Name for the imported collection"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory for downloaded images"),
    batch_size: int = typer.Option(100, "--batch-size", "-b", help="Batch size for concurrent downloads"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="Timeout for HTTP requests in seconds")
):
    """Import images from IIIF manifests or URLs"""
    asyncio.run(_iiif_import(manifest_path, collection_name, output_dir, batch_size, timeout))'''

content = content.replace(structure_cmd, iiif_cmd)

# Add IIIF methods before _get_collection_by_id
last_method = '''    async def _get_collection_by_id(self, collection_id: str):'''

iiiif_methods = '''    async def _iiif_import(self, manifest_path: Path, collection_name: str, output_dir: Optional[Path], batch_size: int, timeout: int):
        """Import images from IIIF manifests or URLs"""
        try:
            console.print(f"[blue]🔄 Starting IIIF import for collection: {collection_name}[/blue]")
            
            # Determine if it's a file or URL
            if manifest_path.is_file():
                # Read manifest file
                manifest_uris = manifest_path.read_text().splitlines()
                manifest_uris = [uri.strip() for uri in manifest_uris if uri.strip() and not uri.startswith("#")]
                console.print(f"[blue]📄 Found {len(manifest_uris)} manifest URIs in file[/blue]")
            else:
                # Treat as single URL
                manifest_uris = [str(manifest_path)]
                console.print(f"[blue]🌐 Using single manifest URL[/blue]")
            
            # Create output directory
            if output_dir is None:
                output_dir = Path(tempfile.mkdtemp(prefix="iiif_import_"))
            else:
                output_dir.mkdir(parents=True, exist_ok=True)
            
            # Download manifests and images
            collection_id = await self._download_iiif_collection(manifest_uris, collection_name, output_dir, batch_size, timeout)
            
            if collection_id:
                console.print(f"[green]✅ IIIF collection '{collection_name}' imported successfully[/green]")
                console.print(f"[blue]📁 Collection ID: {collection_id}[/blue]")
                console.print(f"[blue]📦 Images saved to: {output_dir}[/blue]")
            else:
                console.print(f"[red]❌ Failed to import IIIF collection[/red]")
                
        except Exception as e:
            console.print(f"[red]❌ IIIF import failed: {e}[/red]")

    async def _download_iiif_collection(self, manifest_uris: List[str], collection_name: str, output_dir: Path, batch_size: int, timeout: int) -> Optional[str]:
        """Download IIIF collection from manifest URIs"""
        try:
            with Progress() as progress:
                manifest_task = progress.add_task("[blue]Fetching manifests...", total=len(manifest_uris))
                image_task = progress.add_task("[blue]Downloading images...", total=0)
                
                # Fetch all manifests
                manifests = []
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    for uri in manifest_uris:
                        try:
                            response = await client.get(uri)
                            if response.status_code == 200:
                                manifest = response.json()
                                manifests.append(manifest)
                            else:
                                console.print(f"[yellow]⚠️  Failed to fetch manifest: {uri} (Status: {response.status_code})[/yellow]")
                        except Exception as e:
                            console.print(f"[yellow]⚠️  Error fetching manifest {uri}: {e}[/yellow]")
                        progress.update(manifest_task, advance=1)
                
                if not manifests:
                    console.print(f"[red]❌ No valid manifests found[/red]")
                    return None
                
                # Count total images
                total_images = 0
                for manifest in manifests:
                    if "sequences" in manifest and manifest["sequences"]:
                        total_images += len(manifest["sequences"][0].get("canvases", []))
                
                progress.update(image_task, total=total_images)
                console.print(f"[blue]📊 Found {total_images} images to download[/blue]")
                
                # Download images
                downloaded_count = 0
                for manifest in manifests:
                    if "sequences" in manifest and manifest["sequences"]:
                        images = manifest["sequences"][0].get("canvases", [])
                        
                        # Create subfolder for this manifest
                        manifest_id = manifest.get("@id", "unknown")
                        manifest_folder = output_dir / manifest_id.split('/')[-1]
                        manifest_folder.mkdir(parents=True, exist_ok=True)
                        
                        # Save manifest metadata
                        metadata = {
                            "id": manifest.get("@id"),
                            "label": manifest.get("label"),
                            "description": manifest.get("description"),
                            "metadata": manifest.get("metadata", [])
                        }
                        with open(manifest_folder / "metadata.json", 'w') as f:
                            json.dump(metadata, f, indent=2)
                        
                        # Download images in batches
                        image_tasks = []
                        for image in images:
                            if "images" in image and image["images"]:
                                image_resource = image["images"][0].get("resource", {})
                                if "@id" in image_resource:
                                    image_uri = image_resource["@id"]
                                    image_name = self._generate_image_name(image_uri)
                                    image_path = manifest_folder / image_name
                                    
                                    if not image_path.exists():
                                        image_tasks.append(self._download_image(client, image_uri, image_path, image_task, progress))
                                    else:
                                        progress.update(image_task, advance=1)
                                        downloaded_count += 1
                        
                        # Process images in batches
                        for i in range(0, len(image_tasks), batch_size):
                            batch = image_tasks[i:i + batch_size]
                            await asyncio.gather(*batch, return_exceptions=True)
                            downloaded_count += len(batch)
                
                # Add collection to library
                collection_id = await self.library_manager.add_collection(
                    name=collection_name,
                    collection_type="local",
                    source_path=str(output_dir),
                    description=f"IIIF collection with {downloaded_count} images"
                )
                
                return collection_id
                
        except Exception as e:
            console.print(f"[red]❌ Error downloading IIIF collection: {e}[/red]")
            return None

    async def _download_image(self, client: httpx.AsyncClient, image_uri: str, output_path: Path, task, progress: Progress):
        """Download a single image"""
        try:
            response = await client.get(image_uri)
            if response.status_code == 200:
                output_path.write_bytes(response.content)
                progress.update(task, advance=1)
            else:
                console.print(f"[yellow]⚠️  Failed to download image: {image_uri} (Status: {response.status_code})[/yellow]")
                progress.update(task, advance=1)
        except Exception as e:
            console.print(f"[yellow]⚠️  Error downloading image {image_uri}: {e}[/yellow]")
            progress.update(task, advance=1)

    def _generate_image_name(self, image_uri: str) -> str:
        """Generate a filename for an image URI"""
        # Extract filename from URI
        parts = image_uri.split('/')
        if len(parts) >= 2:
            filename = f"{parts[-2]}_{parts[-1]}"
        else:
            filename = parts[-1]
        
        # Ensure it has a proper extension
        if not any(filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.tiff', '.tif']):
            filename += '.jpg'
        
        return filename

    async def _get_collection_by_id(self, collection_id: str):'''

content = content.replace(last_method, iiif_methods)

# Write the updated file
with open('src/fichero/cli/commands/library_commands.py', 'w') as f:
    f.write(content)

print("✅ IIIF import functionality added successfully!")
