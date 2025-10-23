"""
Import/Export Commands

Collection import and export functionality.
"""

import asyncio
import tempfile
import zipfile
import signal
from pathlib import Path
from typing import Optional
import typer

from .base import BaseLibraryCommands


class ImportExportCommands(BaseLibraryCommands):
    """Import and export collection commands"""

    def __init__(self, app_initializer=None, base_commands=None):
        """Initialize import/export commands - optionally share base instance"""
        if base_commands:
            # Use shared base instance (library_manager, director, etc.)
            self.library_manager = base_commands.library_manager
            self.director = base_commands.director
            self.bridge = base_commands.bridge
            self.console = base_commands.console
            self.app_initializer = app_initializer
        else:
            # Create own instances (standalone mode)
            super().__init__(app_initializer)

    def register_commands(self, app):
        """Register import/export commands"""

        @app.command(name="import", help="Import a collection from a path")
        def import_collection(
            path: Path = typer.Argument(..., help="Path to import collection from"),
            name: Optional[str] = typer.Option(None, "--name", "-n", help="Name for the imported collection"),
            operation: str = typer.Option("copy", "--operation", "-o", help="Operation: 'copy' (default) or 'link'")
        ):
            """Import a collection from a path"""
            asyncio.run(self._import_collection(path, name, operation))

        @app.command(name="export", help="Export a collection to a path")
        def export_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to export"),
            path: Path = typer.Argument(..., help="Path to export collection to")
        ):
            """Export a collection to a path"""
            asyncio.run(self._export_collection(collection_id, path))

        @app.command(name="import-zip-url", help="Download ZIP from URL, extract, and import into library (supports OneDrive links)")
        def import_zip_url(
            url: str = typer.Argument(..., help="URL to ZIP file (supports OneDrive/SharePoint sharing links)"),
            name: str = typer.Argument(..., help="Name for the new collection"),
            description: Optional[str] = typer.Option(None, "--description", "-d", help="Collection description"),
            timeout: int = typer.Option(300, "--timeout", "-t", help="Download timeout in seconds (default: 300)"),
            max_size: int = typer.Option(500, "--max-size", "-s", help="Maximum ZIP size in MB (default: 500)")
        ):
            """Download ZIP from URL, extract, import into library, and delete ZIP file"""
            asyncio.run(self._import_zip_url(url, name, description, timeout, max_size))

        @app.command(name="import-url", help="Import content from URL using auto-detected plugin (ZIP, Box.com, EAP)")
        def import_from_url(
            url: str = typer.Argument(..., help="URL to import from (ZIP, Box.com share, EAP project, etc.)"),
            name: str = typer.Argument(..., help="Name for the new collection"),
            description: Optional[str] = typer.Option(None, "--description", "-d", help="Collection description"),
            timeout: int = typer.Option(600, "--timeout", "-t", help="Download timeout in seconds (default: 600)"),
            max_items: int = typer.Option(1000, "--max-items", help="Maximum number of items to process (default: 1000)"),
            download_mode: Optional[str] = typer.Option(None, "--mode", help="Download mode for EAP plugin: 'link' or 'download' (default: link)")
        ):
            """Import content from URL using auto-detected plugin with progress tracking"""
            asyncio.run(self._import_from_url(url, name, description, timeout, max_items, download_mode))

        @app.command(name="list-import-plugins", help="List all available import plugins and their supported URLs")
        def list_import_plugins():
            """List all available import plugins"""
            asyncio.run(self._list_plugins())
    
    async def _import_collection(self, path: Path, name: Optional[str], operation: str = "copy"):
        """Import a collection from zip file or directory"""
        try:
            # Check if path exists
            if not path.exists():
                self.console.print(f"[red]❌ Path does not exist: {path}[/red]")
                return

            # Validate operation
            if operation not in ["copy", "link"]:
                self.console.print(f"[red]❌ Invalid operation: {operation}. Must be 'copy' or 'link'[/red]")
                return

            # Determine collection name
            collection_name = name or path.stem

            # Check if it's a zip file
            if path.suffix.lower() == '.zip':
                # Import from zip file (always copies to library)
                await self._import_from_zip(path, collection_name)
            else:
                # Import from directory with specified operation
                await self._import_from_directory(path, collection_name, operation)
                
        except Exception as e:
            self.console.print(f"[red]❌ Failed to import collection: {e}[/red]")
    
    async def _import_from_zip(self, zip_path: Path, collection_name: str):
        """Import collection from zip file (either Fichero export or generic ZIP)"""
        try:
            self.console.print(f"[blue]📦 Importing collection from {zip_path.name}...[/blue]")

            # Check if this is a Fichero export (contains manifest.json)
            is_fichero_export = False
            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    is_fichero_export = 'manifest.json' in zf.namelist()
            except zipfile.BadZipFile:
                self.console.print(f"[red]❌ Invalid ZIP file: {zip_path}[/red]")
                return

            if is_fichero_export:
                # This is a Fichero export - use the library manager's import method
                self.console.print(f"[dim]Detected Fichero export format (manifest.json found)[/dim]")
                collection_id = await self.library_manager.import_collection(zip_path, collection_name)

                if collection_id:
                    self.console.print(f"[green]✅ Collection '{collection_name}' imported successfully[/green]")
                    self.console.print(f"[blue]📁 Collection ID: {collection_id}[/blue]")
                else:
                    self.console.print(f"[red]❌ Failed to import collection from zip file[/red]")
            else:
                # This is a generic ZIP - use the plugin system
                self.console.print(f"[dim]Detected generic ZIP file - extracting and importing contents[/dim]")
                await self._import_generic_zip(zip_path, collection_name)

        except Exception as e:
            self.console.print(f"[red]❌ Error importing from zip: {e}[/red]")
    
    async def _import_generic_zip(self, zip_path: Path, collection_name: str):
        """Import generic ZIP file by extracting and importing contents"""
        temp_extract_dir = None

        try:
            import shutil

            # Validate ZIP file
            self.console.print(f"[dim]Validating ZIP file...[/dim]")
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Test ZIP integrity
                bad_file = zf.testzip()
                if bad_file:
                    self.console.print(f"[red]❌ Corrupted file in ZIP: {bad_file}[/red]")
                    return

                # Check for dangerous paths (path traversal attack)
                for name in zf.namelist():
                    if name.startswith('/') or '..' in name:
                        self.console.print(f"[red]❌ Suspicious path in ZIP: {name}[/red]")
                        return

                file_count = len(zf.namelist())
                self.console.print(f"[dim]ZIP validated ({file_count} files)[/dim]")

            # Extract to temp directory
            self.console.print(f"[dim]Extracting ZIP file...[/dim]")
            temp_extract_dir = Path(tempfile.mkdtemp(prefix='fichero_zip_import_'))

            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(temp_extract_dir)

            self.console.print(f"[dim]Extracted to: {temp_extract_dir}[/dim]")

            # Find root folder (skip __MACOSX and hidden folders)
            root_folders = [
                d for d in temp_extract_dir.iterdir()
                if d.is_dir() and not d.name.startswith('.') and d.name != '__MACOSX'
            ]

            # If single root folder, use its contents
            if len(root_folders) == 1:
                import_path = root_folders[0]
                self.console.print(f"[dim]Using single root folder: {import_path.name}[/dim]")
            else:
                import_path = temp_extract_dir
                self.console.print(f"[dim]Using extraction root (multiple folders)[/dim]")

            # Create collection
            self.console.print(f"[blue]Creating collection '{collection_name}'...[/blue]")
            collection_id = await self.library_manager.add_collection(
                name=collection_name,
                collection_type="local",
                source_path=str(import_path),
                description=f"Imported from ZIP file: {zip_path.name}"
            )

            if not collection_id:
                self.console.print(f"[red]❌ Failed to create collection[/red]")
                return

            # Import all files based on folder structure
            self.console.print(f"[blue]Importing files...[/blue]")
            stats = await self.library_manager.add_folder_items_to_collection(
                collection_id=collection_id,
                folder_path=str(import_path),
                operation="copy",  # Copy files to library
                recursive=True  # Preserve folder structure
            )

            # Display results
            self.console.print(f"[green]✅ Collection '{collection_name}' imported successfully[/green]")
            self.console.print(f"[blue]📁 Collection ID: {collection_id}[/blue]")
            self.console.print(f"[green]✓ Files imported: {stats.get('added', 0)}[/green]")

            if stats.get("skipped", 0) > 0:
                self.console.print(f"[yellow]⊘ Files skipped: {stats.get('skipped', 0)}[/yellow]")

            if stats.get("errors", 0) > 0:
                self.console.print(f"[red]✗ Errors: {stats.get('errors', 0)}[/red]")

        except Exception as e:
            self.console.print(f"[red]❌ Error importing generic ZIP: {e}[/red]")
            import traceback
            traceback.print_exc()
        finally:
            # Clean up temp extraction directory
            if temp_extract_dir and temp_extract_dir.exists():
                try:
                    shutil.rmtree(temp_extract_dir)
                    self.console.print(f"[dim]Cleaned up temporary files[/dim]")
                except Exception as e:
                    self.console.print(f"[yellow]⚠️  Failed to clean up temp directory: {e}[/yellow]")

    async def _import_from_directory(self, dir_path: Path, collection_name: str, operation: str = "copy"):
        """Import collection from directory with hierarchical structure"""
        try:
            # Add collection to library
            # Use 'local' type for copy operation, 'external' for link operation
            collection_type = "local" if operation == "copy" else "external"

            collection_id = await self.library_manager.add_collection(
                name=collection_name,
                collection_type=collection_type,
                source_path=str(dir_path),
                description=f"Imported from directory ({'copy' if operation == 'copy' else 'link'})"
            )

            if not collection_id:
                self.console.print(f"[red]❌ Failed to add collection to library[/red]")
                return

            # Import all files preserving folder structure
            operation_verb = "Copying" if operation == "copy" else "Linking"
            self.console.print(f"[blue]{operation_verb} files with hierarchical structure...[/blue]")
            stats = await self.library_manager.add_folder_items_to_collection(
                collection_id=collection_id,
                folder_path=str(dir_path),
                operation=operation,
                recursive=True  # Preserve folder structure
            )

            # Display results
            self.console.print(f"[green]✅ Collection '{collection_name}' imported successfully from directory[/green]")
            self.console.print(f"[blue]📁 Collection ID: {collection_id}[/blue]")
            self.console.print(f"[green]✓ Items imported: {stats.get('added', 0)}[/green]")

            if stats.get("skipped", 0) > 0:
                self.console.print(f"[yellow]⊘ Items skipped: {stats.get('skipped', 0)}[/yellow]")

            if stats.get("errors", 0) > 0:
                self.console.print(f"[red]✗ Errors: {stats.get('errors', 0)}[/red]")

        except Exception as e:
            self.console.print(f"[red]❌ Error importing from directory: {e}[/red]")
    
    async def _export_collection(self, collection_id: str, path: Path):
        """Export a collection to zip file with all files and metadata"""
        try:
            # Get collection first to confirm it exists
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return

            # Ensure the output path has .zip extension
            if not path.suffix.lower() == '.zip':
                path = path.with_suffix('.zip')

            # Create parent directories if they don't exist
            path.parent.mkdir(parents=True, exist_ok=True)

            # Export collection using library manager
            self.console.print(f"[blue]📦 Exporting collection '{collection.name}'...[/blue]")

            success = await self.library_manager.export_collection(collection_id, path)

            if success:
                file_size = path.stat().st_size
                size_mb = file_size / (1024 * 1024)

                self.console.print(f"[green]✅ Collection exported successfully[/green]")
                self.console.print(f"[blue]📦 Export path: {path}[/blue]")
                self.console.print(f"[blue]📊 File size: {size_mb:.1f} MB[/blue]")
            else:
                self.console.print(f"[red]❌ Export failed[/red]")

        except Exception as e:
            self.console.print(f"[red]❌ Failed to export collection: {e}[/red]")

    async def _import_zip_url(
        self,
        url: str,
        name: str,
        description: Optional[str],
        timeout: int,
        max_size: int
    ):
        """Import ZIP file from URL"""
        try:
            # Import ZipManager
            from fichero.library.zip_manager import ZipManager

            # Create ZIP manager
            zip_manager = ZipManager(self.library_manager)

            # Start import
            self.console.print(f"[blue]📥 Starting ZIP import from URL...[/blue]")
            self.console.print(f"[dim]URL: {url}[/dim]")
            self.console.print(f"[dim]Collection: {name}[/dim]")
            self.console.print(f"[dim]Timeout: {timeout}s, Max size: {max_size}MB[/dim]")
            self.console.print()

            # Perform import
            result = await zip_manager.import_from_url(
                url=url,
                collection_name=name,
                collection_description=description or f"Imported from {url}",
                timeout=timeout,
                max_zip_size_mb=max_size
            )

            # Display results
            if result.get("success"):
                self.console.print(f"[green]✅ ZIP import completed successfully![/green]")
                self.console.print()
                self.console.print(f"[blue]📁 Collection: {result['collection_name']}[/blue]")
                self.console.print(f"[blue]🆔 Collection ID: {result['collection_id']}[/blue]")
                self.console.print(f"[green]✓ Files imported: {result['files_imported']}[/green]")

                if result.get("files_skipped", 0) > 0:
                    self.console.print(f"[yellow]⊘ Files skipped: {result['files_skipped']}[/yellow]")

                if result.get("errors", 0) > 0:
                    self.console.print(f"[red]✗ Errors: {result['errors']}[/red]")
            else:
                error = result.get("error", "Unknown error")
                self.console.print(f"[red]❌ ZIP import failed: {error}[/red]")

        except Exception as e:
            self.console.print(f"[red]❌ Failed to import ZIP from URL: {e}[/red]")
            import traceback
            traceback.print_exc()

    async def _import_from_url(
        self,
        url: str,
        name: str,
        description: Optional[str],
        timeout: int,
        max_items: int,
        download_mode: Optional[str]
    ):
        """Import content from URL using shared URLImporter"""
        try:
            from fichero.library.url_importer import URLImporter

            # Create URL importer (shared with GUI)
            importer = URLImporter(self.library_manager)

            # Setup progress tracking
            def progress_callback(current: int, total: int, message: str):
                # Calculate percentage
                if total > 0:
                    percentage = (current / total) * 100
                    self.console.print(f"[blue]⏳ [{percentage:.1f}%] {message}[/blue]")
                else:
                    self.console.print(f"[blue]⏳ {message}[/blue]")

            importer.set_progress_callback(progress_callback)

            # Setup cancellation handler (Ctrl+C)
            def signal_handler(sig, frame):
                self.console.print("\n[yellow]⚠️  Cancellation requested...[/yellow]")
                # TODO: Add cancellation support to URLImporter

            original_handler = signal.signal(signal.SIGINT, signal_handler)

            try:
                # Start import
                self.console.print(f"[blue]📥 Starting import from URL...[/blue]")
                self.console.print(f"[dim]URL: {url}[/dim]")
                self.console.print(f"[dim]Collection: {name}[/dim]")
                self.console.print(f"[dim]Press Ctrl+C to cancel[/dim]")
                self.console.print()

                # Perform import using shared code
                result = await importer.import_from_url(
                    url=url,
                    collection_name=name,
                    description=description,
                    timeout=timeout,
                    max_items=max_items,
                    download_mode=download_mode
                )

                # Display results
                self.console.print()
                if result['success']:
                    self.console.print(f"[green]✅ Import completed successfully![/green]")
                    self.console.print()
                    self.console.print(f"[blue]📁 Collection: {result['collection_name']}[/blue]")
                    self.console.print(f"[blue]🆔 Collection ID: {result['collection_id']}[/blue]")
                    self.console.print(f"[green]✓ Files imported: {result['files_imported']}[/green]")

                    if result['files_skipped'] > 0:
                        self.console.print(f"[yellow]⊘ Files skipped: {result['files_skipped']}[/yellow]")

                    if result['errors'] > 0:
                        self.console.print(f"[red]✗ Errors: {result['errors']}[/red]")

                    # Display metadata if available
                    if result['metadata']:
                        self.console.print("\n[bold]Metadata:[/bold]")
                        for key, value in result['metadata'].items():
                            self.console.print(f"  {key}: {value}")
                else:
                    error = result['error_message'] or "Unknown error"
                    self.console.print(f"[red]❌ Import failed: {error}[/red]")

            finally:
                # Restore original signal handler
                signal.signal(signal.SIGINT, original_handler)

        except KeyboardInterrupt:
            self.console.print("\n[yellow]⚠️  Import cancelled by user[/yellow]")
        except Exception as e:
            self.console.print(f"[red]❌ Failed to import from URL: {e}[/red]")
            import traceback
            traceback.print_exc()

    async def _list_plugins(self):
        """List all available import plugins"""
        try:
            # Import plugin system
            from fichero.library.import_plugins import PluginRegistry
            from fichero.library.import_plugins.zip_plugin import ZipImportPlugin
            from fichero.library.import_plugins.box_plugin import BoxImportPlugin
            from fichero.library.import_plugins.eap_plugin import EAPImportPlugin
            from rich.table import Table

            # Create registry and register all plugins
            registry = PluginRegistry()
            registry.register(ZipImportPlugin(self.library_manager))
            registry.register(BoxImportPlugin(self.library_manager))
            registry.register(EAPImportPlugin(self.library_manager))

            # Create table
            table = Table(title="Available Download Plugins")
            table.add_column("Plugin", style="cyan", no_wrap=True)
            table.add_column("Version", style="green")
            table.add_column("Description", style="white")
            table.add_column("Supported Domains", style="yellow")

            # Add rows for each plugin
            for plugin_info in registry.list_plugins():
                domains = ", ".join(plugin_info.get("supported_domains", []))

                table.add_row(
                    plugin_info.get("name", "Unknown"),
                    plugin_info.get("version", "Unknown"),
                    plugin_info.get("description", ""),
                    domains
                )

            self.console.print(table)

            # Show example usage
            self.console.print("\n[bold]Example Usage:[/bold]")
            self.console.print("  fichero library import-url https://example.com/file.zip \"My Collection\"")
            self.console.print("  fichero library import-url https://box.com/s/abc123 \"Box Import\"")
            self.console.print("  fichero library import-url https://eap.bl.uk/project/EAP123 \"EAP Project\" --mode link")

        except Exception as e:
            self.console.print(f"[red]❌ Failed to list plugins: {e}[/red]")
            import traceback
            traceback.print_exc()
