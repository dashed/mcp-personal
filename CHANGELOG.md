# Changelog

## [Unreleased]

### Added
- **PDF Page Label Support**: Enhanced `extract-pdf` tool to support page labels/aliases (e.g., "v-vii", "ToC", "i", "ii") as they appear in PDF readers
  - Migrated to PyMuPDF for native page label support with better performance
  - Added `_parse_page_spec_pymupdf()` function using PyMuPDF's `get_page_numbers()` API
  - Support for single labels, ranges, and mixed specifications
  - Direct page label extraction via PyMuPDF's page.get_label() method
- **HTML Stripping**: Added `clean_html` parameter (default: true) to strip HTML styling tags from PDF extraction output
  - Uses pandoc with disabled extensions (`-native_divs`, `-native_spans`, `-raw_html`) for clean markdown output
- **Fuzzy Search Filtering**: Added optional `fuzzy_hint` parameter to `extract_pdf_pages` for content-based page filtering
  - Filter multiple extracted pages by content using fzf
  - Useful for extracting only relevant pages from large page ranges
- **New PDF Information Tools**:
  - `get_pdf_page_labels`: Returns mapping of all page indices to their labels
  - `get_pdf_page_count`: Returns total number of pages in a PDF
- **Type Checking**: Added support for `ty` type checker
  - Updated Makefile to use `ty check --exclude git-repos`
  - Added `ty>=0.0.1a16` as dev dependency

### Changed
- **PDF Processing Migration**: Replaced pdfminer.six with PyMuPDF (fitz) for all PDF operations
  - Better performance and native page label support
  - Simplified implementation with PyMuPDF's high-level APIs
  - Updated all PDF-related tests to mock PyMuPDF instead of subprocess/pdfminer
- **Type Checking**: Replaced pyright with ty in Makefile for faster type checking

### Fixed
- **PDF Extraction HTML Output**: Fixed issue where PDF extraction was outputting HTML styling tags like `<span style="font-family: TimesLTPro-Roman; font-size:9px">`
- **Page Extraction Accuracy**: Fixed bug where requesting page "14" would return wrong page content
  - Properly handles PDF page labels vs physical page numbers
- **Type Checking Issues**: Fixed multiple type annotation issues across all files
  - Added proper type annotations for `fuzzy_hint: str | None`
  - Fixed subprocess stdout type issues with proper None checks
  - Added `TYPE_CHECKING` imports and type annotations for conditional imports
  - Fixed `mcp.context` attribute issues with type: ignore comments
- **Test Assertion**: Added missing assertion for `proc.stdin` in CLI tests

### Dependencies
- Replaced `pdfminer.six>=20221105` with `PyMuPDF>=1.23.0` for PDF operations
- Added `ty>=0.0.1a16` as development dependency for type checking
- Updated script inline dependency declaration to use PyMuPDF