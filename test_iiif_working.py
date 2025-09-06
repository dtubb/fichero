#!/usr/bin/env python3
"""
Working IIIF implementation for testing
"""

import asyncio
import httpx
import json
from pathlib import Path
from rich.console import Console
from rich.progress import Progress

console = Console()

async def test_iiif_download():
    """Test downloading images from a IIIF manifest"""
    try:
        # Test with a simple IIIF manifest
        manifest_url = "https://iiif.io/api/presentation/3.0/example/manifests/book1.json"
        
        console.print(f"[blue]🔄 Testing IIIF download from: {manifest_url}[/blue]")
        
        # Create output directory
        output_dir = Path("/tmp/iiif_test")
        output_dir.mkdir(exist_ok=True)
        
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            # Fetch manifest
            response = await client.get(manifest_url)
            
            if response.status_code == 200:
                manifest = response.json()
                console.print(f"[green]✅ Successfully fetched manifest[/green]")
                console.print(f"[blue]📄 Manifest ID: {manifest.get('@id', 'Unknown')}[/blue]")
                console.print(f"[blue]📝 Label: {manifest.get('label', 'Unknown')}[/blue]")
                
                # Check for sequences and canvases
                if "sequences" in manifest and manifest["sequences"]:
                    sequences = manifest["sequences"]
                    console.print(f"[blue]📚 Found {len(sequences)} sequences[/blue]")
                    
                    if sequences[0].get("canvases"):
                        canvases = sequences[0]["canvases"]
                        console.print(f"[blue]🖼️  Found {len(canvases)} canvases (images)[/blue]")
                        
                        # Download first few images as test
                        with Progress() as progress:
                            task = progress.add_task("[blue]Downloading images...", total=min(3, len(canvases)))
                            
                            for i, canvas in enumerate(canvases[:3]):
                                if "images" in canvas and canvas["images"]:
                                    image_resource = canvas["images"][0].get("resource", {})
                                    if "@id" in image_resource:
                                        image_uri = image_resource["@id"]
                                        image_name = f"image_{i+1}.jpg"
                                        image_path = output_dir / image_name
                                        
                                        try:
                                            img_response = await client.get(image_uri)
                                            if img_response.status_code == 200:
                                                image_path.write_bytes(img_response.content)
                                                console.print(f"[green]✅ Downloaded: {image_name}[/green]")
                                            else:
                                                console.print(f"[yellow]⚠️  Failed to download image {i+1}: {img_response.status_code}[/yellow]")
                                        except Exception as e:
                                            console.print(f"[yellow]⚠️  Error downloading image {i+1}: {e}[/yellow]")
                                        
                                        progress.update(task, advance=1)
                        
                        console.print(f"[green]✅ IIIF test completed successfully![/green]")
                        console.print(f"[blue]📦 Images saved to: {output_dir}[/blue]")
                        return True
                    else:
                        console.print(f"[yellow]⚠️  No canvases found in manifest[/yellow]")
                        return False
                else:
                    console.print(f"[yellow]⚠️  No sequences found in manifest[/yellow]")
                    return False
            else:
                console.print(f"[red]❌ Failed to fetch manifest: {response.status_code}[/red]")
                return False
                
    except Exception as e:
        console.print(f"[red]❌ Error testing IIIF: {e}[/red]")
        return False

if __name__ == "__main__":
    asyncio.run(test_iiif_download())
