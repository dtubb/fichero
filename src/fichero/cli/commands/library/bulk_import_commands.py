"""
Bulk Import Commands

Commands for bulk importing from text files containing URLs, URIs, or paths.
"""

import asyncio
import aiohttp
import aiofiles
from pathlib import Path
from typing import List, Optional, Dict, Any
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, TaskID
import time

from .base import BaseLibraryCommands


class BulkImportCommands(BaseLibraryCommands):
    """Bulk import operations from text files"""
    
    def register_commands(self, app):
        """Register bulk import commands"""
        
        @app.command(name="bulk-import", help="Bulk import from text file containing URLs, URIs, or paths")
        def bulk_import(
            text_file: Path = typer.Argument(..., help="Text file containing URLs, URIs, or paths (one per line)"),
            collection_name: str = typer.Argument(..., help="Name for the collection"),
            collection_type: str = typer.Option("hybrid", "--type", "-t", help="Collection type: local, external, url, hybrid"),
            description: str = typer.Option("", "--description", "-d", help="Description for the collection"),
            max_concurrent: int = typer.Option(10, "--concurrent", "-c", help="Maximum concurrent downloads"),
            validate_urls: bool = typer.Option(True, "--validate", help="Validate URLs before adding"),
            skip_duplicates: bool = typer.Option(True, "--skip-duplicates", help="Skip duplicate URLs/paths")
        ):
            """Bulk import from text file containing URLs, URIs, or paths"""
            asyncio.run(self._bulk_import(text_file, collection_name, collection_type, description, max_concurrent, validate_urls, skip_duplicates))
        
        @app.command(name="import-urls", help="Import URLs directly as URL collection (no downloading)")
        def import_urls(
            text_file: Path = typer.Argument(..., help="Text file containing URLs (one per line)"),
            collection_name: str = typer.Argument(..., help="Name for the collection"),
            description: str = typer.Option("", "--description", "-d", help="Description for the collection"),
            validate_urls: bool = typer.Option(True, "--validate", help="Validate URLs before adding")
        ):
            """Import URLs directly as URL collection (no downloading)"""
            asyncio.run(self._import_urls(text_file, collection_name, description, validate_urls))
        
        @app.command(name="import-paths", help="Import local/external paths from text file")
        def import_paths(
            text_file: Path = typer.Argument(..., help="Text file containing paths (one per line)"),
            collection_name: str = typer.Argument(..., help="Name for the collection"),
            collection_type: str = typer.Option("external", "--type", "-t", help="Collection type: local, external"),
            description: str = typer.Option("", "--description", "-d", help="Description for the collection"),
            validate_paths: bool = typer.Option(True, "--validate", help="Validate paths before adding")
        ):
            """Import local/external paths from text file"""
            asyncio.run(self._import_paths(text_file, collection_name, collection_type, description, validate_paths))

        @app.command(name="import-clipboard", help="Import URLs from clipboard (mobile-friendly)")
        def import_clipboard(
            collection_name: str = typer.Argument(..., help="Name for the collection"),
            description: str = typer.Option("", "--description", "-d", help="Description for the collection"),
            validate_urls: bool = typer.Option(True, "--validate", help="Validate URLs before adding")
        ):
            """Import URLs from clipboard - perfect for mobile copy-paste workflow"""
            asyncio.run(self._import_clipboard(collection_name, description, validate_urls))

        @app.command(name="add-urls", help="Interactive URL entry for building collections")
        def add_urls(
            collection_name: str = typer.Argument(..., help="Name for the collection"),
            description: str = typer.Option("", "--description", "-d", help="Description for the collection")
        ):
            """Interactive URL entry - type URLs one by one, press Enter twice to finish"""
            asyncio.run(self._add_urls_interactive(collection_name, description))
    
    async def _bulk_import(self, text_file: Path, collection_name: str, collection_type: str, description: str, max_concurrent: int, validate_urls: bool, skip_duplicates: bool):
        """Bulk import from text file with mixed content types"""
        try:
            # Validate collection type
            valid_types = ["local", "external", "url", "hybrid"]
            if collection_type not in valid_types:
                self.console.print(f"[red]Invalid collection type. Choose from: {', '.join(valid_types)}[/red]")
                return
            
            # Read text file
            if not text_file.exists():
                self.console.print(f"[red]Text file not found: {text_file}[/red]")
                return
            
            async with aiofiles.open(text_file, 'r') as f:
                content = await f.read()
            
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            
            if not lines:
                self.console.print("[yellow]No URLs/paths found in text file[/yellow]")
                return
            
            self.console.print(f"[blue]Found {len(lines)} URLs/paths in text file[/blue]")
            
            # Categorize entries
            urls = []
            paths = []
            
            for line in lines:
                if line.startswith(('http://', 'https://', 'ftp://')):
                    urls.append(line)
                else:
                    paths.append(line)
            
            self.console.print(f"[blue]URLs: {len(urls)}, Paths: {len(paths)}[/blue]")
            
            # Create collection
            collection_id = await self.library_manager.add_collection(
                name=collection_name,
                collection_type=collection_type,
                description=description,
                metadata={
                    'bulk_imported': True,
                    'source_file': str(text_file),
                    'url_count': len(urls),
                    'path_count': len(paths)
                }
            )
            
            if not collection_id:
                self.console.print("[red]Failed to create collection[/red]")
                return
            
            self.console.print(f"[green]✅ Collection '{collection_name}' created with ID: {collection_id}[/green]")
            
            # Process URLs
            if urls:
                await self._process_urls(collection_id, urls, validate_urls, skip_duplicates, max_concurrent)
            
            # Process paths
            if paths:
                await self._process_paths(collection_id, paths, skip_duplicates)
            
            # Show final stats
            items = await self.library_manager.get_collection_items(collection_id)
            self.console.print(f"[green]✅ Bulk import complete! Added {len(items)} items to collection[/green]")
            
        except Exception as e:
            self.console.print(f"[red]Failed to bulk import: {e}[/red]")
    
    async def _import_urls(self, text_file: Path, collection_name: str, description: str, validate_urls: bool):
        """Import URLs directly as URL collection"""
        try:
            # Read text file
            if not text_file.exists():
                self.console.print(f"[red]Text file not found: {text_file}[/red]")
                return
            
            async with aiofiles.open(text_file, 'r') as f:
                content = await f.read()
            
            urls = [line.strip() for line in content.split('\n') if line.strip() and line.startswith(('http://', 'https://', 'ftp://'))]
            
            if not urls:
                self.console.print("[yellow]No valid URLs found in text file[/yellow]")
                return
            
            self.console.print(f"[blue]Found {len(urls)} URLs in text file[/blue]")
            
            # Create URL collection
            collection_id = await self.library_manager.add_collection(
                name=collection_name,
                collection_type="url",
                description=description,
                metadata={
                    'bulk_imported': True,
                    'source_file': str(text_file),
                    'url_count': len(urls)
                }
            )
            
            if not collection_id:
                self.console.print("[red]Failed to create collection[/red]")
                return
            
            self.console.print(f"[green]✅ URL collection '{collection_name}' created with ID: {collection_id}[/green]")
            
            # Add URLs as items
            await self._process_urls(collection_id, urls, validate_urls, True, 10)
            
            # Show final stats
            items = await self.library_manager.get_collection_items(collection_id)
            self.console.print(f"[green]✅ URL import complete! Added {len(items)} URL items[/green]")
            
        except Exception as e:
            self.console.print(f"[red]Failed to import URLs: {e}[/red]")
    
    async def _import_paths(self, text_file: Path, collection_name: str, collection_type: str, description: str, validate_paths: bool):
        """Import paths from text file"""
        try:
            # Validate collection type
            if collection_type not in ["local", "external"]:
                self.console.print("[red]Collection type must be 'local' or 'external' for path import[/red]")
                return
            
            # Read text file
            if not text_file.exists():
                self.console.print(f"[red]Text file not found: {text_file}[/red]")
                return
            
            async with aiofiles.open(text_file, 'r') as f:
                content = await f.read()
            
            paths = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith(('http://', 'https://', 'ftp://'))]
            
            if not paths:
                self.console.print("[yellow]No valid paths found in text file[/yellow]")
                return
            
            self.console.print(f"[blue]Found {len(paths)} paths in text file[/blue]")
            
            # Create collection
            collection_id = await self.library_manager.add_collection(
                name=collection_name,
                collection_type=collection_type,
                description=description,
                metadata={
                    'bulk_imported': True,
                    'source_file': str(text_file),
                    'path_count': len(paths)
                }
            )
            
            if not collection_id:
                self.console.print("[red]Failed to create collection[/red]")
                return
            
            self.console.print(f"[green]✅ Path collection '{collection_name}' created with ID: {collection_id}[/green]")
            
            # Process paths
            await self._process_paths(collection_id, paths, True, validate_paths)
            
            # Show final stats
            items = await self.library_manager.get_collection_items(collection_id)
            self.console.print(f"[green]✅ Path import complete! Added {len(items)} path items[/green]")
            
        except Exception as e:
            self.console.print(f"[red]Failed to import paths: {e}[/red]")
    
    async def _process_urls(self, collection_id: str, urls: List[str], validate_urls: bool, skip_duplicates: bool, max_concurrent: int):
        """Process URLs and add them as items"""
        try:
            seen_urls = set() if skip_duplicates else None
            
            with Progress() as progress:
                task = progress.add_task("[blue]Processing URLs...", total=len(urls))
                
                # Process URLs in batches
                for i in range(0, len(urls), max_concurrent):
                    batch = urls[i:i + max_concurrent]
                    
                    # Validate URLs if requested
                    if validate_urls:
                        valid_urls = await self._validate_urls_batch(batch)
                    else:
                        valid_urls = batch
                    
                    # Add valid URLs as items
                    for url in valid_urls:
                        if skip_duplicates and url in seen_urls:
                            continue
                        
                        if skip_duplicates:
                            seen_urls.add(url)
                        
                        # Add URL as item (no downloading, just reference)
                        await self.library_manager.add_item_to_collection(
                            collection_id=collection_id,
                            item_type="url",
                            source=url,
                            name=Path(url).name or url,
                            operation="link"
                        )
                    
                    progress.update(task, advance=len(batch))
            
            self.console.print(f"[green]✅ Processed {len(urls)} URLs[/green]")
            
        except Exception as e:
            self.console.print(f"[red]Failed to process URLs: {e}[/red]")
    
    async def _process_paths(self, collection_id: str, paths: List[str], skip_duplicates: bool, validate_paths: bool = True):
        """Process paths and add them as items"""
        try:
            seen_paths = set() if skip_duplicates else None
            added_count = 0
            
            for path_str in paths:
                if skip_duplicates and path_str in seen_paths:
                    continue
                
                if skip_duplicates:
                    seen_paths.add(path_str)
                
                # Validate path if requested
                if validate_paths:
                    path_obj = Path(path_str)
                    if not path_obj.exists():
                        self.console.print(f"[yellow]⚠️ Path does not exist: {path_str}[/yellow]")
                        continue
                
                # Determine item type
                path_obj = Path(path_str)
                if path_obj.is_file():
                    item_type = "file"
                elif path_obj.is_dir():
                    item_type = "folder"
                else:
                    item_type = "file"  # Default to file
                
                # Add path as item
                await self.library_manager.add_item_to_collection(
                    collection_id=collection_id,
                    item_type=item_type,
                    source=path_str,
                    name=path_obj.name,
                    operation="link"
                )
                added_count += 1
            
            self.console.print(f"[green]✅ Processed {added_count} paths[/green]")
            
        except Exception as e:
            self.console.print(f"[red]Failed to process paths: {e}[/red]")
    
    async def _validate_urls_batch(self, urls: List[str]) -> List[str]:
        """Validate a batch of URLs"""
        valid_urls = []
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            tasks = []
            for url in urls:
                tasks.append(self._validate_single_url(session, url))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(results):
                if isinstance(result, bool) and result:
                    valid_urls.append(urls[i])
                elif isinstance(result, Exception):
                    self.console.print(f"[yellow]⚠️ URL validation failed: {urls[i]} - {result}[/yellow]")
        
        return valid_urls
    
    async def _validate_single_url(self, session: aiohttp.ClientSession, url: str) -> bool:
        """Validate a single URL"""
        try:
            async with session.head(url) as response:
                return response.status < 400
        except Exception:
            return False

    async def _import_clipboard(self, collection_name: str, description: str, validate_urls: bool):
        """Import URLs from clipboard - mobile-friendly workflow"""
        try:
            import subprocess
            import sys

            self.console.print("[blue]📋 Reading clipboard...[/blue]")

            # Try to read clipboard based on platform
            clipboard_text = None
            try:
                if sys.platform == "darwin":  # macOS
                    result = subprocess.run(['pbpaste'], capture_output=True, text=True)
                    clipboard_text = result.stdout
                elif sys.platform == "linux":  # Linux
                    result = subprocess.run(['xclip', '-selection', 'clipboard', '-o'], capture_output=True, text=True)
                    clipboard_text = result.stdout
                elif sys.platform == "win32":  # Windows
                    import win32clipboard
                    win32clipboard.OpenClipboard()
                    clipboard_text = win32clipboard.GetClipboardData()
                    win32clipboard.CloseClipboard()
            except Exception as e:
                self.console.print(f"[yellow]⚠️ Could not access clipboard: {e}[/yellow]")
                self.console.print("[yellow]Please paste URLs manually or use a text file instead[/yellow]")
                return

            if not clipboard_text or not clipboard_text.strip():
                self.console.print("[red]❌ Clipboard is empty[/red]")
                return

            # Extract URLs from clipboard text
            urls = self._extract_urls_from_text(clipboard_text)

            if not urls:
                self.console.print("[red]❌ No valid URLs found in clipboard[/red]")
                self.console.print("Clipboard content preview:")
                self.console.print(f"[dim]{clipboard_text[:200]}...[/dim]")
                return

            self.console.print(f"[green]✅ Found {len(urls)} URLs in clipboard[/green]")

            # Create collection and add URLs
            await self._import_url_list(urls, collection_name, description, validate_urls)

        except Exception as e:
            self.console.print(f"[red]❌ Error importing from clipboard: {str(e)}[/red]")

    async def _add_urls_interactive(self, collection_name: str, description: str):
        """Interactive URL entry - perfect for building collections one URL at a time"""
        try:
            self.console.print("[blue]🔗 Interactive URL Collection Builder[/blue]")
            self.console.print("Enter URLs one by one. Press Enter on empty line to finish.")
            self.console.print("Type 'quit' or 'exit' to cancel.\n")

            urls = []
            while True:
                try:
                    url = input(f"URL {len(urls) + 1}: ").strip()

                    if not url:  # Empty line = finish
                        break

                    if url.lower() in ['quit', 'exit']:
                        self.console.print("[yellow]Cancelled[/yellow]")
                        return

                    # Validate URL format
                    if self._is_valid_url_format(url):
                        urls.append(url)
                        self.console.print(f"[green]✅ Added: {url}[/green]")
                    else:
                        self.console.print(f"[red]❌ Invalid URL format: {url}[/red]")

                except KeyboardInterrupt:
                    self.console.print("\n[yellow]Cancelled[/yellow]")
                    return

            if not urls:
                self.console.print("[yellow]No URLs entered[/yellow]")
                return

            self.console.print(f"\n[blue]📝 Collected {len(urls)} URLs[/blue]")

            # Create collection and add URLs
            await self._import_url_list(urls, collection_name, description, validate_urls=True)

        except Exception as e:
            self.console.print(f"[red]❌ Error in interactive mode: {str(e)}[/red]")

    def _extract_urls_from_text(self, text: str) -> List[str]:
        """Extract URLs from mixed text content"""
        import re

        if not text:
            return []

        # URL pattern that captures various formats
        url_pattern = re.compile(
            r'https?://[^\s<>"\']+',
            re.IGNORECASE
        )

        urls = []
        lines = text.strip().split('\n')

        for line in lines:
            line = line.strip()

            # Direct URL check
            if self._is_valid_url_format(line):
                urls.append(line)
            else:
                # Extract URLs from mixed content
                found_urls = url_pattern.findall(line)
                for url in found_urls:
                    if self._is_valid_url_format(url):
                        urls.append(url)

        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)

        return unique_urls

    def _is_valid_url_format(self, url: str) -> bool:
        """Quick URL format validation"""
        import re
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return bool(url_pattern.match(url))

    async def _import_url_list(self, urls: List[str], collection_name: str, description: str, validate_urls: bool):
        """Common method to import a list of URLs"""
        try:
            # Create collection
            from fichero.library.models import Collection
            collection = Collection(
                name=collection_name,
                type="url",
                metadata={"description": description, "import_type": "url_references"}
            )

            collection_id = await self.library_manager.add_collection(collection)
            self.console.print(f"[green]✅ Created collection: {collection_name}[/green]")

            # Validate URLs if requested
            if validate_urls:
                self.console.print("[blue]🔍 Validating URLs...[/blue]")
                urls = await self._validate_urls(urls)

            # Add URLs to collection
            added_count = 0
            with Progress() as progress:
                task = progress.add_task("Adding URLs...", total=len(urls))

                for i, url in enumerate(urls, 1):
                    try:
                        # Generate a meaningful name from URL
                        name = self._generate_url_name(url, i)

                        await self.library_manager.add_item_to_collection(
                            collection_id=collection_id,
                            item_type="url",
                            source=url,
                            name=name,
                            operation="link"  # Reference only, no downloading
                        )
                        added_count += 1
                        progress.update(task, advance=1)

                    except Exception as e:
                        self.console.print(f"[red]❌ Failed to add {url}: {str(e)}[/red]")

            self.console.print(f"[green]✅ Successfully added {added_count}/{len(urls)} URLs as references[/green]")
            self.console.print(f"[blue]📚 Collection '{collection_name}' ready for browsing[/blue]")

        except Exception as e:
            self.console.print(f"[red]❌ Error importing URLs: {str(e)}[/red]")

    def _generate_url_name(self, url: str, index: int) -> str:
        """Generate a meaningful name for a URL"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)

            # Try to extract meaningful part from path
            path_parts = [p for p in parsed.path.split('/') if p]
            if path_parts:
                name = path_parts[-1]
                # Remove file extension if present
                if '.' in name:
                    name = name.rsplit('.', 1)[0]
                if name:
                    return f"{name.replace('_', ' ').replace('-', ' ').title()}"

            # Fallback to domain + index
            domain = parsed.netloc or parsed.path
            return f"{domain.replace('www.', '')} - Item {index:03d}"

        except Exception:
            return f"URL Reference {index:03d}"
