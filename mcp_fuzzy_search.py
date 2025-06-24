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
  fuzzy filtering to the results.

Understanding the Search Pipeline
--------------------------------
    Files → ripgrep (all lines) → Lines → fzf (fuzzy filter) → Results
                                           ↑
                                    'fuzzy_filter'

CRITICAL FOR AI AGENTS: NO REGEX SUPPORT
----------------------------------------
The fuzzy_filter parameter does NOT support regular expressions!
- ✗ NO regex patterns like '.*', '\\w+', '[a-z]+', etc.
- ✓ Use fzf's fuzzy matching syntax instead
- ✓ Space-separated terms for AND logic
- ✓ Use | for OR logic, ! for exclusion
- ✓ Use ^ and $ for prefix/suffix (NOT regex anchors!)

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
        "  Basic Terms: Space-separated terms use AND logic (all must match)\n"
        "    'main config' → files containing both 'main' AND 'config'\n"
        "  OR Logic: Use | to match any term\n"
        "    'py$ | js$ | go$' → files ending in .py OR .js OR .go\n"
        "  Exact Match: Wrap in single quotes for exact string matching\n"
        "    ''main.py'' → exact match for 'main.py'\n"
        "    'test → partial exact match for 'test'\n"
        "  Position Anchors (NOT regex anchors):\n"
        "    '^src' → files starting with 'src' (NOT a regex)\n"
        "    '.json$' → files ending with '.json' (NOT a regex)\n"
        "    '^README$' → files exactly named 'README'\n"
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
        "  multiline (bool, optional): Enable multiline record processing. Default false.\n\n"
        "Fuzzy Filter Syntax (NO REGEX - these are fzf patterns):\n"
        "  Basic search: 'update_ondemand_max_spend' → finds all occurrences\n"
        "  Multiple terms: 'update spend' → lines with both terms\n"
        "  OR logic: 'update | modify' → lines with either term\n"
        "  File filtering: 'test.py: update' → only in test.py files\n"
        "  Exact match: ''exact phrase'' → exact string match\n"
        "  Exclusion: 'update !test' → exclude test files\n"
        "  With prefix: '^def update' → lines starting with 'def update' (NOT regex!)\n"
        "  With suffix: 'update$' → lines ending with 'update' (NOT regex!)\n\n"
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
        '     fuzzy_filter="UpdateOndemand", rg_flags="-i -C 2"\n\n'
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
) -> dict[str, Any]:
    """Search all content then apply fuzzy filtering - similar to 'rg . | fzf'."""
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
            fzf_cmd: list[str] = [fzf_bin, "--filter", fuzzy_filter, "--delimiter", ":"]

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

FUZZY FILTER SYNTAX
==================

✓ Multiple terms (AND logic): "update spend"
✓ OR logic: "update | modify | change"
✓ Exact match: "'exact phrase'"
✓ File filtering: "test.py: update"
✓ Exclusion: "update !test"

UNDERSTANDING THE PIPELINE
=========================

Files → ripgrep (all lines) → Lines → fzf (fuzzy_filter) → Results
                                         ↑
                                   fuzzy search (NO REGEX!)
"""
    print(examples)


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Fuzzy search with ripgrep + fzf",
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
    else:
        res = fuzzy_search_content(
            ns.fuzzy_filter,
            ns.path,
            ns.hidden,
            ns.limit,
            ns.rg_flags,
            ns.multiline,
        )

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
