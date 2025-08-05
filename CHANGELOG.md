# Changelog

## [Unreleased]

### Added
- **Root Path Validation**: Added safety mechanism to prevent accidental slow searches from root directory
  - Added `confirm_root` parameter (default: false) to `fuzzy_search_files`, `fuzzy_search_content`, and `fuzzy_search_documents`
  - Functions now check if search path resolves to root directory ("/" on Unix-like systems, drive root on Windows)
  - Returns error message when attempting to search from root without explicitly setting `confirm_root=True`
  - Prevents unintended performance issues from searching entire filesystem
  - Available in both MCP tool interface and CLI with `--confirm-root` flag
  - Cross-platform support for Windows drive roots (e.g., "C:\", "/") and Unix root ("/")
- **Page Labels Slicing**: Added optional `start` and `limit` parameters to `get_pdf_page_labels` tool
  - `start`: 0-based index to begin retrieving labels (e.g., start=100 begins at page 100)
  - `limit`: Maximum number of labels to return (e.g., limit=20 returns at most 20 labels)
  - Useful for paginating through large PDFs or getting specific page ranges
  - Available in both CLI (`--start`, `--limit`) and MCP tool interface
- **PDF Page Label Support**: Enhanced `extract-pdf` tool to support page labels/aliases (e.g., "v-vii", "ToC", "i", "ii") as they appear in PDF readers
  - Migrated to PyMuPDF for native page label support with better performance
  - Added `_parse_page_spec_pymupdf()` function using PyMuPDF's `get_page_numbers()` API
  - Support for single labels, ranges, and mixed specifications
  - Direct page label extraction via PyMuPDF's page.get_label() method
- **Page Indexing Options**: Added flexible page indexing modes to `extract-pdf` tool
  - `zero_based` flag: Interpret page numbers as 0-based indices (0 = first page)
  - `one_based` flag: Interpret page numbers as 1-based indices (1 = first page)
  - Useful for programmatic access when page labels are not needed
  - Available in both CLI (`--zero-based`, `--one-based`) and MCP tool interface
  - Flags are mutually exclusive - only one indexing mode can be used at a time
- **Page Labels in Document Search**: Enhanced `fuzzy_search_documents` to return page labels for PDF search results
  - Returns actual PDF page labels (e.g., "vii", "ToC", "1") alongside page numbers
  - Builds page index to label mapping using PyMuPDF for accurate label extraction
- **HTML Stripping**: Added `clean_html` parameter (default: true) to strip HTML styling tags from PDF extraction output
  - Uses pandoc with disabled extensions (`-native_divs`, `-native_spans`, `-raw_html`) for clean markdown output
- **Fuzzy Search Filtering**: Added optional `fuzzy_hint` parameter to `extract_pdf_pages` for content-based page filtering
  - Filter multiple extracted pages by content using fzf
  - Useful for extracting only relevant pages from large page ranges
- **New PDF Information Tools**:
  - `get_pdf_page_labels`: Returns mapping of all page indices to their labels
  - `get_pdf_page_count`: Returns total number of pages in a PDF
  - `get_pdf_outline`: Extracts table of contents/bookmarks from PDFs
    - Returns hierarchical outline structure with levels, titles, page numbers, and page labels
    - Supports `simple` mode (default) with basic info or detailed mode with link information
    - Optional `max_depth` parameter to limit traversal depth for deep hierarchies
    - Optional `fuzzy_filter` parameter to search outline entries by title using fzf
    - Handles PDFs without outlines gracefully by returning empty structure
    - Available in both CLI (`pdf-outline` command) and MCP tool interface
- **Type Checking**: Added support for `ty` type checker
  - Updated Makefile to use `ty check --exclude git-repos`
  - Added `ty>=0.0.1a16` as dev dependency

### Changed
- **PDF Processing Migration**: Replaced pdfminer.six with PyMuPDF (fitz) for all PDF operations
  - Better performance and native page label support
  - Simplified implementation with PyMuPDF's high-level APIs
  - Updated all PDF-related tests to mock PyMuPDF instead of subprocess/pdfminer
- **Type Checking**: Replaced pyright with ty in Makefile for faster type checking
- **Document Search Output**: Improved `fuzzy_search_documents` results for better LLM consumption
  - Removed "Page N: " prefix from content field (e.g., "topology." instead of "Page 542: topology.")
  - Added `page_index_0based` field for 0-based page indexing alongside existing 1-based `page` field
  - Makes programmatic page access clearer with both 1-based and 0-based indices
  - Page number is available as `page` (1-based), `page_index_0based` (0-based), and `page_label` (PDF label)

### Fixed
- **File Path Handling in Content Search**: Fixed `fuzzy_search_content` to properly handle single file paths
  - Added `--with-filename` flag when searching a single file to ensure consistent output format
  - Previously returned empty results when given a file path instead of directory because ripgrep doesn't include filenames by default when searching single files
  - Now provides consistent output format regardless of whether searching a file or directory
- **PDF Extraction HTML Output**: Fixed issue where PDF extraction was outputting HTML styling tags like `<span style="font-family: TimesLTPro-Roman; font-size:9px">`
- **Page Extraction Accuracy**: Fixed bug where requesting page "14" would return wrong page content
  - Properly handles PDF page labels vs physical page numbers
- **Type Checking Issues**: Fixed multiple type annotation issues across all files
  - Added proper type annotations for `fuzzy_hint: str | None`
  - Fixed subprocess stdout type issues with proper None checks
  - Added `TYPE_CHECKING` imports and type annotations for conditional imports
  - Fixed `mcp.context` attribute issues with type: ignore comments
- **Test Assertion**: Added missing assertion for `proc.stdin` in CLI tests
- **Test Tool Count**: Updated `test_list_tools` to expect 7 tools with addition of `get_pdf_outline`

### Dependencies
- Replaced `pdfminer.six>=20221105` with `PyMuPDF>=1.23.0` for PDF operations
- Added `ty>=0.0.1a16` as development dependency for type checking
- Updated script inline dependency declaration to use PyMuPDF