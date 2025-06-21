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

Quick start
-----------
```bash
# Install required binaries
brew install ripgrep fzf        # macOS
# or apt install ripgrep fzf    # Debian/Ubuntu

chmod +x mcp_fuzzy_search.py

# 1. CLI usage
./mcp_fuzzy_search.py search-files "main" src
./mcp_fuzzy_search.py search-content "TODO" . --filter "implement"

# 2. Run as MCP server
./mcp_fuzzy_search.py
```
"""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import shutil
import subprocess
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Binary discovery
# ---------------------------------------------------------------------------

RG_EXECUTABLE: str | None = shutil.which("rg")
FZF_EXECUTABLE: str | None = shutil.which("fzf")


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

    try:
        if multiline:
            # For multiline mode, get file list first, then read contents
            rg_list_cmd: list[str] = [rg_bin, "--files"]
            if hidden:
                rg_list_cmd.append("--hidden")
            rg_list_cmd.append(path)

            # Get file list
            file_list_result = subprocess.check_output(rg_list_cmd, text=True)
            file_paths = [p for p in file_list_result.splitlines() if p]

            # Build multiline input with null separators
            multiline_input = b""
            for file_path in file_paths:
                try:
                    with open(file_path, 'rb') as f:
                        content = f.read()
                        # Create record: filename: + content + null separator
                        record = f"{file_path}:\n".encode() + content + b'\0'
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
                for chunk in out_bytes.split(b'\0'):
                    if chunk:
                        try:
                            matches.append(chunk.decode('utf-8'))
                        except UnicodeDecodeError:
                            matches.append(chunk.decode('utf-8', errors='replace'))
        else:
            # Standard mode - file paths only
            rg_cmd: list[str] = [rg_bin, "--files"]
            if hidden:
                rg_cmd.append("--hidden")
            rg_cmd.append(path)

            # Pipe through fzf for fuzzy filtering
            fzf_cmd: list[str] = [fzf_bin, "--filter", filter]

            logger.debug("Pipeline: %s | %s", " ".join(rg_cmd), " ".join(fzf_cmd))

            rg_proc = subprocess.Popen(rg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
        "Search all file contents and fuzzy filter results.\n\n"
        "By default searches ALL lines in files (like 'rg .'), then applies fuzzy filtering.\n\n"
        "Args:\n"
        "  filter  (str): fzf query string with advanced syntax support. Required.\n"
        "  path    (str, optional): Directory/file to search. Defaults to current dir.\n"
        "  pattern (str, optional): Regex pattern for ripgrep. Default '.' (all lines).\n"
        "  hidden  (bool, optional): Search hidden files. Default false.\n"
        "  limit   (int, optional): Max results to return. Default 20.\n"
        "  rg_flags (str, optional): Extra flags for ripgrep.\n"
        "  multiline (bool, optional): Enable multiline record processing. Default false.\n\n"
        "fzf Query Syntax for Content Filtering:\n"
        "  Content filtering works on 'file:line:content' format from ripgrep.\n"
        "  Basic Terms: Space-separated for AND logic\n"
        "    'TODO implement' → lines containing both 'TODO' AND 'implement'\n"
        "  OR Logic: Use | for alternatives\n"
        "    'TODO | FIXME | BUG' → lines with any of these markers\n"
        "  File Filtering: Target specific files in results\n"
        "    'main.py:' → only results from main.py files\n"
        "    '.js: function' → function definitions in JS files\n"
        "  Exact Content: Find exact strings in code\n"
        "    ''def __init__'' → exact method definition\n"
        "    'import → partial exact import statements\n"
        "  Line Position: Filter by line characteristics\n"
        "    '^src/' → results from files starting with src/\n"
        "    ':1:' → results from line 1 of files\n"
        "  Exclude Patterns: Remove unwanted results\n"
        "    'function !test' → functions not in test files\n"
        "    'config !.bak$' → config without backup files\n"
        "  Advanced Examples:\n"
        "    'class py$: !test' → Python class definitions, excluding tests\n"
        "    'TODO | FIXME .py: | .js:' → TODOs in Python/JS files\n"
        "    ''async def'' error' → async functions mentioning errors\n\n"
        "Useful rg_flags for enhanced search:\n"
        "  Case: '-i' (ignore case), '-S' (smart case), '-s' (case sensitive)\n"
        "  Types: '-t py' (Python only), '-T test' (exclude tests)\n"
        "  Context: '-A 3' (3 lines after), '-B 2' (2 before), '-C 3' (3 both)\n"
        "  Files: '-.' (include hidden), '--no-ignore' (ignore .gitignore)\n"
        "  Patterns: '-F' (literal strings), '-w' (whole words), '-v' (invert)\n"
        "  Multi-line: '-U' (multiline mode), '-P' (PCRE2 regex)\n"
        "  Examples: '-i -C 2', '-t py --no-ignore', '-F -w'\n\n"
        "Multiline Mode:\n"
        "  When enabled, treats each file as a single multiline record for filtering.\n"
        "  Useful for finding files containing multi-line patterns like functions, classes, etc.\n"
        "  Uses null delimiters for safe handling of complex content.\n"
        "  Example: 'class.*{.*}' could find entire class definitions.\n\n"
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
                    if flag not in ["-n", "--line-number", "-H", "--with-filename", "--no-heading"]:
                        safe_flags.append(flag)
                rg_list_cmd.extend(safe_flags)
            rg_list_cmd.append(path)

            # Get file list
            file_list_result = subprocess.check_output(rg_list_cmd, text=True)
            file_paths = [p for p in file_list_result.splitlines() if p]

            # Build multiline input with file contents
            multiline_input = b""
            for file_path in file_paths:
                try:
                    with open(file_path, 'rb') as f:
                        content = f.read()
                        # Only include files that match the pattern if not default
                        if pattern != ".":
                            # Quick check if pattern matches in content
                            try:
                                import re
                                if not re.search(pattern.encode('utf-8'), content, re.IGNORECASE):
                                    continue
                            except re.error:
                                # If pattern is invalid regex, treat as literal
                                if pattern.encode('utf-8') not in content:
                                    continue

                        # Create record: filename + content + null separator
                        record = f"{file_path}:\n".encode() + content + b'\0'
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
                for chunk in out_bytes.split(b'\0'):
                    if chunk:
                        try:
                            decoded = chunk.decode('utf-8')
                            # Extract filename from first line
                            if ':' in decoded:
                                file_part, content_part = decoded.split(':', 1)
                                matches.append({
                                    "file": file_part.strip(),
                                    "line": 1,  # Multiline records don't have specific line numbers
                                    "content": content_part.strip()[:200] + "..." if len(content_part) > 200 else content_part.strip()
                                })
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
            rg_cmd.extend([pattern, path])

            # Pipe through fzf for fuzzy filtering
            fzf_cmd: list[str] = [fzf_bin, "--filter", filter, "--delimiter", ":"]

            logger.debug("Pipeline: %s | %s", " ".join(rg_cmd), " ".join(fzf_cmd))

            rg_proc = subprocess.Popen(rg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            fzf_proc = subprocess.Popen(
                fzf_cmd, stdin=rg_proc.stdout, stdout=subprocess.PIPE, text=True
            )
            rg_proc.stdout.close()

            out, _ = fzf_proc.communicate()
            rg_stderr = rg_proc.stderr.read().decode() if rg_proc.stderr else ""
            rg_proc.wait()

            if rg_proc.returncode != 0 and rg_proc.returncode != 1:  # 1 = no matches
                return {"error": rg_stderr.strip() or f"ripgrep failed with code {rg_proc.returncode}"}

            # Parse results
            matches = []
            for line in out.splitlines():
                if not line:
                    continue
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    matches.append({
                        "file": parts[0],
                        "line": int(parts[1]),
                        "content": parts[2].strip(),
                    })

        # Apply limit
        matches = matches[:limit]
        return {"matches": matches}
    except subprocess.CalledProcessError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Fuzzy search with ripgrep + fzf",
        epilog="fzf syntax: 'term1 term2' (AND), 'a | b' (OR), '^start', 'end$', '!exclude'"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # search-files subcommand
    p_files = sub.add_parser("search-files", help="Fuzzy search file paths")
    p_files.add_argument("filter", help="fzf query: 'config .json$ !test'")
    p_files.add_argument("path", nargs="?", default=".", help="Directory to search")
    p_files.add_argument("--hidden", action="store_true", help="Include hidden files")
    p_files.add_argument("--limit", type=int, default=20, help="Max results")
    p_files.add_argument("--multiline", action="store_true", help="Search file contents (multiline)")

    # search-content subcommand
    p_content = sub.add_parser("search-content", help="Search all content with fuzzy filter")
    p_content.add_argument("filter", help="fzf query: 'TODO implement .py: !test'")
    p_content.add_argument("path", nargs="?", default=".", help="Directory/file to search")
    p_content.add_argument("--pattern", default=".", help="Ripgrep pattern (default: all lines)")
    p_content.add_argument("--hidden", action="store_true", help="Search hidden files")
    p_content.add_argument("--limit", type=int, default=20, help="Max results")
    p_content.add_argument("--rg-flags", default="", help="rg flags: '-i -C 3 -t py'")
    p_content.add_argument("--multiline", action="store_true", help="Multiline record processing")

    ns = parser.parse_args()

    if ns.cmd == "search-files":
        res = fuzzy_search_files(ns.filter, ns.path, ns.hidden, ns.limit, ns.multiline)
    else:
        res = fuzzy_search_content(
            ns.filter, ns.path, ns.pattern, ns.hidden, ns.limit, ns.rg_flags, ns.multiline
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
