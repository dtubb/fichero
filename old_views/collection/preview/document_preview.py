"""
Document Preview Component

Document preview for Word, PDF, and other document formats.
Uses WebView for rendering and provides document navigation.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from typing import Optional, Callable
from pathlib import Path
import mimetypes
import subprocess
import tempfile
import os

logger = logging.getLogger(__name__)


class DocumentPreview:
    """Document preview with WebView rendering"""
    
    def __init__(self, presenter, width=300, is_mobile=False):
        self.presenter = presenter
        self.width = width
        self.is_mobile = is_mobile
        
        # Document state
        self.current_file_path: Optional[Path] = None
        self.document_type: str = ""
        self.temp_html_path: Optional[Path] = None
        
        # UI components
        self.container = None
        self.header = None
        self.webview = None
        self.toolbar = None
        self.open_button = None
        self.export_button = None
        
        # Callbacks
        self.on_document_open: Optional[Callable[[Path], None]] = None
        
        self._create_ui()
    
    def _create_ui(self):
        """Create document preview UI"""
        # Main container
        style = Pack(direction=COLUMN, margin=10)
        if self.is_mobile:
            # Mobile: use specified width or full width
            if self.width is not None:
                style.width = self.width
            else:
                style.flex = 1  # Full width for mobile
        else:
            # Desktop: always use full width
            style.flex = 1
        self.container = toga.Box(style=style)
        
        # Header with document info
        self.header = toga.Label(
            "Document Preview",
            style=Pack(font_size=12, font_weight="bold", margin_bottom=5)
        )
        self.container.add(self.header)
        
        # Toolbar for actions
        self.toolbar = toga.Box(style=Pack(direction=ROW, margin_bottom=5))
        
        self.open_button = toga.Button(
            "Open",
            on_press=self._open_document,
            style=Pack(margin_right=5)
        )
        self.toolbar.add(self.open_button)
        
        self.export_button = toga.Button(
            "Export",
            on_press=self._export_document,
            style=Pack(margin_right=5)
        )
        self.toolbar.add(self.export_button)
        
        self.container.add(self.toolbar)
        
        # Document display area (WebView)
        self.webview = toga.WebView(
            style=Pack(flex=1)
        )
        self.container.add(self.webview)
        
        # Show placeholder
        self._show_placeholder()
    
    def _show_placeholder(self):
        """Show placeholder content"""
        placeholder_html = """
        <html>
        <head>
            <style>
                body { 
                    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    background: #f5f5f5;
                    color: #666;
                }
                .placeholder {
                    text-align: center;
                    padding: 20px;
                }
            </style>
        </head>
        <body>
            <div class="placeholder">
                <h3>Document Preview</h3>
                <p>Select a document to preview</p>
            </div>
        </body>
        </html>
        """
        self.webview.set_content("", placeholder_html)
        self.open_button.enabled = False
        self.export_button.enabled = False
    
    def show_document(self, file_path: Path):
        """Show document preview"""
        try:
            self.current_file_path = file_path
            self.document_type = self._get_document_type(file_path)
            
            # Update header
            self.header.text = f"Document: {file_path.name}"
            
            # Enable buttons
            self.open_button.enabled = True
            self.export_button.enabled = True
            
            # Convert document to HTML for preview
            html_content = self._convert_document_to_html(file_path)
            if html_content:
                self.webview.set_content("", html_content)
            else:
                self._show_unsupported_document(file_path)
            
            logger.info(f"Showing document: {file_path.name} ({self.document_type})")
            
        except Exception as e:
            logger.error(f"Failed to show document: {e}")
            self._show_error(f"Failed to load document: {file_path.name}")
    
    def _get_document_type(self, file_path: Path) -> str:
        """Get document type based on file extension"""
        extension = file_path.suffix.lower()
        
        if extension in {'.pdf'}:
            return "pdf"
        elif extension in {'.doc', '.docx'}:
            return "word"
        elif extension in {'.xls', '.xlsx'}:
            return "excel"
        elif extension in {'.ppt', '.pptx'}:
            return "powerpoint"
        elif extension in {'.txt', '.md', '.rtf'}:
            return "text"
        else:
            return "unknown"
    
    def _convert_document_to_html(self, file_path: Path) -> Optional[str]:
        """Convert document to HTML for preview"""
        try:
            doc_type = self._get_document_type(file_path)
            
            if doc_type == "pdf":
                return self._convert_pdf_to_html(file_path)
            elif doc_type == "word":
                return self._convert_word_to_html(file_path)
            elif doc_type == "text":
                return self._convert_text_to_html(file_path)
            else:
                return None
                
        except Exception as e:
            logger.error(f"Failed to convert document to HTML: {e}")
            return None
    
    def _convert_pdf_to_html(self, file_path: Path) -> Optional[str]:
        """Convert PDF to HTML using pandoc"""
        try:
            # Use pandoc to convert PDF to HTML
            result = subprocess.run([
                'pandoc', 
                str(file_path),
                '-f', 'pdf',
                '-t', 'html',
                '--standalone',
                '--metadata', 'title=PDF Preview'
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return result.stdout
            else:
                logger.warning(f"Pandoc conversion failed: {result.stderr}")
                return self._create_pdf_fallback_html(file_path)
                
        except subprocess.TimeoutExpired:
            logger.warning("PDF conversion timed out")
            return self._create_pdf_fallback_html(file_path)
        except FileNotFoundError:
            logger.warning("Pandoc not found, using fallback")
            return self._create_pdf_fallback_html(file_path)
        except Exception as e:
            logger.error(f"PDF conversion error: {e}")
            return self._create_pdf_fallback_html(file_path)
    
    def _convert_word_to_html(self, file_path: Path) -> Optional[str]:
        """Convert Word document to HTML using pandoc"""
        try:
            # Use pandoc to convert Word to HTML
            result = subprocess.run([
                'pandoc', 
                str(file_path),
                '-f', 'docx',
                '-t', 'html',
                '--standalone',
                '--metadata', 'title=Word Document Preview'
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return result.stdout
            else:
                logger.warning(f"Pandoc conversion failed: {result.stderr}")
                return self._create_word_fallback_html(file_path)
                
        except subprocess.TimeoutExpired:
            logger.warning("Word conversion timed out")
            return self._create_word_fallback_html(file_path)
        except FileNotFoundError:
            logger.warning("Pandoc not found, using fallback")
            return self._create_word_fallback_html(file_path)
        except Exception as e:
            logger.error(f"Word conversion error: {e}")
            return self._create_word_fallback_html(file_path)
    
    def _convert_text_to_html(self, file_path: Path) -> str:
        """Convert text file to HTML"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Escape HTML and create formatted content
            import html
            escaped_content = html.escape(content)
            
            html_content = f"""
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                        line-height: 1.6;
                        margin: 20px;
                        background: #fff;
                        color: #333;
                    }}
                    pre {{
                        white-space: pre-wrap;
                        word-wrap: break-word;
                        background: #f8f9fa;
                        padding: 15px;
                        border-radius: 5px;
                        border: 1px solid #e9ecef;
                    }}
                </style>
            </head>
            <body>
                <h2>{file_path.name}</h2>
                <pre>{escaped_content}</pre>
            </body>
            </html>
            """
            
            return html_content
            
        except Exception as e:
            logger.error(f"Text conversion error: {e}")
            return self._create_error_html(f"Failed to load text file: {file_path.name}")
    
    def _create_pdf_fallback_html(self, file_path: Path) -> str:
        """Create fallback HTML for PDF when conversion fails"""
        return f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    background: #f5f5f5;
                    color: #666;
                }}
                .fallback {{
                    text-align: center;
                    padding: 20px;
                }}
                .icon {{
                    font-size: 48px;
                    margin-bottom: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="fallback">
                <div class="icon">📄</div>
                <h3>PDF Document</h3>
                <p>{file_path.name}</p>
                <p>Use the "Open" button to view in your default PDF viewer</p>
            </div>
        </body>
        </html>
        """
    
    def _create_word_fallback_html(self, file_path: Path) -> str:
        """Create fallback HTML for Word documents when conversion fails"""
        return f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    background: #f5f5f5;
                    color: #666;
                }}
                .fallback {{
                    text-align: center;
                    padding: 20px;
                }}
                .icon {{
                    font-size: 48px;
                    margin-bottom: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="fallback">
                <div class="icon">📝</div>
                <h3>Word Document</h3>
                <p>{file_path.name}</p>
                <p>Use the "Open" button to view in your default Word application</p>
            </div>
        </body>
        </html>
        """
    
    def _show_unsupported_document(self, file_path: Path):
        """Show message for unsupported document types"""
        html_content = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    background: #f5f5f5;
                    color: #666;
                }}
                .unsupported {{
                    text-align: center;
                    padding: 20px;
                }}
                .icon {{
                    font-size: 48px;
                    margin-bottom: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="unsupported">
                <div class="icon">📄</div>
                <h3>Unsupported Document</h3>
                <p>{file_path.name}</p>
                <p>This document type is not supported for preview.</p>
                <p>Use the "Open" button to view in your default application.</p>
            </div>
        </body>
        </html>
        """
        self.webview.set_content("", html_content)
    
    def _create_error_html(self, message: str) -> str:
        """Create error HTML"""
        return f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    background: #f5f5f5;
                    color: #ff6b6b;
                }}
                .error {{
                    text-align: center;
                    padding: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="error">
                <h3>Error</h3>
                <p>{message}</p>
            </div>
        </body>
        </html>
        """
    
    def _show_error(self, message: str):
        """Show error message"""
        error_html = self._create_error_html(message)
        self.webview.set_content("", error_html)
        self.open_button.enabled = False
        self.export_button.enabled = False
    
    def _open_document(self, widget):
        """Open document in default application"""
        try:
            if self.current_file_path and self.current_file_path.exists():
                # Use system default application
                if os.name == 'nt':  # Windows
                    os.startfile(str(self.current_file_path))
                elif os.name == 'posix':  # macOS and Linux
                    subprocess.run(['open', str(self.current_file_path)], check=True)
                
                logger.info(f"Opened document: {self.current_file_path}")
                
                # Notify callback
                if self.on_document_open:
                    self.on_document_open(self.current_file_path)
            else:
                logger.warning("No document to open")
                
        except Exception as e:
            logger.error(f"Failed to open document: {e}")
    
    def _export_document(self, widget):
        """Export document (placeholder for future implementation)"""
        try:
            if self.current_file_path:
                # Show save dialog
                dialog = toga.SaveFileDialog(
                    title="Export Document",
                    suggested_filename=self.current_file_path.stem + "_export" + self.current_file_path.suffix
                )
                
                # Note: This would need to be implemented with proper file handling
                logger.info(f"Export requested for: {self.current_file_path}")
            else:
                logger.warning("No document to export")
                
        except Exception as e:
            logger.error(f"Failed to export document: {e}")
    
    def clear(self):
        """Clear the preview"""
        self.current_file_path = None
        self.document_type = ""
        
        # Clean up temp files
        if self.temp_html_path and self.temp_html_path.exists():
            try:
                self.temp_html_path.unlink()
            except Exception as e:
                logger.debug(f"Failed to clean up temp file: {e}")
        
        self._show_placeholder()
    
    def get_current_document(self) -> Optional[Path]:
        """Get current document path"""
        return self.current_file_path
    
    def get_document_type(self) -> str:
        """Get current document type"""
        return self.document_type 