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

Understanding the Two-Stage Pipeline
-----------------------------------
    Files → ripgrep (regex) → Lines → fzf (fuzzy) → Results
             ↑                         ↑
          'pattern'                'filter'

Common Mistakes to Avoid
-----------------------
1. **Using regex in the filter parameter**:
   ❌ WRONG: filter="def test_.*credit", pattern="def test_"
   ✅ RIGHT: filter="test credit", pattern="def test_"

2. **Using fuzzy terms in the pattern parameter**:
   ❌ WRONG: pattern="find this text"
   ✅ RIGHT: pattern="find.*this.*text" or pattern="find|this|text"

3. **Confusing which parameter does what**:
   - 'pattern': Regular expression for ripgrep (first stage)
   - 'filter': Fuzzy search terms for fzf (second stage)

Quick start
-----------
```bash
# Install required binaries
brew install ripgrep fzf        # macOS
# or apt install ripgrep fzf    # Debian/Ubuntu

chmod +x mcp_fuzzy_search.py

# 1. CLI usage
./mcp_fuzzy_search.py search-files "main" src
./mcp_fuzzy_search.py search-content "implement" . --pattern "TODO"
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
        "Args:\n"
        "  filter (str): fzf query string with advanced syntax support. Required.\n"
        "  path   (str, optional): Directory to search. Defaults to current dir.\n"
        "  hidden (bool, optional): Include hidden files. Default false.\n"
        "  limit  (int, optional): Max results to return. Default 20.\n"
        "  multiline (bool, optional): Enable multiline file content search. Default false.\n\n"
        "fzf Query Syntax (Extended Search Mode):\n"
        "  Basic Terms: Space-separated terms use AND logic (all must match)\n"
        "    'main config' → files containing both 'main' AND 'config'\n"
        "  OR Logic: Use | to match any term\n"
        "    'py$ | js$ | go$' → files ending in .py OR .js OR .go\n"
        "  Exact Match: Wrap in single quotes for exact string matching\n"
        "    ''main.py'' → exact match for 'main.py'\n"
        "    'test → partial exact match for 'test'\n"
        "  Position Anchors:\n"
        "    '^src' → files starting with 'src'\n"
        "    '.json$' → files ending with '.json'\n"
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
    filter: str,
    path: str = ".",
    hidden: bool = False,
    limit: int = 20,
    multiline: bool = False,
) -> dict[str, Any]:
    """Find files using ripgrep + fzf fuzzy filtering with optional multiline content search."""
    if not filter:
        return {"error": "'filter' argument is required"}

    rg_bin = _require(RG_EXECUTABLE, "rg")
    fzf_bin = _require(FZF_EXECUTABLE, "fzf")

    # Check for potential parameter misuse
    warnings = []
    if _looks_like_regex(filter):
        suggested_terms = _suggest_fuzzy_terms(filter)
        warnings.append(
            f"The 'filter' parameter contains regex-like patterns ({filter!r}). "
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
            fzf_cmd: list[str] = [fzf_bin, "--filter", filter, "--read0", "--print0"]

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
            fzf_cmd: list[str] = [fzf_bin, "--filter", filter]

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
        "Search file contents using a two-stage pipeline:\n\n"
        "    Files → ripgrep (regex) → Lines → fzf (fuzzy) → Results\n"
        "             ↑                         ↑\n"
        "          'pattern'                'filter'\n\n"
        "CORRECT USAGE:\n"
        '  ✓ pattern: "TODO|FIXME"      filter: "implement database"\n'
        '  ✓ pattern: "def test_"       filter: "seer credit"\n'
        '  ✓ pattern: "class"           filter: "Model save"\n\n'
        "INCORRECT USAGE (Common Mistakes):\n"
        '  ✗ pattern: "def test_.*seer" filter: "def test_.*seer"  # Don\'t use regex in filter!\n'
        '  ✗ pattern: "find this text"  filter: "find this text"   # Pattern needs regex syntax\n\n'
        "Args:\n"
        "  filter  (str): fzf fuzzy search query. NOT regex! Required.\n"
        "  path    (str, optional): Directory/file to search. Defaults to current dir.\n"
        "  pattern (str, optional): Regex pattern for ripgrep. Default '.' (all lines).\n"
        "  hidden  (bool, optional): Search hidden files. Default false.\n"
        "  limit   (int, optional): Max results to return. Default 20.\n"
        "  rg_flags (str, optional): Extra flags for ripgrep.\n"
        "  multiline (bool, optional): Enable multiline record processing. Default false.\n\n"
        "Understanding the Two-Stage Process:\n"
        "  1. PATTERN (ripgrep): Finds lines matching regex\n"
        "     - Uses regular expressions\n"
        '     - Examples: "TODO", "def \\w+\\(", "import.*pandas"\n'
        "  2. FILTER (fzf): Fuzzy filters the results\n"
        "     - Uses fuzzy matching on 'file:line:content' format\n"
        '     - Examples: "database save", "test user auth"\n\n'
        "fzf Filter Syntax (Fuzzy Matching):\n"
        "  Basic Terms: Space-separated for AND logic\n"
        "    'TODO implement' → lines with both 'TODO' AND 'implement'\n"
        "  OR Logic: Use | for alternatives\n"
        "    'TODO | FIXME | BUG' → lines with any of these markers\n"
        "  File Filtering: Target specific files in results\n"
        "    'main.py:' → only results from main.py files\n"
        "    '.js: function' → function definitions in JS files\n"
        "  Exact Content: Wrap in single quotes\n"
        "    ''def __init__'' → exact match for 'def __init__'\n"
        "    'import → partial exact match starting with 'import'\n"
        "  Exclude Patterns: Use ! to negate\n"
        "    'function !test' → functions not in test files\n"
        "    'config !.bak$' → config without backup files\n\n"
        "Useful rg_flags:\n"
        "  Case: '-i' (ignore), '-S' (smart), '-s' (sensitive)\n"
        "  Types: '-t py' (Python only), '-T test' (exclude tests)\n"
        "  Context: '-A 3' (after), '-B 2' (before), '-C 3' (both)\n"
        "  Examples: '-i -C 2', '-t py --no-ignore', '-F -w'\n\n"
        "Examples:\n"
        "  1. Find TODO comments about databases:\n"
        '     pattern="TODO" filter="database"\n'
        "  2. Find test functions mentioning 'seer' and 'credit':\n"
        '     pattern="def test_" filter="seer credit"\n'
        "  3. Find all async functions with error handling:\n"
        '     pattern="async def" filter="error try except"\n\n'
        "Returns: { matches: Array<{file: string, line: number, content: string}> } or { error: string }"
    )
)
def fuzzy_search_content(
    filter: str,
    path: str = ".",
    pattern: str = ".",
    hidden: bool = False,
    limit: int = 20,
    rg_flags: str = "",
    multiline: bool = False,
) -> dict[str, Any]:
    """Search all content then apply fuzzy filtering - similar to 'rg . | fzf'."""
    if not filter:
        return {"error": "'filter' argument is required"}

    rg_bin = _require(RG_EXECUTABLE, "rg")
    fzf_bin = _require(FZF_EXECUTABLE, "fzf")

    # Check for potential parameter misuse
    warnings = []
    if _looks_like_regex(filter):
        suggested_terms = _suggest_fuzzy_terms(filter)
        warnings.append(
            f"The 'filter' parameter contains regex-like patterns ({filter!r}). "
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
                        if pattern != ".":
                            # Quick check if pattern matches in content
                            try:
                                import re

                                if not re.search(
                                    pattern.encode("utf-8"), content, re.IGNORECASE
                                ):
                                    continue
                            except re.error:
                                # If pattern is invalid regex, treat as literal
                                if pattern.encode("utf-8") not in content:
                                    continue

                        # Create record: filename + content + null separator
                        normalized_path = _normalize_path(file_path)
                        record = f"{normalized_path}:\n".encode() + content + b"\0"
                        multiline_input += record
                except (OSError, UnicodeDecodeError):
                    continue

            if not multiline_input:
                return {"matches": []}

            # Use fzf with multiline support
            fzf_cmd: list[str] = [fzf_bin, "--filter", filter, "--read0", "--print0"]

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
            rg_cmd.extend([pattern, search_path])

            # Pipe through fzf for fuzzy filtering
            fzf_cmd: list[str] = [fzf_bin, "--filter", filter, "--delimiter", ":"]

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
            rg_match_count = _run_ripgrep_only(pattern, path, hidden, rg_flags)
            if rg_match_count == 0:
                result["diagnostic"] = (
                    f"ripgrep found 0 matches for pattern '{pattern}'. "
                    f"Check if your regex pattern is correct."
                )
            else:
                result["diagnostic"] = (
                    f"ripgrep found {rg_match_count} matches for pattern '{pattern}', "
                    f"but fzf filter '{filter}' matched none. "
                )
                if _looks_like_regex(filter):
                    suggested = _suggest_fuzzy_terms(filter)
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
   $ ./mcp_fuzzy_search.py search-content "database" --pattern "TODO"

2. Find test functions mentioning 'seer' and 'credit':
   $ ./mcp_fuzzy_search.py search-content "seer credit" --pattern "def test_"

3. Find Python files in src directory:
   $ ./mcp_fuzzy_search.py search-files "src py$"

4. Find all async functions with error handling:
   $ ./mcp_fuzzy_search.py search-content "error try except" --pattern "async def"

5. Search with case-insensitive matching:
   $ ./mcp_fuzzy_search.py search-content "config" --pattern "CONFIG" --rg-flags "-i"

COMMON MISTAKES TO AVOID
========================

✗ DON'T use regex in the filter parameter:
  $ ./mcp_fuzzy_search.py search-content "def test_.*seer.*credit"

✓ DO use fuzzy search terms instead:
  $ ./mcp_fuzzy_search.py search-content "test seer credit" --pattern "def test_"

✗ DON'T confuse the parameters:
  filter: For fuzzy matching (space-separated terms)
  pattern: For regex matching (regular expressions)

UNDERSTANDING THE PIPELINE
=========================

Files → ripgrep (--pattern) → Lines → fzf (filter) → Results
         ↑                              ↑
      regex search                 fuzzy filter
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
    p_files.add_argument("filter", help="fzf query: 'config .json$ !test'")
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
    p_content.add_argument("filter", help="fzf query: 'TODO implement .py: !test'")
    p_content.add_argument(
        "path", nargs="?", default=".", help="Directory/file to search"
    )
    p_content.add_argument(
        "--pattern", default=".", help="Ripgrep pattern (default: all lines)"
    )
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
        res = fuzzy_search_files(ns.filter, ns.path, ns.hidden, ns.limit, ns.multiline)
    else:
        res = fuzzy_search_content(
            ns.filter,
            ns.path,
            ns.pattern,
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
