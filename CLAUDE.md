# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ✅ Director-Library Integration Status

**Status: FULLY FUNCTIONAL** (as of October 5, 2025)

The Fichero Director (workflow processing) and Library (collection management) are successfully integrated and working. See `DIRECTOR_INTEGRATION.md` for complete documentation.

**Quick Start:**
```bash
# Direct processing
briefcase dev -- process <input> --output <output> --plan "Transcribir y Catalogar" --workflow "Catalogue"

# Library processing
briefcase dev -- library add "Collection Name" --type external --source /path/to/source
briefcase dev -- library add-item <collection_id> folder /path/to/folder
briefcase dev -- library process <collection_id> --plan "Transcribir y Catalogar" --workflow "Catalogue"
```

**Key Components:**
- ✅ All 94 import errors fixed (tools + utils)
- ✅ Toga packages aligned at 0.5.2
- ✅ Director initialization working
- ✅ Workflows executing correctly
- ✅ Library-Director bridge functional
- ✅ 37 unit tests created

## Development Commands

### Running the Application

**GUI Mode (Recommended):**
```bash
# Using Briefcase for development (recommended for testing)
briefcase dev

# Direct GUI launch (alternative)
python -m src/fichero
```

**Desktop vs Mobile UI Testing:**
```bash
# Desktop UI mode
FORCE_MOBILE_UI=false TOGA_BACKEND=toga_cocoa briefcase dev

# Mobile UI mode (for testing mobile layout on desktop)
FORCE_MOBILE_UI=true TOGA_BACKEND=toga_cocoa briefcase dev
```

**iOS Simulator Testing:**
```bash
# Build and run iOS simulator
FORCE_MOBILE_UI=true briefcase build iOS -u
FORCE_MOBILE_UI=true briefcase run iOS -d "DEVICE_UUID"

# Auto-detect iOS device and run
DEVICE_UUID=$(xcrun simctl list devices available | grep "iPhone" | head -1 | grep -o '[A-F0-9-]\{36\}')
FORCE_MOBILE_UI=true briefcase run iOS -d "$DEVICE_UUID"
```

**CLI Mode:**
```bash
# Using Briefcase (recommended)
briefcase dev -- --help                    # Show all commands
briefcase dev -- process-folders INPUT OUTPUT    # Process documents
briefcase dev -- prepare INPUT OUTPUT      # Prepare folders only
briefcase dev -- worker-status            # Check worker status
briefcase dev -- example                  # Show usage examples

# Direct CLI (alternative)
cd src
python -m fichero --help
python -m fichero process-folders INPUT OUTPUT
python -m fichero prepare INPUT OUTPUT
python -m fichero worker-status
python -m fichero example
```

**Parallel Testing:**
```bash
# Run all modes simultaneously (desktop, mobile, iOS, CLI)
./run_parallel_testing.sh

# Run individual modes
./run_parallel_testing.sh desktop    # Desktop UI only
./run_parallel_testing.sh mobile     # Desktop mobile UI only
./run_parallel_testing.sh ios        # iOS simulator only
./run_parallel_testing.sh cli        # CLI testing only
```

### Building and Distribution

```bash
# Create native app bundle
briefcase create

# Build for distribution
briefcase build

# Create installer package
briefcase package
```

### Dependencies and Environment

```bash
# Install system dependencies (macOS)
brew install poppler libjxl libheif libraw exiftool

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# For BeeWare GUI development
pip install briefcase
```

## Architecture Overview

Fichero is a cross-platform document processing application built with BeeWare/Toga. It processes archival materials through image enhancement, AI transcription, and Word document generation.

### Architecture Refactor Documentation

**Navigation System Refactor** - Comprehensive documentation for the ongoing UI architecture improvements:

- **Main Plan**: `docs/architecture/NAVIGATION_REFACTOR_PLAN.md` - Complete 8-week refactor plan with all phases
- **List Widget Architecture**: `docs/architecture/LIST_WIDGET_ARCHITECTURE.md` - Platform-adaptive list widget with renderer system
- **Progress Tracking**: `docs/architecture/navigation_refactor/PROGRESS_TRACKER.md` - Session-by-session progress updates

Key components being refactored:
- ListWidget (platform-adaptive Table/DetailedList/Tree abstraction)
- ResizableCanvas (drag handles for pane resizing)
- Base View Interface (unified view management)
- Focus Border System (consistent focus indicators)
- Navigation State Management (centralized navigation tracking)

### Core Architecture Layers

**Application Layer:**
- `src/fichero/app.py` - Main GUI application using Toga framework
- `src/fichero/cli/` - Command-line interface
- Platform-specific builds via BeeWare Briefcase (macOS, Windows, Linux, iOS, Android)

**Processing Director System:**
- `src/fichero/director/` - Orchestrates all document processing workflows
- `coordinator.py` - Main workflow coordination
- `folder_processor.py` - Handles folder-based processing
- `backends/` - Pluggable backend system (Python, Celery)
- `monitoring/` - Task monitoring and progress tracking

**Document Processing Tools:**
- `src/fichero/tools/` - Individual processing steps (crop, enhance, transcribe, etc.)
- Tools are chained together via YAML workflow configurations
- Each tool is self-contained and can run independently

**Library Management:**
- `src/fichero/library/` - Collection and document management system
- `library_manager.py` - Main library orchestrator
- `models.py` - Collection and document data models
- `storage.py` - SQLite-based storage layer

**Configuration System:**
- `src/fichero/config/` - Settings, plans, and prompts management
- YAML-based configuration files for workflows and AI prompts
- Multi-language support via gettext

**UI Framework:**
- `src/fichero/windows/` - Window management system
- `src/fichero/shared/` - Shared UI components (toolbars, views)
- Cross-platform responsive design (desktop three-pane, mobile single-pane)

**macOS Native Toolbar System:**
- `src/fichero/shared/commands/mac_toolbar_manager.py` - NSToolbar integration using Rubicon-ObjC
- `src/fichero/shared/commands/command_manager.py` - Unified FicheroCommand system
- Commands declared once work in both menus and toolbar
- NSToolbar features: dropdown menus, SF Symbols, PNG icons, customization, autosave
- Explicit toolbar layout defined in `toolbarDefaultItemIdentifiers_`
- Icon priority: `toolbar_icon` (SF Symbol) → `icon` (PNG file path)
- Set `toolbar_icon=None` to force PNG icon usage instead of SF Symbols

**Toolbar Button Order (November 2025):**
```
[Library] [Collection] [New Collection] [Import ▾] [FlexSpace] [Settings] [Show Inspector] [Process] [Adjust]
```

Key toolbar commands:
- `view.toggle_sidebar` - Library toggle (navigational, left of title)
- `view.toggle_collection` - Collection toggle (PNG: `list.bullet.rectangle@10x.png`)
- `library.new_collection` - New Collection button
- `collection.import` - Import dropdown menu (PNG: `import.png`, `item_type='menu'`)
- `library.settings` - Settings button
- `library.inspector` - Show Inspector (desktop), `library.show_inspector` (mobile only)
- `collection.process` - Process button (PNG: `sparkle@10x.png`)
- `view.toggle_inspector` - Adjust toggle (right sidebar)

### Processing Workflow

1. **Input**: Users select folders containing documents (JPG, PDF, TIFF)
2. **Enhancement**: Images are cropped, contrast-enhanced, backgrounds removed
3. **Transcription**: AI models (Qwen Max, LM Studio) extract text
4. **Output**: Word documents with side-by-side image/text layout

### Platform Support

- **Desktop**: macOS, Windows, Linux (three-pane layout)
- **Mobile**: iOS, Android (single-pane mobile-responsive layout)
- **CLI**: Full command-line interface for automation

### Key Dependencies

- **BeeWare/Toga**: Cross-platform GUI framework
- **OpenAI/DashScope**: AI transcription services
- **Pillow**: Image processing
- **python-docx**: Word document generation
- **SQLite**: Local data storage

### Configuration Files

- `pyproject.toml` - BeeWare project configuration with platform-specific dependencies
- `src/fichero/resources/plans/` - YAML workflow definitions
- `src/fichero/resources/prompts/` - AI prompt templates
- `.env` - API keys (DASHSCOPE_API_KEY for Alibaba services)

### Testing

```bash
# Run tests from project root
python -m pytest tests/

# Test specific components
python -m pytest tests/test_library_core.py

# Parallel testing (all platforms)
./run_parallel_testing.sh

# Individual platform testing
./run_parallel_testing.sh desktop
./run_parallel_testing.sh mobile
./run_parallel_testing.sh ios
./run_parallel_testing.sh cli
```

### Common Development Patterns

- GUI and CLI share the same core systems via `app_initializer.py`
- Mobile/desktop UI differences handled by responsive layout system
- Error handling centralized in `core/error_handler.py`
- Internationalization via gettext with resource files in `resources/locale/`
- All file operations go through path validation and security checks

### Toga Styling Guidelines

**IMPORTANT**: When working with Toga styles, be aware of these key changes:

- **`Pack.padding` is DEPRECATED**: Use `Pack.margin` instead
- **Directional properties**: Use `margin_top`, `margin_bottom`, `margin_left`, `margin_right` instead of `padding_*`
- **Tuple format**: `margin=(top, right, bottom, left)` or `margin=(vertical, horizontal)`

**Common fixes needed:**
```python
# OLD (deprecated, causes crashes):
style=Pack(padding=(5, 10))
style=Pack(padding_right=10)

# NEW (correct):
style=Pack(margin=(5, 10))
style=Pack(margin_right=10)
```

Reference: Toga manuals are available in `/toga manuals/` directory.

### Environment Variables

- `FORCE_MOBILE_UI=true` - Force mobile UI layout on desktop
- `FORCE_MOBILE_UI=false` - Force desktop UI layout
- `TOGA_BACKEND=toga_cocoa` - Use Cocoa backend on macOS
- `DASHSCOPE_API_KEY` - API key for Alibaba Cloud services