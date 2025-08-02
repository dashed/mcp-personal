#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=0.1.0", "PyMuPDF>=1.23.0"]
#
# [project.optional-dependencies]
# dev = ["pytest>=7.0", "pytest-asyncio>=0.21.0"]
# ///
"""
`mcp_fuzzy_search.py` – **Model Context Protocol** server for fuzzy searching
file contents using **ripgrep** and **fzf** in non-interactive filter mode.

This combines the power of ripgrep's fast content search with fzf's fuzzy
filtering capabilities, perfect for finding code snippets, configurations,
or any text patterns across your codebase.

Tools exposed to LLMs
--------------------
* **`fuzzy_search_files`** – Search for file paths using fuzzy matching.
* **`fuzzy_search_content`** – Search file contents with ripgrep, then apply
  fuzzy filtering to the results. Supports both path+content and content-only modes.

Understanding the Search Pipeline
--------------------------------
    Files → ripgrep (all lines) → Lines → fzf (fuzzy filter) → Results
                                           ↑
                                    'fuzzy_filter'

Default: Matches on file paths AND content (--nth=1,3..)
Content-only: Matches ONLY on content (--nth=3..)

CRITICAL FOR AI AGENTS: NO REGEX SUPPORT
----------------------------------------
The fuzzy_filter parameter does NOT support regular expressions!
- ✗ NO regex patterns like '.*', '\\w+', '[a-z]+', etc.
- ✓ Use fzf's fuzzy matching syntax instead
- ✓ Space-separated terms for AND logic
- ✓ Use | for OR logic, ! for exclusion
- ✓ Use ^ and $ for prefix/suffix (NOT regex anchors!)

SPACES MATTER - THEY SEPARATE SEARCH PATTERNS!
----------------------------------------------
- 'foo bar' → Matches items with 'foo' AND 'bar' (2 patterns)
- 'foo/bar' → Matches items with 'foo/bar' (1 pattern)
- 'src /test$' → Matches items with 'src' AND ending with '/test'
- 'src/test$' → Matches items ending with 'src/test'
- 'foo\\ bar' → Matches items with literal 'foo bar' (escaped space)

ADVANCED FZF FEATURES (from source code analysis)
------------------------------------------------
1. Smart Case: lowercase = case-insensitive, MixedCase = case-sensitive
2. Exact match prefix: 'exact → disables fuzzy matching
3. Exact boundary match: ''exact'' → matches at word boundaries
4. Scoring algorithm: Length, position, and consecutiveness affect ranking
5. Extended search mode: Always enabled, allows complex queries
6. ANSI color codes: Automatically stripped before matching
7. Multi-select: Not used (we process all matches)
8. Latin script normalization: café matches cafe (unless --literal is used)

Examples
--------
# Find Python files containing 'update' AND 'config':
fuzzy_search_content('update config', path='src/', rg_flags='-t py')

# Find test functions for seer credit operations:
fuzzy_search_content('def test_ seer credit')

# Find all TODO comments related to auth (case-insensitive):
fuzzy_search_content("TODO auth", rg_flags="-i")

# Find React components with 'Modal' in the name:
fuzzy_search_files('Modal tsx$ | jsx$')

# Content-only mode - find 'className' in code without matching filenames:
fuzzy_search_content('className', content_only=True)

Requirements
-----------
* **ripgrep** (rg) – https://github.com/BurntSushi/ripgrep
* **fzf** – https://github.com/junegunn/fzf
* Python 3.10+

Authors
------
Varol Aksoy (@vaksoy)
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

try:
    import fitz  # PyMuPDF

    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

# Tool names as seen by LLMs
FUZZY_SEARCH_FILES_TOOL = "fuzzy_search_files"
FUZZY_SEARCH_CONTENT_TOOL = "fuzzy_search_content"
FUZZY_SEARCH_DOCUMENTS_TOOL = "fuzzy_search_documents"
EXTRACT_PDF_PAGES_TOOL = "extract_pdf_pages"

# Default parameters
DEFAULT_PATH = "."
DEFAULT_LIMIT = 20
DEFAULT_HIDDEN = False
DEFAULT_MULTILINE = False

# Executables - will check availability at startup
RG_EXECUTABLE = shutil.which("rg")
FZF_EXECUTABLE = shutil.which("fzf")
RGA_EXECUTABLE = shutil.which("rga")
PANDOC_EXECUTABLE = shutil.which("pandoc")

# Logger
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------
mcp = FastMCP("fuzzy-search")


def _require(exe: str | None, name: str) -> str:
    """Ensure required executable exists."""
    if not exe:
        raise RuntimeError(f"{name} not found. Please install it first.")
    return exe


def _get_page_label(doc, page_idx: int) -> str:
    """Get the label for a specific page index.

    Args:
        doc: PyMuPDF document object
        page_idx: 0-based page index

    Returns:
        Page label string, or str(page_idx + 1) if no label
    """
    try:
        # Use PyMuPDF's page.get_label() method
        page = doc[page_idx]
        if hasattr(page, "get_label"):
            label = page.get_label()
            if label:
                return label
    except Exception:
        pass

    # Default to 1-based physical page number
    return str(page_idx + 1)


def _int_to_roman(num: int) -> str:
    """Convert integer to Roman numerals."""
    val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syms = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
    roman_num = ""
    i = 0
    while num > 0:
        for _ in range(num // val[i]):
            roman_num += syms[i]
            num -= val[i]
        i += 1
    return roman_num


def _parse_page_spec_pymupdf(page_spec: str, doc) -> list[int]:
    """Parse a page specification into 0-based page indices using PyMuPDF.

    Handles:
    - Single labels: "v", "ToC", "14"
    - Ranges: "v-vii", "1-5"

    Args:
        page_spec: Page specification string
        doc: PyMuPDF document object

    Returns:
        List of 0-based page indices
    """
    indices = []

    # Handle range
    if "-" in page_spec:
        parts = page_spec.split("-", 1)
        start_spec = parts[0].strip()
        end_spec = parts[1].strip()

        # Resolve start using PyMuPDF's get_page_numbers
        start_indices = doc.get_page_numbers(start_spec)
        if not start_indices:
            # Try as physical page number (1-based)
            try:
                page_num = int(start_spec)
                if 1 <= page_num <= doc.page_count:
                    start_indices = [page_num - 1]
            except ValueError:
                pass

        if not start_indices:
            return []  # Invalid start

        # Resolve end
        end_indices = doc.get_page_numbers(end_spec)
        if not end_indices:
            # Try as physical page number (1-based)
            try:
                page_num = int(end_spec)
                if 1 <= page_num <= doc.page_count:
                    end_indices = [page_num - 1]
            except ValueError:
                pass

        if not end_indices:
            return []  # Invalid end

        # Generate range (inclusive) from first start to first end
        start_idx = start_indices[0]
        end_idx = end_indices[0]
        indices = list(range(start_idx, end_idx + 1))
    else:
        # Single page - try PyMuPDF's get_page_numbers first
        all_indices = doc.get_page_numbers(page_spec)

        if all_indices:
            # Take only the first match (like PDF readers do)
            indices = [all_indices[0]]
        else:
            # Try as physical page number (1-based)
            try:
                page_num = int(page_spec)
                if 1 <= page_num <= doc.page_count:
                    indices = [page_num - 1]
            except ValueError:
                pass

    return indices


# ---------------------------------------------------------------------------
# Tool: extract_pdf_pages
# ---------------------------------------------------------------------------
@mcp.tool(
    description=(
        "Extract specific pages from a PDF and convert to various formats.\n\n"
        "Uses PyMuPDF for fast page extraction with direct page label support.\n\n"
        "Args:\n"
        "  file (str): Path to PDF file. Required.\n"
        "  pages (str): Comma-separated page specifications. Required.\n"
        "  format (str, optional): Output format (markdown,html,plain). Default: markdown.\n"
        "  preserve_layout (bool, optional): Try to preserve layout. Default: false.\n"
        "  clean_html (bool, optional): Strip HTML styling tags. Default: true.\n\n"
        "Page specifications:\n"
        "  - Page labels: 'v', 'vii', 'ToC', 'Introduction' (as shown in PDF readers)\n"
        "  - Ranges: 'v-vii', '1-5'\n"
        "  - Physical pages: '1', '14' (1-based if not found as label)\n"
        "  - Mixed: 'v,vii,1,5-8,ToC'\n\n"
        "Examples:\n"
        "  Extract roman numeral pages: pages='v,vi,vii'\n"
        "  Extract range: pages='v-vii'\n"
        "  Extract by page number: pages='14'\n"
        "  Extract mixed: pages='ToC,v-vii,1,2'\n\n"
        "Returns: { content: string, pages_extracted: number[], page_labels: string[], format: string } or { error: string }"
    )
)
def extract_pdf_pages(
    file: str,
    pages: str,
    format: str = "markdown",
    preserve_layout: bool = False,
    clean_html: bool = True,
) -> dict[str, Any]:
    """Extract specific pages from PDF using PyMuPDF."""
    if not file or not pages:
        return {"error": "Both 'file' and 'pages' arguments are required"}

    # Check if PyMuPDF is available
    if not PYMUPDF_AVAILABLE:
        return {
            "error": "PyMuPDF is not installed. Install it with: pip install PyMuPDF"
        }

    # Check if file exists
    pdf_path = Path(file)
    if not pdf_path.exists():
        return {"error": f"PDF file not found: {file}"}

    try:
        # Open PDF with PyMuPDF
        doc = fitz.open(pdf_path)

        # Parse page specifications
        page_indices = []
        page_labels_used = []

        for page_spec in pages.split(","):
            page_spec = page_spec.strip()
            if not page_spec:
                continue

            spec_indices = _parse_page_spec_pymupdf(page_spec, doc)
            if not spec_indices:
                doc.close()
                return {
                    "error": f"Invalid page specification: '{page_spec}'. Not found as page label or valid page number."
                }

            page_indices.extend(spec_indices)

            # Track which labels were used
            # Check if this spec matched a label (not just a physical page number)
            if doc.get_page_numbers(page_spec):
                page_labels_used.append(page_spec)
            elif "-" in page_spec:
                # For ranges, track if they were label-based
                parts = page_spec.split("-", 1)
                if doc.get_page_numbers(parts[0].strip()) or doc.get_page_numbers(
                    parts[1].strip()
                ):
                    page_labels_used.append(page_spec)

        if not page_indices:
            doc.close()
            return {"error": "No valid pages specified."}

        # Remove duplicates while preserving order
        seen = set()
        unique_indices = []
        for idx in page_indices:
            if idx not in seen:
                seen.add(idx)
                unique_indices.append(idx)

        # Extract content based on format
        content_parts = []

        # Determine extraction format
        if format == "html" or (format == "markdown" and PANDOC_EXECUTABLE):
            # Extract as HTML for pandoc conversion
            extract_format = "html"
        else:
            # Extract as plain text
            extract_format = "text"

        # Extract pages
        for idx in unique_indices:
            page = doc[idx]

            # Get page label for context
            labels = doc.get_page_labels()
            page_label = labels[idx] if labels and idx < len(labels) else str(idx + 1)

            # Extract content
            if extract_format == "html":
                page_content = page.get_text("html")
                # Clean HTML if requested
                if clean_html:
                    # Remove style attributes
                    page_content = re.sub(r'\sstyle="[^"]*"', "", page_content)
                    # Remove font tags
                    page_content = re.sub(r"</?font[^>]*>", "", page_content)
                    # Remove span tags but keep content
                    page_content = re.sub(r"<span[^>]*>", "", page_content)
                    page_content = re.sub(r"</span>", "", page_content)

                # Add page marker
                content_parts.append(
                    f'<div class="page" data-page="{idx + 1}" data-label="{page_label}">'
                )
                content_parts.append(page_content)
                content_parts.append("</div>")
            else:
                # Plain text extraction
                page_content = page.get_text("text")
                # Add page marker
                content_parts.append(f"\n[Page {idx + 1}] (Label: {page_label})\n")
                content_parts.append(page_content)

        # Join content
        if extract_format == "html":
            full_content = "<html><body>" + "".join(content_parts) + "</body></html>"
        else:
            full_content = "\n".join(content_parts)

        # Convert format if needed
        if format == "markdown" and extract_format == "html" and PANDOC_EXECUTABLE:
            # Use pandoc to convert HTML to markdown
            pandoc_bin = _require(PANDOC_EXECUTABLE, "pandoc")

            # Build pandoc command
            if clean_html:
                from_format = "html-native_divs-native_spans"
                to_format = "gfm+tex_math_dollars-raw_html"
            else:
                from_format = "html"
                to_format = "gfm+tex_math_dollars"

            pandoc_cmd = [
                pandoc_bin,
                f"--from={from_format}",
                f"--to={to_format}",
                "--wrap=none",
            ]

            if clean_html:
                pandoc_cmd.append("--strip-comments")

            # Run pandoc
            try:
                pandoc_proc = subprocess.run(
                    pandoc_cmd,
                    input=full_content.encode(),
                    capture_output=True,
                    check=False,
                    timeout=30,
                )

                if pandoc_proc.returncode != 0:
                    return {
                        "error": f"pandoc conversion failed: {pandoc_proc.stderr.decode()}"
                    }

                content = pandoc_proc.stdout.decode()
            except subprocess.TimeoutExpired:
                return {"error": "pandoc conversion timed out"}
            except Exception as e:
                return {"error": f"pandoc conversion error: {e}"}
        else:
            content = full_content

        # Build response
        # Get actual page labels for extracted pages
        extracted_labels = []
        for idx in unique_indices:
            page = doc[idx]
            label = page.get_label() if hasattr(page, "get_label") else str(idx + 1)
            extracted_labels.append(label)

        # Close the document
        doc.close()

        return {
            "content": content,
            "pages_extracted": unique_indices,
            "page_labels": extracted_labels,
            "format": format,
        }

    except Exception as e:
        return {"error": f"Failed to extract pages: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool: fuzzy_search_files
# ---------------------------------------------------------------------------
@mcp.tool(
    description=(
        "Search for file paths using fuzzy matching.\n\n"
        "IMPORTANT: NO REGEX SUPPORT - fuzzy_filter uses fzf's fuzzy matching syntax, NOT regular expressions!\n\n"
        "Args:\n"
        "  fuzzy_filter (str): fzf query string (NOT regex). Required.\n"
        "  path   (str, optional): Directory to search. Defaults to current dir.\n"
        "  hidden (bool, optional): Include hidden files. Default false.\n"
        "  limit  (int, optional): Max results to return. Default 20.\n"
        "  multiline (bool, optional): Enable multiline file content search. Default false.\n\n"
        "fzf Query Syntax (NO REGEX SUPPORT):\n"
        "  CRITICAL: SPACES SEPARATE SEARCH TERMS - Each space creates a new fuzzy pattern!\n"
        "  Basic Terms: Space-separated terms use AND logic (all must match)\n"
        "    'main config' → files containing both 'main' AND 'config'\n"
        "  OR Logic: Use | to match any term\n"
        "    'py$ | js$ | go$' → files ending in .py OR .js OR .go\n"
        "  Exact Match: Single quote prefix for exact (non-fuzzy) matching\n"
        "    'test → exact match for 'test' (NOT fuzzy)\n"
        "  Exact Boundary Match: Wrap in quotes for word boundary matching\n"
        "    ''main.py'' → matches 'main.py' at word boundaries\n"
        "  Position Anchors (NOT regex anchors):\n"
        "    '^src' → files starting with 'src' (prefix match)\n"
        "    '.json$' → files ending with '.json' (suffix match)\n"
        "    '^README$' → files exactly equal to 'README'\n"
        "  Escaped Spaces: Use backslash to match literal spaces\n"
        "    'foo\\\\ bar' → matches literal 'foo bar' (one pattern)\n\n"
        "UNDERSTANDING SPACES (Critical!):\n"
        "  'temp/test$' → Matches paths containing 'temp/test' at the end\n"
        "  'temp /test$' → Matches paths with 'temp' AND ending with '/test' (space matters!)\n"
        "  'dir test' → Matches paths containing 'dir' AND 'test' anywhere\n"
        "  'dir/test' → Matches paths containing 'dir/test' as one pattern\n"
        "  'My\\\\ Documents' → Matches literal 'My Documents' (escaped space)\n"
        "  Negation: Use ! to exclude matches\n"
        "    '!test' → exclude files containing 'test'\n"
        "    '!^src' → exclude files starting with 'src'\n"
        "    '!.tmp$' → exclude files ending with '.tmp'\n"
        "  Complex Examples:\n"
        "    'config .json$ !test' → JSON config files, excluding test files\n"
        "    '^src py$ | js$' → files in src/ ending with .py or .js\n"
        "    ''package.json'' | ''yarn.lock''' → exact package manager files\n\n"
        "Multiline Mode:\n"
        "  When enabled, searches through complete file contents instead of just filenames.\n"
        "  Each file becomes a multiline record with 'filename:' prefix followed by content.\n"
        "  Useful for finding files containing specific code patterns, configurations, or text.\n"
        "  Example: 'function.*async' would find files containing async function definitions.\n\n"
        "Returns: { matches: string[] } or { error: string }"
    )
)
def fuzzy_search_files(
    fuzzy_filter: str,
    path: str = ".",
    hidden: bool = False,
    limit: int = 20,
    multiline: bool = False,
) -> dict[str, Any]:
    """Find files using ripgrep + fzf fuzzy filtering with optional multiline content search."""
    if not fuzzy_filter:
        return {"error": "'fuzzy_filter' argument is required"}

    rg_bin = _require(RG_EXECUTABLE, "rg")
    fzf_bin = _require(FZF_EXECUTABLE, "fzf")

    try:
        if multiline:
            # For multiline mode, get file list first, then read contents
            search_path = str(Path(path).resolve())
            rg_list_cmd = [rg_bin, "--files"]
            if hidden:
                rg_list_cmd.append("--hidden")
            rg_list_cmd.append(search_path)

            # Get file list
            file_list_result = subprocess.check_output(rg_list_cmd, text=True)
            file_paths = [
                str(Path(p).resolve()) for p in file_list_result.splitlines() if p
            ]

            # Build multiline input with null separators
            multiline_input = b""
            for file_path in file_paths:
                try:
                    path_obj = Path(file_path)
                    with path_obj.open("rb") as f:
                        content = f.read()
                        # Create record: filename: + content + null separator
                        record = f"{file_path}:\n".encode() + content + b"\0"
                        multiline_input += record
                except (OSError, UnicodeDecodeError):
                    continue  # Skip files that can't be read

            if not multiline_input:
                return {"matches": []}

            # Use fzf with multiline support
            fzf_cmd = [
                fzf_bin,
                "--filter",
                fuzzy_filter,
                "--read0",
                "--print0",
            ]

            fzf_proc = subprocess.Popen(
                fzf_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=False
            )
            out_bytes, _ = fzf_proc.communicate(multiline_input)

            # Parse null-separated output
            matches = []
            if out_bytes:
                for chunk in out_bytes.split(b"\0"):
                    if chunk:
                        try:
                            decoded = chunk.decode("utf-8")
                            # In multiline mode, return the full content including filename prefix
                            matches.append(decoded)
                        except UnicodeDecodeError:
                            matches.append(chunk.decode("utf-8", errors="replace"))
        else:
            # Standard mode - file paths only
            search_path = str(Path(path).resolve())
            rg_cmd = [rg_bin, "--files"]
            if hidden:
                rg_cmd.append("--hidden")
            rg_cmd.append(search_path)

            # Pipe through fzf for fuzzy filtering
            fzf_cmd = [fzf_bin, "--filter", fuzzy_filter]

            logger.debug("Pipeline: %s | %s", " ".join(rg_cmd), " ".join(fzf_cmd))

            rg_proc = subprocess.Popen(
                rg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            fzf_proc = subprocess.Popen(
                fzf_cmd, stdin=rg_proc.stdout, stdout=subprocess.PIPE, text=True
            )
            rg_proc.stdout.close()

            out, _ = fzf_proc.communicate()
            rg_proc.wait()

            matches = [p for p in out.splitlines() if p]

        # Apply limit
        matches = matches[:limit]

        return {"matches": matches}
    except subprocess.CalledProcessError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: fuzzy_search_content
# ---------------------------------------------------------------------------
@mcp.tool(
    description=(
        "Search file contents using fuzzy filtering.\n\n"
        "CRITICAL: NO REGEX SUPPORT - fuzzy_filter does NOT accept regular expressions!\n\n"
        "    Files → ripgrep (all lines) → fzf (fuzzy filter) → Results\n\n"
        "Args:\n"
        "  fuzzy_filter (str): Fuzzy search query (NOT regex!). Required.\n"
        "  path (str, optional): Directory/file to search. Defaults to current dir.\n"
        "  hidden (bool, optional): Search hidden files. Default false.\n"
        "  limit (int, optional): Max results to return. Default 20.\n"
        "  rg_flags (str, optional): Extra flags for ripgrep (see below).\n"
        "  multiline (bool, optional): Enable multiline record processing. Default false.\n"
        "  content_only (bool, optional): Match only on content, ignore file paths. Default false.\n\n"
        "Fuzzy Filter Syntax (NO REGEX - these are fzf patterns):\n"
        "  CRITICAL: SPACES MATTER! Each space separates fuzzy patterns (AND logic)\n"
        "  Basic search: 'update_ondemand_max_spend' → finds all occurrences\n"
        "  Multiple terms: 'update spend' → lines with both terms (space = AND)\n"
        "  OR logic: 'update | modify' → lines with either term\n"
        "  File filtering: 'test.py: update' → only in test.py files (when content_only=false)\n"
        "  Exact match prefix: 'update → exact (non-fuzzy) match\n"
        "  Exact boundary: ''exact phrase'' → matches at word boundaries\n"
        "  Exclusion: 'update !test' → exclude lines with 'test'\n"
        "  With prefix: '^def update' → lines starting with 'def update'\n"
        "  With suffix: 'update$' → lines ending with 'update'\n"
        "  Escaped spaces: 'TODO:\\\\ fix' → matches literal 'TODO: fix'\n\n"
        "MATCHING BEHAVIOR:\n"
        "  Default (content_only=false): Matches on file path AND content (skips line numbers)\n"
        "  With content_only=true: Matches ONLY on content, ignores file paths\n\n"
        "UNDERSTANDING SPACES - CRITICAL FOR PRECISE SEARCHES:\n"
        "  'def update_method' → Lines containing the exact pattern 'def update_method'\n"
        "  'def update method' → Lines containing 'def' AND 'update' AND 'method' (3 patterns!)\n"
        "  'src/test$' → Lines ending with 'src/test'\n"
        "  'src /test$' → Lines containing 'src' AND ending with '/test' (space matters!)\n"
        "  'TODO: fix' → Lines containing 'TODO:' AND 'fix' (space creates 2 patterns)\n"
        "  ''TODO: fix'' → Lines with 'TODO: fix' at word boundaries\n"
        "  'TODO:\\\\ fix' → Lines containing literal 'TODO: fix' (escaped space)\n\n"
        "COMMON MISTAKES TO AVOID:\n"
        "  ✗ 'def.*update' → WRONG! This is regex, not supported\n"
        "  ✓ 'def update' → CORRECT! Fuzzy matches both terms\n"
        "  ✗ 'class\\\\s+\\\\w+' → WRONG! Regex not supported\n"
        "  ✓ 'class' → CORRECT! Fuzzy match\n\n"
        "Useful rg_flags for search optimization:\n"
        "  File Types: '-t py' (Python), '-t js' (JavaScript), '-T test' (exclude tests)\n"
        "  Case: '-i' (ignore case), '-S' (smart case), '-s' (case sensitive)\n"
        "  Context: '-A 3' (lines after), '-B 2' (lines before), '-C 3' (both)\n"
        "  Exclusions: '--glob '!node_modules'' (exclude paths), '--max-filesize 1M'\n"
        "  Special: '-w' (whole words), '-v' (invert match), '-U' (multiline)\n\n"
        "Examples:\n"
        "  1. Find function definitions:\n"
        '     fuzzy_filter="def update_ondemand_max_spend"\n'
        "  2. Find TODO comments about billing:\n"
        '     fuzzy_filter="TODO billing"\n'
        "  3. Find imports in Python files only:\n"
        '     fuzzy_filter="import pandas", rg_flags="-t py"\n'
        "  4. Case-insensitive search with context:\n"
        '     fuzzy_filter="UpdateOndemand", rg_flags="-i -C 2"\n'
        "  5. PRACTICAL EXAMPLE - Finding specific test files:\n"
        '     Finding "def test_" in files ending with "_test.py":\n'
        '     fuzzy_filter="def test_ _test.py:" (space separates patterns!)\n'
        '     Finding "def test_" in files containing "test" at end of path:\n'
        '     fuzzy_filter="def test_ /test.py:" (matches src/test.py, lib/test.py)\n\n'
        "Returns: { matches: Array<{file: string, line: number, content: string}> } or { error: string }"
    )
)
def fuzzy_search_content(
    fuzzy_filter: str,
    path: str = ".",
    hidden: bool = False,
    limit: int = 20,
    rg_flags: str = "",
    multiline: bool = False,
    content_only: bool = False,
) -> dict[str, Any]:
    """Search all content then apply fuzzy filtering - similar to 'rg . | fzf'.

    By default, matches on both file paths AND content (skips line numbers).
    With content_only=True, matches ONLY on content, ignoring file paths.
    """
    if not fuzzy_filter:
        return {"error": "'fuzzy_filter' argument is required"}

    rg_bin = _require(RG_EXECUTABLE, "rg")
    fzf_bin = _require(FZF_EXECUTABLE, "fzf")

    try:
        if multiline:
            # For multiline mode, get files and treat each as a single record
            rg_list_cmd = [rg_bin, "--files"]
            if hidden:
                rg_list_cmd.append("--hidden")
            if rg_flags:
                # Filter out options that don't apply to --files
                safe_flags = []
                for flag in rg_flags.split():
                    if flag not in [
                        "-n",
                        "--line-number",
                        "-H",
                        "--with-filename",
                        "--no-heading",
                    ]:
                        safe_flags.append(flag)
                rg_list_cmd.extend(safe_flags)
            search_path = str(Path(path).resolve())
            rg_list_cmd.append(search_path)

            # Get file list
            file_list_result = subprocess.check_output(rg_list_cmd, text=True)
            file_paths = [
                str(Path(p).resolve()) for p in file_list_result.splitlines() if p
            ]

            # Build multiline input with file contents
            multiline_input = b""
            for file_path in file_paths:
                try:
                    path_obj = Path(file_path)
                    with path_obj.open("rb") as f:
                        content = f.read()
                        # Create record: filename + content + null separator
                        record = f"{file_path}:\n".encode() + content + b"\0"
                        multiline_input += record
                except (OSError, UnicodeDecodeError):
                    continue

            if not multiline_input:
                return {"matches": []}

            # Use fzf with multiline support
            fzf_cmd = [
                fzf_bin,
                "--filter",
                fuzzy_filter,
                "--read0",
                "--print0",
            ]

            fzf_proc = subprocess.Popen(
                fzf_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=False
            )
            out_bytes, _ = fzf_proc.communicate(multiline_input)

            # Parse multiline results - return as file records
            matches = []
            if out_bytes:
                for chunk in out_bytes.split(b"\0"):
                    if chunk:
                        try:
                            decoded = chunk.decode("utf-8")
                            # Extract filename from first line
                            if ":\n" in decoded:
                                file_part, content_part = decoded.split(":\n", 1)
                                matches.append(
                                    {
                                        "file": file_part.strip(),
                                        "line": 1,  # Multiline records don't have specific line numbers
                                        "content": content_part.strip()[:200] + "..."
                                        if len(content_part) > 200
                                        else content_part.strip(),
                                    }
                                )
                        except UnicodeDecodeError:
                            continue
        else:
            # Standard mode - line-by-line results
            rg_cmd = [
                rg_bin,
                "--line-number",
                "--no-heading",
                "--color=never",
            ]
            if hidden:
                rg_cmd.append("--hidden")
            if rg_flags:
                rg_cmd.extend(rg_flags.split())
            search_path = str(Path(path).resolve())
            rg_cmd.extend([".", search_path])  # Always search all lines

            # Pipe through fzf for fuzzy filtering
            # Default: match on file path (field 1) and content (field 3+), skip line number
            if content_only:
                # Match only on content (field 3+), ignore file path and line number
                fzf_cmd = [
                    fzf_bin,
                    "--filter",
                    fuzzy_filter,
                    "--delimiter",
                    ":",
                    "--nth=3..",
                ]
            else:
                # Match on file path (field 1) and content (field 3+), skip line number
                fzf_cmd = [
                    fzf_bin,
                    "--filter",
                    fuzzy_filter,
                    "--delimiter",
                    ":",
                    "--nth=1,3..",
                ]

            logger.debug("Pipeline: %s | %s", " ".join(rg_cmd), " ".join(fzf_cmd))

            rg_proc = subprocess.Popen(
                rg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            fzf_proc = subprocess.Popen(
                fzf_cmd, stdin=rg_proc.stdout, stdout=subprocess.PIPE, text=True
            )
            rg_proc.stdout.close()

            out, _ = fzf_proc.communicate()
            rg_stderr = rg_proc.stderr.read().decode() if rg_proc.stderr else ""
            rg_proc.wait()

            if rg_proc.returncode != 0 and rg_proc.returncode != 1:  # 1 = no matches
                return {
                    "error": rg_stderr.strip()
                    or f"ripgrep failed with code {rg_proc.returncode}"
                }

            # Parse results
            matches = []
            for line in out.splitlines():
                if not line:
                    continue

                # Parse ripgrep output: file:line:content
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    try:
                        matches.append(
                            {
                                "file": parts[0],
                                "line": int(parts[1]),
                                "content": parts[2].strip(),
                            }
                        )
                    except (ValueError, IndexError):
                        continue

        # Apply limit
        matches = matches[:limit]

        return {"matches": matches}
    except subprocess.CalledProcessError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: fuzzy_search_documents
# ---------------------------------------------------------------------------
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

    # Check if rga is available
    if not RGA_EXECUTABLE:
        return {"error": "ripgrep-all (rga) is not installed. Install it first."}

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

        # Run rga and collect JSON output
        rga_proc = subprocess.Popen(
            rga_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        # Parse JSON lines and build formatted output for fzf
        formatted_lines = []
        line_to_data = {}  # Map formatted line to original data

        for line in rga_proc.stdout:
            if not line.strip():
                continue

            try:
                data = json.loads(line)
                if data.get("type") == "match":
                    match_data = data.get("data", {})
                    file_path = match_data.get("path", {}).get("text", "")
                    line_num = match_data.get("line_number") or 0

                    # Extract text from lines
                    lines = match_data.get("lines", {})
                    text = lines.get("text", "")

                    # Extract matched text from submatches
                    submatches = match_data.get("submatches", [])
                    match_text = submatches[0]["match"]["text"] if submatches else text

                    # Build formatted line for fzf
                    formatted = f"{file_path}:{line_num}:{text}"
                    formatted_lines.append(formatted)

                    # Store mapping for later reconstruction
                    line_to_data[formatted] = {
                        "file": file_path,
                        "line": line_num,
                        "content": text,
                        "match_text": match_text,
                        "page": (line_num or 0)
                        + 1,  # For PDFs, convert to 1-based page number
                    }
            except json.JSONDecodeError:
                continue

        rga_proc.wait()

        if not formatted_lines:
            return {"matches": []}

        # Feed to fzf for fuzzy filtering
        fzf_input = "\n".join(formatted_lines)
        fzf_cmd = [fzf_bin, "--filter", fuzzy_filter]

        fzf_proc = subprocess.Popen(
            fzf_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
        )
        out, _ = fzf_proc.communicate(fzf_input)

        # Build results from filtered lines
        matches = []
        for line in out.splitlines():
            if line in line_to_data:
                matches.append(line_to_data[line])

        # Apply limit
        matches = matches[:limit]

        return {"matches": matches}
    except subprocess.CalledProcessError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print_examples():
    """Print interactive examples and usage patterns."""
    examples = """
FUZZY SEARCH EXAMPLES
====================

1. Find TODO comments about databases:
   $ ./mcp_fuzzy_search.py search-content "TODO database"

2. Find test functions mentioning 'seer' and 'credit':
   $ ./mcp_fuzzy_search.py search-content "def test_ seer credit"

3. Find Python files in src directory:
   $ ./mcp_fuzzy_search.py search-files "src py$"

4. Find all async functions with error handling:
   $ ./mcp_fuzzy_search.py search-content "async def error try except"

5. Search with case-insensitive matching:
   $ ./mcp_fuzzy_search.py search-content "config" --rg-flags "-i"

6. CONTENT-ONLY MODE - Search content without matching file paths:
   $ ./mcp_fuzzy_search.py search-content "test" --content-only
   # Won't match files named 'test.py', only content with 'test'

7. DEFAULT MODE - Match both file paths AND content:
   $ ./mcp_fuzzy_search.py search-content "test.py: update"
   # Finds 'update' in files named test.py

8. SPACES MATTER - Find files named 'test' with no extension in temp dir:
   $ ./mcp_fuzzy_search.py search-files "temp /test$"  # Space before /test$ is critical!
   vs
   $ ./mcp_fuzzy_search.py search-files "temp/test$"   # Different! Looks for 'temp/test' at end

FUZZY FILTER SYNTAX
==================

✓ Multiple terms (AND logic): "update spend"
✓ OR logic: "update | modify | change"
✓ Exact match: "'exact phrase'"
✓ File filtering: "test.py: update"
✓ Exclusion: "update !test"

CRITICAL: UNDERSTANDING SPACES
=============================
Spaces separate fuzzy patterns! This is crucial for precise searches:

  "temp/test" → One pattern: paths containing 'temp/test'
  "temp test" → Two patterns: paths containing 'temp' AND 'test' anywhere
  "temp /test$" → Two patterns: paths with 'temp' AND ending with '/test'
  "src config.json" → Two patterns: paths with 'src' AND 'config.json'
  "My\\ Documents" → One pattern: paths containing literal 'My Documents'

ADDITIONAL FZF FEATURES
======================
- Smart Case: lowercase query = case-insensitive, Mixed Case = case-sensitive
- Single Quote Prefix: 'term → exact match (disables fuzzy)
- Double Single Quotes: ''term'' → exact match at word boundaries
- Latin Normalization: café matches cafe (unless --literal is used)

UNDERSTANDING THE PIPELINE
=========================

Files → ripgrep (all lines) → Lines → fzf (fuzzy_filter) → Results
                                         ↑
                                   fuzzy search (NO REGEX!)

MATCHING BEHAVIOR
================
Default mode: Matches on file paths (field 1) AND content (field 3+)
  - Allows filtering like "test.py: update" to find updates in test.py files
  - Line numbers (field 2) are always skipped to prevent accidental matches

Content-only mode (--content-only): Matches ONLY on content (field 3+)
  - Pure content search when file paths might interfere
  - Useful when searching for terms that might appear in filenames
"""
    print(examples)


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Fuzzy search with ripgrep + fzf. Default matches file paths AND content.",
        epilog="fzf syntax: 'term1 term2' (AND), 'a | b' (OR), '^start', 'end$', '!exclude'",
    )

    # Add --examples flag
    parser.add_argument(
        "--examples",
        action="store_true",
        help="Show interactive examples and common usage patterns",
    )

    sub = parser.add_subparsers(dest="cmd", required=False)

    # search-files subcommand
    p_files = sub.add_parser("search-files", help="Fuzzy search file paths")
    p_files.add_argument("fuzzy_filter", help="fzf query: 'config .json$ !test'")
    p_files.add_argument("path", nargs="?", default=".", help="Directory to search")
    p_files.add_argument("--hidden", action="store_true", help="Include hidden files")
    p_files.add_argument("--limit", type=int, default=20, help="Max results")
    p_files.add_argument(
        "--multiline", action="store_true", help="Search file contents (multiline)"
    )

    # search-content subcommand
    p_content = sub.add_parser("search-content", help="Fuzzy search file content")
    p_content.add_argument("fuzzy_filter", help="fzf query: 'update !test TODO'")
    p_content.add_argument("path", nargs="?", default=".", help="Directory to search")
    p_content.add_argument("--hidden", action="store_true", help="Include hidden files")
    p_content.add_argument("--limit", type=int, default=20, help="Max results")
    p_content.add_argument("--rg-flags", default="", help="Extra ripgrep flags")
    p_content.add_argument(
        "--multiline", action="store_true", help="Search multiline records"
    )
    p_content.add_argument(
        "--content-only",
        action="store_true",
        help="Match only content, ignore file paths",
    )

    # search-documents subcommand
    p_docs = sub.add_parser("search-documents", help="Search PDFs and documents")
    p_docs.add_argument("fuzzy_filter", help="fzf query")
    p_docs.add_argument("path", nargs="?", default=".", help="Directory to search")
    p_docs.add_argument(
        "--file-types", default="", help="Comma-separated types (pdf,docx,epub)"
    )
    p_docs.add_argument("--limit", type=int, default=20, help="Max results")

    # extract-pdf subcommand
    p_pdf = sub.add_parser("extract-pdf", help="Extract pages from PDF")
    p_pdf.add_argument("file", help="PDF file path")
    p_pdf.add_argument("pages", help="Pages: 'v,vii,1,5-8,ToC'")
    p_pdf.add_argument(
        "--format",
        default="markdown",
        choices=["markdown", "html", "plain"],
        help="Output format",
    )
    p_pdf.add_argument("--preserve-layout", action="store_true", help="Preserve layout")
    p_pdf.add_argument(
        "--no-clean-html",
        dest="clean_html",
        action="store_false",
        help="Keep HTML styling",
    )

    ns = parser.parse_args()

    if ns.examples:
        _print_examples()
        return

    if not ns.cmd:
        parser.print_help()
        return

    # Execute command and print result
    if ns.cmd == "search-files":
        res = fuzzy_search_files(
            ns.fuzzy_filter, ns.path, ns.hidden, ns.limit, ns.multiline
        )
    elif ns.cmd == "search-content":
        res = fuzzy_search_content(
            ns.fuzzy_filter,
            ns.path,
            ns.hidden,
            ns.limit,
            ns.rg_flags,
            ns.multiline,
            ns.content_only,
        )
    elif ns.cmd == "search-documents":
        res = fuzzy_search_documents(
            ns.fuzzy_filter, ns.path, ns.file_types, True, ns.limit
        )
    elif ns.cmd == "extract-pdf":
        res = extract_pdf_pages(
            ns.file, ns.pages, ns.format, ns.preserve_layout, ns.clean_html
        )
    else:
        parser.error(f"Unknown command: {ns.cmd}")

    print(json.dumps(res, indent=2))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) > 1:
        _cli()
    else:
        # Ensure required binaries before exposing tools
        _require(RG_EXECUTABLE, "rg")
        _require(FZF_EXECUTABLE, "fzf")
        mcp.run()
