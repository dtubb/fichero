#!/usr/bin/env python3
"""
Add IIIF command after structure command
"""

# Read the current file
with open('src/fichero/cli/commands/library_commands.py', 'r') as f:
    content = f.read()

# Find the structure command and add IIIF command after it
structure_end = '''        @self.app.command(name="structure", help="Preview collection structure")
        def preview_structure(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            max_depth: int = typer.Option(3, "--depth", "-d", help="Maximum depth to show")
        ):
            """Preview collection structure"""
            asyncio.run(self._preview_structure(collection_id, max_depth))'''

iiiif_command = '''        @self.app.command(name="structure", help="Preview collection structure")
        def preview_structure(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            max_depth: int = typer.Option(3, "--depth", "-d", help="Maximum depth to show")
        ):
            """Preview collection structure"""
            asyncio.run(self._preview_structure(collection_id, max_depth))

        @self.app.command(name="iiif-import", help="Import images from IIIF manifests or URLs")
        def iiif_import(
            manifest_path: Path = typer.Argument(..., help="Path to IIIF manifest file or single manifest URL"),
            collection_name: str = typer.Option(..., "--name", "-n", help="Name for the imported collection"),
            output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory for downloaded images"),
            batch_size: int = typer.Option(100, "--batch-size", "-b", help="Batch size for concurrent downloads"),
            timeout: int = typer.Option(30, "--timeout", "-t", help="Timeout for HTTP requests in seconds")
        ):
            """Import images from IIIF manifests or URLs"""
            asyncio.run(self._iiif_import(manifest_path, collection_name, output_dir, batch_size, timeout))'''

content = content.replace(structure_end, iiif_command)

# Write the updated file
with open('src/fichero/cli/commands/library_commands.py', 'w') as f:
    f.write(content)

print("✅ IIIF command added successfully!")
