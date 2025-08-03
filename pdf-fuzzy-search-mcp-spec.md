# PDF Fuzzy Search MCP Server Specification

## Overview

This MCP server provides fuzzy search capabilities for PDFs and other document formats supported by ripgrep-all (rga), along with specific page extraction and conversion features. The server integrates three powerful tools:

1. **ripgrep-all (rga)** - For searching through various file formats including PDFs, Office documents, archives, and more
2. **fzf** - For fuzzy finding and interactive selection
3. **pdfminer.six (pdf2txt.py) + pandoc** - For extracting specific pages from PDFs and converting to markdown

## Core Features

### 1. Fuzzy Search Across Document Types
- Search through PDFs, DOCX, EPUB, archives, databases, and more
- Interactive fuzzy search using fzf
- Preview search results with context
- Support for nested documents (e.g., PDFs inside ZIP files)

### 2. PDF Page Extraction
- Extract specific pages from PDF files
- Convert extracted pages to markdown format
- Preserve formatting and structure during conversion

## MCP Server Architecture

### Server Name
`pdf-fuzzy-search`

### Tools

#### 1. `fuzzy_search`
Performs fuzzy search across documents using ripgrep-all and fzf.

**Parameters:**
- `query` (string, optional): Initial search query
- `path` (string, optional): Directory or file to search in (default: current directory)
- `file_types` (array, optional): Limit search to specific file types (e.g., ["pdf", "docx"])
- `interactive` (boolean, optional): Enable interactive fuzzy search with fzf (default: true)
- `preview` (boolean, optional): Show preview of matches (default: true)
- `max_results` (integer, optional): Maximum number of results to return (default: 50)

**Returns:**
```json
{
  "matches": [
    {
      "file": "path/to/document.pdf",
      "line_number": 42,
      "content": "matched content with context",
      "page": 5,  // for PDFs
      "adapter": "pdf"  // which rga adapter was used
    }
  ],
  "total_matches": 123
}
```

**Example Usage:**
```
"use fuzzy search mcp on file.pdf" -> 
fuzzy_search(path="file.pdf", interactive=true)
```

#### 2. `extract_pdf_page`
Extracts specific pages from a PDF and converts them to markdown.

**Parameters:**
- `file` (string, required): Path to the PDF file
- `pages` (array of integers, required): Page numbers to extract (1-indexed)
- `output_format` (string, optional): Output format (default: "markdown")
  - Supported: "markdown", "html", "plain", "latex", "docx"
- `preserve_layout` (boolean, optional): Try to preserve layout (default: false)

**Returns:**
```json
{
  "content": "# Page 5\n\nExtracted markdown content...",
  "pages_extracted": [5],
  "format": "markdown"
}
```

**Example Usage:**
```
"get page 5 from file.pdf" ->
extract_pdf_page(file="file.pdf", pages=[5])
```

#### 3. `search_in_file`
Search for specific content within a file using ripgrep-all.

**Parameters:**
- `file` (string, required): Path to the file
- `pattern` (string, required): Search pattern (regex supported)
- `context_lines` (integer, optional): Number of context lines (default: 2)
- `case_sensitive` (boolean, optional): Case-sensitive search (default: false)

**Returns:**
```json
{
  "matches": [
    {
      "line_number": 10,
      "content": "matched line",
      "context_before": ["line 8", "line 9"],
      "context_after": ["line 11", "line 12"]
    }
  ]
}
```

#### 4. `list_searchable_files`
Lists all files that can be searched by ripgrep-all in a directory.

**Parameters:**
- `path` (string, optional): Directory path (default: current directory)
- `file_types` (array, optional): Filter by file types

**Returns:**
```json
{
  "files": [
    {
      "path": "document.pdf",
      "type": "pdf",
      "size": 1048576,
      "adapter": "pdftotext"
    }
  ]
}
```

### Resources

#### 1. `adapters`
Information about available ripgrep-all adapters.

**URI:** `adapters://list`

**Returns:**
```json
{
  "adapters": [
    {
      "name": "pdf",
      "description": "PDF files using pdftotext",
      "extensions": ["pdf"],
      "binary": "pdftotext"
    }
  ]
}
```

#### 2. `config`
Server configuration and custom adapters.

**URI:** `config://settings`

## Implementation Details

### Dependencies

1. **System Dependencies:**
   - `ripgrep-all` (rga) - Must be installed
   - `fzf` - For interactive fuzzy search
   - `pdf2txt.py` from pdfminer.six
   - `pandoc` - For format conversion
   - `pdftotext` (poppler-utils) - Used by rga for PDFs

2. **Python Dependencies:**
   - `mcp` - Model Context Protocol SDK
   - `asyncio` - For async operations
   - `subprocess` - For running external commands
   - `pdfminer.six` - For pdf2txt.py

### Core Implementation Structure

```python
import asyncio
import subprocess
from typing import List, Dict, Any, Optional
from mcp.server import Server
from mcp.types import Tool, Resource

class PDFFuzzySearchServer:
    def __init__(self):
        self.server = Server("pdf-fuzzy-search")
        self._register_tools()
        self._register_resources()
    
    async def fuzzy_search(self, query: Optional[str] = None, 
                          path: Optional[str] = ".", 
                          file_types: Optional[List[str]] = None,
                          interactive: bool = True,
                          preview: bool = True,
                          max_results: int = 50) -> Dict[str, Any]:
        """Implement fuzzy search using rga and fzf"""
        # Build rga command
        cmd = ["rga", "--json"]
        if file_types:
            cmd.extend(["--type", ",".join(file_types)])
        
        if interactive and self._is_interactive():
            return await self._interactive_search(cmd, query, preview)
        else:
            return await self._batch_search(cmd, query, max_results)
    
    async def extract_pdf_page(self, file: str, 
                              pages: List[int],
                              output_format: str = "markdown") -> Dict[str, Any]:
        """Extract specific pages from PDF"""
        # Use pdf2txt.py to extract pages as HTML
        pdf_cmd = [
            "pdf2txt.py", 
            "-t", "html",
            "--page-numbers", *[str(p) for p in pages],
            file
        ]
        
        # Pipe to pandoc for conversion
        pandoc_format = self._get_pandoc_format(output_format)
        pandoc_cmd = [
            "pandoc",
            "--from=html",
            f"--to={pandoc_format}",
            "--wrap=none"
        ]
        
        # Execute pipeline
        pdf_process = await asyncio.create_subprocess_exec(
            *pdf_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        pandoc_process = await asyncio.create_subprocess_exec(
            *pandoc_cmd,
            stdin=pdf_process.stdout,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        content, _ = await pandoc_process.communicate()
        return {
            "content": content.decode('utf-8'),
            "pages_extracted": pages,
            "format": output_format
        }
```

### Configuration File

The server will support a configuration file for custom adapters and settings:

```json
{
  "pdf_fuzzy_search": {
    "cache_enabled": true,
    "cache_dir": "~/.cache/pdf-fuzzy-search",
    "default_preview_lines": 5,
    "custom_adapters": [
      {
        "name": "custom_pdf",
        "extensions": ["pdf"],
        "command": "custom-pdf-extractor",
        "args": ["--extract", "$input"]
      }
    ]
  }
}
```

## Usage Examples

### 1. Interactive Fuzzy Search
```python
# LLM interprets: "use fuzzy search mcp on project docs"
result = await server.call_tool("fuzzy_search", {
    "path": "./docs",
    "interactive": True
})
```

### 2. Extract Specific PDF Pages
```python
# LLM interprets: "get page 5 from report.pdf"
result = await server.call_tool("extract_pdf_page", {
    "file": "report.pdf",
    "pages": [5]
})
```

### 3. Search in Specific File
```python
# LLM interprets: "find 'revenue' in financial.pdf"
result = await server.call_tool("search_in_file", {
    "file": "financial.pdf",
    "pattern": "revenue",
    "context_lines": 3
})
```

## Error Handling

The server will handle common errors gracefully:

1. **Missing Dependencies**: Clear error messages if rga, fzf, pdf2txt.py, or pandoc are not installed
2. **File Not Found**: Return appropriate error for non-existent files
3. **Invalid PDF**: Handle corrupted or encrypted PDFs
4. **No Matches**: Return empty results with appropriate message
5. **Interactive Mode Unavailable**: Fall back to batch mode in non-TTY environments

## Performance Considerations

1. **Caching**: Leverage rga's built-in caching for repeated searches
2. **Streaming**: Use async subprocess for large file processing
3. **Parallel Processing**: Support concurrent search operations
4. **Resource Limits**: Implement timeouts and memory limits for large documents

## Security Considerations

1. **Input Validation**: Sanitize file paths and search patterns
2. **Command Injection**: Use subprocess with arrays, not shell=True
3. **File Access**: Respect file system permissions
4. **Resource Limits**: Prevent DoS through large file processing

## Future Enhancements

1. **OCR Support**: Integrate with Tesseract for scanned PDFs
2. **Cloud Storage**: Support searching in S3, Google Drive, etc.
3. **Incremental Indexing**: Build persistent search index
4. **AI-Enhanced Search**: Use embeddings for semantic search
5. **Multi-language Support**: Better handling of non-English documents

## Testing Strategy

1. **Unit Tests**: Test individual tool functions
2. **Integration Tests**: Test full pipelines with real files
3. **Performance Tests**: Benchmark with large documents
4. **Compatibility Tests**: Test across different OS and Python versions