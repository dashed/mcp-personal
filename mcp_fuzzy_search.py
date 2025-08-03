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
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    import fitz

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


def _parse_page_spec_zero_based(page_spec: str, doc) -> list[int]:
    """Parse a page specification as 0-based indices directly.

    Handles:
    - Single indices: "0", "14", "266"
    - Ranges: "0-4", "266-273"

    Args:
        page_spec: Page specification string (0-based indices)
        doc: PyMuPDF document object

    Returns:
        List of 0-based page indices
    """
    indices = []

    # Handle range
    if "-" in page_spec:
        parts = page_spec.split("-", 1)
        try:
            start = int(parts[0].strip())
            end = int(parts[1].strip())

            # Validate range
            if start < 0 or end >= doc.page_count:
                return []
            if start > end:
                return []

            # Add all indices in range (inclusive)
            indices.extend(range(start, end + 1))
        except ValueError:
            return []
    else:
        # Single index
        try:
            idx = int(page_spec.strip())
            if 0 <= idx < doc.page_count:
                indices.append(idx)
        except ValueError:
            return []

    return indices


def _parse_page_spec_one_based(page_spec: str, doc) -> list[int]:
    """Parse a page specification as 1-based indices directly.

    Handles:
    - Single indices: "1", "15", "267"
    - Ranges: "1-5", "267-274"

    Args:
        page_spec: Page specification string (1-based indices)
        doc: PyMuPDF document object

    Returns:
        List of 0-based page indices
    """
    indices = []

    # Handle range
    if "-" in page_spec:
        parts = page_spec.split("-", 1)
        try:
            start = int(parts[0].strip())
            end = int(parts[1].strip())

            # Convert 1-based to 0-based
            start_idx = start - 1
            end_idx = end - 1

            # Validate range
            if start_idx < 0 or end_idx >= doc.page_count:
                return []
            if start_idx > end_idx:
                return []

            # Add all indices in range (inclusive)
            indices.extend(range(start_idx, end_idx + 1))
        except ValueError:
            return []
    else:
        # Single page
        try:
            page_num = int(page_spec.strip())
            # Convert 1-based to 0-based
            page_idx = page_num - 1

            if 0 <= page_idx < doc.page_count:
                indices.append(page_idx)
        except ValueError:
            return []

    return indices


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


def _filter_pages_fuzzy(
    page_data: list[tuple[int, str, str]], fuzzy_hint: str, format_type: str
) -> list[tuple[int, str, str]]:
    """Filter extracted pages using fuzzy search on their content.

    Args:
        page_data: List of (page_idx, page_label, page_content) tuples
        fuzzy_hint: Fuzzy search query to filter pages
        format_type: "html" or "text" - the format of page_content

    Returns:
        Filtered list of page data tuples matching the fuzzy hint
    """
    if not FZF_EXECUTABLE or not fuzzy_hint:
        return page_data  # Can't filter without fzf or hint

    try:
        # Build multiline input for fzf
        multiline_input = b""
        record_map = {}  # Map record identifier to page data

        for idx, label, content in page_data:
            # Create searchable text (strip HTML if needed for better searching)
            if format_type == "html":
                # Strip HTML tags for searching
                import re

                search_text = re.sub(r"<[^>]+>", " ", content)
                # Normalize whitespace
                search_text = " ".join(search_text.split())
            else:
                search_text = content

            # Create record identifier
            record_id = f"Page {idx + 1} (Label: {label})"

            # Create full record for fzf: identifier + content + null separator
            record = f"{record_id}\n{search_text}\0"
            record_bytes = record.encode("utf-8", errors="ignore")
            multiline_input += record_bytes

            # Store mapping from identifier to full page data
            record_map[record_id] = (idx, label, content)

        if not multiline_input:
            return page_data

        # Run fzf with multiline filtering
        fzf_cmd = [
            FZF_EXECUTABLE,
            "--filter",
            fuzzy_hint,
            "--read0",  # Read null-separated input
            "--print0",  # Print null-separated output
        ]

        result = subprocess.run(
            fzf_cmd, input=multiline_input, capture_output=True, check=False
        )

        # Parse results and rebuild matching pages list
        matched_pages = []
        if result.stdout:
            for chunk in result.stdout.split(b"\0"):
                if chunk:
                    try:
                        record_text = chunk.decode("utf-8")
                        # Extract the page identifier (first line)
                        lines = record_text.split("\n", 1)
                        if lines and lines[0] in record_map:
                            matched_pages.append(record_map[lines[0]])
                    except UnicodeDecodeError:
                        continue

        # Return matched pages, or all pages if no matches (to avoid empty result)
        return matched_pages if matched_pages else page_data

    except Exception:
        # On any error, return original page data
        return page_data


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
        "  clean_html (bool, optional): Strip HTML styling tags. Default: true.\n"
        "  fuzzy_hint (str, optional): Fuzzy search to filter extracted pages by content.\n"
        "  zero_based (bool, optional): Interpret page numbers as 0-based indices. Default: false.\n"
        "  one_based (bool, optional): Interpret page numbers as 1-based indices. Default: false.\n\n"
        "Note: zero_based and one_based cannot be used together.\n\n"
        "Page specifications (default - when both flags are false):\n"
        "  - Page labels: 'v', 'vii', 'ToC', 'Introduction' (as shown in PDF readers)\n"
        "  - Ranges: 'v-vii', '1-5'\n"
        "  - Physical pages: '1', '14' (1-based if not found as label)\n"
        "  - Mixed: 'v,vii,1,5-8,ToC'\n\n"
        "Page specifications (when one_based=true):\n"
        "  - Direct 1-based pages: '1', '15', '267' (physical page numbers)\n"
        "  - Ranges: '1-5' (pages 1-5), '267-274' (pages 267-274)\n"
        "  - Mixed: '1,2,267,574'\n"
        "  - No label lookup performed - all numbers treated as 1-based pages\n\n"
        "Page specifications (when zero_based=true):\n"
        "  - Direct indices: '0', '14', '266' (0-based page indices)\n"
        "  - Ranges: '0-4' (pages 1-5), '266-273' (pages 267-274)\n"
        "  - Mixed: '0,1,266,573'\n"
        "  - No label lookup performed - all numbers treated as 0-based indices\n\n"
        "Examples:\n"
        "  Extract roman numeral pages: pages='v,vi,vii'\n"
        "  Extract range: pages='v-vii'\n"
        "  Extract by page number: pages='14'\n"
        "  Extract mixed: pages='ToC,v-vii,1,2'\n"
        "  Extract with fuzzy filter: pages='1-50', fuzzy_hint='neural network'\n"
        "  Extract with 1-based pages: pages='1,2,3', one_based=true (gets pages 1,2,3)\n"
        "  Extract pages 267-274: pages='267-274', one_based=true\n"
        "  Extract with 0-based indices: pages='0,1,2', zero_based=true (gets pages 1,2,3)\n"
        "  Extract pages 267-274: pages='266-273', zero_based=true\n\n"
        "Returns: { content: string, pages_extracted: number[], page_labels: string[], format: string } or { error: string }"
    )
)
def extract_pdf_pages(
    file: str,
    pages: str,
    format: str = "markdown",
    preserve_layout: bool = False,
    clean_html: bool = True,
    fuzzy_hint: str | None = None,
    zero_based: bool = False,
    one_based: bool = False,
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

    # Validate that zero_based and one_based are not both True
    if zero_based and one_based:
        return {"error": "Cannot use both zero_based and one_based flags together"}

    try:
        # Open PDF with PyMuPDF
        doc: fitz.Document = fitz.open(pdf_path)

        # Parse page specifications
        page_indices = []
        index_to_spec = {}  # Map page index to original specification

        for page_spec in pages.split(","):
            page_spec = page_spec.strip()
            if not page_spec:
                continue

            # Use appropriate parsing function based on flags
            if zero_based:
                spec_indices = _parse_page_spec_zero_based(page_spec, doc)
                if not spec_indices:
                    doc.close()
                    return {
                        "error": f"Invalid page specification: '{page_spec}'. Must be a valid 0-based index or range (0 to {doc.page_count - 1})."
                    }
            elif one_based:
                spec_indices = _parse_page_spec_one_based(page_spec, doc)
                if not spec_indices:
                    doc.close()
                    return {
                        "error": f"Invalid page specification: '{page_spec}'. Must be a valid 1-based page number or range (1 to {doc.page_count})."
                    }
            else:
                spec_indices = _parse_page_spec_pymupdf(page_spec, doc)
                if not spec_indices:
                    doc.close()
                    return {
                        "error": f"Invalid page specification: '{page_spec}'. Not found as page label or valid page number."
                    }

            # Map each index to its original specification
            # For ranges, map each index to its individual page number/label
            if "-" in page_spec and len(spec_indices) > 1:
                # This is a range - map each page to its actual label or index
                for idx in spec_indices:
                    if idx not in index_to_spec:  # Only map first occurrence
                        if zero_based:
                            # For zero-based mode, use the 0-based index
                            index_to_spec[idx] = str(idx)
                        elif one_based:
                            # For one-based mode, use the 1-based page number
                            index_to_spec[idx] = str(idx + 1)
                        else:
                            # Get the actual label for this page
                            labels = doc.get_page_labels()  # type: ignore[attr-defined]
                            if labels and idx < len(labels):
                                index_to_spec[idx] = labels[idx]
                            else:
                                index_to_spec[idx] = str(idx + 1)
            else:
                # Single page specification
                for idx in spec_indices:
                    if idx not in index_to_spec:  # Only map first occurrence
                        index_to_spec[idx] = page_spec

            page_indices.extend(spec_indices)

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
        # Determine extraction format
        if format == "html" or (format == "markdown" and PANDOC_EXECUTABLE):
            # Extract as HTML for pandoc conversion
            extract_format = "html"
        else:
            # Extract as plain text
            extract_format = "text"

        # Extract pages and store individually for potential filtering
        page_data = []  # List of (idx, label, content) tuples

        for idx in unique_indices:
            page = doc[idx]

            # Get page label for context
            labels = doc.get_page_labels()  # type: ignore[attr-defined]
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
            else:
                # Plain text extraction
                page_content = page.get_text("text")

            # Store page data for filtering
            page_data.append((idx, page_label, page_content))

        # Apply fuzzy filtering if hint provided
        if fuzzy_hint:
            page_data = _filter_pages_fuzzy(page_data, fuzzy_hint, extract_format)

        # Build final content from (potentially filtered) pages
        content_parts = []
        filtered_indices = []  # Track which pages made it through filtering

        for idx, page_label, page_content in page_data:
            filtered_indices.append(idx)

            if extract_format == "html":
                # Add page marker
                content_parts.append(
                    f'<div class="page" data-page="{idx + 1}" data-label="{page_label}">'
                )
                content_parts.append(page_content)
                content_parts.append("</div>")
            else:
                # Plain text - add page marker
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
        # Get original page specifications for extracted (and filtered) pages
        extracted_labels = []
        for idx in filtered_indices:
            # Use the original specification that was used to request this page
            extracted_labels.append(index_to_spec.get(idx, str(idx + 1)))

        # Close the document
        doc.close()

        result = {
            "content": content,
            "pages_extracted": filtered_indices,
            "page_labels": extracted_labels,
            "format": format,
        }

        # Add info about fuzzy filtering if it was applied
        if fuzzy_hint:
            result["fuzzy_hint"] = fuzzy_hint
            result["pages_before_filter"] = len(unique_indices)
            result["pages_after_filter"] = len(filtered_indices)

        return result

    except Exception as e:
        return {"error": f"Failed to extract pages: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool: get_pdf_page_labels
# ---------------------------------------------------------------------------
@mcp.tool(
    description=(
        "Get all page labels from a PDF file.\n\n"
        "Returns a mapping of page indices (0-based) to their labels.\n"
        "This is useful for understanding what page labels are available before extracting.\n\n"
        "Args:\n"
        "  file (str): Path to PDF file. Required.\n"
        "  start (int, optional): Start index (0-based) for slicing results. Default: 0.\n"
        "  limit (int, optional): Maximum number of labels to return. Default: all pages.\n\n"
        "Returns: { page_count: number, page_labels: object } or { error: string }\n"
        "  where page_labels is a mapping like: {'0': 'i', '1': 'ii', '2': 'iii', '3': '1', ...}\n"
        "  The page_labels object will only contain entries for the requested range."
    )
)
def get_pdf_page_labels(
    file: str, start: int | None = None, limit: int | None = None
) -> dict[str, Any]:
    """Get all page labels from a PDF file."""
    if not file:
        return {"error": "'file' argument is required"}

    # Check if PyMuPDF is available
    if not PYMUPDF_AVAILABLE:
        return {
            "error": "PyMuPDF is not installed. Install it with: pip install PyMuPDF"
        }

    # Check if file exists
    pdf_path = Path(file)
    if not pdf_path.exists():
        return {"error": f"PDF file not found: {file}"}

    # Validate start and limit
    if start is not None and start < 0:
        return {"error": "start must be non-negative"}
    if limit is not None and limit <= 0:
        return {"error": "limit must be positive"}

    try:
        # Open PDF with PyMuPDF
        doc: fitz.Document = fitz.open(pdf_path)

        # Get page count
        page_count = doc.page_count

        # Determine range to process
        start_idx = start if start is not None else 0
        end_idx = page_count
        if limit is not None:
            end_idx = min(start_idx + limit, page_count)

        # Build page label mapping for the requested range
        page_label_map = {}
        for i in range(start_idx, end_idx):
            page = doc[i]
            label = page.get_label()
            page_label_map[str(i)] = label

        doc.close()

        return {"page_count": page_count, "page_labels": page_label_map}

    except Exception as e:
        return {"error": f"Failed to get page labels: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool: get_pdf_page_count
# ---------------------------------------------------------------------------
@mcp.tool(
    description=(
        "Get the total number of pages in a PDF file.\n\n"
        "Args:\n"
        "  file (str): Path to PDF file. Required.\n\n"
        "Returns: { page_count: number } or { error: string }"
    )
)
def get_pdf_page_count(file: str) -> dict[str, Any]:
    """Get the total number of pages in a PDF file."""
    if not file:
        return {"error": "'file' argument is required"}

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
        doc: fitz.Document = fitz.open(pdf_path)
        page_count = doc.page_count
        doc.close()

        return {"page_count": page_count}

    except Exception as e:
        return {"error": f"Failed to get page count: {str(e)}"}


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
            if rg_proc.stdout:
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
    # Enable debug logging for Windows investigation
    import logging
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(message)s')
    logger = logging.getLogger(__name__)
    
    logger.debug("fuzzy_search_content called with: fuzzy_filter=%r, path=%r, hidden=%r, limit=%r, rg_flags=%r, multiline=%r, content_only=%r", 
                 fuzzy_filter, path, hidden, limit, rg_flags, multiline, content_only)
    
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
            rg_cmd.extend([".", search_path])  # Search for all content in the path

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

            # Run ripgrep first to capture its output for debugging
            rg_proc = subprocess.run(
                rg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            
            logger.debug("Ripgrep returncode: %d", rg_proc.returncode)
            logger.debug("Ripgrep stdout length: %d", len(rg_proc.stdout))
            if rg_proc.stdout:
                logger.debug("Ripgrep stdout sample: %r", rg_proc.stdout[:200])
            if rg_proc.stderr:
                logger.debug("Ripgrep stderr: %r", rg_proc.stderr[:200])

            if rg_proc.returncode != 0 and rg_proc.returncode != 1:  # 1 = no matches
                return {
                    "error": rg_proc.stderr.strip()
                    or f"ripgrep failed with code {rg_proc.returncode}"
                }

            # Now run fzf with ripgrep's output
            fzf_proc = subprocess.run(
                fzf_cmd, input=rg_proc.stdout, stdout=subprocess.PIPE, text=True
            )
            
            logger.debug("Fzf returncode: %d", fzf_proc.returncode)
            logger.debug("Fzf stdout length: %d", len(fzf_proc.stdout))
            if fzf_proc.stdout:
                logger.debug("Fzf stdout sample: %r", fzf_proc.stdout[:200])
            
            out = fzf_proc.stdout

            # Parse results
            matches = []
            lines = out.splitlines()
            logger.debug("Total output lines to parse: %d", len(lines))
            
            for i, line in enumerate(lines):
                if not line:
                    continue

                logger.debug("Parsing line %d: %r", i, line)
                # Parse ripgrep output: file:line:content
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    try:
                        match = {
                            "file": parts[0],
                            "line": int(parts[1]),
                            "content": parts[2].strip(),
                        }
                        matches.append(match)
                        logger.debug("Added match: %r", match)
                    except (ValueError, IndexError) as e:
                        logger.debug("Failed to parse line %d: %s", i, e)
                        continue
                else:
                    logger.debug("Line %d has insufficient parts: %d", i, len(parts))
            
            logger.debug("Final matches count: %d", len(matches))

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
        "Returns: { matches: Array<{file, content, match_text, page?, page_index_0based?, page_label?}> }\n"
        "  - page: Physical page number (1-based) for PDF files\n"
        "  - page_index_0based: Zero-based page index for programmatic access (page - 1)\n"
        "  - page_label: Page label/alias as shown in PDF readers (e.g., 'v', 'ToC')"
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
            # Map common file types to rga adapters
            adapter_map = {
                "pdf": "poppler",
                "docx": "pandoc",
                "doc": "pandoc",
                "epub": "pandoc",
                "zip": "zip",
                "tar": "tar",
                "sqlite": "sqlite",
                "db": "sqlite",
            }
            adapters = []
            for ft in file_types.split(","):
                ft_clean = ft.strip().lower()
                adapter = adapter_map.get(ft_clean, ft_clean)
                adapters.append(adapter)

            # Join adapters with comma and add as single argument with equals sign
            adapter_string = "+" + ",".join(adapters)
            rga_cmd.append(f"--rga-adapters={adapter_string}")

        # Search pattern and path
        search_path = str(Path(path).resolve())
        # Use the fuzzy filter as the initial search pattern for rga
        # This will be further refined by fzf
        rga_cmd.extend([fuzzy_filter, search_path])

        # Debug: Log the command
        logger.debug(f"Running rga command: {' '.join(rga_cmd)}")

        # Run rga and collect JSON output with better subprocess handling
        rga_proc = subprocess.Popen(
            rga_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        # Parse JSON lines and build formatted output for fzf
        formatted_lines = []
        line_to_data = {}  # Map formatted line to original data

        # Cache for PDF page labels to avoid re-opening files
        pdf_page_labels_cache = {}

        # Read all stdout first to avoid broken pipe
        stdout_data = ""
        stderr_data = ""
        try:
            # Use communicate to properly handle large outputs
            result = rga_proc.communicate()
            if result:
                stdout_data = result[0] if result[0] else ""
                stderr_data = result[1] if len(result) > 1 and result[1] else ""
        except Exception as e:
            logger.warning(f"Error communicating with rga: {e}")

        # Log any stderr output
        if stderr_data:
            # Filter out broken pipe errors which are expected with large outputs
            if "broken pipe" not in stderr_data.lower():
                logger.debug(f"rga stderr: {stderr_data}")

        # Process the stdout data
        for line in stdout_data.splitlines():
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
                    # Strip newlines to ensure consistent formatting
                    text = text.strip()

                    # Extract matched text from submatches
                    submatches = match_data.get("submatches", [])
                    match_text = submatches[0]["match"]["text"] if submatches else text

                    # Parse page number from "Page N: " prefix if present
                    page_number = None
                    page_label = None
                    content = text  # Default to full text
                    if text.startswith("Page ") and ": " in text:
                        try:
                            parts = text.split(": ", 1)
                            page_prefix = parts[0]
                            page_number = int(page_prefix.replace("Page ", ""))
                            # Strip the "Page N: " prefix from content
                            content = parts[1] if len(parts) > 1 else text

                            # For PDF files, get page label
                            if file_path.lower().endswith(".pdf") and PYMUPDF_AVAILABLE:
                                # Get page labels from cache or load them
                                if file_path not in pdf_page_labels_cache:
                                    try:
                                        doc = fitz.open(file_path)
                                        # Build mapping from page index to actual label
                                        label_map = {}
                                        for i in range(doc.page_count):
                                            page = doc[i]
                                            label_map[i] = page.get_label()
                                        pdf_page_labels_cache[file_path] = label_map
                                        doc.close()
                                    except Exception:
                                        pdf_page_labels_cache[file_path] = {}

                                label_map = pdf_page_labels_cache[file_path]
                                # Page numbers from pdftotext are 1-based, convert to 0-based for index
                                page_idx = page_number - 1
                                if page_idx in label_map:
                                    page_label = label_map[page_idx]
                        except (ValueError, IndexError):
                            pass

                    # Build formatted line for fzf
                    formatted = f"{file_path}:{line_num}:{text}"
                    formatted_lines.append(formatted)

                    # Store mapping for later reconstruction
                    result_data = {
                        "file": file_path,
                        "line": line_num,
                        "content": content,
                        "match_text": match_text,
                    }

                    # Add page information if available
                    if page_number is not None:
                        result_data["page"] = (
                            page_number  # 1-based page number from ripgrep-all
                        )
                        result_data["page_index_0based"] = (
                            page_number - 1
                        )  # 0-based index for programmatic access
                        if page_label:
                            result_data["page_label"] = page_label

                    line_to_data[formatted] = result_data
            except json.JSONDecodeError:
                continue

        if not formatted_lines:
            logger.debug(f"No formatted lines from rga for path: {search_path}")
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
    p_pdf.add_argument(
        "--fuzzy-hint",
        help="Fuzzy search to filter extracted pages by content",
    )

    # Create a mutually exclusive group for indexing options
    index_group = p_pdf.add_mutually_exclusive_group()
    index_group.add_argument(
        "--zero-based",
        action="store_true",
        help="Interpret page numbers as 0-based indices (e.g., 0 = first page)",
    )
    index_group.add_argument(
        "--one-based",
        action="store_true",
        help="Interpret page numbers as 1-based indices (e.g., 1 = first page)",
    )

    # page-labels command
    p_labels = sub.add_parser("page-labels", help="Get all page labels from PDF")
    p_labels.add_argument("file", help="PDF file path")
    p_labels.add_argument(
        "--start", type=int, default=None, help="Start index (0-based)"
    )
    p_labels.add_argument(
        "--limit", type=int, default=None, help="Maximum number of labels to return"
    )

    # page-count command
    p_count = sub.add_parser("page-count", help="Get total page count from PDF")
    p_count.add_argument("file", help="PDF file path")

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
            ns.file,
            ns.pages,
            ns.format,
            ns.preserve_layout,
            ns.clean_html,
            getattr(ns, "fuzzy_hint", None),
            getattr(ns, "zero_based", False),
            getattr(ns, "one_based", False),
        )
    elif ns.cmd == "page-labels":
        res = get_pdf_page_labels(ns.file, ns.start, ns.limit)
    elif ns.cmd == "page-count":
        res = get_pdf_page_count(ns.file)
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
