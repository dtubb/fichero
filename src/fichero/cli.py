"""
Fichero CLI Interface - Thin Wrapper (Refactored)

This is now a lightweight wrapper that delegates to organized command modules.
The original 800-line monolithic CLI has been refactored into clean, maintainable modules.

NEW ARCHITECTURE:
- cli.py: Thin wrapper (like app.py)
- cli/cli_app.py: Main CLI application class
- cli/commands/core_commands.py: Core application commands
- cli/commands/backend_commands.py: Backend management commands

This follows the same clean pattern as the GUI architecture.
"""

# Simple import and delegation to the new organized structure
from .cli.cli_app import FicheroCLI

def main():
    """Main CLI entry point"""
    cli = None
    try:
        # Initialize CLI
        cli = FicheroCLI()
        cli.startup()
        
        # Run CLI
        cli.run()
        
    except KeyboardInterrupt:
        print("\n🔄 Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up resources before director shutdown
        try:
            import asyncio
            import gc
            
            # Get the current event loop if it exists
            try:
                loop = asyncio.get_running_loop()
                # Cancel all pending tasks
                pending_tasks = asyncio.all_tasks(loop)
                if pending_tasks:
                    for task in pending_tasks:
                        if not task.done():
                            task.cancel()
                    
                    # Wait briefly for tasks to cancel
                    try:
                        loop.run_until_complete(asyncio.wait(pending_tasks, timeout=1.0))
                    except Exception:
                        pass
                
                # Close the loop if it's not the main loop
                if not loop.is_closed():
                    loop.close()
                    
            except RuntimeError:
                # No running event loop
                pass
            
            # Force garbage collection to clean up any remaining resources
            gc.collect()
            
        except Exception:
            # Ignore cleanup errors
            pass
        
        # Finalize CLI
        if cli:
            try:
                cli.finalize()
            except Exception as e:
                print(f"Warning: Error during cleanup: {e}")

if __name__ == "__main__":
    main() 