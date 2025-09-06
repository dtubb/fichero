#!/usr/bin/env python3
"""
Simple IIIF test without srsly
"""

import asyncio
import httpx
import json
from pathlib import Path
from rich.console import Console
from rich.progress import Progress

console = Console()

async def test_iiif_manifest():
    """Test fetching a IIIF manifest"""
    try:
        manifest_url = "https://iiif.io/api/presentation/3.0/example/manifests/book1.json"
        
        console.print(f"[blue]🔄 Testing IIIF manifest: {manifest_url}[/blue]")
        
        async with httpx.AsyncClient(timeout=30) as client:
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
                        
                        # Show first few images
                        for i, canvas in enumerate(canvases[:3]):
                            if "images" in canvas and canvas["images"]:
                                image_resource = canvas["images"][0].get("resource", {})
                                if "@id" in image_resource:
                                    console.print(f"[blue]  Image {i+1}: {image_resource['@id']}[/blue]")
                
                return True
            else:
                console.print(f"[red]❌ Failed to fetch manifest: {response.status_code}[/red]")
                return False
                
    except Exception as e:
        console.print(f"[red]❌ Error testing IIIF: {e}[/red]")
        return False

if __name__ == "__main__":
    asyncio.run(test_iiif_manifest())
