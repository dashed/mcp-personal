# Analysis: Adding PDF Tools to mcp_fuzzy_search.py

## Executive Summary

The existing `mcp_fuzzy_search.py` file provides an excellent foundation for adding PDF search capabilities. Its modular architecture, clear patterns, and robust error handling make it highly extensible. This document analyzes how to add new PDF-specific tools while maintaining consistency with the existing implementation.

## Architectural Compatibility

### Current Architecture Strengths

1. **FastMCP Framework**: Already using FastMCP for tool registration
2. **Binary Management**: Existing pattern for checking/requiring external binaries
3. **Subprocess Pipelines**: Well-established patterns for piping between commands
4. **Error Handling**: Comprehensive error handling for subprocess failures
5. **CLI Interface**: Built-in CLI for testing without MCP client
6. **Result Format**: Consistent JSON response structure

### Understanding ripgrep-all Workflow

Based on source code analysis, here's how ripgrep-all (rga) actually works:

1. **Preprocessing Architecture**:
   - rga acts as a wrapper around ripgrep (rg)
   - It uses a preprocessor pattern via `rga-preproc` binary
   - Different adapters handle different file types

2. **PDF Processing Flow**:
   ```
   PDF file → pdftotext (stdin→stdout) → ASCII text with \x0c page breaks
           → postproc adapter → Text with "Page N: " prefixes
           → ripgrep search → JSON output
   ```

3. **Key Insights**:
   - rga doesn't implement its own JSON format
   - The `--json` flag is passed through to ripgrep
   - PDF line numbers are `null` because PDFs don't have traditional lines
   - Page information is embedded in the text as "Page N: " prefixes

4. **Adapter System**:
   - Built-in adapters defined in `src/adapters/custom.rs`
   - PDF adapter: `pdftotext - -` with output hint `.txt.asciipagebreaks`
   - Postprocessor converts page breaks to readable format

### Integration Points

The file has several natural extension points:

1. **Binary Discovery** (lines 105-106):
   ```python
   RG_EXECUTABLE: str | None = shutil.which("rg")
   FZF_EXECUTABLE: str | None = shutil.which("fzf")
   # Add:
   RGA_EXECUTABLE: str | None = shutil.which("rga")
   PDF2TXT_EXECUTABLE: str | None = shutil.which("pdf2txt.py")
   PANDOC_EXECUTABLE: str | None = shutil.which("pandoc")
   ```

2. **Tool Registration** (line 256):
   ```python
   mcp = FastMCP("fuzzy-search")
   # PDF tools will be added with @mcp.tool decorator
   ```

3. **Helper Functions** (lines 119-238):
   - Can add PDF-specific parsing functions
   - Reuse existing path normalization

## Reusable Patterns

### 1. Tool Definition Pattern

```python
@mcp.tool(
    description=(
        "Detailed multi-line description with:\n"
        "- Purpose\n"
        "- Arguments\n"
        "- Examples\n"
        "- Return format"
    )
)
def tool_name(param1: type, param2: type = default) -> dict[str, Any]:
    """Implementation"""
```

### 2. Binary Requirement Pattern

```python
def _require(binary: str | None, name: str) -> str:
    if not binary:
        raise BinaryMissing(
            f"Cannot find the `{name}` binary on PATH. Install it first."
        )
    return binary
```

### 3. Subprocess Execution Pattern

```python
# Single command
result = subprocess.run(cmd, capture_output=True, text=True)

# Pipeline
proc1 = subprocess.Popen(cmd1, stdout=subprocess.PIPE)
proc2 = subprocess.Popen(cmd2, stdin=proc1.stdout, stdout=subprocess.PIPE)
proc1.stdout.close()
output, _ = proc2.communicate()
```

### 4. Result Format Pattern

```python
return {
    "matches": [...],
    "warnings": [...],  # Optional
    "diagnostic": "..."  # Optional
}
```

## Implementation Approach

### 1. Add PDF-specific Binaries

```python
# After line 106
RGA_EXECUTABLE: str | None = shutil.which("rga")
PDF2TXT_EXECUTABLE: str | None = shutil.which("pdf2txt.py")
PANDOC_EXECUTABLE: str | None = shutil.which("pandoc")

# In main block (line 904)
_require(RGA_EXECUTABLE, "rga")
_require(PDF2TXT_EXECUTABLE, "pdf2txt.py")
_require(PANDOC_EXECUTABLE, "pandoc")
```

### 2. Add PDF Search Tool

#### Understanding ripgrep-all JSON Output

Based on analysis of the rga source code and actual JSON output, here's how rga works:

1. **rga delegates to ripgrep**: When called with `--json`, rga passes this to ripgrep
2. **PDF preprocessing**: 
   - `pdftotext` extracts text with ASCII form feed (`\x0c`) as page delimiters
   - A postprocessor converts these to "Page N: " line prefixes
   - For PDFs, `line_number` is `null` in JSON output
3. **JSON format**: Each line is a separate JSON object (not an array)
   - Type "match": Contains actual search results
   - Type "end": Stats for a single file
   - Type "summary": Overall search statistics

Example JSON output from rga:
```json
{"type":"match","data":{"path":{"text":"./Linear Algebra Done Right 4e.pdf"},"lines":{"text":"Page 402: of scalar and vector, 12\n"},"line_number":null,"absolute_offset":1174364,"submatches":[{"match":{"text":"vector"},"start":24,"end":30}]}}
```

```python
# Add to imports at top of file
import re

@mcp.tool(
    description=(
        "Search through PDFs and other document formats using ripgrep-all.\n\n"
        "Searches through PDFs, Office docs, archives, and more using rga (ripgrep-all).\n"
        "Supports fuzzy filtering of results with fzf.\n\n"
        "Args:\n"
        "  fuzzy_filter (str): Fuzzy search query. Required.\n"
        "  path (str, optional): Directory/file to search. Default: current dir.\n"
        "  file_types (str, optional): Comma-separated file types (pdf,docx,epub).\n"
        "  preview (bool, optional): Include preview context. Default: true.\n"
        "  limit (int, optional): Max results. Default: 20.\n\n"
        "Returns: { matches: Array<{file, page, content, match_text}> } or { error: string }"
    )
)
def fuzzy_search_documents(
    fuzzy_filter: str,
    path: str = ".",
    file_types: str = "",
    preview: bool = True,
    limit: int = 20,
) -> dict[str, Any]:
    """Search documents using ripgrep-all with fuzzy filtering."""
    if not fuzzy_filter:
        return {"error": "'fuzzy_filter' argument is required"}
    
    rga_bin = _require(RGA_EXECUTABLE, "rga")
    fzf_bin = _require(FZF_EXECUTABLE, "fzf")
    
    try:
        # Build rga command - pass everything to match ripgrep's behavior
        rga_cmd = [rga_bin, "--json", "--no-heading"]
        
        # Add file type filters if specified
        if file_types:
            for ft in file_types.split(","):
                rga_cmd.extend(["--rga-adapters", f"+{ft.strip()}"])
        
        # Search pattern and path
        search_path = str(Path(path).resolve())
        rga_cmd.extend([".", search_path])  # "." searches all content
        
        # Execute rga and collect output for fzf
        rga_proc = subprocess.Popen(
            rga_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        
        # Collect all lines for fzf filtering
        lines_for_fzf = []
        json_lines = []  # Store original JSON for later parsing
        
        for line in rga_proc.stdout:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "match":
                    match_data = data["data"]
                    path_str = match_data["path"]["text"]
                    lines_text = match_data["lines"]["text"].strip()
                    
                    # Extract page number from text if present
                    page_match = re.match(r"Page (\d+):", lines_text)
                    page_num = int(page_match.group(1)) if page_match else None
                    
                    # Format for fzf: path:content (similar to ripgrep output)
                    fzf_line = f"{path_str}:{lines_text}"
                    lines_for_fzf.append(fzf_line)
                    json_lines.append((fzf_line, data))
                    
            except json.JSONDecodeError:
                continue
        
        rga_proc.wait()
        
        if not lines_for_fzf:
            return {"matches": []}
        
        # Use fzf to filter results
        fzf_input = "\n".join(lines_for_fzf)
        fzf_proc = subprocess.Popen(
            [fzf_bin, "--filter", fuzzy_filter],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True
        )
        
        fzf_output, _ = fzf_proc.communicate(fzf_input)
        
        # Parse filtered results
        matches = []
        matched_lines = set(fzf_output.strip().splitlines())
        
        for fzf_line, json_data in json_lines:
            if fzf_line in matched_lines:
                match_data = json_data["data"]
                path_str = match_data["path"]["text"]
                lines_text = match_data["lines"]["text"].strip()
                
                # Extract page number if present
                page_match = re.match(r"Page (\d+): (.+)", lines_text)
                if page_match:
                    page_num = int(page_match.group(1))
                    content = page_match.group(2)
                else:
                    page_num = None
                    content = lines_text
                
                # Get matched text from submatches
                match_texts = []
                for submatch in match_data.get("submatches", []):
                    match_texts.append(submatch["match"]["text"])
                
                matches.append({
                    "file": _normalize_path(path_str),
                    "page": page_num,
                    "content": content,
                    "match_text": " ".join(match_texts) if match_texts else ""
                })
                
                if len(matches) >= limit:
                    break
        
        return {"matches": matches}
        
    except subprocess.CalledProcessError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}
```

### 3. Add PDF Page Extraction Tool

```python
@mcp.tool(
    description=(
        "Extract specific pages from a PDF and convert to various formats.\n\n"
        "Uses pdf2txt.py to extract pages and pandoc for format conversion.\n\n"
        "Args:\n"
        "  file (str): Path to PDF file. Required.\n"
        "  pages (str): Comma-separated page numbers (1-indexed). Required.\n"
        "  format (str, optional): Output format (markdown,html,plain). Default: markdown.\n"
        "  preserve_layout (bool, optional): Try to preserve layout. Default: false.\n\n"
        "Examples:\n"
        "  Extract page 5: pages='5'\n"
        "  Extract pages 1,3,5: pages='1,3,5'\n"
        "  Extract pages 2-10: pages='2,3,4,5,6,7,8,9,10'\n\n"
        "Returns: { content: string, pages_extracted: number[], format: string } or { error: string }"
    )
)
def extract_pdf_pages(
    file: str,
    pages: str,
    format: str = "markdown",
    preserve_layout: bool = False,
) -> dict[str, Any]:
    """Extract specific pages from PDF with format conversion."""
    if not file or not pages:
        return {"error": "Both 'file' and 'pages' arguments are required"}
    
    pdf2txt_bin = _require(PDF2TXT_EXECUTABLE, "pdf2txt.py")
    pandoc_bin = _require(PANDOC_EXECUTABLE, "pandoc")
    
    # Parse page numbers
    try:
        page_list = [int(p.strip()) for p in pages.split(",")]
    except ValueError:
        return {"error": "Invalid page numbers. Use comma-separated integers."}
    
    # Check if file exists
    pdf_path = Path(file)
    if not pdf_path.exists():
        return {"error": f"PDF file not found: {file}"}
    
    try:
        # Build pdf2txt command
        pdf_cmd = [pdf2txt_bin, "-t", "html"]
        
        # Add page numbers
        pdf_cmd.extend(["--page-numbers"] + [str(p) for p in page_list])
        
        # Add layout preservation if requested
        if preserve_layout:
            pdf_cmd.extend(["-Y", "exact"])
        
        pdf_cmd.append(str(pdf_path.resolve()))
        
        # Map format to pandoc format
        pandoc_formats = {
            "markdown": "gfm+tex_math_dollars",
            "html": "html",
            "plain": "plain",
            "latex": "latex",
            "docx": "docx"
        }
        
        pandoc_format = pandoc_formats.get(format, "gfm+tex_math_dollars")
        
        # Build pandoc command
        pandoc_cmd = [
            pandoc_bin,
            "--from=html",
            f"--to={pandoc_format}",
            "--wrap=none"
        ]
        
        # Execute pipeline
        pdf_proc = subprocess.Popen(
            pdf_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        pandoc_proc = subprocess.Popen(
            pandoc_cmd,
            stdin=pdf_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        pdf_proc.stdout.close()
        
        content, pandoc_err = pandoc_proc.communicate()
        pdf_proc.wait()
        
        if pdf_proc.returncode != 0:
            _, pdf_err = pdf_proc.communicate()
            return {"error": f"pdf2txt failed: {pdf_err.decode()}"}
        
        if pandoc_proc.returncode != 0:
            return {"error": f"pandoc failed: {pandoc_err}"}
        
        return {
            "content": content,
            "pages_extracted": page_list,
            "format": format
        }
        
    except subprocess.CalledProcessError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}
```

### 4. Add CLI Subcommands

```python
# In _cli() function, after line 830
# Add new subcommands for PDF tools

# search-documents subcommand
p_docs = sub.add_parser("search-documents", help="Search through PDFs and documents")
p_docs.add_argument("fuzzy_filter", help="fzf query for document search")
p_docs.add_argument("path", nargs="?", default=".", help="Directory/file to search")
p_docs.add_argument("--file-types", default="", help="Comma-separated file types")
p_docs.add_argument("--limit", type=int, default=20, help="Max results")

# extract-pdf subcommand
p_pdf = sub.add_parser("extract-pdf", help="Extract pages from PDF")
p_pdf.add_argument("file", help="PDF file path")
p_pdf.add_argument("pages", help="Comma-separated page numbers")
p_pdf.add_argument("--format", default="markdown", help="Output format")
p_pdf.add_argument("--preserve-layout", action="store_true", help="Preserve layout")

# In command handling (after line 876)
elif ns.cmd == "search-documents":
    res = fuzzy_search_documents(
        ns.fuzzy_filter, ns.path, ns.file_types, True, ns.limit
    )
elif ns.cmd == "extract-pdf":
    res = extract_pdf_pages(
        ns.file, ns.pages, ns.format, ns.preserve_layout
    )
```

## Testing Strategy

### 1. Unit Tests Pattern

```python
async def test_fuzzy_search_documents(tmp_path: Path):
    """Test fuzzy_search_documents with real binaries."""
    _skip_if_missing("rga")
    _skip_if_missing("fzf")
    
    # Create test PDF (would need actual PDF)
    test_pdf = tmp_path / "test.pdf"
    # ... create PDF content ...
    
    async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
        result = await client.call_tool(
            "fuzzy_search_documents",
            {"fuzzy_filter": "test", "path": str(tmp_path)}
        )
        
        data = json.loads(result.content[0].text)
        assert "matches" in data
        
        # Verify PDF-specific fields
        if data["matches"]:
            match = data["matches"][0]
            assert "page" in match  # Should have page number for PDFs
            assert "match_text" in match  # Actual matched text
            assert match["file"].endswith(".pdf")
```

### 2. Testing ripgrep-all JSON Output

For testing the JSON parsing, you can mock the rga output:

```python
def test_parse_rga_json():
    """Test parsing of actual rga JSON output."""
    sample_json = '''{"type":"match","data":{"path":{"text":"test.pdf"},"lines":{"text":"Page 1: Hello world\\n"},"line_number":null,"submatches":[{"match":{"text":"world"},"start":14,"end":19}]}}'''
    
    data = json.loads(sample_json)
    assert data["type"] == "match"
    assert data["data"]["line_number"] is None  # PDFs don't have line numbers
    assert "Page 1:" in data["data"]["lines"]["text"]
```

### 3. CLI Testing

```bash
# Test document search
./mcp_fuzzy_search.py search-documents "vector" ./pdfs

# Test with specific file types
./mcp_fuzzy_search.py search-documents "equation" . --file-types "pdf,epub"

# Test PDF extraction
./mcp_fuzzy_search.py extract-pdf report.pdf "1,3,5" --format markdown

# Debug JSON output from rga directly
rga --json "search term" ./test.pdf | head -20
```

## Potential Challenges and Solutions

### 1. Binary Dependencies

**Challenge**: Users need multiple binaries installed (rga, pdf2txt.py, pandoc)

**Solution**: 
- Clear error messages with installation instructions
- Optional tools - only require binaries when specific tools are used
- Add installation helper script

### 2. Large PDF Processing

**Challenge**: PDFs can be very large, causing memory issues

**Solution**:
- Stream processing where possible
- Add file size limits or warnings
- Implement pagination for large results

### 3. Encoding Issues

**Challenge**: PDFs may contain various encodings

**Solution**:
- Use existing encoding handling patterns from the file
- Default to UTF-8 with fallback to replacement characters

### 4. Performance

**Challenge**: ripgrep-all can be slow on first run (building cache)

**Solution**:
- Add progress indicators
- Implement caching options
- Add timeout parameters

### 5. JSON Format Parsing

**Challenge**: ripgrep outputs newline-delimited JSON, not a JSON array

**Solution**:
- Parse line by line, handling each JSON object separately
- Filter by type ("match", "end", "summary")
- Handle missing line_number for binary formats like PDFs
- Extract page numbers from the text content for PDFs

## Recommendations

1. **Start Simple**: Begin with basic PDF search using ripgrep-all
2. **Incremental Addition**: Add tools one at a time with thorough testing
3. **Maintain Consistency**: Follow existing patterns for errors, results, and CLI
4. **Documentation**: Update docstrings with PDF-specific examples
5. **Optional Features**: Make PDF tools optional to avoid forcing dependencies

## Code Organization

The additions would fit naturally into the existing file structure:

```
Lines 1-104:    Headers and imports
Lines 105-110:  Binary discovery (ADD PDF BINARIES HERE)
Lines 111-252:  Helper functions (ADD PDF HELPERS HERE)
Lines 253-731:  Existing tools
Lines 732-900:  (ADD NEW PDF TOOLS HERE)
Lines 901-907:  Main entry point (ADD BINARY CHECKS HERE)
```

## Implementation Plan

### Phase 1: Foundation (Week 1)
1. **Add Binary Discovery**
   - Add rga, pdf2txt.py, pandoc to binary discovery section
   - Implement conditional loading (tools only available if binaries exist)
   - Add installation instructions in error messages

2. **Create Helper Functions**
   - Add `_parse_rga_json_output()` for processing ripgrep-all JSON
   - Add `_get_file_type_from_path()` for file type detection
   - Extend `_normalize_path()` for cross-platform PDF paths

3. **Update Binary Requirements**
   - Make PDF tools optional (don't fail server startup)
   - Add `--check-binaries` CLI flag to verify installations

### Phase 2: Core PDF Tools (Week 2)
1. **Implement fuzzy_search_documents**
   - Start with basic rga integration
   - Add JSON parsing for rga output
   - Integrate with fzf for fuzzy filtering
   - Test with various document types

2. **Implement extract_pdf_pages**
   - Create pdf2txt.py → pandoc pipeline
   - Handle page number parsing and validation
   - Support multiple output formats
   - Add error handling for invalid PDFs

### Phase 3: LLM Disambiguation (Week 3)
1. **Enhanced Tool Descriptions**
   - Add decision trees to each tool description
   - Include explicit file type lists
   - Add "When to use" and "When NOT to use" sections

2. **Query Pattern Examples**
   - Add 10+ examples per tool showing typical user queries
   - Include edge cases and clarifications

3. **Consider Unified Interface**
   - Evaluate adding a `smart_search` tool that routes to appropriate backend
   - Implement file type detection logic

### Phase 4: Testing & Documentation (Week 4)
1. **Comprehensive Testing**
   - Unit tests for each new tool
   - Integration tests with real PDFs
   - Performance benchmarks
   - Cross-platform testing

2. **Documentation**
   - Update README with PDF search examples
   - Create troubleshooting guide
   - Add performance tuning tips

## LLM Disambiguation Analysis

### The Challenge

With multiple search tools available, LLM agents need clear guidance to choose the right tool:

1. **fuzzy_search_files** - Search for file paths/names
2. **fuzzy_search_content** - Search text content in code/text files
3. **fuzzy_search_documents** - Search PDFs, Office docs, and other binary formats
4. **extract_pdf_pages** - Extract specific pages from PDFs

The main confusion point is between `fuzzy_search_content` and `fuzzy_search_documents`.

### Disambiguation Strategies

#### 1. Clear Tool Naming and Descriptions

**Current State:**
- `fuzzy_search_content` - Generic name, could apply to any content

**Proposed Enhancement:**
```python
@mcp.tool(
    description=(
        "Search plain text files (source code, configs, logs) using ripgrep.\n\n"
        "✅ USE THIS TOOL FOR:\n"
        "- Source code files (.py, .js, .java, .c, .cpp, .go, .rs)\n"
        "- Configuration files (.json, .yaml, .xml, .ini, .conf)\n"
        "- Text documents (.txt, .md, .rst)\n"
        "- Log files (.log)\n"
        "- Shell scripts (.sh, .bash)\n\n"
        "❌ DO NOT USE FOR:\n"
        "- PDFs → Use fuzzy_search_documents\n"
        "- Office documents → Use fuzzy_search_documents\n"
        "- Binary files → Use fuzzy_search_documents\n\n"
        "DECISION RULE: If you can open it in a text editor, use this tool.\n"
    )
)
```

#### 2. File Type Decision Matrix

Add to each tool description:

```
FILE TYPE QUICK REFERENCE:
┌─────────────────────┬─────────────────────────┬──────────────────────┐
│ File Extension      │ Tool to Use             │ Example Query        │
├─────────────────────┼─────────────────────────┼──────────────────────┤
│ .py, .js, .java     │ fuzzy_search_content    │ "find TODO in code"  │
│ .pdf                │ fuzzy_search_documents  │ "search PDF for X"   │
│ .docx, .xlsx        │ fuzzy_search_documents  │ "find in Word doc"   │
│ .txt, .md           │ fuzzy_search_content    │ "search text files"  │
│ .epub, .mobi        │ fuzzy_search_documents  │ "search ebooks"      │
│ Just filenames      │ fuzzy_search_files      │ "find files named X" │
└─────────────────────┴─────────────────────────┴──────────────────────┘
```

#### 3. Query Pattern Recognition

Add examples showing how users typically phrase requests:

```python
# In tool descriptions
"QUERY PATTERNS:\n"
"- 'search for X in PDF' → fuzzy_search_documents\n"
"- 'find X in code' → fuzzy_search_content\n"
"- 'grep for X' → fuzzy_search_content\n"
"- 'search Word documents' → fuzzy_search_documents\n"
"- 'find files containing X' → Ambiguous! Ask user for file type\n"
```

#### 4. Smart Routing Approach

Consider adding a meta-tool:

```python
@mcp.tool(
    description=(
        "Intelligently search files based on content and type.\n"
        "This tool automatically selects the best search method.\n"
    )
)
def smart_search(
    query: str,
    path: str = ".",
    file_types: Optional[List[str]] = None
) -> dict[str, Any]:
    """Route to appropriate search tool based on file types."""
    
    if file_types:
        # Explicit file types provided
        text_types = {'.py', '.js', '.txt', '.md', ...}
        doc_types = {'.pdf', '.docx', '.xlsx', ...}
        
        if any(ft in text_types for ft in file_types):
            return fuzzy_search_content(query, path)
        elif any(ft in doc_types for ft in file_types):
            return fuzzy_search_documents(query, path)
    
    # Auto-detect based on directory contents
    # ... detection logic ...
```

#### 5. Capability Comparison Table

Add to documentation:

```
TOOL CAPABILITIES COMPARISON:
┌─────────────────────────┬────────┬────────┬───────────┬─────────┐
│ Feature                 │ files  │ content│ documents │ extract │
├─────────────────────────┼────────┼────────┼───────────┼─────────┤
│ Search file names       │   ✓    │        │           │         │
│ Search text content     │        │   ✓    │     ✓     │         │
│ Search PDFs             │        │        │     ✓     │         │
│ Search Office docs      │        │        │     ✓     │         │
│ Extract PDF pages       │        │        │           │    ✓    │
│ Fuzzy matching          │   ✓    │   ✓    │     ✓     │         │
│ Fast performance        │   ✓    │   ✓    │           │    ✓    │
│ Handles large files     │   ✓    │   ✓    │     ✓     │    ✓    │
└─────────────────────────┴────────┴────────┴───────────┴─────────┘
```

### Edge Cases and Solutions

#### 1. Mixed Content Queries
**User Query**: "Search all files including PDFs for 'invoice'"

**Solution**:
- Implement a combined search that runs both tools
- Return results grouped by tool/file type
- Add guidance in tool description about using multiple tools

#### 2. Ambiguous Extensions
**Issue**: Some files like `.log` could be huge binary or text

**Solution**:
- Add MIME type detection as fallback
- Set size thresholds for automatic tool selection
- Provide override parameters

#### 3. Performance Expectations
**Issue**: ripgrep-all is slower than ripgrep

**Solution**:
```python
# In tool description
"PERFORMANCE NOTE: Searching PDFs and Office documents is slower than\n"
"searching text files. For mixed directories, consider using file_types\n"
"parameter to limit search scope.\n"
```

### Recommended Tool Description Structure

Each tool should follow this structure:

```
1. ONE-LINE SUMMARY
2. WHEN TO USE (with examples)
3. WHEN NOT TO USE (with alternatives)
4. FILE TYPES SUPPORTED
5. EXAMPLE QUERIES
6. PARAMETERS
7. RETURN FORMAT
8. PERFORMANCE NOTES
```

### Alternative: Unified Interface

Instead of multiple tools, consider a single interface:

```python
@mcp.tool(
    description="Unified search interface that automatically handles all file types"
)
def search(
    query: str,
    path: str = ".",
    search_type: Literal["auto", "filenames", "text", "documents", "all"] = "auto",
    **kwargs
) -> dict[str, Any]:
    """Single entry point for all searches."""
```

Benefits:
- No confusion for LLM agents
- Automatic file type detection
- Consistent interface

Drawbacks:
- Less explicit control
- Harder to optimize for specific use cases
- May hide important performance differences

## Conclusion

The `mcp_fuzzy_search.py` file is well-architected for extension. Adding PDF search tools would:

1. Leverage existing patterns for consistency
2. Reuse subprocess execution and error handling
3. Maintain the same user experience
4. Provide both MCP and CLI interfaces
5. Follow established testing patterns

The key to successful implementation is:
- Clear disambiguation through detailed tool descriptions
- Explicit file type guidance
- Comprehensive examples
- Consideration of edge cases
- Potential unified interface for simpler LLM interaction

The modular design makes it straightforward to add new tools without modifying existing functionality, while the disambiguation strategies ensure LLM agents can reliably choose the appropriate tool for each use case.