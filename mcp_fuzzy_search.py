#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=0.1.0"]
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
- Smart Case: Case-insensitive by default, case-sensitive if query has uppercase
- Normalization: Accented chars normalized (café → cafe) unless --literal used
- Exact Boundary Match: ''word'' matches at word boundaries (_ counts as boundary)
- Scoring: Matches at word boundaries, path separators, camelCase get bonus points

Key Features
-----------
- Searches through ALL file contents by default
- Uses fuzzy matching to find relevant lines (NOT regex!)
- Supports advanced fzf syntax (OR, exact match, exclusions)
- Can be optimized with rg_flags for specific file types

Quick start
-----------
```bash
# Install required binaries
brew install ripgrep fzf        # macOS
# or apt install ripgrep fzf    # Debian/Ubuntu

chmod +x mcp_fuzzy_search.py

# 1. CLI usage
./mcp_fuzzy_search.py search-files "main" src
./mcp_fuzzy_search.py search-content "TODO implement" .
./mcp_fuzzy_search.py search-content "async await" . --content-only
./mcp_fuzzy_search.py --examples  # Show usage examples

# 2. Run as MCP server
./mcp_fuzzy_search.py
```
"""

from __future__ import annotations

import argparse
import json
import logging
import platform
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Binary discovery
# ---------------------------------------------------------------------------

RG_EXECUTABLE: str | None = shutil.which("rg")
FZF_EXECUTABLE: str | None = shutil.which("fzf")
RGA_EXECUTABLE: str | None = shutil.which("rga")
PDF2TXT_EXECUTABLE: str | None = shutil.which("pdf2txt.py")
PANDOC_EXECUTABLE: str | None = shutil.which("pandoc")

# Platform detection
IS_WINDOWS = platform.system() == "Windows"


def _normalize_path(path: str) -> str:
    """Normalize path to use forward slashes consistently across platforms."""
    # Replace backslashes with forward slashes for cross-platform consistency
    # This handles Windows paths even when running on Unix systems
    return path.replace("\\", "/")


def _parse_ripgrep_line(line: str) -> tuple[str, int, str] | None:
    """Parse a ripgrep output line, handling Windows paths correctly.

    Returns (file_path, line_number, content) or None if parsing fails.
    """
    if not line:
        return None

    # On Windows, check if line starts with a drive letter (e.g., C:\)
    if IS_WINDOWS and len(line) >= 3 and line[1] == ":" and line[0].isalpha():
        # Windows path format: C:\path\file.py:10:content
        parts = line.split(":", 3)
        if len(parts) >= 4:
            try:
                file_path = parts[0] + ":" + parts[1]  # C:\path\file.py
                line_num = int(parts[2])
                content = parts[3] if len(parts) > 3 else ""
                return (_normalize_path(file_path), line_num, content.strip())
            except (ValueError, IndexError):
                return None
    else:
        # Unix path format: /path/file.py:10:content
        parts = line.split(":", 2)
        if len(parts) >= 3:
            try:
                return (_normalize_path(parts[0]), int(parts[1]), parts[2].strip())
            except (ValueError, IndexError):
                return None

    return None


def _looks_like_regex(text: str) -> bool:
    """Detect if a string looks like a regex pattern rather than fuzzy search terms."""
    import re

    # Common regex metacharacters and patterns
    regex_indicators = [
        r"\.\*",  # .* (any characters)
        r"\.\+",  # .+ (one or more)
        r"\\\w",  # \w (word character)
        r"\\\d",  # \d (digit)
        r"\\\s",  # \s (whitespace)
        r"\[.*\]",  # [abc] character class
        r"\{.*\}",  # {n,m} quantifiers
        r"\(\?",  # (? special groups
        r"\$\s*$",  # $ at end
        r"^\s*\^",  # ^ at start
    ]

    # Check if string contains regex metacharacters
    for pattern in regex_indicators:
        if re.search(pattern, text):
            return True

    # Check for escaped characters
    if text.count("\\") > 0:
        return True

    return False


def _suggest_fuzzy_terms(regex_pattern: str) -> str:
    """Convert a regex pattern to suggested fuzzy search terms."""
    import re

    # Remove common regex metacharacters
    fuzzy = regex_pattern

    # Replace regex patterns with spaces
    replacements = [
        (r"\.\*", " "),
        (r"\.\+", " "),
        (r"\.", ""),
        (r"\^", ""),
        (r"\$", ""),
        (r"\[([^\]]+)\]", r"\1"),  # [abc] -> abc
        (r"\{[^\}]+\}", ""),
        (r"[\\()]", ""),
        (r"_", " "),  # Common in function names
    ]

    for pattern, replacement in replacements:
        fuzzy = re.sub(pattern, replacement, fuzzy)

    # Clean up multiple spaces and trim
    fuzzy = " ".join(fuzzy.split())

    return fuzzy if fuzzy else "try using space-separated words"


def _run_ripgrep_only(
    pattern: str, path: str, hidden: bool = False, rg_flags: str = ""
) -> int:
    """Run ripgrep and return the number of matches found."""
    rg_bin = _require(RG_EXECUTABLE, "rg")

    cmd = [rg_bin, "--count-matches", "--no-heading", "--color=never"]
    if hidden:
        cmd.append("--hidden")
    if rg_flags:
        cmd.extend(shlex.split(rg_flags))
    cmd.extend([pattern, str(Path(path).resolve())])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            # Sum up all match counts
            total = 0
            for line in result.stdout.splitlines():
                if ":" in line:
                    parts = line.rsplit(":", 1)
                    if len(parts) == 2 and parts[1].isdigit():
                        total += int(parts[1])
            return total
    except Exception:
        pass

    return 0


class BinaryMissing(RuntimeError):
    """Raised when a required CLI binary is missing from PATH."""


def _require(binary: str | None, name: str) -> str:
    if not binary:
        raise BinaryMissing(
            f"Cannot find the `{name}` binary on PATH. Install it first."
        )
    return binary


# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("fuzzy-search")

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

    # Check for potential parameter misuse
    warnings = []
    if _looks_like_regex(fuzzy_filter):
        suggested_terms = _suggest_fuzzy_terms(fuzzy_filter)
        warnings.append(
            f"The 'fuzzy_filter' parameter contains regex-like patterns ({fuzzy_filter!r}). "
            f"This parameter expects fuzzy search terms, not regex. "
            f"Try: {suggested_terms!r}"
        )

    try:
        if multiline:
            # For multiline mode, get file list first, then read contents
            # Ensure path is properly formatted
            search_path = str(Path(path).resolve())
            rg_list_cmd: list[str] = [rg_bin, "--files"]
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
                        normalized_path = _normalize_path(file_path)
                        record = f"{normalized_path}:\n".encode() + content + b"\0"
                        multiline_input += record
                except (OSError, UnicodeDecodeError):
                    continue  # Skip files that can't be read

            if not multiline_input:
                return {"matches": []}

            # Use fzf with multiline support
            fzf_cmd: list[str] = [
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
            # Ensure path is properly formatted
            search_path = str(Path(path).resolve())
            rg_cmd: list[str] = [rg_bin, "--files"]
            if hidden:
                rg_cmd.append("--hidden")
            rg_cmd.append(search_path)

            # Pipe through fzf for fuzzy filtering
            fzf_cmd: list[str] = [fzf_bin, "--filter", fuzzy_filter]

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

            matches = [_normalize_path(p) for p in out.splitlines() if p]

        # Apply limit
        matches = matches[:limit]

        # Build result with warnings if any
        result = {"matches": matches}
        if warnings:
            result["warnings"] = warnings

        return result
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

    # Check for potential parameter misuse
    warnings = []
    if _looks_like_regex(fuzzy_filter):
        suggested_terms = _suggest_fuzzy_terms(fuzzy_filter)
        warnings.append(
            f"The 'fuzzy_filter' parameter contains regex-like patterns ({fuzzy_filter!r}). "
            f"This parameter expects fuzzy search terms, not regex. "
            f"Try: {suggested_terms!r}"
        )

    try:
        if multiline:
            # For multiline mode, get files and treat each as a single record
            rg_list_cmd: list[str] = [rg_bin, "--files"]
            if hidden:
                rg_list_cmd.append("--hidden")
            if rg_flags:
                # Filter out options that don't apply to --files
                safe_flags = []
                for flag in shlex.split(rg_flags):
                    if flag not in [
                        "-n",
                        "--line-number",
                        "-H",
                        "--with-filename",
                        "--no-heading",
                    ]:
                        safe_flags.append(flag)
                rg_list_cmd.extend(safe_flags)
            # Ensure path is properly formatted
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
                        # Only include files that match the pattern if not default
                        # Always include all files since we're using "." pattern

                        # Create record: filename + content + null separator
                        normalized_path = _normalize_path(file_path)
                        record = f"{normalized_path}:\n".encode() + content + b"\0"
                        multiline_input += record
                except (OSError, UnicodeDecodeError):
                    continue

            if not multiline_input:
                return {"matches": []}

            # Use fzf with multiline support
            fzf_cmd: list[str] = [
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
                            # Format is: filepath:\ncontent
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
            rg_cmd: list[str] = [
                rg_bin,
                "--line-number",
                "--no-heading",
                "--color=never",
            ]
            if hidden:
                rg_cmd.append("--hidden")
            if rg_flags:
                rg_cmd.extend(shlex.split(rg_flags))
            # Ensure path is properly formatted
            search_path = str(Path(path).resolve())
            rg_cmd.extend([".", search_path])  # Always search all lines

            # Pipe through fzf for fuzzy filtering
            # Default: match on file path (field 1) and content (field 3+), skip line number
            if content_only:
                # Match only on content (field 3+), ignore file path and line number
                fzf_cmd: list[str] = [
                    fzf_bin,
                    "--filter",
                    fuzzy_filter,
                    "--delimiter",
                    ":",
                    "--nth=3..",
                ]
            else:
                # Match on file path (field 1) and content (field 3+), skip line number
                fzf_cmd: list[str] = [
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

                # Use the helper function to parse ripgrep output
                parsed = _parse_ripgrep_line(line)
                if parsed:
                    file_path, line_num, content = parsed
                    matches.append(
                        {
                            "file": file_path,
                            "line": line_num,
                            "content": content,
                        }
                    )

        # Apply limit
        matches = matches[:limit]

        # Add diagnostic information if no matches found
        result: dict[str, Any] = {"matches": matches}

        if warnings:
            result["warnings"] = warnings

        if not matches and not multiline:
            # Run diagnostic check to see if ripgrep found anything
            rg_match_count = _run_ripgrep_only(".", path, hidden, rg_flags)
            if rg_match_count == 0:
                result["diagnostic"] = (
                    "No files found in the specified path. "
                    "Check if the path exists and contains files."
                )
            else:
                result["diagnostic"] = (
                    f"Found {rg_match_count} lines in files, "
                    f"but fuzzy filter '{fuzzy_filter}' matched none. "
                )
                if _looks_like_regex(fuzzy_filter):
                    suggested = _suggest_fuzzy_terms(fuzzy_filter)
                    result["diagnostic"] += f"\nTry fuzzy terms like: '{suggested}'"
                else:
                    result["diagnostic"] += (
                        "\nTry different fuzzy search terms or check the file paths."
                    )

        return result
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

        # Execute rga and collect output for fzf
        rga_proc = subprocess.Popen(
            rga_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        # Collect all lines for fzf filtering
        lines_for_fzf = []
        json_lines = []  # Store original JSON for later parsing

        if rga_proc.stdout is None:
            return {"error": "Failed to create subprocess stdout pipe"}

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
            text=True,
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

                matches.append(
                    {
                        "file": _normalize_path(path_str),
                        "page": page_num,
                        "content": content,
                        "match_text": " ".join(match_texts) if match_texts else "",
                    }
                )

                if len(matches) >= limit:
                    break

        return {"matches": matches}

    except subprocess.CalledProcessError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Tool: extract_pdf_pages
# ---------------------------------------------------------------------------


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

    # Check if required binaries are available
    if not PDF2TXT_EXECUTABLE:
        return {"error": "pdf2txt.py is not installed. Install pdfminer.six first."}
    if not PANDOC_EXECUTABLE:
        return {"error": "pandoc is not installed. Install it first."}

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
        # Build pdf2txt command - file path must come before options
        pdf_cmd = [pdf2txt_bin, str(pdf_path.resolve()), "-t", "html"]

        # Add page numbers
        pdf_cmd.append("--page-numbers")
        pdf_cmd.extend([str(p) for p in page_list])

        # Add layout preservation if requested
        if preserve_layout:
            pdf_cmd.extend(["-Y", "exact"])

        # Map format to pandoc format
        pandoc_formats = {
            "markdown": "gfm+tex_math_dollars",
            "html": "html",
            "plain": "plain",
            "latex": "latex",
            "docx": "docx",
        }

        pandoc_format = pandoc_formats.get(format, "gfm+tex_math_dollars")

        # Build pandoc command
        pandoc_cmd = [pandoc_bin, "--from=html", f"--to={pandoc_format}", "--wrap=none"]

        # Execute pipeline
        pdf_proc = subprocess.Popen(
            pdf_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        pandoc_proc = subprocess.Popen(
            pandoc_cmd,
            stdin=pdf_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        pdf_proc.stdout.close()

        content, pandoc_err = pandoc_proc.communicate()
        pdf_proc.wait()

        if pdf_proc.returncode != 0:
            _, pdf_err = pdf_proc.communicate()
            return {"error": f"pdf2txt failed: {pdf_err.decode()}"}

        if pandoc_proc.returncode != 0:
            return {"error": f"pandoc failed: {pandoc_err}"}

        return {"content": content, "pages_extracted": page_list, "format": format}

    except subprocess.CalledProcessError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------


def _show_examples() -> None:
    """Display interactive examples for using the fuzzy search tools."""
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
    p_content = sub.add_parser(
        "search-content", help="Search all content with fuzzy filter"
    )
    p_content.add_argument(
        "fuzzy_filter", help="fzf query: 'TODO implement .py: !test'"
    )
    p_content.add_argument(
        "path", nargs="?", default=".", help="Directory/file to search"
    )
    # Removed --regex-pattern argument as we always use "." now
    p_content.add_argument("--hidden", action="store_true", help="Search hidden files")
    p_content.add_argument("--limit", type=int, default=20, help="Max results")
    p_content.add_argument("--rg-flags", default="", help="rg flags: '-i -C 3 -t py'")
    p_content.add_argument(
        "--multiline", action="store_true", help="Multiline record processing"
    )
    p_content.add_argument(
        "--content-only",
        action="store_true",
        help="Match only on content, ignore file paths",
    )

    # search-documents subcommand
    p_docs = sub.add_parser(
        "search-documents", help="Search through PDFs and documents"
    )
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

    ns = parser.parse_args()

    # Handle --examples flag
    if ns.examples:
        _show_examples()
        return

    # Require a subcommand if not showing examples
    if not ns.cmd:
        parser.error("Please specify a subcommand or use --examples")

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
        res = extract_pdf_pages(ns.file, ns.pages, ns.format, ns.preserve_layout)
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
