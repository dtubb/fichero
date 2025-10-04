"""
Cache Management Commands

Commands for downloading and managing cached URL items.
"""

import asyncio
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, TaskID
from typing import Optional

from .base import BaseLibraryCommands


class CacheCommands(BaseLibraryCommands):
    """Cache management operations for URL items"""

    def register_commands(self, app):
        """Register cache management commands"""

        @app.command(name="download-urls", help="Download and cache all URLs in a collection")
        def download_urls(
            collection_id: str = typer.Argument(..., help="Collection ID"),
            max_concurrent: int = typer.Option(5, "--concurrent", "-c", help="Maximum concurrent downloads"),
            skip_cached: bool = typer.Option(True, "--skip-cached", help="Skip already cached items"),
            timeout: int = typer.Option(30, "--timeout", "-t", help="Download timeout in seconds")
        ):
            """Download and cache all URL items in a collection"""
            asyncio.run(self._download_urls(collection_id, max_concurrent, skip_cached, timeout))

        @app.command(name="download-item", help="Download and cache a single URL item")
        def download_item(
            item_id: str = typer.Argument(..., help="Item ID"),
            timeout: int = typer.Option(30, "--timeout", "-t", help="Download timeout in seconds")
        ):
            """Download and cache a single URL item"""
            asyncio.run(self._download_item(item_id, timeout))

        @app.command(name="cache-info", help="Show cache information and statistics")
        def cache_info(
            collection_id: Optional[str] = typer.Argument(None, help="Optional collection ID to filter by")
        ):
            """Show cache information and statistics"""
            asyncio.run(self._cache_info(collection_id))

        @app.command(name="clear-cache", help="Clear cached files")
        def clear_cache(
            collection_id: Optional[str] = typer.Argument(None, help="Optional collection ID to clear (clears all if omitted)"),
            confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt")
        ):
            """Clear cached files"""
            asyncio.run(self._clear_cache(collection_id, confirm))

    async def _download_urls(self, collection_id: str, max_concurrent: int, skip_cached: bool, timeout: int):
        """Download all URLs in a collection"""
        try:
            # Verify collection exists
            collection = await self.library_manager.get_collection(collection_id)
            if not collection:
                self.console.print(f"[red]Collection not found: {collection_id}[/red]")
                return

            self.console.print(f"[blue]Downloading URLs from collection: {collection.name}[/blue]")

            # Get collection items to count URL items
            items = await self.library_manager.get_collection_items(collection_id)
            url_items = [item for item in items if item.type == "url"]

            if not url_items:
                self.console.print("[yellow]No URL items found in collection[/yellow]")
                return

            self.console.print(f"[blue]Found {len(url_items)} URL items[/blue]")

            # Download with progress tracking
            with Progress() as progress:
                task = progress.add_task("[cyan]Downloading...", total=len(url_items))

                # Track progress
                downloaded = 0
                failed = 0

                for item in url_items:
                    # Check if already cached
                    if skip_cached and item.local_path:
                        progress.advance(task)
                        continue

                    try:
                        success = await self.library_manager.download_url_item(item.id, timeout=timeout)
                        if success:
                            downloaded += 1
                        else:
                            failed += 1
                    except Exception as e:
                        self.console.print(f"[red]Failed to download {item.name}: {e}[/red]")
                        failed += 1

                    progress.advance(task)

            # Show results
            self.console.print(f"[green]✅ Download complete![/green]")
            self.console.print(f"[green]Downloaded: {downloaded}[/green]")
            if failed > 0:
                self.console.print(f"[red]Failed: {failed}[/red]")

            # Show cache info
            cache_info = await self.library_manager.get_cache_info(collection_id)
            self.console.print(f"[blue]Cache size: {cache_info['total_size_mb']} MB[/blue]")

        except Exception as e:
            self.console.print(f"[red]Failed to download URLs: {e}[/red]")

    async def _download_item(self, item_id: str, timeout: int):
        """Download a single URL item"""
        try:
            # Get item info
            item = await self.library_manager.get_item(item_id)
            if not item:
                self.console.print(f"[red]Item not found: {item_id}[/red]")
                return

            if item.type != "url":
                self.console.print(f"[red]Item is not a URL item[/red]")
                return

            self.console.print(f"[blue]Downloading: {item.name}[/blue]")
            self.console.print(f"[blue]URL: {item.source_path}[/blue]")

            # Download
            success = await self.library_manager.download_url_item(item_id, timeout=timeout)

            if success:
                # Get updated item
                item = await self.library_manager.get_item(item_id)
                self.console.print(f"[green]✅ Downloaded successfully![/green]")
                self.console.print(f"[green]Cached at: {item.local_path}[/green]")

                if "file_size" in item.metadata:
                    size_mb = item.metadata["file_size"] / (1024 * 1024)
                    self.console.print(f"[blue]Size: {size_mb:.2f} MB[/blue]")
            else:
                self.console.print(f"[red]Failed to download item[/red]")

        except Exception as e:
            self.console.print(f"[red]Failed to download item: {e}[/red]")

    async def _cache_info(self, collection_id: Optional[str]):
        """Show cache information"""
        try:
            if collection_id:
                # Verify collection exists
                collection = await self.library_manager.get_collection(collection_id)
                if not collection:
                    self.console.print(f"[red]Collection not found: {collection_id}[/red]")
                    return

                self.console.print(f"[blue]Cache info for collection: {collection.name}[/blue]")
            else:
                self.console.print(f"[blue]Global cache information:[/blue]")

            # Get cache info
            cache_info = await self.library_manager.get_cache_info(collection_id)

            # Create table
            table = Table(title="Cache Statistics")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="magenta")

            table.add_row("Total Size (MB)", f"{cache_info['total_size_mb']}")
            table.add_row("Total Size (Bytes)", f"{cache_info['total_size_bytes']:,}")
            table.add_row("Cached Items", f"{cache_info['cached_items']}")
            table.add_row("Total URL Items", f"{cache_info['total_url_items']}")
            table.add_row("Cache Percentage", f"{cache_info['cache_percentage']}%")

            self.console.print(table)

        except Exception as e:
            self.console.print(f"[red]Failed to get cache info: {e}[/red]")

    async def _clear_cache(self, collection_id: Optional[str], confirm: bool):
        """Clear cached files"""
        try:
            if collection_id:
                # Verify collection exists
                collection = await self.library_manager.get_collection(collection_id)
                if not collection:
                    self.console.print(f"[red]Collection not found: {collection_id}[/red]")
                    return

                target = f"collection '{collection.name}'"
            else:
                target = "ALL collections"

            # Get cache info first
            cache_info = await self.library_manager.get_cache_info(collection_id)

            if cache_info['cached_items'] == 0:
                self.console.print("[yellow]No cached items to clear[/yellow]")
                return

            # Confirm
            if not confirm:
                response = typer.prompt(
                    f"Clear cache for {target}? ({cache_info['total_size_mb']} MB, {cache_info['cached_items']} items) [y/N]"
                )
                if response.lower() != 'y':
                    self.console.print("[yellow]Cancelled[/yellow]")
                    return

            # Clear cache
            self.console.print(f"[blue]Clearing cache for {target}...[/blue]")
            deleted_count = await self.library_manager.clear_cache(collection_id)

            self.console.print(f"[green]✅ Cleared {deleted_count} cached files ({cache_info['total_size_mb']} MB)[/green]")

        except Exception as e:
            self.console.print(f"[red]Failed to clear cache: {e}[/red]")
