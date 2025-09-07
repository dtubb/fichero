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
