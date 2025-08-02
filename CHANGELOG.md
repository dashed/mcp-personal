# Changelog

## [Unreleased]

### Added
- **PDF Page Label Support**: Enhanced `extract-pdf` tool to support page labels/aliases (e.g., "v-vii", "ToC", "i", "ii") as they appear in PDF readers
  - Added `_build_page_label_mapping()` function to extract page labels from PDFs using pdfminer.six
  - Added `_parse_page_spec()` function to parse page specifications with support for:
    - Single page labels: "v", "ToC", "Introduction"  
    - Page ranges: "i-v", "1-10"
    - Mixed specifications: "i,iii,5-7"
    - Fallback to 0-based indices when labels aren't found
  - Added optional dependency on `pdfminer.six>=20221105` for PDF page label extraction
  - Graceful degradation when pdfminer.six is not available (falls back to numeric-only page specifications)
  - Comprehensive test suite with mocking to avoid requiring actual PDF files

### Fixed
- Fixed `pdf2txt.py` command line argument ordering issue where file path was incorrectly placed after options
- Fixed type checking errors in `mcp_fd_server.py` by adding proper type annotations
- Fixed code formatting issues to pass CI checks

### Dependencies
- Added `pdfminer.six>=20221105` as optional dependency in `pyproject.toml`
- Added `pdfminer.six>=20221105` to script inline dependency declaration